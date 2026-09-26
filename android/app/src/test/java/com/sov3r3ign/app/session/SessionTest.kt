package com.sov3r3ign.app.session

import com.sov3r3ign.app.api.ApiClient
import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.api.HttpReply
import com.sov3r3ign.app.api.Transport
import com.sov3r3ign.app.storage.Secrets
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SessionTest {

    private class MapSecrets : Secrets {
        val map = HashMap<String, String>()
        override fun put(name: String, value: String) { map[name] = value }
        override fun get(name: String): String? = map[name]
        override fun remove(name: String) { map.remove(name) }
        override fun clear() = map.clear()
    }

    /** Answers in order, and remembers what was asked. */
    private class Script(vararg replies: HttpReply) : Transport {
        private val queue = ArrayDeque(replies.toList())
        val calls = mutableListOf<String>()
        override fun send(method: String, path: String, token: String?, jsonBody: String?): HttpReply {
            calls += "$method $path"
            return queue.removeFirstOrNull() ?: throw AssertionError("unexpected call: $method $path")
        }
    }

    private val token = HttpReply(200, """{"access_token":"T1","token_type":"bearer","role":"client"}""")
    private val created = HttpReply(201, """{"id":"u","username":"new","email":"n@x.test","is_active":true,"is_subscribed":false,"peer_ip":null}""")
    private val profile = HttpReply(200, """{"ok":true,"username":"paid","email":"p@x.test","is_subscribed":true,"peer_ip":null,"subscribed_until":"2026-10-12T09:26:42.848714"}""")

    @Test
    fun `signing in keeps the token and never the password`() {
        val secrets = MapSecrets()
        val s = Session(ApiClient(Script(token)), secrets)
        assertTrue(s.signIn("paid", "secret") is ApiResult.Ok)
        assertEquals(mapOf("token" to "T1"), secrets.map)
        assertTrue(s.isSignedIn)
    }

    @Test
    fun `a wrong password stores nothing`() {
        val secrets = MapSecrets()
        val s = Session(ApiClient(Script(HttpReply(401, """{"detail":"Invalid credentials"}"""))), secrets)
        assertEquals(ApiResult.Failed(ApiError.Unauthorized), s.signIn("paid", "wrong"))
        assertTrue(secrets.map.isEmpty())
        assertFalse(s.isSignedIn)
    }

    @Test
    fun `registration signs in straight after, with the same details`() {
        val script = Script(created, token)
        val secrets = MapSecrets()
        assertTrue(Session(ApiClient(script), secrets).register(" new ", "n@x.test", "longenough") is ApiResult.Ok)
        assertEquals(listOf("POST /api/client/register", "POST /api/auth/token"), script.calls)
        assertEquals("T1", secrets.map["token"])
    }

    @Test
    fun `a taken name stops before any sign-in`() {
        val script = Script(HttpReply(409, """{"detail":"Username 'new' already exists"}"""))
        val r = Session(ApiClient(script), MapSecrets()).register("new", "n@x.test", "longenough")
        assertTrue(r is ApiResult.Failed)
        assertEquals(listOf("POST /api/client/register"), script.calls)
    }

    @Test
    fun `without a token the profile is Unauthorized and nothing is sent`() {
        val script = Script()
        assertEquals(ApiResult.Failed(ApiError.Unauthorized), Session(ApiClient(script), MapSecrets()).profile())
        assertTrue(script.calls.isEmpty())
    }

    @Test
    fun `an expired token is forgotten, so the app shows sign-in`() {
        val secrets = MapSecrets().apply { put("token", "OLD") }
        val s = Session(ApiClient(Script(HttpReply(401, """{"detail":"Invalid or expired token"}"""))), secrets)
        assertEquals(ApiResult.Failed(ApiError.Unauthorized), s.profile())
        assertNull(secrets.map["token"])
        assertFalse(s.isSignedIn)
    }

    @Test
    fun `a server failure does not sign the customer out`() {
        val secrets = MapSecrets().apply { put("token", "T1") }
        val s = Session(ApiClient(Script(HttpReply(502, "<html>"))), secrets)
        assertEquals(ApiResult.Failed(ApiError.Server(502)), s.profile())
        assertEquals("T1", secrets.map["token"])
    }

    @Test
    fun `the profile is fetched with the stored token`() {
        val secrets = MapSecrets().apply { put("token", "T1") }
        val r = Session(ApiClient(Script(profile)), secrets).profile()
        assertEquals("paid", (r as ApiResult.Ok).value.username)
    }

    @Test
    fun `signing out leaves nothing`() {
        val secrets = MapSecrets().apply { put("token", "T1"); put("conf", "x") }
        Session(ApiClient(Script()), secrets).signOut()
        assertTrue(secrets.map.isEmpty())
    }
}
