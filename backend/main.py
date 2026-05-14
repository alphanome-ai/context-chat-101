from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.root import router as root_router
from app.core.config import get_settings
from app.core.logging import get_app_logger, setup_logging
from app.core.middleware import RequestContextMiddleware
from app.db.session import init_db

logger = get_app_logger()


@asynccontextmanager
async def lifespan(application: FastAPI):
    setup_logging()
    logger.info("application_starting")
    init_db()
    yield
    logger.info("application_stopping")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    if settings.trusted_hosts and settings.trusted_hosts != ["*"]:
        application.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.trusted_hosts,
        )

    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "X-Process-Time-Ms"],
        )

    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(RequestContextMiddleware)

    @application.exception_handler(RequestValidationError)
    async def _request_validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(status_code=422, content=jsonable_encoder({"detail": exc.errors()}))

    @application.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            extra={
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
            },
        )

        content: dict[str, Any] = {
            "error": {
                "message": "Internal Server Error",
                "code": "INTERNAL_ERROR",
            }
        }
        if settings.debug:
            content["error"]["metadata"] = {"raw": str(exc)}
        return JSONResponse(status_code=500, content=content)

    application.include_router(root_router)
    return application


app = create_app()
