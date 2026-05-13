from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.status import router as status_router
from api.clients import router as clients_router
from api.logs import router as logs_router
from api.auth import router as auth_router

app = FastAPI(title="VPN SRE API", version="0.4.0")

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


@app.get("/")
async def root():
    return {"status": "ok", "version": "0.4.0"}
