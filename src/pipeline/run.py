import logging

from src.config import Settings
from src.pipeline.migration import cleanup_migration_artifacts
from src.pipeline.paths import clone_filename
from src.pipeline.staging import (
    copy_to_container, download_from_s3,
    ensure_fms_migration_dir, ensure_staging_dir, remove_staging_clone
)
from src.pipeline.upgrade import run_solution_upgrade

logger = logging.getLogger(__name__)


def run_upgrade(settings: Settings) -> None:
    clone_name = clone_filename(settings.solution)
    logger.info(
        "Upgrade started: solution=%s bucket=%s clone=%s container=%s",
        settings.solution, settings.bucket, clone_name, settings.fms_container
    )

    staging = ensure_staging_dir()
    local_path = staging / clone_name
    succeeded = False
    container = settings.fms_container
    try:
        download_from_s3(settings, local_path)
        ensure_fms_migration_dir(container, settings)
        copy_to_container(settings, local_path)
        run_solution_upgrade(settings)
        succeeded = True
    finally:
        if not succeeded:
            remove_staging_clone(local_path)
            cleanup_migration_artifacts(container, settings)

    logger.info("Upgrade completed successfully for solution=%s", settings.solution)
