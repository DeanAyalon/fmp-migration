import logging
import shlex
import subprocess
from pathlib import Path

from src.config import Settings

logger = logging.getLogger(__name__)
STAGING_DIR = Path("staging")


class PipelineError(Exception):
    """Raised when a migration pipeline step fails."""
    def __init__(self, step: str, detail: str) -> None:
        self.step = step
        self.detail = detail
        super().__init__(f"{step}: {detail}")


def fms_exec_args() -> list[str]:
    # TODO: replace with real FileMaker migration commands
    return ["ls", "-la", "/tmp/migration"]


def _clone_filename(solution: str) -> str: return f"{solution}_clone.fmp12"


def _run_step(step: str, cmd: list[str]) -> None:
    cmd_display = " ".join(shlex.quote(arg) for arg in cmd)
    logger.info("[%s] starting: %s", step, cmd_display)
    try:
        # Inherit stdout/stderr so aws s3 cp progress and docker output appear in container logs.
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        detail = f"exit code {exc.returncode}"
        logger.error("[%s] failed: %s", step, detail)
        raise PipelineError(step, detail) from exc
    logger.info("[%s] complete", step)


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
    _run_step("docker_prepare", ["docker", "exec", container, "rm", "/tmp/migration/clone.fmp12"])


def _copy_to_container(settings: Settings, local_path: Path) -> None:
    dest = f"{settings.fms_container}:/tmp/migration/clone.fmp12"
    _run_step("docker_cp", ["docker", "cp", str(local_path), dest])


def _remove_staging_clone(local_path: Path) -> None:
    if not local_path.exists(): return
    local_path.unlink()
    logger.info("Removed staging clone: %s", local_path)


def run_fms_migration(container: str) -> None:
    _run_step("docker_exec", ["docker", "exec", container, *fms_exec_args()])


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
        run_fms_migration(settings.fms_container)
        succeeded = True
    finally: 
        if not succeeded: _remove_staging_clone(local_path)

    logger.info("Migration completed successfully for solution=%s", settings.solution)

