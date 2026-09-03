import logging
import sys

# ── Logging: surface app-module logs (mailer, etc.) in container stdout ──
# Without this, logger.info/error from our modules are swallowed — only
# uvicorn's own logs appear. This wires the root logger to stdout at INFO
# so `docker logs sovereign-pwa` shows email sends, resets, ticket errors.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.status import router as status_router
from api.clients import router as clients_router
from api.logs import router as logs_router
from api.auth import router as auth_router
from api.analyze import router as analyze_router
from api.register import router as register_router
from api.payment import router as payment_router
from api.config import router as config_router
from api.password_reset import router as password_reset_router
from api.support import router as support_router

app = FastAPI(title="Sovereign PWA", version="0.8.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(status_router)
app.include_router(clients_router)
app.include_router(logs_router)
app.include_router(analyze_router)
app.include_router(register_router)
app.include_router(payment_router)
app.include_router(config_router)
app.include_router(password_reset_router)
app.include_router(support_router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def landing():
    return FileResponse("static/landing.html")


@app.get("/offer")
async def offer_page():
    return FileResponse("static/offer.html")


@app.get("/app")
async def app_page():
    return FileResponse("static/index.html")

@app.get("/reset")
async def reset_page():
    # serves the same SPA; frontend reads ?token= and shows the reset form
    return FileResponse("static/index.html")

@app.get("/api")
async def api_root():
    return {"status": "ok", "version": "0.8.0"}