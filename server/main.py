"""
Sconsole Server - Main Entry Point
FastAPI application with REST API and WebSocket support.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from server.api.routes import router as api_router
from server.api.ws_routes import ws_router
from server.config import SERVER_HOST, SERVER_PORT

# Create FastAPI app
app = FastAPI(
    title="Sconsole Server",
    description="Agent deployment and management console server",
    version="0.1.0",
)

# CORS for console web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount REST API and WebSocket routes
app.include_router(api_router)
app.include_router(ws_router)

# Mount console static files
console_static = os.path.join(os.path.dirname(os.path.dirname(__file__)), "console", "static")
if os.path.isdir(console_static):
    app.mount("/static", StaticFiles(directory=console_static), name="static")


@app.get("/")
async def root():
    """Serve the console web UI."""
    index_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "console", "templates", "index.html",
    )
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Sconsole Server is running", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


def main():
    """Run the server."""
    from server.db.database import init_db
    try:
        init_db()
        print("[Server] Database initialized.")
    except Exception as e:
        print(f"[Server] Database init warning (non-fatal): {e}")

    print(f"[Server] Starting Sconsole on {SERVER_HOST}:{SERVER_PORT}")
    uvicorn.run(
        "server.main:app",
        host=SERVER_HOST,
        port=SERVER_PORT,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
