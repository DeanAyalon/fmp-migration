import asyncio
import logging

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from uvicorn.logging import DefaultFormatter

from src.auth import verify_bearer_token
from src.config import Settings, get_settings
from src.pipeline import PipelineError, run_upgrade

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    # Match uvicorn's colored level prefixes instead of plain basicConfig output.
    handler = logging.StreamHandler()
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s"))
    app_logger = logging.getLogger("src")
    app_logger.handlers = [handler]
    app_logger.setLevel(logging.INFO)


_configure_logging()

# Fail fast if required env vars are missing or empty.
get_settings()

app = FastAPI()
_upgrade_lock = asyncio.Lock()


@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}


@app.post("/migrate", dependencies=[Depends(verify_bearer_token)], response_model=None)
async def migrate(settings: Settings = Depends(get_settings)):
    if _upgrade_lock.locked():
        logger.warning("Upgrade request rejected: another run is in progress")
        return JSONResponse(status_code=409, content={"status": "busy"})

    await _upgrade_lock.acquire()
    try:
        logger.info("Upgrade request accepted for solution=%s", settings.solution)
        try: await asyncio.to_thread(run_upgrade, settings)
        except PipelineError as exc:
            logger.error("Upgrade failed at step=%s: %s", exc.step, exc.detail)
            return JSONResponse(
                status_code=502,
                content={"status": "error", "step": exc.step, "detail": exc.detail},
            )

        logger.info("Upgrade request finished successfully for solution=%s", settings.solution)
        return {"status": "ok"}
    finally: _upgrade_lock.release()


# Entrypoint
def main() -> None:
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )

if __name__ == "__main__": main()
