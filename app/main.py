from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.logger import setup_logging
from app.services import debate_store
from app.services.retrieval import load_retriever

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    debate_store.load_demos()
    yield


app = FastAPI(
    title="Argus Debate System",
    description="Multi-Agent Debate System for Verified Claims",
    lifespan=lifespan,
)

_origins = settings.cors_origin_list

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Wildcard origins and credentials are mutually exclusive: browsers reject
    # "Access-Control-Allow-Origin: *" on a credentialed request, so the previous
    # combination of both silently failed cross-origin. The API is stateless and
    # uses no cookies or auth headers, so credentials are simply off unless an
    # explicit origin list is configured.
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline response hardening.

    This is a JSON API, so the valuable headers are the ones that stop a
    response being reinterpreted as something executable or embedded elsewhere.
    HSTS is deliberately omitted: it is the reverse proxy's to set, and sending
    it over plain HTTP in local development would pin the browser to https for
    localhost.
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    # No markup is served from this origin, so everything can be denied.
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
    )
    return response


app.include_router(router)


@app.get("/")
def read_root():
    return {"message": "Welcome to the Argus API"}


@app.get("/health")
def health():
    """Liveness probe for the host, and a quick check that the deployment has
    what it needs: hosts expect a cheap endpoint, and a missing evidence corpus
    or LLM key should be visible here rather than at the first request."""
    return {
        "status": "ok",
        "llm_configured": bool(settings.llm_api_key and settings.llm_model),
        "evidence_corpus": load_retriever() is not None,
        "demo_debates": debate_store.count(),
    }
