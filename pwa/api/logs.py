from fastapi import APIRouter, Query, Depends
from concurrent.futures import ThreadPoolExecutor
import asyncio
from auth.jwt import require_auth
from services.net_manager import get_logs

router = APIRouter()
executor = ThreadPoolExecutor()


async def run_sync(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func, *args)


@router.get("/api/logs")
async def get_all_logs(lines: int = Query(default=50, le=200), _: dict = Depends(require_auth)):
    logs = await run_sync(get_logs, lines)
    return {
        "ok": True,
        "node": "moldova",
        "logs": {
            service: content.splitlines()
            for service, content in logs.items()
        },
    }


@router.get("/api/logs/{service}")
async def get_service_logs(service: str, lines: int = Query(default=50, le=200), _: dict = Depends(require_auth)):
    valid = {"awg", "sshd", "fail2ban"}
    if service not in valid:
        return {"ok": False, "error": f"Unknown service. Valid: {list(valid)}"}

    logs = await run_sync(get_logs, lines)
    content = logs.get(service, "")
    return {
        "ok": True,
        "node": "moldova",
        "service": service,
        "lines": content.splitlines() if content else [],
    }
