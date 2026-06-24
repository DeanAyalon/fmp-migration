import logging
import time

from src.config import Settings
from src.pipeline.commands import fmsadmin, fmsadmin_output
from src.pipeline.constants import (
    _OPEN_STATUSES, _CLOSED_STATUSES, 
    _CLOSE_POLL_INTERVAL_SECONDS, _CLOSE_POLL_TIMEOUT_SECONDS,
    _GRACE_POLL_INTERVAL_SECONDS, _GRACE_WAIT_SECONDS,
    _MAINTENANCE_WARNING, _MIGRATION_DISCONNECT_MESSAGE,
    _REOPEN_DELAY_SECONDS, _REOPEN_MAX_ATTEMPTS, _REOPEN_RETRY_INTERVAL_SECONDS
)
from src.pipeline.errors import PipelineError
from src.pipeline.listing import (db_status, list_clients, list_files, solution_client_ids)
from src.pipeline.paths import db_filename

logger = logging.getLogger(__name__)


def is_db_hosted(container: str, settings: Settings) -> bool:
    listing = fmsadmin_output(container, settings, "fms_list_files", "list", "files", "-s")
    return db_filename(settings) in listing


def wait_for_db_closed(container: str, settings: Settings) -> None:
    db_file = db_filename(settings)
    deadline = time.monotonic() + _CLOSE_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        listing = list_files(container, settings)
        status = db_status(listing, db_file)
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


def disconnect_clients(
    container: str, settings: Settings,
    client_ids: list[str], message: str, step: str
) -> None:
    if not client_ids: return
    logger.info("[%s] disconnecting %s client(s) from %s", step, len(client_ids), settings.solution)
    for client_id in client_ids:
        fmsadmin(
            container, settings, step,
            "disconnect", "client", "-y", "-m", message, client_id
        )


def grace_wait_and_disconnect(container: str, settings: Settings, initial_client_ids: list[str]) -> None:
    db_file = db_filename(settings)
    solution = settings.solution
    initial_ids = set(initial_client_ids)
    disconnected_ids: set[str] = set()

    fmsadmin(
        container, settings, "fms_send_warning",
        "send", db_file, "-m", _MAINTENANCE_WARNING
    )
    logger.info("[fms_grace_wait] waiting %s seconds after user warning", _GRACE_WAIT_SECONDS)

    deadline = time.monotonic() + _GRACE_WAIT_SECONDS
    while time.monotonic() < deadline:
        listing = list_clients(container, settings)
        current_ids = solution_client_ids(listing, solution)
        late_joiners = [
            client_id for client_id in current_ids
            if client_id not in initial_ids and client_id not in disconnected_ids
        ]
        if late_joiners:
            disconnect_clients(
                container, settings, late_joiners,
                _MIGRATION_DISCONNECT_MESSAGE, "fms_disconnect_late_client",
            )
            disconnected_ids.update(late_joiners)
        remaining = deadline - time.monotonic()
        if remaining <= 0: break
        time.sleep(min(_GRACE_POLL_INTERVAL_SECONDS, remaining))

    logger.info("[fms_grace_wait] complete")

    listing = list_clients(container, settings)
    remaining_ids = [
        client_id for client_id in solution_client_ids(listing, solution)
        if client_id not in disconnected_ids
    ]
    disconnect_clients(
        container, settings, remaining_ids,
        _MIGRATION_DISCONNECT_MESSAGE, "fms_disconnect_client"
    )


def disconnect_solution_clients(container: str, settings: Settings, message: str, step: str) -> None:
    listing = list_clients(container, settings)
    client_ids = solution_client_ids(listing, settings.solution)
    disconnect_clients(container, settings, client_ids, message, step)


def prepare_hosted_db(container: str, settings: Settings) -> bool:
    db_file = db_filename(settings)
    solution = settings.solution

    listing = list_clients(container, settings)
    initial_client_ids = solution_client_ids(listing, solution)
    if initial_client_ids:
        logger.info(
            "[fms_prepare] %s client(s) connected to %s; starting grace period",
            len(initial_client_ids), solution
        )
        grace_wait_and_disconnect(container, settings, initial_client_ids)
    else: logger.info("[fms_prepare] no clients connected to %s; skipping grace period", solution)

    # Catch clients that connected after the initial check (or during a skipped grace period).
    disconnect_solution_clients(container, settings, _MIGRATION_DISCONNECT_MESSAGE, "fms_disconnect_client")
    fmsadmin(
        container, settings, "fms_close_db",
        "close", db_file, "-y", "-f", "-m", _MIGRATION_DISCONNECT_MESSAGE
    )
    wait_for_db_closed(container, settings)
    return True


def reopen_db(container: str, settings: Settings) -> None:
    db_file = db_filename(settings)
    logger.info("[fms_reopen_wait] waiting %s seconds before reopen", _REOPEN_DELAY_SECONDS)
    time.sleep(_REOPEN_DELAY_SECONDS)
    logger.info("[fms_reopen_wait] complete")

    listing = list_files(container, settings)
    status = db_status(listing, db_file)
    if status in _OPEN_STATUSES:
        logger.info("[fms_open_db] skip: %s already open (status=%s)", db_file, status)
        return

    last_exc: PipelineError | None = None
    for attempt in range(1, _REOPEN_MAX_ATTEMPTS + 1):
        try:
            fmsadmin(container, settings, "fms_open_db", "open", db_file)
            return
        except PipelineError as exc:
            last_exc = exc
            if attempt >= _REOPEN_MAX_ATTEMPTS: break
            logger.warning(
                "[fms_open_db] attempt %s/%s failed at %s: %s; retrying in %ss",
                attempt, _REOPEN_MAX_ATTEMPTS,
                exc.step, exc.detail,
                _REOPEN_RETRY_INTERVAL_SECONDS
            )
            time.sleep(_REOPEN_RETRY_INTERVAL_SECONDS)
            listing = list_files(container, settings)
            status = db_status(listing, db_file)
            if status in _OPEN_STATUSES:
                logger.info("[fms_open_db] skip: %s opened externally (status=%s)", db_file, status)
                return

    listing = list_files(container, settings)
    logger.error(
        "Best-effort reopen of %s failed at %s: %s\nlist files:\n%s",
        db_file,
        last_exc.step if last_exc else "fms_open_db",
        last_exc.detail if last_exc else "unknown",
        listing.rstrip()
    )
