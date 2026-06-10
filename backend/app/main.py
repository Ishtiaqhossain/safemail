from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import get_settings
from app.ratelimit import limiter
from app.routers import auth, children, alerts, preferences, stats, admin, developer

settings = get_settings()

app = FastAPI(
    title="SafeMail API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting (slowapi). The limiter is referenced by @limiter.limit decorators
# on auth routes; here we wire it into the app and register the 429 handler.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/v1"
app.include_router(auth.router, prefix=API_PREFIX)
app.include_router(children.router, prefix=API_PREFIX)
app.include_router(alerts.router, prefix=API_PREFIX)
app.include_router(preferences.router, prefix=API_PREFIX)
app.include_router(stats.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)
app.include_router(developer.router, prefix=API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "type": "https://api.safemail.com/errors/internal-error",
            "title": "Internal Server Error",
            "status": 500,
            "detail": str(exc),
        },
    )
