from fastapi import APIRouter
from concurrent.futures import ThreadPoolExecutor
import asyncio
from services.net_manager import get_full_status_data, get_system_health, get_network_quality

router = APIRouter()
executor = ThreadPoolExecutor()


async def run_sync(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, func, *args)


@router.get("/api/status")
async def get_status():
    peers, err = await run_sync(get_full_status_data)
    if err:
        return {"ok": False, "error": err}

    return {
        "ok": True,
        "interface": "awg0",
        "node": "moldova",
        "total_peers": len(peers) if peers else 0,
        "active_peers": sum(
            1 for p in peers
            if p.handshake != "never" and p.handshake != "0"
        ) if peers else 0,
        "peers": [
            {
                "public_key": p.public_key[:12] + "...",
                "handshake": p.handshake,
                "transfer": p.transfer,
                "endpoint": p.endpoint,
            }
            for p in (peers or [])
        ]
    }


@router.get("/api/health")
async def get_health():
    local_m, remote_m, err = await run_sync(get_system_health)
    net_q = await run_sync(get_network_quality)

    return {
        "ok": True,
        "bulgaria": local_m,
        "moldova": remote_m if not err else {"error": err},
        "tunnel": net_q,
    }
