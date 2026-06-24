import logging
from pathlib import Path

from src.config import Settings
from src.pipeline.commands import run_step
from src.pipeline.constants import STAGING_DIR
from src.pipeline.paths import clone_filename, migration_paths

logger = logging.getLogger(__name__)


def ensure_staging_dir() -> Path:
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    return STAGING_DIR


def download_from_s3(settings: Settings, local_path: Path) -> None:
    object_key = clone_filename(settings.solution)
    s3_uri = f"s3://{settings.bucket}/{object_key}"
    logger.info("[%s] downloading %s -> %s", "s3_download", s3_uri, local_path)
    run_step("s3_download", ["aws", "s3", "cp", s3_uri, str(local_path)])
    size_bytes = local_path.stat().st_size
    logger.info("[%s] saved %s bytes to %s", "s3_download", size_bytes, local_path)


def ensure_fms_migration_dir(container: str, settings: Settings) -> None:
    paths = migration_paths(settings.solution)
    run_step("docker_prepare", ["docker", "exec", container, "mkdir", "-p", paths["dir"]])
    run_step(
        "docker_prepare",
        [
            "docker", "exec", container, "rm", "-f",
            paths["clone"], paths["source"], paths["output"],
        ],
    )


def copy_to_container(settings: Settings, local_path: Path) -> None:
    dest = f"{settings.fms_container}:/tmp/migration/clone.fmp12"
    run_step("docker_cp", ["docker", "cp", str(local_path), dest])
    remove_staging_clone(local_path)


def remove_staging_clone(local_path: Path) -> None:
    if not local_path.exists(): return
    local_path.unlink()
    logger.info("Removed staging clone: %s", local_path)
