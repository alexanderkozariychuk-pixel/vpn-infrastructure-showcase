# Client API — observed contract

Captured by running the application and recording what it actually returned,
not by reading the handlers. The first attempt guessed the device-name field
and got a 422; that is the reason for doing it this way.

Regenerate with `PYTHONPATH=. python ../tools/capture_api.py` from `pwa/`. Values
below come from seeded data and are scrubbed; shapes and status codes are
real.

## What the app has to know

**Device names are at most 6 characters.** `POST /api/client/configs` rejects
longer ones with 422. The limit exists because Amnezia's Android client
refuses longer `.conf` filenames — a constraint inherited from the client we
are replacing. Our own app does not need it, but the server enforces it, so
the app must either restrict the field or relax the server first.

**402 means the subscription lapsed.** Listing devices, adding one and
fetching a config all return 402 for a user whose paid period is over. That
is a distinct state from 401 and the app should show it differently: one says
sign in again, the other says renew.

**409 means the plan is full.** Distinct from 402 and from a server failure;
the message names the limit.

**Timestamps in production carry an offset; the ones below do not.** This
capture ran on SQLite, which returns naive datetimes
(`"2026-10-12T09:26:42.848714"`). Production runs PostgreSQL and returns
`timestamptz` with the offset (`"2026-09-19T19:11:04.609756+00:00"`). Both are
UTC. The first Android build read only the shape recorded here and crashed on
a real account — a client must accept both.

**`is_subscribed` in `/api/client/me` is the raw flag, not the gate.** Access
is decided by `has_active_subscription`: the flag *and* `subscribed_until`
still ahead. The flag is cleared by a periodic sweep some time after the date
passes, so `/me` can say `true` about a period that is over. Clients must
apply the same rule, and treat a missing date as no subscription.

**The `.conf` is plain text, not JSON.** `Content-Type: text/plain`. It is
handed to the tunnel as-is.


## Вход

Возвращает JWT и роль.

```
POST /api/auth/token
→ 200  application/json
```

```
{
  "access_token": "<JWT>",
  "token_type": "bearer",
  "role": "client"
}
```

## Неверный пароль

Роль клиента не раскрывается, сообщение одинаковое.

```
POST /api/auth/token
→ 401  application/json
```

```
{
  "detail": "Invalid credentials"
}
```

## Нет заголовка

Так отвечает защита, когда токена нет вообще.

```
GET /api/client/me
→ 401  application/json
```

```
{
  "detail": "Not authenticated"
}
```

## Битый токен

Отличается от предыдущего кодом.

```
GET /api/client/me
→ 401  application/json
```

```
{
  "detail": "Invalid or expired token"
}
```

## Профиль

Статус подписки, тариф, дата окончания.

```
GET /api/client/me
→ 200  application/json
```

```
{
  "ok": true,
  "username": "paid",
  "email": "paid@example.test",
  "is_subscribed": true,
  "peer_ip": null,
  "subscribed_until": "2026-10-12T09:26:42.848714"
}
```

## Список устройств — пусто

Сразу после регистрации.

```
GET /api/client/configs
→ 200  application/json
```

```
{
  "ok": true,
  "plan": "basic-1m",
  "limit": 2,
  "used": 0,
  "configs": []
}
```

## Добавить устройство

Имя не длиннее 6 символов, иначе 422.

```
POST /api/client/configs
→ 201  application/json
```

```
{
  "ok": true,
  "config": {
    "id": "50ad16ee-a71d-40e1-9ee7-e1036389a1cb",
    "name": "phone",
    "peer_ip": "10.88.88.50",
    "created_at": "2026-09-25T09:26:43"
  },
  "used": 1,
  "limit": 2
}
```

## Добавить второе

Базовый тариф допускает два.

```
POST /api/client/configs
→ 201  application/json
```

```
{
  "ok": true,
  "config": {
    "id": "bddb174e-f00a-4d37-89a3-7a9d7b5dd227",
    "name": "laptop",
    "peer_ip": "10.88.88.51",
    "created_at": "2026-09-25T09:26:43"
  },
  "used": 2,
  "limit": 2
}
```

## Третье — лимит

Ключевая ошибка: превышен лимит тарифа.

```
POST /api/client/configs
→ 409  application/json
```

```
{
  "detail": "Plan allows 2 device(s); remove one first"
}
```

## Список устройств

То, что рисует экран.

```
GET /api/client/configs
→ 200  application/json
```

```
{
  "ok": true,
  "plan": "basic-1m",
  "limit": 2,
  "used": 2,
  "configs": [
    {
      "id": "50ad16ee-a71d-40e1-9ee7-e1036389a1cb",
      "name": "phone",
      "peer_ip": "10.88.88.50",
      "created_at": "2026-09-25T09:26:43"
    },
    {
      "id": "bddb174e-f00a-4d37-89a3-7a9d7b5dd227",
      "name": "laptop",
      "peer_ip": "10.88.88.51",
      "created_at": "2026-09-25T09:26:43"
    }
  ]
}
```

## Файл конфигурации

Текст .conf — его получает туннель.

```
GET /api/client/configs/50ad16ee-a71d-40e1-9ee7-e1036389a1cb/raw
→ 200  text/plain
```

```
[Interface]
PrivateKey = <PRIVATE_KEY>
Address = 10.88.88.50/32
DNS = 1.1.1.1
MTU = 1300
Jc = 3
Jmin = 50
Jmax = 1000
S1 = 72
S2 = 146
H1 = 1163059398
H2 = 1787455160
H3 = 970047041
H4 = 133143559

[Peer]
PublicKey = <BRIDGE_PUBLIC_KEY>
PresharedKey = <PRESHARED_KEY>
Endpoint = <BRIDGE_ENDPOINT>
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25

```

## Удалить устройство

Освобождает место в тарифе.

```
DELETE /api/client/configs/50ad16ee-a71d-40e1-9ee7-e1036389a1cb
→ 200  application/json
```

```
{
  "ok": true,
  "removed": "50ad16ee-a71d-40e1-9ee7-e1036389a1cb"
}
```

## Профиль без подписки

Что видит приложение, когда платить перестали.

```
GET /api/client/me
→ 200  application/json
```

```
{
  "ok": true,
  "username": "lapsed",
  "email": "lapsed@example.test",
  "is_subscribed": false,
  "peer_ip": null,
  "subscribed_until": null
}
```

## Конфиг без подписки

Поведение при истёкшей подписке.

```
GET /api/client/configs
→ 402  application/json
```

```
{
  "detail": "No active subscription"
}
```
