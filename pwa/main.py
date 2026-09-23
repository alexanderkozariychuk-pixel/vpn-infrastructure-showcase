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
from api.referral import router as referral_router
from api.admin_promo import router as admin_promo_router

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
app.include_router(referral_router)
app.include_router(admin_promo_router)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def landing():
    return FileResponse("static/landing.html")

@app.get("/offer")
async def offer_page():
    return FileResponse("static/offer.html")
    
@app.get("/about")
async def about_page():
    return FileResponse("static/about.html")

@app.get("/privacy")
async def privacy_page():
    return FileResponse("static/privacy.html")

@app.get("/app")
async def app_page():
    return FileResponse("static/index.html")

@app.get("/reset")
async def reset_page():
    # serves the same SPA; frontend reads ?token= and shows the reset form
    return FileResponse("static/index.html")

# Both must answer from the site root — a crawler looks for /robots.txt and
# nowhere else, and a sitemap under /static would not be trusted for URLs
# outside that directory.
# Requested by browsers and crawlers whether or not a page declares it, so a
# 404 here is a blank icon for anyone who looks in the usual place.
@app.get("/favicon.ico")
async def favicon():
    return FileResponse("static/icons/favicon.ico", media_type="image/x-icon")


@app.get("/robots.txt")
async def robots():
    return FileResponse("static/robots.txt", media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap():
    return FileResponse("static/sitemap.xml", media_type="application/xml")


@app.get("/api")
async def api_root():
    """
    Public on purpose: the portal pings it to measure latency.

    It carries no version. Nothing needs one here, and a build number on an
    unauthenticated endpoint is free reconnaissance for anyone deciding
    whether this service is worth a closer look.
    """
    return {"status": "ok"}