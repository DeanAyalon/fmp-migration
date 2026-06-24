import logging
import shlex

from src.config import Settings
from src.pipeline.commands import docker_sh
from src.pipeline.errors import PipelineError
from src.pipeline.paths import live_db_path, migration_paths

logger = logging.getLogger(__name__)


def prepare_migration_source(container: str, settings: Settings) -> None:
    paths = migration_paths(settings.solution)
    live = live_db_path(settings.solution)
    script = f"cp {shlex.quote(live)} {shlex.quote(paths['source'])}"
    docker_sh(container, "fms_copy_live_to_source", script)


def run_migration_tool(container: str) -> None:
    # Placeholder until real FMDataMigrationTool invocation is wired up.
    docker_sh(container, "fms_migration", "echo FMDataMigrationTool")


def run_migration(container: str, settings: Settings) -> None:
    """Run FMDataMigrationTool against the prepared source and clone files."""
    prepare_migration_source(container, settings)
    run_migration_tool(container)


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
