import asyncio

import uvicorn
from fastapi import Depends, FastAPI

from src.auth import verify_bearer_token
from src.config import Settings, get_settings

app = FastAPI()
_migration_lock = asyncio.Lock()


@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}


@app.post("/migrate", dependencies=[Depends(verify_bearer_token)])
async def migrate(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    if _migration_lock.locked(): return {"status": "busy"}
    async with _migration_lock:
        # Pipeline implementation will be wired in a later step.
        return {"status": "ok"}


# Entrypoint
def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True
    )

if __name__ == "__main__": main()
