import logging
import shlex
import subprocess

from src.config import Settings
from src.pipeline.constants import _SENSITIVE_FLAGS
from src.pipeline.errors import PipelineError

logger = logging.getLogger(__name__)


def cmd_display(cmd: list[str]) -> str:
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


def run_step(step: str, cmd: list[str]) -> None:
    logger.info("[%s] starting: %s", step, cmd_display(cmd))
    try:
        # Inherit stdout/stderr so aws s3 cp progress and docker output appear in container logs.
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        detail = f"exit code {exc.returncode}"
        logger.error("[%s] failed: %s", step, detail)
        raise PipelineError(step, detail) from exc
    logger.info("[%s] complete", step)


def docker_sh(container: str, step: str, script: str) -> None:
    run_step(step, ["docker", "exec", container, "sh", "-c", script])


def fmsadmin_cmd(container: str, settings: Settings, *args: str) -> list[str]:
    return [
        "docker", "exec", container,
        "fmsadmin", "-y",
        "-u", settings.fms_admin_user,
        "-p", settings.fms_admin_password,
        *args
    ]


def fmsadmin(container: str, settings: Settings, step: str, *args: str) -> None:
    run_step(step, fmsadmin_cmd(container, settings, *args))


def fmsadmin_output(container: str, settings: Settings, step: str, *args: str) -> str:
    cmd = fmsadmin_cmd(container, settings, *args)
    logger.info("[%s] starting: %s", step, cmd_display(cmd))
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = f"exit code {exc.returncode}"
        logger.error("[%s] failed: %s", step, detail)
        raise PipelineError(step, detail) from exc
    logger.info("[%s] complete", step)
    return result.stdout
