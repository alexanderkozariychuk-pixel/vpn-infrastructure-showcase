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
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.ui.theme.Sov
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Sign-in and registration on one form, in the design system: the mark and
 * the wordmark, an Unbounded title, the site's fields and accent button, and
 * a two-way switch between the modes. Registration signs in straight after,
 * with the same details.
 *
 * The username and email survive rotation; the passwords do not, on purpose:
 * saved screen state is kept by the system outside the app.
 */
@Composable
fun AuthScreen(session: Session, notice: String?, onSignedIn: () -> Unit) {
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    var registering by rememberSaveable { mutableStateOf(false) }
    var username by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var shown by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf(notice) }

    fun submit() {
        if (busy) return
        val problem =
            if (registering) validateRegistration(username, email, password, confirm)
            else validateSignIn(username, password)
        if (problem != null) {
            error = problem
            return
        }
        busy = true
        error = null
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                if (registering) session.register(username, email, password)
                else session.signIn(username, password)
            }
            busy = false
            when (result) {
                is ApiResult.Ok -> onSignedIn()
                is ApiResult.Failed -> {
                    error = describe(result.error, if (registering) Action.REGISTER else Action.SIGN_IN)
                }
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 24.dp)
            .padding(top = 48.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Canvas(Modifier.size(40.dp)) { drawMark() }
            Text(wordmark(), style = MaterialTheme.typography.titleLarge, color = Sov.TextBright)
        }
        Spacer(Modifier.height(16.dp))
        Text(
            if (registering) "Регистрация" else "Вход",
            style = MaterialTheme.typography.headlineMedium,
            color = Sov.TextBright,
        )
        ModeSwitch(registering, enabled = !busy) {
            if (it != registering) {
                registering = it
                error = null
            }
        }

        Field(
            label = "Имя пользователя",
            value = username,
            onValue = { username = it },
            enabled = !busy,
            keyboard = KeyboardOptions(
                capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false,
                keyboardType = KeyboardType.Ascii, imeAction = ImeAction.Next,
            ),
        )
        if (registering) {
            Hint(USERNAME_HINT)
            Field(
                label = "Email",
                value = email,
                onValue = { email = it },
                enabled = !busy,
                keyboard = KeyboardOptions(
                    capitalization = KeyboardCapitalization.None, autoCorrectEnabled = false,
                    keyboardType = KeyboardType.Email, imeAction = ImeAction.Next,
                ),
            )
        }
        Field(
            label = "Пароль",
            value = password,
            onValue = { password = it },
            enabled = !busy,
            secret = !shown,
            keyboard = KeyboardOptions(
                keyboardType = KeyboardType.Password,
                imeAction = if (registering) ImeAction.Next else ImeAction.Done,
            ),
            onDone = { submit() },
            trailing = {
                TextButton(onClick = { shown = !shown }, modifier = Modifier.heightIn(min = 48.dp)) {
                    Text(if (shown) "Скрыть" else "Показать", color = Sov.TextDim, fontSize = 14.sp)
                }
            },
        )
        if (registering) {
            Field(
                label = "Пароль ещё раз",
                value = confirm,
                onValue = { confirm = it },
                enabled = !busy,
                secret = !shown,
                keyboard = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
                onDone = { submit() },
            )
            Hint("Пароль — не короче $MIN_PASSWORD символов.")
        }

        error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Sov.Red) }

        Button(
            onClick = { submit() },
            enabled = !busy,
            shape = RoundedCornerShape(8.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = Sov.Accent, contentColor = Sov.OnAccent,
                disabledContainerColor = Sov.Accent.copy(alpha = 0.45f), disabledContentColor = Sov.OnAccent,
            ),
            modifier = Modifier.fillMaxWidth().height(52.dp),
        ) {
            if (busy) {
                CircularProgressIndicator(Modifier.size(22.dp), color = Sov.OnAccent, strokeWidth = 2.dp)
            } else {
                Text(if (registering) "Зарегистрироваться" else "Войти", style = MaterialTheme.typography.labelLarge)
            }
        }

        if (registering) {
            Hint(REGISTER_NOTE)
        } else {
            // The reset letter and its form live on the site; the app has no copy of them.
            TextButton(
                onClick = { runCatching { uriHandler.openUri(PAYMENT_URL) } },
                enabled = !busy,
                modifier = Modifier.heightIn(min = 48.dp),
            ) { Text("Забыли пароль? Восстановить на сайте ›", color = Sov.Accent, fontSize = 15.sp) }
        }
    }
}

/** «Вход | Регистрация»: two halves, the chosen one filled. */
@Composable
private fun ModeSwitch(registering: Boolean, enabled: Boolean, onChoose: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .height(48.dp)
            .clip(RoundedCornerShape(8.dp))
            .border(BorderStroke(1.dp, Sov.BorderBright), RoundedCornerShape(8.dp)),
    ) {
        listOf(false to "Вход", true to "Регистрация").forEach { (mode, label) ->
            val chosen = mode == registering
            Box(
                Modifier
                    .weight(1f)
                    .fillMaxHeight()
                    .background(if (chosen) Sov.Bg3 else Sov.Bg)
                    .clickable(enabled = enabled, role = Role.Tab) { onChoose(mode) },
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    label,
                    fontSize = 15.sp,
                    fontWeight = FontWeight(if (chosen) 600 else 400),
                    color = if (chosen) Sov.Accent else Sov.TextDim,
                )
            }
        }
    }
}

@Composable
private fun Field(
    label: String,
    value: String,
    onValue: (String) -> Unit,
    enabled: Boolean,
    keyboard: KeyboardOptions,
    secret: Boolean = false,
    onDone: () -> Unit = {},
    trailing: (@Composable () -> Unit)? = null,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onValue,
        label = { Text(label) },
        singleLine = true,
        enabled = enabled,
        shape = RoundedCornerShape(8.dp),
        visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = keyboard,
        keyboardActions = KeyboardActions(onDone = { onDone() }),
        trailingIcon = trailing,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = Sov.Accent,
            unfocusedBorderColor = Sov.BorderBright,
            focusedContainerColor = Sov.Bg2,
            unfocusedContainerColor = Sov.Bg2,
            focusedTextColor = Sov.TextBright,
            unfocusedTextColor = Sov.TextBright,
            focusedLabelColor = Sov.Accent,
            unfocusedLabelColor = Sov.TextDim,
            cursorColor = Sov.Accent,
        ),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun Hint(text: String) {
    Text(text, style = MaterialTheme.typography.bodySmall, color = Sov.TextDim)
}
