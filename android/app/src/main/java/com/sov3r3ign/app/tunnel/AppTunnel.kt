package com.sov3r3ign.app.tunnel

import android.content.Context
import android.util.Log
import com.sov3r3ign.app.state.TunnelControl
import org.amnezia.awg.backend.Tunnel

/** The real tunnel behind AccountModel's TunnelControl. Blocking; the model calls it off the main thread. */
class AppTunnel(context: Context) : TunnelControl {
    private val context = context.applicationContext

    override fun isUp(): Boolean = VpnTunnel.state.value == Tunnel.State.UP

    override fun up(conf: String) {
        runCatching { VpnTunnel.up(context, conf) }.onFailure { Log.e("sovrn-tunnel", "up from the account failed", it) }
    }

    override fun down() {
        runCatching { VpnTunnel.down(context) }.onFailure { Log.e("sovrn-tunnel", "down from the account failed", it) }
    }
}
