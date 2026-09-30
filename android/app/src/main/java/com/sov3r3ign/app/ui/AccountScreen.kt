package com.sov3r3ign.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.api.Device
import com.sov3r3ign.app.api.DeviceList
import com.sov3r3ign.app.api.Profile
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.tunnel.VpnTunnel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.amnezia.awg.backend.Tunnel

/**
 * The account, its devices, and which of them this phone uses. Choosing a
 * device downloads its config into the encrypted store; the switch above the
 * list starts the tunnel from that stored copy.
 */
@Composable
fun AccountScreen(session: Session, onSignedOut: (notice: String?) -> Unit) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val uriHandler = LocalUriHandler.current
    var profile by remember { mutableStateOf<Profile?>(null) }
    var devices by remember { mutableStateOf<DeviceList?>(null) }
    var selected by remember { mutableStateOf<Session.Selected?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var newName by rememberSaveable { mutableStateOf("phone") }
    var reload by remember { mutableIntStateOf(0) }

    /** Every call can find the token expired; that always ends at sign-in. */
    fun failed(e: ApiError) {
        if (e == ApiError.Unauthorized) {
            onSignedOut("Сессия истекла — войдите снова")
        } else {
            error = describe(e, Action.LOAD)
        }
    }

    LaunchedEffect(reload) {
        error = null
        selected = withContext(Dispatchers.IO) { session.selected() }
        when (val p = withContext(Dispatchers.IO) { session.profile() }) {
            is ApiResult.Ok -> { profile = p.value }
            is ApiResult.Failed -> { failed(p.error); return@LaunchedEffect }
        }
        when (val d = withContext(Dispatchers.IO) { session.devices() }) {
            is ApiResult.Ok -> { devices = d.value }
            is ApiResult.Failed -> { devices = null; failed(d.error) }
        }
    }

    /**
     * A running tunnel is on the previous device's key: move it onto the one
     * just chosen, or the phone keeps using a config the customer left.
     */
    suspend fun followSelection() {
        if (VpnTunnel.state.value != Tunnel.State.UP) return
        withContext(Dispatchers.IO) {
            session.storedConfig()?.let { conf -> runCatching { VpnTunnel.up(context, conf) } }
        }
    }

    fun use(device: Device) {
        busy = true
        error = null
        scope.launch {
            val r = withContext(Dispatchers.IO) { session.select(device) }
            busy = false
            when (r) {
                is ApiResult.Ok -> {
                    selected = withContext(Dispatchers.IO) { session.selected() }
                    followSelection()
                }
                is ApiResult.Failed -> failed(r.error)
            }
        }
    }

    fun add() {
        val problem = validateDeviceName(newName)
        if (problem != null) {
            error = problem
            return
        }
        busy = true
        error = null
        scope.launch {
            when (val r = withContext(Dispatchers.IO) { session.addDevice(newName) }) {
                is ApiResult.Ok -> {
                    // A device added from this phone is meant for this phone.
                    when (val s = withContext(Dispatchers.IO) { session.select(r.value) }) {
                        is ApiResult.Ok -> followSelection()
                        is ApiResult.Failed -> failed(s.error)
                    }
                    busy = false
                    reload++
                }
                is ApiResult.Failed -> {
                    busy = false
                    failed(r.error)
                }
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Sovereign", style = MaterialTheme.typography.headlineMedium)

        val p = profile
        if (p != null) {
            Text("Вы вошли как ${p.username}")
            planLine(p)?.let { Text(it) }
            Text(subscriptionLine(p))
            expiryWarning(p)?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            if (needsPayment(p)) {
                // No browser on the phone is rare, but it must not crash the screen.
                OutlinedButton(onClick = { runCatching { uriHandler.openUri(PAYMENT_URL) } }) {
                    Text("Оплатить на сайте")
                }
            }
        } else if (error == null) {
            CircularProgressIndicator()
        }

        val here = selected
        if (here != null) {
            HorizontalDivider()
            Text("На этом телефоне: ${here.name}")
            ConnectionPanel(session)
        }

        val list = devices
        if (list != null) {
            HorizontalDivider()
            Text(
                "Устройства — ${list.used} из ${list.limit}",
                style = MaterialTheme.typography.titleMedium,
            )
            if (list.configs.isEmpty()) {
                Text("Пока ни одного. Добавьте этот телефон ниже.")
            }
            list.configs.forEach { d ->
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(d.name, style = MaterialTheme.typography.bodyLarge)
                    if (here?.id == d.id) {
                        Text("выбрано", color = MaterialTheme.colorScheme.primary)
                    } else {
                        TextButton(onClick = { use(d) }, enabled = !busy) {
                            Text("Использовать здесь")
                        }
                    }
                }
            }
            Text(ONE_DEVICE_PER_CONFIG, style = MaterialTheme.typography.bodySmall)

            if (list.hasRoom) {
                HorizontalDivider()
                OutlinedTextField(
                    value = newName,
                    onValueChange = { newName = it },
                    label = { Text("Название: до 6 символов, латиница и цифры") },
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
                Button(onClick = { add() }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                    Text("Добавить этот телефон")
                }
            }
        }

        if (busy) CircularProgressIndicator()

        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
            TextButton(onClick = { reload++ }, enabled = !busy) { Text("Повторить") }
        }

        HorizontalDivider()
        OutlinedButton(onClick = {
            scope.launch {
                withContext(Dispatchers.IO) {
                    // Down first: wiping the key under a running tunnel would
                    // leave the phone connected on an account it signed out of.
                    runCatching { VpnTunnel.down(context) }
                    session.signOut()
                }
                onSignedOut(null)
            }
        }) { Text("Выйти") }
    }
}
