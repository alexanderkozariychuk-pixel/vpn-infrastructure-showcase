package com.sov3r3ign.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sov3r3ign.app.api.Device
import com.sov3r3ign.app.state.AccountModel
import com.sov3r3ign.app.ui.theme.JetBrainsMono
import com.sov3r3ign.app.ui.theme.Sov
import com.sov3r3ign.app.ui.theme.Unbounded
import kotlinx.coroutines.launch

/**
 * The account's profiles (the design canvas, row D): choose one for this
 * phone, add, and — behind «⋯», so nobody deletes one by a stray tap —
 * rename and remove. The screen shows [model]'s state and passes taps on;
 * what happens to the tunnel when lives in AccountModel, where it is tested.
 *
 * "Профиль" is what people read; the API and the code keep "device".
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DevicesScreen(model: AccountModel, onBack: () -> Unit) {
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    val ui by model.ui.collectAsState()
    val list = ui.devices
    val busy = ui.busy
    var newName by rememberSaveable { mutableStateOf("") }
    var addError by remember { mutableStateOf<String?>(null) }
    var acting by remember { mutableStateOf<Device?>(null) }

    LaunchedEffect(Unit) { model.load() }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp)
            .padding(bottom = 24.dp),
    ) {
        Row(Modifier.height(64.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = onBack, modifier = Modifier.heightIn(min = 48.dp)) {
                Text("‹ Назад", color = Sov.Accent, fontSize = 16.sp)
            }
        }
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Bottom,
        ) {
            Text("Профили", style = MaterialTheme.typography.titleLarge, color = Sov.TextBright)
            if (list != null) {
                Row(verticalAlignment = Alignment.Bottom) {
                    Text("${list.used} из ${list.limit}", fontFamily = JetBrainsMono, fontSize = 15.sp, color = Sov.TextBright)
                    Text(" в тарифе", fontSize = 15.sp, color = Sov.TextDim)
                }
            }
        }

        Spacer(Modifier.height(20.dp))
        if (list == null && ui.error == null) {
            Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
        }

        if (list != null) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                list.configs.forEach { d ->
                    ProfileCard(
                        name = d.name,
                        chosen = ui.selected?.id == d.id,
                        busy = busy,
                        onChoose = { scope.launch { model.use(d) } },
                        onMore = { acting = d },
                    )
                }
            }
            Spacer(Modifier.height(16.dp))
            if (list.hasRoom) {
                AddBlock(
                    name = newName,
                    error = addError,
                    busy = busy,
                    onName = { newName = it; addError = null },
                    onAdd = {
                        scope.launch {
                            val problem = model.add(newName)
                            addError = problem
                            if (problem == null && model.ui.value.error == null) newName = ""
                        }
                    },
                )
            } else {
                FullBlock(list.plan) { runCatching { uriHandler.openUri(PLANS_URL) } }
            }
        }

        Spacer(Modifier.height(16.dp))
        ui.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Sov.Yellow) }
        ui.error?.let {
            Text(it, style = MaterialTheme.typography.bodySmall, color = Sov.Red)
            TextButton(onClick = { scope.launch { model.load() } }, enabled = !busy) { Text("Повторить", color = Sov.Accent) }
        }
        Spacer(Modifier.height(24.dp))
        Text(ONE_DEVICE_PER_CONFIG, style = MaterialTheme.typography.bodySmall, color = Sov.TextDim)
    }

    acting?.let { d ->
        ModalBottomSheet(
            onDismissRequest = { if (!busy) acting = null },
            containerColor = Sov.Bg2,
            scrimColor = Sov.Bg.copy(alpha = 0.72f),
        ) {
            ActionsSheet(
                device = d,
                onThisPhone = ui.selected?.id == d.id,
                busy = busy,
                onRename = { name ->
                    scope.launch {
                        if (model.rename(d, name) == null) acting = null
                    }
                },
                onDelete = {
                    scope.launch {
                        model.delete(d)
                        acting = null
                    }
                },
                onCancel = { acting = null },
            )
        }
    }
}

@Composable
private fun ProfileCard(name: String, chosen: Boolean, busy: Boolean, onChoose: () -> Unit, onMore: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(Sov.Bg2)
            .border(BorderStroke(1.dp, if (chosen) Sov.AccentDim else Sov.Border), RoundedCornerShape(8.dp))
            .padding(start = 16.dp, top = 14.dp, bottom = 14.dp, end = 8.dp),
        verticalAlignment = Alignment.Top,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(Modifier.weight(1f)) {
            Text(name, fontSize = 18.sp, fontWeight = FontWeight(600), color = Sov.TextBright)
            if (chosen) {
                Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Canvas(Modifier.size(16.dp)) {
                        val s = size.width / 24f
                        val w = 2.4f * s
                        drawLine(Sov.Green, Offset(5f * s, 12.5f * s), Offset(9.5f * s, 17f * s), w, StrokeCap.Round)
                        drawLine(Sov.Green, Offset(9.5f * s, 17f * s), Offset(19f * s, 7.5f * s), w, StrokeCap.Round)
                    }
                    Text("Выбрано", fontSize = 14.sp, color = Sov.Green)
                }
            } else {
                OutlinedButton(
                    onClick = onChoose,
                    enabled = !busy,
                    shape = RoundedCornerShape(8.dp),
                    border = BorderStroke(1.dp, Sov.BorderBright),
                    modifier = Modifier.padding(top = 8.dp).heightIn(min = 44.dp),
                ) { Text("Выбрать", color = Sov.Text, fontSize = 15.sp, fontWeight = FontWeight(600)) }
            }
        }
        Box(
            Modifier
                .size(48.dp)
                .clip(RoundedCornerShape(8.dp))
                .clickable(enabled = !busy, role = Role.Button, onClickLabel = "Действия с $name", onClick = onMore),
            contentAlignment = Alignment.Center,
        ) {
            Canvas(Modifier.size(22.dp)) {
                val s = size.width / 24f
                listOf(5f, 12f, 19f).forEach { x -> drawCircle(Sov.Text, 1.8f * s, Offset(x * s, 12f * s)) }
            }
        }
    }
}

@Composable
private fun AddBlock(name: String, error: String?, busy: Boolean, onName: (String) -> Unit, onAdd: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .drawBehind {
                // the mockup's dashed outline: a place still free in the plan
                drawRoundRect(
                    Sov.BorderBright,
                    cornerRadius = CornerRadius(8.dp.toPx()),
                    style = Stroke(1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx()))),
                )
            }
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("ДОБАВИТЬ ПРОФИЛЬ", style = MaterialTheme.typography.labelMedium, color = Sov.TextDim)
        Text("Название — до 6 символов: латинские буквы, цифры, - и _", style = MaterialTheme.typography.bodySmall, color = Sov.TextDim)
        OutlinedTextField(
            value = name,
            onValueChange = onName,
            placeholder = { Text("Введите название", color = Sov.TextDim) },
            singleLine = true,
            enabled = !busy,
            shape = RoundedCornerShape(8.dp),
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
            colors = fieldColors(),
            modifier = Modifier.fillMaxWidth(),
        )
        error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Sov.Red) }
        Button(
            onClick = onAdd,
            // Empty until the customer names it: no name is suggested for them.
            enabled = !busy && name.isNotBlank(),
            shape = RoundedCornerShape(8.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Sov.Accent, contentColor = Sov.OnAccent,
                disabledContainerColor = Sov.Accent.copy(alpha = 0.45f), disabledContentColor = Sov.OnAccent,
            ),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) { Text("Добавить", style = MaterialTheme.typography.labelLarge) }
    }
}

@Composable
private fun FullBlock(plan: String?, onPlans: () -> Unit) {
    Column(
        Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(Sov.Bg2)
            .border(BorderStroke(1.dp, Sov.Border), RoundedCornerShape(8.dp))
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("В тарифе больше нет мест", fontSize = 16.sp, fontWeight = FontWeight(600), color = Sov.Yellow)
        Text(planFullAdvice(plan), style = MaterialTheme.typography.bodyMedium, color = Sov.TextDim)
        TextButton(onClick = onPlans, modifier = Modifier.heightIn(min = 44.dp)) {
            Text("Тарифы на сайте ›", color = Sov.Accent, fontSize = 15.sp)
        }
    }
}

/** Behind «⋯»: rename, and remove only after a second, explicit step. */
@Composable
private fun ActionsSheet(
    device: Device,
    onThisPhone: Boolean,
    busy: Boolean,
    onRename: (String) -> Unit,
    onDelete: () -> Unit,
    onCancel: () -> Unit,
) {
    var confirming by remember(device.id) { mutableStateOf(false) }
    var name by remember(device.id) { mutableStateOf(device.name) }
    var problem by remember(device.id) { mutableStateOf<String?>(null) }

    Column(
        Modifier.fillMaxWidth().padding(start = 24.dp, end = 24.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (!confirming) {
            Text(device.name, fontFamily = Unbounded, fontSize = 20.sp, color = Sov.TextBright)
            Text("Новое название", style = MaterialTheme.typography.bodySmall, color = Sov.TextDim)
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it; problem = null },
                    singleLine = true,
                    enabled = !busy,
                    shape = RoundedCornerShape(8.dp),
                    keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false),
                    colors = fieldColors(),
                    modifier = Modifier.weight(1f),
                )
                Button(
                    onClick = {
                        // checked here first, so the sheet says what is wrong without a request
                        problem = validateDeviceName(name)
                        if (problem == null) onRename(name)
                    },
                    enabled = !busy,
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Sov.Accent, contentColor = Sov.OnAccent),
                    modifier = Modifier.height(52.dp),
                ) { Text("Сохранить", fontSize = 16.sp, fontWeight = FontWeight(600)) }
            }
            problem?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Sov.Red) }
            Text(
                "Меняется только название. Подключение и ключ остаются прежними.",
                style = MaterialTheme.typography.bodySmall, color = Sov.TextDim,
            )
            HorizontalDivider(color = Sov.Border, modifier = Modifier.padding(vertical = 6.dp))
            OutlinedButton(
                onClick = { confirming = true },
                enabled = !busy,
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, Sov.Red),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) { Text("Удалить профиль", color = Sov.Red, fontSize = 17.sp, fontWeight = FontWeight(600)) }
        } else {
            Text(DELETE_QUESTION, fontFamily = Unbounded, fontSize = 20.sp, lineHeight = 26.sp, color = Sov.TextBright)
            Text(deleteExplanation(onThisPhone), style = MaterialTheme.typography.bodyMedium, color = Sov.Text)
            Text("Место в тарифе освободится.", style = MaterialTheme.typography.bodySmall, color = Sov.TextDim)
            Button(
                onClick = onDelete,
                enabled = !busy,
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Sov.Red, contentColor = Sov.Bg),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) { Text("Удалить", fontSize = 17.sp, fontWeight = FontWeight(700)) }
            OutlinedButton(
                onClick = onCancel,
                enabled = !busy,
                shape = RoundedCornerShape(8.dp),
                border = BorderStroke(1.dp, Sov.BorderBright),
                modifier = Modifier.fillMaxWidth().height(52.dp),
            ) { Text("Отмена", color = Sov.Text, fontSize = 17.sp, fontWeight = FontWeight(600)) }
        }
    }
}

@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = Sov.Accent,
    unfocusedBorderColor = Sov.AccentDim,
    focusedContainerColor = Sov.Bg,
    unfocusedContainerColor = Sov.Bg,
    focusedTextColor = Sov.TextBright,
    unfocusedTextColor = Sov.TextBright,
    cursorColor = Sov.Accent,
)
