import asyncio
import logging

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from uvicorn.logging import DefaultFormatter

from src.auth import verify_bearer_token
from src.config import Settings, get_settings
from src.pipeline import PipelineError, run_migration

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    # Match uvicorn's colored level prefixes instead of plain basicConfig output.
    handler = logging.StreamHandler()
    handler.setFormatter(DefaultFormatter("%(levelprefix)s %(message)s"))
    app_logger = logging.getLogger("src")
    app_logger.handlers = [handler]
    app_logger.setLevel(logging.INFO)


_configure_logging()

app = FastAPI()
_migration_lock = asyncio.Lock()


@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}


@app.post("/migrate", dependencies=[Depends(verify_bearer_token)], response_model=None)
async def migrate(settings: Settings = Depends(get_settings)):
    if _migration_lock.locked():
        logger.warning("Migration request rejected: another run is in progress")
        return JSONResponse(status_code=409, content={"status": "busy"})

    await _migration_lock.acquire()
    try:
        logger.info("Migration request accepted for solution=%s", settings.solution)
        try: await asyncio.to_thread(run_migration, settings)
        except PipelineError as exc:
            logger.error("Migration failed at step=%s: %s", exc.step, exc.detail)
            return JSONResponse(
                status_code=502,
                content={"status": "error", "step": exc.step, "detail": exc.detail},
            )

        logger.info("Migration request finished successfully for solution=%s", settings.solution)
        return {"status": "ok"}
    finally: _migration_lock.release()


# Entrypoint
def main() -> None:
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )

if __name__ == "__main__": main()
