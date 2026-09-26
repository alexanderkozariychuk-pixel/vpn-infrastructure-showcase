package com.sov3r3ign.app

import android.app.Activity
import android.content.Context
import android.net.VpnService
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.amnezia.awg.backend.GoBackend
import org.amnezia.awg.backend.Tunnel
import org.amnezia.awg.config.Config

private const val TAG = "sovrn-spike"

/*
 * Stage 0 spike (docs/android-app.md): bring one tunnel up from a config
 * bundled in assets. Throwaway by design — no login, no storage, one button.
 * It answers two questions: does the library, built the way we built it,
 * carry traffic on a real phone, and does the tunnel survive the screen
 * locking.
 */

/** The library calls back through this when the tunnel goes up or down. */
object SpikeTunnel : Tunnel {
    val state = MutableStateFlow(Tunnel.State.DOWN)

    override fun getName(): String = "sovrn"

    override fun onStateChange(newState: Tunnel.State) {
        Log.i(TAG, "state -> $newState")
        state.value = newState
    }
}

/**
 * One backend per process. It binds the VPN service; a second instance, for
 * example after the activity is recreated on rotation, would fight the first.
 */
object Backend {
    @Volatile private var instance: GoBackend? = null

    fun get(context: Context): GoBackend =
        instance ?: synchronized(this) {
            instance ?: GoBackend(context.applicationContext).also { instance = it }
        }
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(Modifier.fillMaxSize()) { SpikeScreen() }
            }
        }
    }
}

private fun handshakeAge(unixSeconds: Long?): String = when {
    unixSeconds == null -> "—"
    unixSeconds == 0L -> "none yet"
    unixSeconds < 0 -> "error $unixSeconds"
    else -> "${System.currentTimeMillis() / 1000 - unixSeconds} s ago"
}

@Composable
fun SpikeScreen() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val state by SpikeTunnel.state.collectAsState()
    var error by remember { mutableStateOf<String?>(null) }
    var handshake by remember { mutableStateOf<Long?>(null) }

    // setState blocks until the service is up, so it never runs on the main
    // thread: the screen would freeze for as long as the handshake takes.
    fun switchTo(up: Boolean) = scope.launch {
        error = null
        try {
            val result = withContext(Dispatchers.IO) {
                val backend = Backend.get(context)
                if (up) {
                    val config = context.assets.open("spike.conf").use { Config.parse(it) }
                    backend.setState(SpikeTunnel, Tunnel.State.UP, config)
                } else {
                    backend.setState(SpikeTunnel, Tunnel.State.DOWN, null)
                }
            }
            Log.i(TAG, "setState returned $result")
            SpikeTunnel.state.value = result
        } catch (e: Exception) {
            Log.e(TAG, "setState failed", e)
            error = "${e.javaClass.simpleName}: ${e.message}"
        }
    }

    // Android asks once whether this app may act as a VPN. Until the user
    // agrees, the backend refuses to bring anything up.
    val consent = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) switchTo(true)
        else error = "VPN permission refused"
    }

    // The library documents this as "seconds" and no more. Measured on a
    // Galaxy A71: it is Unix time of the last handshake, matching the
    // "Received handshake response" log line to the second. 0 means none yet,
    // negative values are errors.
    LaunchedEffect(state) {
        while (state == Tunnel.State.UP) {
            handshake = withContext(Dispatchers.IO) {
                runCatching { Backend.get(context).getLastHandshake(SpikeTunnel) }.getOrNull()
            }
            delay(2000)
        }
        handshake = null
    }

    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text("Sovereign — spike", style = MaterialTheme.typography.headlineSmall)
        Text("Tunnel: $state")
        Text("Last handshake: ${handshakeAge(handshake)}")
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button(onClick = {
            if (state == Tunnel.State.UP) {
                switchTo(false)
            } else {
                val intent = VpnService.prepare(context)
                if (intent != null) consent.launch(intent) else switchTo(true)
            }
        }) {
            Text(if (state == Tunnel.State.UP) "Disconnect" else "Connect")
        }
    }
}
