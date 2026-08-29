from fastapi import FastAPI
from app.api.routes import router
from app.core.logger import setup_logging

setup_logging()

app = FastAPI(title="Argus Debate System", description="Multi-Agent Debate System for Verified Claims")

app.include_router(router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the Argus API"}
