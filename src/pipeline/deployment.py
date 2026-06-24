import shlex

from src.config import Settings
from src.pipeline.commands import docker_sh
from src.pipeline.lifecycle import is_db_hosted, prepare_hosted_db, reopen_db
from src.pipeline.paths import live_db_path, migration_paths



def prepare_for_migration(container: str, settings: Settings) -> bool:
    """Pre-migration deployment: take the hosted database offline if it is open."""
    if not is_db_hosted(container, settings): return False
    prepare_hosted_db(container, settings)
    return True


def deploy_migrated_db(container: str, settings: Settings) -> None:
    paths = migration_paths(settings.solution)
    live = live_db_path(settings.solution)
    script = f"cp {shlex.quote(paths['output'])} {shlex.quote(live)}"
    docker_sh(container, "fms_deploy_migrated_db", script)


def reopen_if_needed(container: str, settings: Settings, db_was_closed: bool) -> None:
    if db_was_closed: reopen_db(container, settings)


def complete_deployment(container: str, settings: Settings, db_was_closed: bool) -> None:
    """Post-migration deployment: promote the migrated file and reopen the database."""

    # deploy_migrated_db(container, settings)
    reopen_if_needed(container, settings, db_was_closed)
