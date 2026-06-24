from src.config import Settings
from src.pipeline.deployment import complete_deployment, prepare_for_migration, reopen_if_needed
from src.pipeline.migration import cleanup_migration_artifacts, run_migration


def run_solution_upgrade(settings: Settings) -> None:
    """Upgrade a hosted solution: deploy down, migrate, deploy up."""

    container = settings.fms_container
    db_was_closed = False
    try:
        db_was_closed = prepare_for_migration(container, settings)
        run_migration(container, settings)
        complete_deployment(container, settings, db_was_closed)
    except Exception:
        cleanup_migration_artifacts(container, settings)
        reopen_if_needed(container, settings, db_was_closed)
        raise
