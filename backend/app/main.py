from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .database import init_db
from .routers import machines, users, logs, ping
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

app = FastAPI(title="Admin Pharma API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

app.include_router(machines.router, prefix="/api/machines")
app.include_router(users.router, prefix="/api/users")
app.include_router(logs.router, prefix="/api/logs")
app.include_router(ping.router, prefix="/api")

# Serve frontend if built
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
else:
    @app.get("/")
    def index():
        return {"message": "Frontend not built. Build the frontend into frontend/dist to serve static UI."}
