package com.sov3r3ign.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.session.Session
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Sign-in and registration on one form. Registration signs in straight after,
 * with the same details.
 *
 * The username and email survive rotation; the passwords do not, on purpose:
 * saved screen state is kept by the system outside the app.
 */
@Composable
fun AuthScreen(session: Session, notice: String?, onSignedIn: () -> Unit) {
    val scope = rememberCoroutineScope()
    var registering by rememberSaveable { mutableStateOf(false) }
    var username by rememberSaveable { mutableStateOf("") }
    var email by rememberSaveable { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var confirm by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf(notice) }

    fun submit() {
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
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Sovereign", style = MaterialTheme.typography.headlineMedium)
        Text(if (registering) "Регистрация" else "Вход", style = MaterialTheme.typography.titleMedium)

        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("Имя пользователя") },
            singleLine = true,
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
        )
        if (registering) {
            OutlinedTextField(
                value = email,
                onValueChange = { email = it },
                label = { Text("Email") },
                singleLine = true,
                enabled = !busy,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                modifier = Modifier.fillMaxWidth(),
            )
        }
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Пароль") },
            singleLine = true,
            enabled = !busy,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
            modifier = Modifier.fillMaxWidth(),
        )
        if (registering) {
            OutlinedTextField(
                value = confirm,
                onValueChange = { confirm = it },
                label = { Text("Пароль ещё раз") },
                singleLine = true,
                enabled = !busy,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth(),
            )
        }

        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }

        Button(onClick = { submit() }, enabled = !busy, modifier = Modifier.fillMaxWidth()) {
            Text(if (registering) "Зарегистрироваться" else "Войти")
        }
        TextButton(
            onClick = {
                registering = !registering
                error = null
            },
            enabled = !busy,
        ) {
            Text(if (registering) "Уже есть аккаунт? Войти" else "Нет аккаунта? Зарегистрироваться")
        }
        if (busy) CircularProgressIndicator()
    }
}
