package com.sov3r3ign.app.ui

import android.app.Activity
import android.net.VpnService
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.tunnel.VpnTunnel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.amnezia.awg.backend.BackendException
import org.amnezia.awg.backend.Tunnel
import org.amnezia.awg.config.BadConfigException

/**
 * The switch. Starts the tunnel from the config stored for this phone — no
 * network call, so it works with an expired token and before the portal is
 * reachable.
 */
@Composable
fun ConnectionPanel(session: Session) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state by VpnTunnel.state.collectAsState()
    val up = state == Tunnel.State.UP
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var handshake by remember { mutableStateOf<Long?>(null) }
    var now by remember { mutableLongStateOf(System.currentTimeMillis() / 1000) }
    var upSince by remember { mutableStateOf<Long?>(null) }

    fun connect() {
        busy = true
        error = null
        scope.launch {
            val conf = withContext(Dispatchers.IO) { session.storedConfig() }
            if (conf == null) {
                error = "Сначала выберите устройство"
            } else {
                try {
                    withContext(Dispatchers.IO) { VpnTunnel.up(context, conf) }
                } catch (e: Exception) {
                    Log.e("sovrn-tunnel", "up failed", e)
                    error = tunnelFailure(
                        when (e) {
                            is BackendException -> e.reason.name
                            is BadConfigException -> "BAD_CONFIG"
                            else -> e.javaClass.simpleName
                        }
                    )
                }
            }
            busy = false
        }
    }

    fun disconnect() {
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

    // Android asks once whether this app may be a VPN; the backend refuses
    // to start until it has.
    val consent = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            connect()
        } else {
            error = "Без разрешения Android не даст включить VPN"
        }
    }

    // The screen may open while the tunnel is already running.
    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) { VpnTunnel.refresh(context) }
    }

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

    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            connectionLine(up, busy, handshake, now, upSince),
            style = MaterialTheme.typography.titleMedium,
        )
        if (up) {
            OutlinedButton(
                onClick = { disconnect() },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Отключить") }
        } else {
            Button(
                onClick = {
                    val intent = VpnService.prepare(context)
                    if (intent != null) consent.launch(intent) else connect()
                },
                enabled = !busy,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("Подключить") }
        }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    }
}
