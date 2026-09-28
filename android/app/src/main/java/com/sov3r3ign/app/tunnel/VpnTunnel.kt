package com.sov3r3ign.app.tunnel

import android.content.Context
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.amnezia.awg.backend.GoBackend
import org.amnezia.awg.backend.Tunnel
import org.amnezia.awg.config.Config
import java.io.ByteArrayInputStream

private const val TAG = "sovrn-tunnel"

/**
 * The one tunnel this app runs, over the AmneziaWG library's GoBackend.
 * Came out of the stage-0 spike unchanged in substance; what changed is where
 * the config comes from — the encrypted store, not a file in the APK.
 *
 * One backend per process: it binds the VPN service, and a second instance
 * (after the activity is recreated on rotation, say) would fight the first.
 *
 * up() and down() block until the service answers. Call them off the main
 * thread.
 */
object VpnTunnel : Tunnel {

    private val mutableState = MutableStateFlow(Tunnel.State.DOWN)
    val state: StateFlow<Tunnel.State> = mutableState

    @Volatile
    private var backend: GoBackend? = null

    private fun backend(context: Context): GoBackend =
        backend ?: synchronized(this) {
            backend ?: GoBackend(context.applicationContext).also { backend = it }
        }

    // Fixed name: the library allows 15 characters, and the customer's device
    // name is not needed here.
    override fun getName(): String = "sovrn"

    /** The library calls this when the tunnel goes up or down, including when
     *  the system takes it down — another VPN app, or the switch in settings. */
    override fun onStateChange(newState: Tunnel.State) {
        Log.i(TAG, "state -> $newState")
        mutableState.value = newState
    }

    /** Brings the tunnel up with [conf], or moves a running one onto it. */
    @Throws(Exception::class)
    fun up(context: Context, conf: String) {
        val config = Config.parse(ByteArrayInputStream(conf.toByteArray(Charsets.UTF_8)))
        mutableState.value = backend(context).setState(this, Tunnel.State.UP, config)
    }

    @Throws(Exception::class)
    fun down(context: Context) {
        // Nothing was ever started in this process; nothing to stop, and no
        // reason to load the native library just to say so.
        val b = backend ?: return
        mutableState.value = b.setState(this, Tunnel.State.DOWN, null)
    }

    /** Unix seconds of the last handshake; 0 before the first; null if unknown. */
    fun lastHandshake(context: Context): Long? =
        runCatching { backend(context).getLastHandshake(this) }.getOrNull()

    /** Re-reads the real state, for a screen opened while the tunnel may be running. */
    fun refresh(context: Context) {
        val b = backend ?: return
        mutableState.value = runCatching { b.getState(this) }.getOrDefault(Tunnel.State.DOWN)
    }
}
