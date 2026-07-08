import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import Base, engine
from app.routers import documents, permits, chat

# Root logging config — without this, INFO-level logs (like the vision
# model debug output in llm_client.py) are silently dropped since Python
# defaults to WARNING level, making real debugging output invisible.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Logistisy Permit Copilot API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(documents.router)
app.include_router(permits.router)
app.include_router(chat.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}


# Frontend static files — Vite builds to frontend/dist, copied in during
# the Docker build. Served from the same origin as the API, so the
# frontend needs no VITE_API_BASE_URL — plain relative fetches work.
FRONTEND = Path("frontend/dist")
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND / "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        return FileResponse(FRONTEND / "index.html")
