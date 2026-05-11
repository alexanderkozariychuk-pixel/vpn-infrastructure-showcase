from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.status import router as status_router

app = FastAPI(title="VPN SRE API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status_router)


@app.get("/")
async def root():
    return {"status": "ok", "version": "0.1.0"}
