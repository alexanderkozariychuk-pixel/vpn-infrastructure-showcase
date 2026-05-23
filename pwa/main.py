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

app = FastAPI(title="VPN SRE API", version="0.7.0")

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

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/api")
async def api_root():
    return {"status": "ok", "version": "0.7.0"}
