from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adapters.api.exception_handlers import register_exception_handlers
from .adapters.api.health import router as health_router
from .adapters.api.middleware import RequestContextMiddleware
from .adapters.api.v1.analyses import router as analyses_router
from .adapters.api.v1.rule import router as rule_router
from .infrastructure.config.settings import Settings, get_settings
from .infrastructure.logging.setup import configure_logging


def _configure_cors(app: FastAPI, settings: Settings) -> None:
    if settings.environment in {"local", "dev"}:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app() -> FastAPI:
    """FastAPI factory. API versionada e processo HTTP sem trabalho pesado.

    >>> app = create_app()  # doctest: +SKIP
    """
    settings = get_settings()
    configure_logging()
    app = FastAPI(title=settings.app_name, version="0.3.0")
    app.add_middleware(RequestContextMiddleware)
    _configure_cors(app, settings)
    register_exception_handlers(app)
    app.include_router(health_router)
    prefix = settings.api_v1_prefix
    app.include_router(analyses_router, prefix=prefix)
    app.include_router(rule_router, prefix=prefix)
    return app


app = create_app()
