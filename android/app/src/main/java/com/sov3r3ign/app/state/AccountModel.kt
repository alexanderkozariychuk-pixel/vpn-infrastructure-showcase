package com.sov3r3ign.app.state

import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.api.AppRelease
import com.sov3r3ign.app.api.Device
import com.sov3r3ign.app.api.DeviceList
import com.sov3r3ign.app.api.Profile
import com.sov3r3ign.app.api.TrialOffer
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.ui.Action
import com.sov3r3ign.app.ui.DEVICE_GONE
import com.sov3r3ign.app.ui.LETTER_SENT
import com.sov3r3ign.app.ui.describe
import com.sov3r3ign.app.ui.validateDeviceName
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withContext
import java.time.Instant

/**
 * The tunnel as the account needs it. VpnTunnel is the real one; tests use a
 * fake that records the order of calls, which is the point of most of them.
 */
interface TunnelControl {
    fun isUp(): Boolean

    /** Starts the tunnel on [conf], or moves a running one onto it. Failures are swallowed. */
    fun up(conf: String)

    /** Failures are swallowed: nothing here can do better than carry on. */
    fun down()
}

/** What the account screens show. One value, replaced whole on every change. */
data class AccountUi(
    val profile: Profile? = null,
    val devices: DeviceList? = null,
    val selected: Session.Selected? = null,
    val busy: Boolean = false,
    val error: String? = null,
    val notice: String? = null,
    /** The site's trial offer; asked only of an account that could take one. */
    val trialOffer: TrialOffer? = null,
    /** The APK the site offers; null until asked, or when the site did not answer. */
    val release: AppRelease? = null,
    /** Set once the session has ended: the app goes to sign-in, with this line if any. */
    val signedOut: SignedOut? = null,
)

data class SignedOut(val notice: String?)

/**
 * The account's state and the order of operations around it, out of the
 * screens, so that several pages can share one copy and the order can be
 * tested on a laptop. Every order below was found the hard way:
 *
 * - sign-out brings the tunnel down before the key is wiped, or a shared
 *   phone stays connected on an account it left;
 * - removing this phone's own device brings the tunnel down first — the
 *   server takes the peer off the node before it answers, so a request sent
 *   through that tunnel loses its own answer;
 * - a device list without this phone's device means it was removed
 *   elsewhere: the session forgets it and the tunnel comes down (decided
 *   2026-09-30: without asking);
 * - choosing or adding a device while connected moves the tunnel onto it;
 * - an account without access is not asked for its list: the server answers
 *   it with 402, and the screen has nothing to show from it but the trial
 *   offer and the pay button.
 *
 * Blocking work runs on [io]; the methods are called from the UI's scope.
 */
class AccountModel(
    private val session: Session,
    private val tunnel: TunnelControl,
    private val io: CoroutineDispatcher = Dispatchers.IO,
    private val clock: () -> Instant = Instant::now,
) {
    private val state = MutableStateFlow(AccountUi())
    val ui: StateFlow<AccountUi> = state.asStateFlow()

    suspend fun load() {
        state.update { it.copy(error = null) }
        val had = withContext(io) { session.selected() }
        state.update { it.copy(selected = had) }
        when (val p = withContext(io) { session.profile() }) {
            is ApiResult.Ok -> state.update { it.copy(profile = p.value) }
            is ApiResult.Failed -> { failed(p.error, reload = false); return }
        }
        val profile = state.value.profile ?: return
        if (!profile.hasAccessAt(clock())) {
            state.update { it.copy(devices = null) }
            askTrialOffer(profile)
            return
        }
        when (val d = withContext(io) { session.devices() }) {
            is ApiResult.Ok -> {
                // The list may carry a new name for this phone's device, or
                // show it gone; then the session has already forgotten it.
                val now = withContext(io) { session.selected() }
                if (had != null && now == null) {
                    withContext(io) { tunnel.down() }
                    state.update { it.copy(notice = DEVICE_GONE) }
                }
                state.update { it.copy(devices = d.value, selected = now) }
            }
            is ApiResult.Failed -> {
                state.update { it.copy(devices = null) }
                failed(d.error, reload = false)
            }
        }
    }

    suspend fun use(device: Device) = work {
        when (val r = withContext(io) { session.select(device) }) {
            is ApiResult.Ok -> {
                // A profile is chosen: "this phone's profile was removed" is over.
                state.update { it.copy(notice = null) }
                refreshSelected()
                followSelection()
            }
            is ApiResult.Failed -> failed(r.error)
        }
    }

    /** Returns a problem with the name for the form to show, or null once sent. */
    suspend fun add(name: String): String? {
        validateDeviceName(name)?.let { return it }
        var added = false
        work {
            when (val r = withContext(io) { session.addDevice(name) }) {
                is ApiResult.Ok -> {
                    added = true
                    // A device added from this phone is meant for this phone.
                    when (val s = withContext(io) { session.select(r.value) }) {
                        is ApiResult.Ok -> {
                            state.update { it.copy(notice = null) }
                            followSelection()
                        }
                        is ApiResult.Failed -> failed(s.error)
                    }
                }
                is ApiResult.Failed -> failed(r.error)
            }
        }
        if (added && state.value.signedOut == null) load()
        return null
    }

    /** Returns a problem with the name for the dialog to show, or null once sent. */
    suspend fun rename(device: Device, name: String): String? {
        validateDeviceName(name)?.let { return it }
        var ok = false
        work {
            when (val r = withContext(io) { session.renameDevice(device.id, name) }) {
                is ApiResult.Ok -> { refreshSelected(); ok = true }
                is ApiResult.Failed -> failed(r.error)
            }
        }
        if (ok) load()
        return null
    }

    suspend fun delete(device: Device) {
        val onThisPhone = state.value.selected?.id == device.id
        state.update { it.copy(notice = null) }
        var ok = false
        work {
            val r = withContext(io) {
                // Down first, then the request over the phone's own network.
                // If removal fails the tunnel stays down and the key stays:
                // the customer can reconnect.
                if (onThisPhone) tunnel.down()
                session.deleteDevice(device.id)
            }
            when (r) {
                is ApiResult.Ok -> { refreshSelected(); ok = true }
                is ApiResult.Failed -> failed(r.error, Action.DELETE)
            }
        }
        if (ok) load()
    }

    /**
     * Starts the trial and makes its device this phone's, as an added device
     * is. The profile is read again either way: on a refusal such as
     * "already running" the screen was out of date.
     */
    suspend fun startTrial() {
        var reload = false
        work {
            when (val r = withContext(io) { session.startTrial() }) {
                is ApiResult.Ok -> {
                    reload = true
                    when (val s = withContext(io) { session.select(r.value) }) {
                        is ApiResult.Ok -> {
                            state.update { it.copy(notice = null) }
                            followSelection()
                        }
                        is ApiResult.Failed -> failed(s.error, Action.TRIAL)
                    }
                }
                is ApiResult.Failed -> {
                    failed(r.error, Action.TRIAL)
                    reload = r.error is ApiError.Conflict
                }
            }
        }
        if (reload && state.value.signedOut == null) {
            val kept = state.value.error
            load()
            state.update { it.copy(error = kept ?: it.error) }
        }
    }

    /** Sends the confirmation letter again; if the address is confirmed already, reads the profile anew. */
    suspend fun resendConfirmation() {
        var confirmed = false
        state.update { it.copy(notice = null) }
        work {
            when (val r = withContext(io) { session.resendVerification() }) {
                is ApiResult.Ok -> if (r.value) confirmed = true else state.update { it.copy(notice = LETTER_SENT) }
                is ApiResult.Failed -> failed(r.error, Action.RESEND)
            }
        }
        if (confirmed) load()
    }

    /**
     * Asks the site once which APK it offers. Silent on failure: the check is
     * a courtesy and must never stand between the customer and connecting.
     */
    suspend fun checkRelease() {
        if (state.value.release != null) return
        val r = withContext(io) { session.latestRelease() }
        if (r is ApiResult.Ok) state.update { it.copy(release = r.value) }
    }

    suspend fun signOut() {
        withContext(io) {
            // Down first: wiping the key under a running tunnel would leave
            // the phone connected on an account it signed out of.
            tunnel.down()
            session.signOut()
        }
        state.update { it.copy(signedOut = SignedOut(null)) }
    }

    fun dismissNotice() = state.update { it.copy(notice = null) }

    /**
     * The offer matters only in the two states that can lead to a trial, and
     * it does not change within a session: asked once. A failure leaves it
     * unasked, so the next load tries again.
     */
    private suspend fun askTrialOffer(profile: Profile) {
        if (state.value.trialOffer != null) return
        if (profile.trial?.state != "available" && profile.trial?.state != "needs_verify") return
        val r = withContext(io) { session.trialOffer() }
        if (r is ApiResult.Ok) state.update { it.copy(trialOffer = r.value) }
    }

    private suspend fun refreshSelected() {
        val s = withContext(io) { session.selected() }
        state.update { it.copy(selected = s) }
    }

    /** A running tunnel is on the previous device's key: move it onto the one just chosen. */
    private suspend fun followSelection() {
        if (!tunnel.isUp()) return
        withContext(io) { session.storedConfig()?.let { tunnel.up(it) } }
    }

    private suspend fun work(block: suspend () -> Unit) {
        state.update { it.copy(busy = true, error = null) }
        try {
            block()
        } finally {
            state.update { it.copy(busy = false) }
        }
    }

    /**
     * Every call can find the token expired; that always ends at sign-in.
     * [reload] is off inside load() itself, so a 404 there cannot loop.
     */
    private suspend fun failed(e: ApiError, action: Action = Action.LOAD, reload: Boolean = true) {
        if (e == ApiError.Unauthorized) {
            state.update { it.copy(signedOut = SignedOut("Сессия истекла — войдите снова")) }
            return
        }
        state.update { it.copy(error = describe(e, action, tunnelUp = tunnel.isUp())) }
        // The device is gone from the account: the list on screen is stale.
        if (e == ApiError.NotFound && reload) {
            val kept = state.value.error
            load()
            state.update { it.copy(error = kept) }
        }
    }
}
