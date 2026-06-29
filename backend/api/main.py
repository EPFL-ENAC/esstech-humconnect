from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging import INFO, basicConfig, warning

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi_cache import FastAPICache
from fastapi_cache.backends.inmemory import InMemoryBackend
from fastmcp.utilities.lifespan import combine_lifespans
from pydantic import BaseModel
from starlette.routing import Route

from api.config import config
from api.db import dispose_engine
from api.views.chats import mark_interrupted_messages_on_startup, router as chats_router
from api.views.recorded_events import router as recorded_events_router
# from api.views.files import router as files_router
from meditron_mcp.main import mcp as meditron_mcp

basicConfig(level=INFO)


@asynccontextmanager
async def app_lifespan(_: FastAPI) -> AsyncIterator[None]:
    FastAPICache.init(InMemoryBackend(), prefix="fastapi-cache")
    await mark_interrupted_messages_on_startup()
    try:
        yield
    finally:
        await dispose_engine()


meditron_mcp_app = meditron_mcp.http_app(path="/mcp")

app = FastAPI(
    root_path=config.API_PATH,
    lifespan=combine_lifespans(app_lifespan, meditron_mcp_app.lifespan),
)

origins = [config.APP_URL] if config.APP_URL else []
if not config.APP_URL:
    warning(
        "config.APP_URL is not set. CORS will not allow any origins. "
        "Set config.APP_URL to enable cross-origin requests."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthCheck(BaseModel):
    """Response model to validate and return when performing a health check."""

    status: str = "OK"


@app.get(
    "/healthz",
    tags=["Healthcheck"],
    summary="Perform a Health Check",
    response_description="Return HTTP Status Code 200 (OK)",
    status_code=status.HTTP_200_OK,
)
async def get_health() -> HealthCheck:
    """Endpoint to perform an API healthcheck."""

    return HealthCheck(status="OK")


class _MCPMountSlashFix:
    """Handle exact mount path without trailing slash to avoid Starlette's
    broken trailing-slash redirect behind path-stripping reverse proxies.
    """

    def __init__(self, mcp_app, mount_path: str):
        self.mcp_app = mcp_app
        self.mount_path = mount_path

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope = dict(scope)
            root_path = scope.get("root_path", "")
            scope["root_path"] = root_path + self.mount_path
            scope["path"] = "/"
        await self.mcp_app(scope, receive, send)


def add_mcp_proxy(mount_path: str, mcp_app):
    app.routes.insert(
        0,
        Route(
            mount_path,
            endpoint=_MCPMountSlashFix(mcp_app, mount_path),
            include_in_schema=False,
        ),
    )
    app.mount(mount_path, mcp_app)


add_mcp_proxy("/mcp/meditron", meditron_mcp_app)

app.include_router(chats_router)
app.include_router(recorded_events_router)


# app.include_router(
#     files_router,
#     prefix="/files",
#     tags=["Files"],
# )
