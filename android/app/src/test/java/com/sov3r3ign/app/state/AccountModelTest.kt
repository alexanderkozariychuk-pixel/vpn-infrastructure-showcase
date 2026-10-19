package com.sov3r3ign.app.state

import com.sov3r3ign.app.api.ApiClient
import com.sov3r3ign.app.api.Device
import com.sov3r3ign.app.api.HttpReply
import com.sov3r3ign.app.api.Transport
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.storage.Secrets
import com.sov3r3ign.app.ui.DEVICE_GONE
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The orders that used to live in the screen and were checked only by hand.
 * The transport, the tunnel and the store write to one log, so a test reads
 * what happened in the order it happened.
 */
class AccountModelTest {

    private val log = mutableListOf<String>()

    private inner class Store : Secrets {
        val map = HashMap<String, String>()
        override fun put(name: String, value: String) { map[name] = value }
        override fun get(name: String): String? = map[name]
        override fun remove(name: String) { map.remove(name) }
        override fun clear() { log += "wipe"; map.clear() }
    }

    private inner class Server(vararg replies: HttpReply) : Transport {
        private val queue = ArrayDeque(replies.toList())
        override fun send(method: String, path: String, token: String?, jsonBody: String?): HttpReply {
            log += "$method $path"
            return queue.removeFirstOrNull() ?: throw AssertionError("unexpected call: $method $path")
        }
    }

    private inner class Tunnel(var running: Boolean) : TunnelControl {
        override fun isUp() = running
        override fun up(conf: String) { log += "tunnel up ${conf.lines().first()}"; running = true }
        override fun down() { log += "tunnel down"; running = false }
    }

    private val phoneId = "50ad16ee-a71d-40e1-9ee7-e1036389a1cb"
    private val lapId = "bddb174e-f00a-4d37-89a3-7a9d7b5dd227"
    private val phone = Device(phoneId, "phone")
    private val lap = Device(lapId, "laptop")

    private val profile = HttpReply(200, """{"ok":true,"username":"paid","is_subscribed":true,"plan":"basic-1m","active":true,"subscribed_until":"2026-10-12T09:26:42"}""")
    private fun list(vararg d: Device) = HttpReply(200,
        """{"ok":true,"plan":"basic-1m","limit":2,"used":${d.size},"configs":[""" +
            d.joinToString(",") { """{"id":"${it.id}","name":"${it.name}"}""" } + "]}")
    private val lapConf = HttpReply(200, "[Interface] laptop\nPrivateKey = <K>\n")

    /** Signed in, this phone on its own device, the tunnel as given. */
    private fun model(up: Boolean, vararg replies: HttpReply): Triple<AccountModel, Store, Tunnel> {
        val store = Store().apply {
            put("token", "T1"); put("conf", "[Interface] phone\nPrivateKey = <K>\n")
            put("device_name", "phone"); put("device_id", phoneId)
        }
        val tunnel = Tunnel(up)
        return Triple(AccountModel(Session(ApiClient(Server(*replies)), store), tunnel, Dispatchers.Unconfined), store, tunnel)
    }

    @Test
    fun `signing out brings the tunnel down before the key is wiped`() = runBlocking {
        val (m, store, _) = model(up = true)
        m.signOut()
        assertEquals(listOf("tunnel down", "wipe"), log)
        assertTrue(store.map.isEmpty())
        assertEquals(SignedOut(null), m.ui.value.signedOut)
    }

    @Test
    fun `removing this phone's own device takes the tunnel down before the request`() = runBlocking {
        val (m, store, _) = model(up = true, profile, list(phone, lap),
            HttpReply(200, """{"ok":true,"removed":"$phoneId"}"""), profile, list(lap))
        m.load(); log.clear()
        m.delete(phone)
        assertEquals("tunnel down", log[0])
        assertEquals("DELETE /api/client/configs/$phoneId", log[1])
        assertNull(m.ui.value.selected)
        assertNull(store.map["conf"])
    }

    @Test
    fun `a refused removal leaves the key, so the phone can reconnect`() = runBlocking {
        val (m, store, tunnel) = model(up = true, profile, list(phone, lap),
            HttpReply(503, """{"detail":"Could not remove the device"}"""))
        m.load()
        m.delete(phone)
        assertFalse(tunnel.running)
        assertEquals(phoneId, store.map["device_id"])
        assertTrue(m.ui.value.error!!.contains("503"))
    }

    @Test
    fun `removing another device leaves the tunnel alone`() = runBlocking {
        val (m, _, tunnel) = model(up = true, profile, list(phone, lap),
            HttpReply(200, """{"ok":true,"removed":"$lapId"}"""), profile, list(phone))
        m.load(); log.clear()
        m.delete(lap)
        assertFalse(log.contains("tunnel down"))
        assertTrue(tunnel.running)
        assertEquals(phoneId, m.ui.value.selected?.id)
    }

    @Test
    fun `a device removed elsewhere brings the tunnel down and says so`() = runBlocking {
        val (m, store, tunnel) = model(up = true, profile, list(lap))
        m.load()
        assertFalse(tunnel.running)
        assertNull(m.ui.value.selected)
        assertNull(store.map["conf"])
        assertEquals(DEVICE_GONE, m.ui.value.notice)
    }

    @Test
    fun `choosing another profile puts the removal notice away`() = runBlocking {
        val (m, _, _) = model(up = true, profile, list(lap), lapConf)
        m.load()
        assertEquals(DEVICE_GONE, m.ui.value.notice)
        m.use(lap)
        assertNull(m.ui.value.notice)
    }

    @Test
    fun `a failed list forgets nothing and leaves the tunnel up`() = runBlocking {
        val (m, _, tunnel) = model(up = true, profile, HttpReply(502, "<html>"))
        m.load()
        assertTrue(tunnel.running)
        assertEquals(phoneId, m.ui.value.selected?.id)
    }

    @Test
    fun `choosing another device while connected moves the tunnel onto it`() = runBlocking {
        val (m, _, _) = model(up = true, profile, list(phone, lap), lapConf)
        m.load(); log.clear()
        m.use(lap)
        assertEquals(listOf("GET /api/client/configs/$lapId/raw", "tunnel up [Interface] laptop"), log)
        assertEquals(lapId, m.ui.value.selected?.id)
    }

    @Test
    fun `choosing a device while disconnected does not start the tunnel`() = runBlocking {
        val (m, _, tunnel) = model(up = false, profile, list(phone, lap), lapConf)
        m.load()
        m.use(lap)
        assertFalse(tunnel.running)
    }

    @Test
    fun `an expired token ends at sign-in, with the reason`() = runBlocking {
        val (m, _, _) = model(up = false, HttpReply(401, """{"detail":"Invalid or expired token"}"""))
        m.load()
        assertEquals(SignedOut("Сессия истекла — войдите снова"), m.ui.value.signedOut)
    }

    @Test
    fun `a device gone from the account reloads the list and keeps the message`() = runBlocking {
        val (m, _, _) = model(up = false, profile, list(phone, lap),
            HttpReply(404, """{"detail":"Config not found"}"""), profile, list(phone))
        m.load()
        m.rename(lap, "lap2")
        assertEquals(listOf(phone), m.ui.value.devices!!.configs.map { Device(it.id, it.name) })
        assertTrue(m.ui.value.error!!.startsWith("Профиль не найден"))
    }

    @Test
    fun `a name the portal would not take is refused before any request`() = runBlocking {
        val (m, _, _) = model(up = false)
        assertEquals("Только латинские буквы, цифры, - и _", m.rename(phone, "тел"))
        assertEquals("Только латинские буквы, цифры, - и _", m.add("тел"))
        assertTrue(log.isEmpty())
    }

    @Test
    fun `a failed add does not reload the list`() = runBlocking {
        val (m, _, _) = model(up = false, profile, list(phone, lap),
            HttpReply(409, """{"detail":"Plan allows 2 device(s); remove one first"}"""))
        m.load(); log.clear()
        m.add("tab")
        assertEquals(listOf("POST /api/client/configs"), log)
        assertFalse(m.ui.value.busy)
    }

    // ── the trial ────────────────────────────────────────────────────────────

    private fun noAccess(state: String) = HttpReply(200,
        """{"ok":true,"username":"new","is_subscribed":false,"plan":null,"active":false,"subscribed_until":null,""" +
            """"email_verified":${state != "needs_verify"},"trial":{"state":"$state","until":null}}""")
    private val trialProfile = HttpReply(200,
        """{"ok":true,"username":"new","is_subscribed":false,"plan":null,"active":false,"subscribed_until":null,""" +
            """"email_verified":true,"trial":{"state":"active","until":"2026-10-22T18:00:00+00:00"}}""")
    private val offer = HttpReply(200, """{"enabled":true,"days":3}""")
    private val trialId = "7f0c2b8e-5b1d-4f4e-9a57-0c8d2f1e6a11"

    /** Signed in, nothing chosen yet: a new customer. */
    private fun fresh(vararg replies: HttpReply): Pair<AccountModel, Store> {
        val store = Store().apply { put("token", "T1") }
        return AccountModel(Session(ApiClient(Server(*replies)), store), Tunnel(false), Dispatchers.Unconfined) to store
    }

    @Test
    fun `an account without access is not asked for its list, and is shown the offer`() = runBlocking {
        val (m, _) = fresh(noAccess("available"), offer)
        m.load()
        assertEquals(listOf("GET /api/client/me", "GET /api/public/trial"), log)
        assertNull(m.ui.value.devices)
        assertNull(m.ui.value.error)
        assertEquals(3, m.ui.value.trialOffer?.days)
    }

    @Test
    fun `the offer is asked once, and not at all when the trial was used`() = runBlocking {
        val (m, _) = fresh(noAccess("available"), offer, noAccess("available"))
        m.load(); m.load()
        assertEquals(1, log.count { it == "GET /api/public/trial" })
        val (used, _) = fresh(noAccess("used"))
        log.clear()
        used.load()
        assertEquals(listOf("GET /api/client/me"), log)
    }

    @Test
    fun `a started trial becomes this phone's profile`() = runBlocking {
        val (m, store) = fresh(noAccess("available"), offer,
            HttpReply(201, """{"ok":true,"trial_until":"2026-10-22T18:00:00+00:00","config":{"id":"$trialId","name":"trial","kind":"trial"}}"""),
            HttpReply(200, "[Interface] trial\nPrivateKey = <K>\n"),
            trialProfile,
            HttpReply(200, """{"ok":true,"plan":null,"limit":1,"used":1,"configs":[{"id":"$trialId","name":"trial","kind":"trial"}]}"""))
        m.load(); log.clear()
        m.startTrial()
        assertEquals(listOf("POST /api/client/trial", "GET /api/client/configs/$trialId/raw",
            "GET /api/client/me", "GET /api/client/configs"), log)
        assertEquals(trialId, store.map["device_id"])
        assertEquals(trialId, m.ui.value.selected?.id)
        assertTrue(m.ui.value.devices!!.configs.single().isTrial)
        assertNull(m.ui.value.error)
    }

    @Test
    fun `a trial already running reloads the profile and keeps the reason`() = runBlocking {
        val (m, _) = fresh(noAccess("available"), offer,
            HttpReply(409, """{"detail":"trial_active"}"""),
            trialProfile, HttpReply(200, """{"ok":true,"plan":null,"limit":1,"used":0,"configs":[]}"""))
        m.load()
        m.startTrial()
        assertEquals("Пробный период уже идёт.", m.ui.value.error)
        assertEquals("active", m.ui.value.profile?.trial?.state)
    }

    @Test
    fun `no free trial places is said as such, with nothing stored`() = runBlocking {
        val (m, store) = fresh(noAccess("available"), offer, HttpReply(503, """{"detail":"trial_busy"}"""))
        m.load()
        m.startTrial()
        assertEquals("Сейчас нет свободных мест для пробного периода. Попробуйте позже.", m.ui.value.error)
        assertNull(store.map["device_id"])
    }

    @Test
    fun `the letter goes again, and a confirmed address reloads instead`() = runBlocking {
        val (m, _) = fresh(noAccess("needs_verify"), offer,
            HttpReply(200, """{"ok":true,"already_verified":false}"""))
        m.load()
        m.resendConfirmation()
        assertEquals(com.sov3r3ign.app.ui.LETTER_SENT, m.ui.value.notice)

        val (c, _) = fresh(noAccess("needs_verify"), offer,
            HttpReply(200, """{"ok":true,"already_verified":true}"""), noAccess("available"))
        c.load(); log.clear()
        c.resendConfirmation()
        assertEquals(listOf("POST /api/auth/resend-verification", "GET /api/client/me"), log)
        assertNull(c.ui.value.notice)
    }

    // ── the update check ─────────────────────────────────────────────────────

    @Test
    fun `the site's release is asked once, and a failure is silent`() = runBlocking {
        val (m, _) = fresh(HttpReply(502, "<html>"),
            HttpReply(200, """{"available":true,"version_code":2,"version_name":"1.1","size":1,"sha256":"ab","url":"/download/android"}"""))
        m.checkRelease()
        assertNull(m.ui.value.release)
        assertNull(m.ui.value.error)
        m.checkRelease(); m.checkRelease()
        assertEquals(2, m.ui.value.release?.versionCode)
        assertEquals(2, log.count { it == "GET /api/public/android" })
    }
}
