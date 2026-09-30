package com.sov3r3ign.app.ui.main

import android.app.Activity
import android.net.VpnService
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.tunnel.VpnTunnel
import com.sov3r3ign.app.ui.ConnectionStatus
import com.sov3r3ign.app.ui.Link
import com.sov3r3ign.app.ui.STOPPED_FROM_OUTSIDE
import com.sov3r3ign.app.ui.connectionStatus
import com.sov3r3ign.app.ui.tunnelFailure
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.amnezia.awg.backend.BackendException
import org.amnezia.awg.backend.Tunnel
import org.amnezia.awg.config.BadConfigException

/** The switch as the main screen sees it: what to say, and what one press does. */
class Connection(val status: ConnectionStatus, val error: String?, val press: () -> Unit)

/**
 * The tunnel's state, polled while it runs, and the one button. Starts from
 * the config stored for this phone — no network call, so it works with an
 * expired token and before the portal is reachable. Was ConnectionPanel.
 */
@Composable
fun rememberConnection(session: Session): Connection {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state by VpnTunnel.state.collectAsState()
    val up = state == Tunnel.State.UP
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var handshake by remember { mutableStateOf<Long?>(null) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis() / 1000) }
    var upSince by remember { mutableStateOf<Long?>(null) }

    fun reasonOf(e: Exception): String = when (e) {
        is BackendException -> e.reason.name
        is BadConfigException -> "BAD_CONFIG"
        else -> e.javaClass.simpleName
    }

    fun start(downFirst: Boolean = false) {
        busy = true
        error = null
        scope.launch {
            val conf = withContext(Dispatchers.IO) { session.storedConfig() }
            if (conf == null) {
                error = "Сначала выберите устройство"
            } else {
                try {
                    withContext(Dispatchers.IO) {
                        // A reconnect is a real one: down, then up, so the
                        // tunnel handshakes afresh on whatever network is there now.
                        if (downFirst) VpnTunnel.down(context)
                        VpnTunnel.up(context, conf)
                    }
                } catch (e: Exception) {
                    Log.e("sovrn-tunnel", "up failed", e)
                    error = tunnelFailure(reasonOf(e))
                }
            }
            busy = false
        }
    }

    fun stop() {
        busy = true
        error = null
        scope.launch {
            try {
                withContext(Dispatchers.IO) { VpnTunnel.down(context) }
            } catch (e: Exception) {
                Log.e("sovrn-tunnel", "down failed", e)
                error = "Не удалось выключить VPN (${e.javaClass.simpleName})"
            }
            busy = false
        }
    }

    // Android asks once whether this app may be a VPN; the backend refuses to start until it has.
    val consent = rememberLauncherForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        if (result.resultCode == Activity.RESULT_OK) start() else error = "Без разрешения Android не даст включить VPN"
    }

    // The screen may open while the tunnel is already running.
    LaunchedEffect(Unit) { withContext(Dispatchers.IO) { VpnTunnel.refresh(context) } }

    LaunchedEffect(up) {
        if (up) {
            upSince = System.currentTimeMillis() / 1000
        } else {
            upSince = null
            if (VpnTunnel.stoppedFromOutside) error = STOPPED_FROM_OUTSIDE
        }
        while (up) {
            handshake = withContext(Dispatchers.IO) { VpnTunnel.lastHandshake(context) }
            now = System.currentTimeMillis() / 1000
            delay(2000)
        }
        handshake = null
    }

    val status = connectionStatus(up, busy, handshake, now, upSince)
    val press: () -> Unit = {
        when (status.link) {
            Link.OFF -> {
                val intent = VpnService.prepare(context)
                if (intent != null) consent.launch(intent) else start()
            }
            Link.ON -> stop()
            Link.CONNECTING -> if (!busy) stop()
            Link.NO_ANSWER -> start(downFirst = true)
        }
    }
    return Connection(status, error, press)
}
