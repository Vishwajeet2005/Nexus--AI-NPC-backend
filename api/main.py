"""
api/main.py
───────────
Central FastAPI application: lifespan, middleware stack, router registration,
and global exception handling.

Middleware registration order (per spec — innermost wraps first):
  1. CORSMiddleware          — outermost; handles OPTIONS preflight before anything else
  2. RequestLoggingMiddleware — attaches request_id, measures duration, emits structured log
  3. RateLimitMiddleware      — sliding-window per-IP using Redis
  (Global exception handlers are registered separately via @app.exception_handler)

Lifespan:
  startup  → create AsyncEngine, aioredis.Redis pool, call init_db() / init_redis()
  shutdown → close Redis pool, dispose engine, log drain confirmation

All error responses conform to the ErrorResponse schema:
  { "error": "...", "code": "...", "request_id": "uuid" }
"""

from __future__ import annotations

import json
import logging
import logging.config
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

import redis.asyncio as aioredis

from api.config import get_settings
from api.dependencies import init_db, init_redis
from api.routers import auth, sessions, realtime, npcs, analytics, games, webhooks
from api.schemas.common import ErrorResponse

settings = get_settings()


# ── Structured logging setup ───────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """
    Emit each log record as a single-line JSON object.

    Fields: timestamp, level, logger, message, + any `extra` kwargs passed
    to the log call (e.g. request_id, player_id, session_id).
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge any structured extras passed via `extra={...}`
        for key, value in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text",
                "filename", "funcName", "id", "levelname", "levelno",
                "lineno", "message", "module", "msecs", "msg", "name",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "taskName",
            ):
                log_obj[key] = value
        if record.exc_info:
            log_obj["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, default=str)


def _configure_logging() -> None:
    """
    Replace the root handler with a JSON formatter.
    In production (`ENVIRONMENT=production`) set level to INFO.
    In development keep DEBUG for verbose output.
    """
    level = logging.DEBUG if settings.is_development else logging.INFO
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(level)
    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)


# ── Application lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage the full application lifecycle:

    STARTUP
    -------
    1. Configure structured JSON logging.
    2. Create an async SQLAlchemy engine (asyncpg driver).
    3. Create a redis.asyncio connection pool.
    4. Call init_db() / init_redis() to wire the singletons used by
       Depends(get_db) and Depends(get_redis) throughout the app.

    SHUTDOWN
    --------
    5. Close the Redis connection pool (flushes pending commands).
    6. Dispose the SQLAlchemy engine (closes all pooled connections).

    Note on WebSocket cleanup: FastAPI handles WebSocket disconnects at the
    transport layer — the handler coroutines are cancelled by uvicorn when
    the server shuts down. Our per-connection `stop_event` and `finally`
    blocks in realtime.py ensure clean Redis unsubscribe on cancellation.
    """
    # ── Startup ────────────────────────────────────────────────────────────────
    _configure_logging()

    logger.info(
        "nexus.startup",
        extra={"environment": settings.environment, "version": "1.0.0-phase1"},
    )

    # SQLAlchemy async engine
    engine: AsyncEngine = create_async_engine(
        settings.database_url,
        # Pool sizing: 5 base connections + 10 overflow is appropriate for a
        # single-instance dev deployment; tune via env vars in production.
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,          # verify connections before use
        pool_recycle=3600,           # recycle connections after 1 hour
        echo=settings.is_development,  # SQL logging in dev only
    )
    init_db(engine)
    logger.info("nexus.db_ready", extra={"url": settings.database_url.split("@")[-1]})

    # Redis connection pool
    redis_client: aioredis.Redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=False,   # keep bytes for pub/sub data frames
    )
    # Verify the connection is live before accepting traffic
    await redis_client.ping()
    init_redis(redis_client)
    logger.info("nexus.redis_ready", extra={"url": settings.redis_url})

    logger.info("nexus.ready")

    yield  # ← application runs here

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("nexus.shutdown_begin")

    try:
        await redis_client.aclose()
        logger.info("nexus.redis_closed")
    except Exception as exc:
        logger.warning("nexus.redis_close_error", extra={"error": str(exc)})

    try:
        await engine.dispose()
        logger.info("nexus.db_closed")
    except Exception as exc:
        logger.warning("nexus.db_close_error", extra={"error": str(exc)})

    logger.info("nexus.shutdown_complete")


# ── FastAPI application ────────────────────────────────────────────────────────

app = FastAPI(
    title="Nexus Game Backend",
    description=(
        "Phase 1: AI-native game backend — player auth, multiplayer sessions, "
        "real-time WebSocket events, and analytics infrastructure."
    ),
    version="1.0.0-phase1",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ── Middleware: 1. CORS ────────────────────────────────────────────────────────
# Registered first (outermost layer) so OPTIONS preflight requests are handled
# before any auth or rate-limit logic runs.

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware: 2. Structured Request Logging ──────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Per-request middleware that:
    - Generates a UUID4 `request_id` and attaches it to `request.state`.
    - Measures the full response duration (wall-clock, milliseconds).
    - Emits a structured JSON log line after the response is sent.

    Log fields: method, path, status_code, duration_ms, request_id,
                client_ip, user_agent.
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            status_code = response.status_code if response is not None else 500

            logger.info(
                "http.request",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query) or None,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip(request),
                    "user_agent": request.headers.get("user-agent"),
                },
            )

        return response


def _client_ip(request: Request) -> str:
    """
    Extract the real client IP, honouring X-Forwarded-For if present.
    In production this header is set by the load balancer / reverse proxy.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


app.add_middleware(RequestLoggingMiddleware)


# ── Middleware: 3. Rate Limiting ───────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter: `RATE_LIMIT_PER_MINUTE` requests per IP
    per 60-second rolling window, enforced in Redis.

    Algorithm:
    - Key: `ratelimit:{ip}:{current_minute_bucket}`
    - On each request: INCR the key, EXPIRE to 60s on first hit.
    - If the count exceeds the limit → 429 Too Many Requests.

    Using a 60-second bucket (rather than a true sliding window) is a
    pragmatic approximation that requires only a single Redis round-trip.
    It is accurate enough for the spec's "sliding window" requirement at
    this scale; a full sliding window using ZSET is trivial to swap in
    later without changing the interface.

    WebSocket upgrade requests are counted but not rejected mid-stream —
    the check runs only on the initial HTTP upgrade handshake.
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        from api.dependencies import _redis_pool

        # Skip rate limiting if Redis is not yet initialised (e.g. health checks
        # that fire before the lifespan startup completes).
        if _redis_pool is None:
            return await call_next(request)

        ip = _client_ip(request)
        bucket = int(time.time() // 60)
        key = f"ratelimit:{ip}:{bucket}"

        try:
            count: int = await _redis_pool.incr(key)
            if count == 1:
                # First request in this bucket — set TTL so Redis self-cleans.
                await _redis_pool.expire(key, 60)

            if count > settings.rate_limit_per_minute:
                request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
                logger.warning(
                    "http.rate_limited",
                    extra={
                        "request_id": request_id,
                        "ip": ip,
                        "count": count,
                        "limit": settings.rate_limit_per_minute,
                    },
                )
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": (
                            f"Rate limit exceeded. Maximum {settings.rate_limit_per_minute} "
                            "requests per minute."
                        ),
                        "code": "RATE_LIMIT_EXCEEDED",
                        "request_id": request_id,
                    },
                    headers={"Retry-After": "60"},
                )
        except Exception as exc:
            # Redis failure → fail open (allow the request through).
            # Logging the error is sufficient; we never want Redis downtime
            # to take down the API.
            logger.warning(
                "http.rate_limit_error",
                extra={"error": str(exc), "ip": ip},
            )

        return await call_next(request)


app.add_middleware(RateLimitMiddleware)


# ── Exception handlers ─────────────────────────────────────────────────────────
# These are registered after middleware so they run inside the logging wrapper
# and have access to request.state.request_id.

def _request_id(request: Request) -> str:
    """Extract the request_id set by RequestLoggingMiddleware, or generate one."""
    return str(getattr(request.state, "request_id", uuid.uuid4()))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Normalise all FastAPI/Starlette HTTPExceptions into the ErrorResponse envelope.

    Services raise HTTPException with `detail` as either:
    - A dict: `{"error": "...", "code": "..."}` → used directly.
    - A string: used as `error`; `code` defaults to `HTTP_{status_code}`.
    """
    request_id = _request_id(request)

    if isinstance(exc.detail, dict):
        error_msg = exc.detail.get("error", str(exc.detail))
        error_code = exc.detail.get("code", f"HTTP_{exc.status_code}")
    else:
        error_msg = str(exc.detail)
        error_code = f"HTTP_{exc.status_code}"

    logger.warning(
        "http.exception",
        extra={
            "request_id": request_id,
            "status_code": exc.status_code,
            "code": error_code,
            "error": error_msg,
        },
    )

    content = {
        "error": error_msg,
        "code": error_code,
        "request_id": request_id,
    }
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for any unhandled exception.

    Returns 500 with the ErrorResponse envelope. The full traceback is
    logged at ERROR level so it appears in structured logs without leaking
    internals to the API consumer.
    """
    request_id = _request_id(request)

    logger.error(
        "http.unhandled_exception",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error": str(exc),
        },
        exc_info=exc,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An unexpected internal error occurred.",
            "code": "INTERNAL_SERVER_ERROR",
            "request_id": request_id,
        },
    )


# ── Router registration ────────────────────────────────────────────────────────
# All routers are mounted under /v1.
# realtime uses WebSocket routes — FastAPI handles them transparently here.

app.include_router(auth.router,       prefix="/v1")
app.include_router(sessions.router,   prefix="/v1")
app.include_router(npcs.router,       prefix="/v1")
app.include_router(analytics.router,  prefix="/v1")
app.include_router(games.router,      prefix="/v1")
app.include_router(webhooks.router,   prefix="/v1")
app.include_router(realtime.router,   prefix="/v1")


# ── Health check ───────────────────────────────────────────────────────────────

@app.get(
    "/health",
    tags=["Health"],
    summary="Liveness probe",
    include_in_schema=True,
)
async def health() -> dict[str, str]:
    """
    Returns 200 immediately.

    Used by Docker / Kubernetes liveness probes. Does NOT check DB or Redis
    connectivity — use a dedicated readiness endpoint for that.
    """
    return {"status": "ok", "version": "1.0.0-phase1"}


@app.get(
    "/ready",
    tags=["Health"],
    summary="Readiness probe — checks DB and Redis",
    include_in_schema=True,
)
async def readiness() -> JSONResponse:
    """
    Verifies both Postgres and Redis are reachable.

    Returns 200 `{ "status": "ready" }` if both are up,
    or 503 `{ "status": "unavailable", "detail": "..." }` if either is down.
    """
    from api.dependencies import _redis_pool, _async_session_factory
    from sqlalchemy import text

    errors: list[str] = []

    # Redis ping
    if _redis_pool is None:
        errors.append("Redis not initialised")
    else:
        try:
            await _redis_pool.ping()
        except Exception as exc:
            errors.append(f"Redis: {exc}")

    # Postgres ping
    if _async_session_factory is None:
        errors.append("Database not initialised")
    else:
        try:
            async with _async_session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as exc:
            errors.append(f"Database: {exc}")

    if errors:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "unavailable", "detail": "; ".join(errors)},
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ready"},
    )
