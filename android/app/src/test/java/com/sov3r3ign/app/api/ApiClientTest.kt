package com.sov3r3ign.app.api

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.IOException
import java.time.Instant

/*
 * Every response body below is copied from docs/api-contract.md, which was
 * recorded by running the server — not written from the handlers. The section
 * each one comes from is named beside it. If the server changes, re-record the
 * contract and these fixtures with it.
 */
class ApiClientTest {

    private class Recorder(private val code: Int, private val body: String) : Transport {
        val calls = mutableListOf<String>()
        var lastBody: String? = null

        override fun send(method: String, path: String, token: String?, jsonBody: String?): HttpReply {
            calls += "$method $path ${token ?: "-"}"
            lastBody = jsonBody
            return HttpReply(code, body)
        }
    }

    private fun <T> ok(result: ApiResult<T>): T = when (result) {
        is ApiResult.Ok -> result.value
        is ApiResult.Failed -> throw AssertionError("expected success, got ${result.error}")
    }

    private fun error(result: ApiResult<*>): ApiError = when (result) {
        is ApiResult.Ok -> throw AssertionError("expected failure, got ${result.value}")
        is ApiResult.Failed -> result.error
    }

    // «Вход»
    private val login = """
        {
          "access_token": "<JWT>",
          "token_type": "bearer",
          "role": "client"
        }
    """.trimIndent()

    // «Профиль»
    private val profile = """
        {
          "ok": true,
          "username": "paid",
          "email": "paid@example.test",
          "is_subscribed": true,
          "peer_ip": null,
          "subscribed_until": "2026-10-12T09:26:42.848714"
        }
    """.trimIndent()

    // «Профиль без подписки»
    private val lapsedProfile = """
        {
          "ok": true,
          "username": "lapsed",
          "email": "lapsed@example.test",
          "is_subscribed": false,
          "peer_ip": null,
          "subscribed_until": null
        }
    """.trimIndent()

    // «Список устройств»
    private val devices = """
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
    """.trimIndent()

    // «Список устройств — пусто»
    private val noDevices = """
        {
          "ok": true,
          "plan": "basic-1m",
          "limit": 2,
          "used": 0,
          "configs": []
        }
    """.trimIndent()

    // «Добавить устройство»
    private val added = """
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
    """.trimIndent()

    // «Файл конфигурации», trimmed to its first lines
    private val conf = "[Interface]\nPrivateKey = <PRIVATE_KEY>\nAddress = 10.88.88.50/32\n"

    // --- sign in -------------------------------------------------------------

    @Test
    fun `sign in returns the token and sends the credentials as JSON`() {
        val t = Recorder(200, login)
        val token = ok(ApiClient(t).login("paid", "secret"))
        assertEquals("<JWT>", token.accessToken)
        assertEquals(listOf("POST /api/auth/token -"), t.calls)
        assertEquals("""{"username":"paid","password":"secret"}""", t.lastBody)
    }

    @Test
    fun `a wrong password is Unauthorized`() {
        // «Неверный пароль»
        val r = ApiClient(Recorder(401, """{"detail": "Invalid credentials"}""")).login("paid", "x")
        assertEquals(ApiError.Unauthorized, error(r))
    }

    @Test
    fun `the admin account is refused, not kept`() {
        val admin = login.replace("\"client\"", "\"admin\"")
        val e = error(ApiClient(Recorder(200, admin)).login("admin", "x"))
        assertTrue(e is ApiError.Rejected)
    }

    @Test
    fun `registration succeeds on 201 and a taken name is a Conflict with the reason`() {
        val created = """{"id":"u1","username":"new","email":"new@example.test","is_active":true,"is_subscribed":false,"peer_ip":null}"""
        ok(ApiClient(Recorder(201, created)).register("new", "new@example.test", "secret"))

        val taken = ApiClient(Recorder(409, """{"detail": "Username 'new' already exists"}"""))
            .register("new", "new@example.test", "secret")
        assertEquals(ApiError.Conflict("Username 'new' already exists"), error(taken))
    }

    // --- profile -------------------------------------------------------------

    @Test
    fun `the expiry date is read as UTC, not local time`() {
        val p = ok(ApiClient(Recorder(200, profile)).profile("tok"))
        assertTrue(p.isSubscribed)
        assertEquals(Instant.parse("2026-10-12T09:26:42.848714Z"), p.subscribedUntil)
    }

    @Test
    fun `production writes the offset, and that is read too`() {
        // Recorded on SQLite, the contract has no offset; PostgreSQL adds one.
        // The first build read only the contract's shape and crashed on this.
        val prod = profile.replace("09:26:42.848714\"", "09:26:42.848714+00:00\"")
        val p = ok(ApiClient(Recorder(200, prod)).profile("tok"))
        assertEquals(Instant.parse("2026-10-12T09:26:42.848714Z"), p.subscribedUntil)
    }

    @Test
    fun `an unreadable date is null, never an exception`() {
        val odd = profile.replace("2026-10-12T09:26:42.848714", "next Tuesday")
        assertEquals(null, ok(ApiClient(Recorder(200, odd)).profile("tok")).subscribedUntil)
    }

    @Test
    fun `a lapsed profile has no expiry date and is not subscribed`() {
        val p = ok(ApiClient(Recorder(200, lapsedProfile)).profile("tok"))
        assertFalse(p.isSubscribed)
        assertEquals(null, p.subscribedUntil)
    }

    @Test
    fun `a bad token is Unauthorized and the token is sent`() {
        // «Битый токен»
        val t = Recorder(401, """{"detail": "Invalid or expired token"}""")
        assertEquals(ApiError.Unauthorized, error(ApiClient(t).profile("tok")))
        assertEquals(listOf("GET /api/client/me tok"), t.calls)
    }

    // --- devices -------------------------------------------------------------

    @Test
    fun `the device list is read, and a full plan has no room`() {
        val list = ok(ApiClient(Recorder(200, devices)).devices("tok"))
        assertEquals(listOf("phone", "laptop"), list.configs.map { it.name })
        assertEquals("10.88.88.50", list.configs[0].peerIp)
        assertFalse(list.hasRoom)
    }

    @Test
    fun `an empty list after registration has room`() {
        val list = ok(ApiClient(Recorder(200, noDevices)).devices("tok"))
        assertTrue(list.configs.isEmpty())
        assertTrue(list.hasRoom)
    }

    @Test
    fun `a lapsed subscription is its own state, not a sign-in problem`() {
        // «Конфиг без подписки»
        val r = ApiClient(Recorder(402, """{"detail": "No active subscription"}""")).devices("tok")
        assertEquals(ApiError.SubscriptionLapsed, error(r))
    }

    @Test
    fun `adding a device returns the new device`() {
        val t = Recorder(201, added)
        val d = ok(ApiClient(t).addDevice("tok", "phone"))
        assertEquals("50ad16ee-a71d-40e1-9ee7-e1036389a1cb", d.id)
        assertEquals("""{"name":"phone"}""", t.lastBody)
    }

    @Test
    fun `a full plan is a Conflict carrying the server's reason`() {
        // «Третье — лимит»
        val r = ApiClient(Recorder(409, """{"detail": "Plan allows 2 device(s); remove one first"}"""))
            .addDevice("tok", "tablet")
        assertEquals(ApiError.Conflict("Plan allows 2 device(s); remove one first"), error(r))
    }

    @Test
    fun `a name over six characters is refused before any request`() {
        val never = Transport { _, _, _, _ -> fail("must not reach the network"); HttpReply(0, "") }
        assertTrue(error(ApiClient(never).addDevice("tok", "Galaxy A71")) is ApiError.Rejected)
        assertTrue(error(ApiClient(never).addDevice("tok", "   ")) is ApiError.Rejected)
    }

    @Test
    fun `a validation error reads the message out of FastAPI's list`() {
        val body = """{"detail":[{"type":"string_too_long","loc":["body","name"],"msg":"String should have at most 6 characters"}]}"""
        val r = ApiClient(Recorder(422, body)).addDevice("tok", "phone")
        assertEquals(ApiError.Rejected("String should have at most 6 characters"), error(r))
    }

    @Test
    fun `the config comes back as the text it was sent as`() {
        val t = Recorder(200, conf)
        assertEquals(conf, ok(ApiClient(t).config("tok", "abc")))
        assertEquals(listOf("GET /api/client/configs/abc/raw tok"), t.calls)
    }

    @Test
    fun `a device id that could walk the URL path is refused before any request`() {
        val never = Transport { _, _, _, _ -> fail("must not reach the network"); HttpReply(0, "") }
        assertTrue(error(ApiClient(never).config("tok", "x/../../me")) is ApiError.Rejected)
        assertTrue(error(ApiClient(never).config("tok", "")) is ApiError.Rejected)
    }

    // --- failures that are not the server's answer ---------------------------

    @Test
    fun `no network is its own error`() {
        val offline = Transport { _, _, _, _ -> throw IOException("unreachable") }
        assertTrue(error(ApiClient(offline).profile("tok")) is ApiError.Network)
    }

    @Test
    fun `a server failure keeps its status`() {
        assertEquals(ApiError.Server(502), error(ApiClient(Recorder(502, "<html>")).profile("tok")))
    }

    @Test
    fun `a success that does not match the contract is Malformed, not a crash`() {
        assertTrue(error(ApiClient(Recorder(200, "<html>")).devices("tok")) is ApiError.Malformed)
    }

    @Test
    fun `fields the server adds later do not break the app`() {
        val extended = profile.replace("\"ok\": true,", "\"ok\": true, \"new_field\": 1,")
        assertEquals("paid", ok(ApiClient(Recorder(200, extended)).profile("tok")).username)
    }
}
