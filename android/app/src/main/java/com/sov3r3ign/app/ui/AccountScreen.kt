package com.sov3r3ign.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.unit.dp
import com.sov3r3ign.app.api.Device
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.state.AccountModel
import kotlinx.coroutines.launch

/**
 * The account, its devices, and which of them this phone uses. The screen
 * only shows [model]'s state and passes taps on; the order of operations —
 * what happens to the tunnel when — lives in AccountModel, where it is tested.
 */
@Composable
fun AccountScreen(session: Session, model: AccountModel, onSignedOut: (notice: String?) -> Unit) {
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    val ui by model.ui.collectAsState()
    val profile = ui.profile
    val devices = ui.devices
    val selected = ui.selected
    val busy = ui.busy
    val error = ui.error
    val notice = ui.notice
    var newName by rememberSaveable { mutableStateOf("phone") }
    var renaming by remember { mutableStateOf<Device?>(null) }
    var renameText by rememberSaveable { mutableStateOf("") }
    var renameError by remember { mutableStateOf<String?>(null) }
    var deleting by remember { mutableStateOf<Device?>(null) }
    var addError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) { model.load() }
    LaunchedEffect(ui.signedOut) { ui.signedOut?.let { onSignedOut(it.notice) } }

    fun use(device: Device) { scope.launch { model.use(device) } }

    fun rename() {
        val device = renaming ?: return
        scope.launch {
            val problem = model.rename(device, renameText)
            if (problem != null) renameError = problem else renaming = null
        }
    }

    fun delete(device: Device) {
        scope.launch {
            model.delete(device)
            deleting = null
        }
    }

    fun add() {
        scope.launch { addError = model.add(newName) }
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
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(
                            onClick = {
                                renaming = d
                                renameText = d.name
                                renameError = null
                            },
                            enabled = !busy,
                        ) { Text("Переименовать") }
                        TextButton(onClick = { deleting = d }, enabled = !busy) {
                            Text("Удалить", color = MaterialTheme.colorScheme.error)
                        }
                        if (here?.id == d.id) {
                            Text("выбрано", color = MaterialTheme.colorScheme.primary)
                        } else {
                            TextButton(onClick = { use(d) }, enabled = !busy) {
                                Text("Использовать здесь")
                            }
                        }
                    }
                }
            }
            Text(ONE_DEVICE_PER_CONFIG, style = MaterialTheme.typography.bodySmall)

            if (list.hasRoom) {
                HorizontalDivider()
                OutlinedTextField(
                    value = newName,
                    onValueChange = { newName = it; addError = null },
                    label = { Text("Название: до 6 символов, латиница и цифры") },
                    singleLine = true,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
                addError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                Button(onClick = { add() }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
                    Text("Добавить этот телефон")
                }
            }
        }

        if (busy) CircularProgressIndicator()

        notice?.let { Text(it, color = MaterialTheme.colorScheme.primary) }

        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
            TextButton(onClick = { scope.launch { model.load() } }, enabled = !busy) { Text("Повторить") }
        }

        deleting?.let { d ->
            AlertDialog(
                onDismissRequest = { if (!busy) deleting = null },
                title = { Text("Удалить «${d.name}»?") },
                text = { Text(deleteQuestion(d.name, onThisPhone = selected?.id == d.id)) },
                confirmButton = {
                    TextButton(onClick = { delete(d) }, enabled = !busy) {
                        Text("Удалить", color = MaterialTheme.colorScheme.error)
                    }
                },
                dismissButton = {
                    TextButton(onClick = { deleting = null }, enabled = !busy) { Text("Отмена") }
                },
            )
        }

        renaming?.let { d ->
            AlertDialog(
                onDismissRequest = { if (!busy) renaming = null },
                title = { Text("Переименовать «${d.name}»") },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(
                            value = renameText,
                            onValueChange = { renameText = it; renameError = null },
                            label = { Text("До 6 символов, латиница и цифры") },
                            singleLine = true,
                            enabled = !busy,
                        )
                        renameError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
                        Text(
                            "Меняется только название. Подключение и ключ остаются прежними.",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                },
                confirmButton = {
                    TextButton(onClick = { rename() }, enabled = !busy) { Text("Сохранить") }
                },
                dismissButton = {
                    TextButton(onClick = { renaming = null }, enabled = !busy) { Text("Отмена") }
                },
            )
        }

        HorizontalDivider()
        OutlinedButton(onClick = { scope.launch { model.signOut() } }) { Text("Выйти") }
    }
}
