"""
Record what the client API actually returns, for the Android client to be
written against. Observed behaviour, not a reading of the source.
"""
import asyncio, json, os, uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("JWT_SECRET", "capture-secret")
os.environ.setdefault("ADMIN_PASSWORD", "capture-admin")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("FERNET_KEY", "8ZVnLbQ6fJ0xTjWn7l5cPq2sR9dY4hK1vG3mA6uE0oI=")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.base import Base, get_db
from db.models import User, Config
from auth.jwt import hash_password
from api.auth import router as auth_router
from api.config import router as config_router
from api.register import router as register_router
from services import provisioner

engine = create_async_engine("sqlite+aiosqlite:///./capture.db")
maker = async_sessionmaker(engine, expire_on_commit=False)

app = FastAPI()
for r in (auth_router, config_router, register_router):
    app.include_router(r)

async def _o():
    async with maker() as s:
        yield s
app.dependency_overrides[get_db] = _o

# The SSH path is stubbed; everything else is the real handler.
_n = [0]
async def fake_issue(user, db, name="device"):
    _n[0] += 1
    c = Config(id=str(uuid.uuid4()), user_id=user.id, name=name,
               peer_ip=f"10.88.88.{49 + _n[0]}",
               private_key=provisioner._encrypt("PRIV" + "A" * 40),
               public_key="PUB" + "B" * 40,
               preshared_key=provisioner._encrypt("PSK" + "C" * 41),
               is_active=True)
    db.add(c)
    return c
# api/config.py does `from services.provisioner import issue_config`, so the
# bound name in that module is what has to be replaced — patching the
# provisioner module alone leaves the handler calling the real one, which
# reaches for ssh and dies.
import api.config as _cfg
provisioner.issue_config = fake_issue
_cfg.issue_config = fake_issue

# Removal reaches the node over ssh as well. Sync, returns (ok, reason) —
# it is called through run_in_executor.
def fake_remove(pub):
    return True, ""
provisioner._remove_peer_from_bridge = fake_remove
_cfg._remove_peer_from_bridge = fake_remove

NOW = datetime.now(timezone.utc)

async def seed():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)
        await c.run_sync(Base.metadata.create_all)
    async with maker() as s:
        s.add(User(id=str(uuid.uuid4()), username="paid", email="paid@example.test",
                   password_hash=hash_password("correct-horse"), is_subscribed=True,
                   plan="basic-1m", subscribed_until=NOW + timedelta(days=17)))
        s.add(User(id=str(uuid.uuid4()), username="lapsed", email="lapsed@example.test",
                   password_hash=hash_password("correct-horse"), is_subscribed=False))
        await s.commit()
asyncio.run(seed())

c = TestClient(app)
out = []

def rec(title, note, method, path, *, headers=None, json_body=None):
    r = getattr(c, method.lower())(path, headers=headers or {}, **({"json": json_body} if json_body else {}))
    try:
        body = json.dumps(r.json(), ensure_ascii=False, indent=2)
    except Exception:
        body = r.text
    if len(body) > 900:
        body = body[:900] + "\n… (обрезано)"
    out.append({"title": title, "note": note, "method": method, "path": path,
                "status": r.status_code, "ct": r.headers.get("content-type", "").split(";")[0],
                "body": body})
    return r

tok = rec("Вход", "Возвращает JWT и роль.", "POST", "/api/auth/token",
          json_body={"username": "paid", "password": "correct-horse"}).json()["access_token"]
H = {"Authorization": f"Bearer {tok}"}

rec("Неверный пароль", "Роль клиента не раскрывается, сообщение одинаковое.", "POST",
    "/api/auth/token", json_body={"username": "paid", "password": "wrong"})
rec("Нет заголовка", "Так отвечает защита, когда токена нет вообще.", "GET", "/api/client/me")
rec("Битый токен", "Отличается от предыдущего кодом.", "GET", "/api/client/me",
    headers={"Authorization": "Bearer not.a.token"})
rec("Профиль", "Статус подписки, тариф, дата окончания.", "GET", "/api/client/me", headers=H)
rec("Список устройств — пусто", "Сразу после регистрации.", "GET", "/api/client/configs", headers=H)
first = rec("Добавить устройство", "Имя не длиннее 6 символов, иначе 422.", "POST",
            "/api/client/configs", headers=H, json_body={"name": "phone"}).json()
rec("Добавить второе", "Базовый тариф допускает два.", "POST", "/api/client/configs",
    headers=H, json_body={"name": "laptop"})
rec("Третье — лимит", "Ключевая ошибка: превышен лимит тарифа.", "POST",
    "/api/client/configs", headers=H, json_body={"name": "tablet"})
rec("Список устройств", "То, что рисует экран.", "GET", "/api/client/configs", headers=H)
cid = first.get("id") or first.get("config", {}).get("id")
rec("Файл конфигурации", "Текст .conf — его получает туннель.", "GET",
    f"/api/client/configs/{cid}/raw", headers=H)
rec("Удалить устройство", "Освобождает место в тарифе.", "DELETE",
    f"/api/client/configs/{cid}", headers=H)

tok2 = c.post("/api/auth/token", json={"username": "lapsed", "password": "correct-horse"}).json()["access_token"]
H2 = {"Authorization": f"Bearer {tok2}"}
rec("Профиль без подписки", "Что видит приложение, когда платить перестали.", "GET", "/api/client/me", headers=H2)
rec("Конфиг без подписки", "Поведение при истёкшей подписке.", "GET", "/api/client/configs", headers=H2)

json.dump(out, open("/tmp/claude-0/-home-claude/516589b3-43e8-5816-a92b-6b9d3617912b/scratchpad/api_capture.json", "w"), ensure_ascii=False, indent=2)
print(f"записано {len(out)} вызовов")
