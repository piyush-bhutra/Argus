from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.logger import setup_logging
from app.services import debate_store

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allowing all for local development, adjust as needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def read_root():
    return {"message": "Welcome to the Argus API"}
