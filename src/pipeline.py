import logging
import shlex
import subprocess
import time
from pathlib import Path

from src.config import Settings

logger = logging.getLogger(__name__)
STAGING_DIR = Path("staging")
_SENSITIVE_FLAGS = frozenset({"-p", "--password"})
_CLOSE_POLL_INTERVAL_SECONDS = 2
_CLOSE_POLL_TIMEOUT_SECONDS = 120
_GRACE_WAIT_SECONDS = 60
_GRACE_POLL_INTERVAL_SECONDS = 2
_REOPEN_DELAY_SECONDS = 5
_MAINTENANCE_WARNING = "Database maintenance in 1 minute. Please save your work."
_MIGRATION_DISCONNECT_MESSAGE = "Database migration is about to commence. Please login again in a few minutes."
_REOPEN_RETRY_INTERVAL_SECONDS = 5
_REOPEN_MAX_ATTEMPTS = 6
_OPEN_STATUSES = frozenset({"Normal", "Opening"})
_CLOSED_STATUSES = frozenset({"Closed"})


def _cmd_display(cmd: list[str]) -> str:
    """Build a shell-safe command string for logs, redacting secret flag values."""
    safe: list[str] = []
    redact_next = False
    for arg in cmd:
        if redact_next:
            safe.append("***")
            redact_next = False
        elif arg in _SENSITIVE_FLAGS:
            safe.append(arg)
            redact_next = True
        else:
            safe.append(arg)
    return " ".join(shlex.quote(arg) for arg in safe)

class PipelineError(Exception):
    """Raised when a migration pipeline step fails."""
    def __init__(self, step: str, detail: str) -> None:
        self.step = step
        self.detail = detail
        super().__init__(f"{step}: {detail}")


def _clone_filename(solution: str) -> str: return f"{solution}_clone.fmp12"
def _fms_databases_dir() -> str: return "/opt/FileMaker/FileMaker Server/Data/Databases"
def _live_db_path(solution: str) -> str: return f"{_fms_databases_dir()}/{solution}.fmp12"
def _migration_paths(solution: str) -> dict[str, str]:
    migration_dir = "/tmp/migration"
    return {
        "dir": migration_dir,
        "clone": f"{migration_dir}/clone.fmp12",
        "source": f"{migration_dir}/source.fmp12",
        "output": f"{migration_dir}/{solution}.fmp12",
    }

def _run_step(step: str, cmd: list[str]) -> None:
    logger.info("[%s] starting: %s", step, _cmd_display(cmd))
    try:
        # Inherit stdout/stderr so aws s3 cp progress and docker output appear in container logs.
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        detail = f"exit code {exc.returncode}"
        logger.error("[%s] failed: %s", step, detail)
        raise PipelineError(step, detail) from exc
    logger.info("[%s] complete", step)


def _docker_sh(container: str, step: str, script: str) -> None:
    _run_step(step, ["docker", "exec", container, "sh", "-c", script])

def _fmsadmin_cmd(container: str, settings: Settings, *args: str) -> list[str]:
    return [
        "docker", "exec", container,
        "fmsadmin", "-y",
        "-u", settings.fms_admin_user,
        "-p", settings.fms_admin_password,
        *args
    ]

def _fmsadmin(container: str, settings: Settings, step: str, *args: str) -> None:
    _run_step(step, _fmsadmin_cmd(container, settings, *args))

def _fmsadmin_output(container: str, settings: Settings, step: str, *args: str) -> str:
    cmd = _fmsadmin_cmd(container, settings, *args)
    logger.info("[%s] starting: %s", step, _cmd_display(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = f"exit code {exc.returncode}"
        logger.error("[%s] failed: %s", step, detail)
        raise PipelineError(step, detail) from exc
    logger.info("[%s] complete", step)
    return result.stdout


def _db_filename(settings: Settings) -> str:
    return f"{settings.solution}.fmp12"


def _list_files(container: str, settings: Settings) -> str:
    cmd = _fmsadmin_cmd(container, settings, "list", "files", "-s")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def _list_clients(container: str, settings: Settings) -> str:
    cmd = _fmsadmin_cmd(container, settings, "list", "clients", "-s")
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def _solution_client_ids(listing: str, solution: str) -> list[str]:
    """Return client IDs connected to the solution database (File Name column)."""
    client_ids: list[str] = []
    for line in listing.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Client ID"):
            continue
        if solution not in stripped:
            continue
        client_id = stripped.split(None, 1)[0]
        if client_id.isdigit():
            client_ids.append(client_id)
    return client_ids


def _disconnect_clients(
    container: str,
    settings: Settings,
    client_ids: list[str],
    message: str,
    step: str,
) -> None:
    if not client_ids:
        return
    logger.info("[%s] disconnecting %s client(s) from %s", step, len(client_ids), settings.solution)
    for client_id in client_ids:
        _fmsadmin(
            container, settings, step,
            "disconnect", "client", "-y", "-m", message, client_id,
        )


def _db_status_line(listing: str, db_file: str) -> str | None:
    for line in listing.splitlines():
        if db_file in line and not line.strip().startswith("ID "):
            return line
    return None


def _parse_db_status(line: str, db_file: str) -> str | None:
    parts = line.split()
    try:
        file_index = parts.index(db_file)
    except ValueError:
        return None
    status_index = file_index + 3
    if status_index >= len(parts):
        return None
    return parts[status_index]


def _db_status(listing: str, db_file: str) -> str | None:
    line = _db_status_line(listing, db_file)
    if line is None:
        return None
    return _parse_db_status(line, db_file)


def _is_db_hosted(container: str, settings: Settings) -> bool:
    listing = _fmsadmin_output(container, settings, "fms_list_files", "list", "files", "-s")
    return _db_filename(settings) in listing


def _wait_for_db_closed(container: str, settings: Settings) -> None:
    db_file = _db_filename(settings)
    deadline = time.monotonic() + _CLOSE_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        listing = _list_files(container, settings)
        status = _db_status(listing, db_file)
        if status in _CLOSED_STATUSES:
            logger.info("[fms_close_wait] %s status=%s", db_file, status)
            return
        if db_file not in listing:
            logger.info("[fms_close_wait] %s no longer listed (safe to copy)", db_file)
            return
        logger.info("[fms_close_wait] waiting for Closed (current status=%s)", status)
        time.sleep(_CLOSE_POLL_INTERVAL_SECONDS)
    raise PipelineError(
        "fms_close_wait",
        f"timed out after {_CLOSE_POLL_TIMEOUT_SECONDS}s waiting for {db_file} to close",
    )


def _grace_wait_and_disconnect(container: str, settings: Settings, initial_client_ids: list[str]) -> None:
    db_file = _db_filename(settings)
    solution = settings.solution
    initial_ids = set(initial_client_ids)
    disconnected_ids: set[str] = set()

    _fmsadmin(
        container, settings, "fms_send_warning",
        "send", db_file, "-m", _MAINTENANCE_WARNING,
    )
    logger.info("[fms_grace_wait] waiting %s seconds after user warning", _GRACE_WAIT_SECONDS)

    deadline = time.monotonic() + _GRACE_WAIT_SECONDS
    while time.monotonic() < deadline:
        listing = _list_clients(container, settings)
        current_ids = _solution_client_ids(listing, solution)
        late_joiners = [
            client_id for client_id in current_ids
            if client_id not in initial_ids and client_id not in disconnected_ids
        ]
        if late_joiners:
            _disconnect_clients(
                container, settings, late_joiners,
                _MIGRATION_DISCONNECT_MESSAGE, "fms_disconnect_late_client",
            )
            disconnected_ids.update(late_joiners)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(_GRACE_POLL_INTERVAL_SECONDS, remaining))

    logger.info("[fms_grace_wait] complete")

    listing = _list_clients(container, settings)
    remaining_ids = [
        client_id for client_id in _solution_client_ids(listing, solution)
        if client_id not in disconnected_ids
    ]
    _disconnect_clients(
        container, settings, remaining_ids,
        _MIGRATION_DISCONNECT_MESSAGE, "fms_disconnect_client",
    )


def _disconnect_solution_clients(container: str, settings: Settings, message: str, step: str) -> None:
    listing = _list_clients(container, settings)
    client_ids = _solution_client_ids(listing, settings.solution)
    _disconnect_clients(container, settings, client_ids, message, step)


def _prepare_hosted_db(container: str, settings: Settings) -> bool:
    db_file = _db_filename(settings)
    solution = settings.solution

    listing = _list_clients(container, settings)
    initial_client_ids = _solution_client_ids(listing, solution)
    if initial_client_ids:
        logger.info(
            "[fms_prepare] %s client(s) connected to %s; starting grace period",
            len(initial_client_ids), solution,
        )
        _grace_wait_and_disconnect(container, settings, initial_client_ids)
    else:
        logger.info("[fms_prepare] no clients connected to %s; skipping grace period", solution)

    # Catch clients that connected after the initial check (or during a skipped grace period).
    _disconnect_solution_clients(
        container, settings, _MIGRATION_DISCONNECT_MESSAGE, "fms_disconnect_client",
    )
    _fmsadmin(
        container, settings, "fms_close_db",
        "close", db_file, "-y", "-f", "-m", _MIGRATION_DISCONNECT_MESSAGE,
    )
    _wait_for_db_closed(container, settings)
    return True


def _reopen_db(container: str, settings: Settings) -> None:
    db_file = _db_filename(settings)
    logger.info(
        "[fms_reopen_wait] waiting %s seconds before reopen",
        _REOPEN_DELAY_SECONDS,
    )
    time.sleep(_REOPEN_DELAY_SECONDS)
    logger.info("[fms_reopen_wait] complete")

    listing = _list_files(container, settings)
    status = _db_status(listing, db_file)
    if status in _OPEN_STATUSES:
        logger.info("[fms_open_db] skip: %s already open (status=%s)", db_file, status)
        return

    last_exc: PipelineError | None = None
    for attempt in range(1, _REOPEN_MAX_ATTEMPTS + 1):
        try:
            _fmsadmin(container, settings, "fms_open_db", "open", db_file)
            return
        except PipelineError as exc:
            last_exc = exc
            if attempt >= _REOPEN_MAX_ATTEMPTS:
                break
            logger.warning(
                "[fms_open_db] attempt %s/%s failed at %s: %s; retrying in %ss",
                attempt,
                _REOPEN_MAX_ATTEMPTS,
                exc.step,
                exc.detail,
                _REOPEN_RETRY_INTERVAL_SECONDS,
            )
            time.sleep(_REOPEN_RETRY_INTERVAL_SECONDS)
            listing = _list_files(container, settings)
            status = _db_status(listing, db_file)
            if status in _OPEN_STATUSES:
                logger.info("[fms_open_db] skip: %s opened externally (status=%s)", db_file, status)
                return

    listing = _list_files(container, settings)
    logger.error(
        "Best-effort reopen of %s failed at %s: %s\nlist files:\n%s",
        db_file,
        last_exc.step if last_exc else "fms_open_db",
        last_exc.detail if last_exc else "unknown",
        listing.rstrip(),
    )


def _copy_live_to_source(container: str, settings: Settings) -> None:
    paths = _migration_paths(settings.solution)
    live = _live_db_path(settings.solution)
    script = f"cp {shlex.quote(live)} {shlex.quote(paths['source'])}"
    _docker_sh(container, "fms_copy_live_to_source", script)


def _run_migration_tool(container: str) -> None:
    # Placeholder until real FMDataMigrationTool invocation is wired up.
    _docker_sh(container, "fms_migration", "echo FMDataMigrationTool")


def _deploy_migrated_db(container: str, settings: Settings) -> None:
    paths = _migration_paths(settings.solution)
    live = _live_db_path(settings.solution)
    script = f"cp {shlex.quote(paths['output'])} {shlex.quote(live)}"
    _docker_sh(container, "fms_deploy_migrated_db", script)


def _cleanup_migration_artifacts(container: str, settings: Settings) -> None:
    paths = _migration_paths(settings.solution)
    script = f"rm -f {shlex.quote(paths['clone'])} {shlex.quote(paths['output'])}"
    try:
        _docker_sh(container, "fms_cleanup_artifacts", script)
    except PipelineError as exc:
        logger.error(
            "Best-effort cleanup of migration artifacts failed at %s: %s",
            exc.step, exc.detail
        )

def _ensure_staging_dir() -> Path:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    return STAGING_DIR

def _download_from_s3(settings: Settings, local_path: Path) -> None:
    object_key = _clone_filename(settings.solution)
    s3_uri = f"s3://{settings.bucket}/{object_key}"
    logger.info("[%s] downloading %s -> %s", "s3_download", s3_uri, local_path)
    _run_step("s3_download", ["aws", "s3", "cp", s3_uri, str(local_path)])
    size_bytes = local_path.stat().st_size
    logger.info("[%s] saved %s bytes to %s", "s3_download", size_bytes, local_path)

def _ensure_fms_migration_dir(container: str) -> None:
    _run_step("docker_prepare", ["docker", "exec", container, "mkdir", "-p", "/tmp/migration"])
    _run_step("docker_prepare", ["docker", "exec", container, "rm", "-f", "/tmp/migration/clone.fmp12", "/tmp/migration/source.fmp12"])


def _copy_to_container(settings: Settings, local_path: Path) -> None:
    dest = f"{settings.fms_container}:/tmp/migration/clone.fmp12"
    _run_step("docker_cp", ["docker", "cp", str(local_path), dest])


def _remove_staging_clone(local_path: Path) -> None:
    if not local_path.exists(): return
    local_path.unlink()
    logger.info("Removed staging clone: %s", local_path)


def run_fms_migration(settings: Settings) -> None:
    container = settings.fms_container
    db_closed = False
    try:
        if _is_db_hosted(container, settings):
            db_closed = _prepare_hosted_db(container, settings)
        _copy_live_to_source(container, settings)
        _run_migration_tool(container)
        # _deploy_migrated_db(container, settings)
        # todo: copy_migrated_to_live
        if db_closed:
            _reopen_db(container, settings)
    except Exception:
        _cleanup_migration_artifacts(container, settings)
        if db_closed:
            _reopen_db(container, settings)
        raise


def run_migration(settings: Settings) -> None:
    clone_name = _clone_filename(settings.solution)
    logger.info(
        "Migration started: solution=%s bucket=%s clone=%s container=%s",
        settings.solution,
        settings.bucket,
        clone_name,
        settings.fms_container
    )

    staging = _ensure_staging_dir()
    local_path = staging / clone_name
    succeeded = False
    try:
        _download_from_s3(settings, local_path)
        _ensure_fms_migration_dir(settings.fms_container)
        _copy_to_container(settings, local_path)
        run_fms_migration(settings)
        succeeded = True
    finally: 
        if not succeeded: _remove_staging_clone(local_path)

    logger.info("Migration completed successfully for solution=%s", settings.solution)

