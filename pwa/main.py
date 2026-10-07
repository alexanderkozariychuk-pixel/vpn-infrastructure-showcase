import logging
import os
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
import hashlib
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
from api.email_verify import router as email_verify_router
from api.trial import router as trial_router
from api.notifications import router as notifications_router
from api.admin_grant import router as admin_grant_router

app = FastAPI(title="Sovereign PWA", version="0.8.0")
# Only the site itself calls the API from a browser; the Android app is not
# a browser and is not subject to CORS. "*" let any page on the internet read
# responses for whoever was signed in — harmless only while every request
# needs a token from localStorage, and not worth keeping on that bet.
_ORIGINS = sorted({o.rstrip("/") for o in (os.getenv("SITE_URL", ""), os.getenv("PORTAL_BASE_URL", "")) if o})
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ORIGINS,
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
app.include_router(email_verify_router)
app.include_router(trial_router)
app.include_router(notifications_router)
app.include_router(admin_grant_router)
app.mount("/static", StaticFiles(directory="static"), name="static")


# Pages are revalidated on every load. Without a Cache-Control header a
# browser may reuse a page for a while on its own heuristics — Safari does,
# including for an icon on the home screen — and a deploy would reach some
# customers hours late. With no-cache the check is cheap: an unchanged page
# answers 304 by its ETag.
def _page(path: str) -> FileResponse:
    return FileResponse(path, headers={"Cache-Control": "no-cache"})


# The portal's build, for the page to notice a deploy while it stays open
# (a home-screen app can sit in memory for days). Read once at start: a
# deploy restarts the container.
from pathlib import Path
APP_VERSION = hashlib.sha256((Path(__file__).parent / "static" / "index.html").read_bytes()).hexdigest()[:12]


@app.get("/api/version")
async def app_version():
    return {"version": APP_VERSION}


@app.get("/")
async def landing():
    return _page("static/landing.html")

@app.get("/offer")
async def offer_page():
    return _page("static/offer.html")
    
@app.get("/about")
async def about_page():
    return _page("static/about.html")

@app.get("/privacy")
async def privacy_page():
    return _page("static/privacy.html")

@app.get("/app")
async def app_page():
    return _page("static/index.html")

@app.get("/reset")
async def reset_page():
    # serves the same SPA; frontend reads ?token= and shows the reset form
    return _page("static/index.html")

@app.get("/verify")
async def verify_page():
    # The confirmation link from the welcome letter. The page posts the token
    # to /api/auth/verify-email; nothing is confirmed by the GET itself.
    return _page("static/index.html")

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