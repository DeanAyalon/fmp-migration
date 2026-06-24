import logging
import shlex

from src.config import Settings
from src.pipeline.commands import docker_sh, run_step
from src.pipeline.errors import PipelineError
from src.pipeline.paths import live_db_path, migration_paths

logger = logging.getLogger(__name__)


def prepare_migration_source(container: str, settings: Settings) -> None:
    paths = migration_paths(settings.solution)
    live = live_db_path(settings.solution)
    script = f"cp {shlex.quote(live)} {shlex.quote(paths['source'])}"
    docker_sh(container, "fms_copy_live_to_source", script)


def _migration_tool_cmd(container: str, settings: Settings, paths: dict[str, str]) -> list[str]:
    return [
        "docker", "exec", container,
        "FMDataMigration",
        "-src_path", paths["source"],
        "-src_account", settings.fm_account,
        "-src_pwd", settings.fm_password,
        "-clone_path", paths["clone"],
        "-clone_account", settings.fm_account,
        "-clone_pwd", settings.fm_password,
        "-target_path", paths["output"],
        "-ignore_valuelists",
        "-ignore_accounts",
        "-v"
    ]


def run_migration_tool(container: str, settings: Settings) -> None:
    paths = migration_paths(settings.solution)
    run_step("fms_migration", _migration_tool_cmd(container, settings, paths))


def run_migration(container: str, settings: Settings) -> None:
    """Run FMDataMigration against the prepared source and clone files."""
    prepare_migration_source(container, settings)
    run_migration_tool(container, settings)


def cleanup_migration_artifacts(container: str, settings: Settings) -> None:
    """Remove transient migration files from the FMS container (best-effort).

    Deletes clone.fmp12 and the migration tool output ({solution}.fmp12) only.
    Does not remove source.fmp12 — that copy of the live DB is kept for recovery
    and debugging after a failed run."""

    paths = migration_paths(settings.solution)
    script = f"rm -f {shlex.quote(paths['clone'])} {shlex.quote(paths['output'])}"
    try: docker_sh(container, "fms_cleanup_artifacts", script)
    except PipelineError as exc:
        logger.error(
            "Best-effort cleanup of migration artifacts failed at %s: %s",
            exc.step, exc.detail
        )
