package com.sov3r3ign.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.api.Profile
import com.sov3r3ign.app.session.Session
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Temporary: proves the chain phone → HTTPS → portal → database with the
 * customer's own token. The device list replaces the middle of it in step 4.
 */
@Composable
fun AccountScreen(session: Session, onSignedOut: (notice: String?) -> Unit) {
    val scope = rememberCoroutineScope()
    var profile by remember { mutableStateOf<Profile?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var attempt by remember { mutableIntStateOf(0) }

    LaunchedEffect(attempt) {
        error = null
        when (val r = withContext(Dispatchers.IO) { session.profile() }) {
            is ApiResult.Ok -> { profile = r.value }
            is ApiResult.Failed -> {
                if (r.error == ApiError.Unauthorized) {
                    onSignedOut("Сессия истекла — войдите снова")
                } else {
                    error = describe(r.error, Action.LOAD)
                }
            }
        }
    }

    Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Sovereign", style = MaterialTheme.typography.headlineMedium)

        val p = profile
        if (p != null) {
            Text("Вы вошли как ${p.username}")
            Text(subscriptionLine(p))
        } else if (error == null) {
            CircularProgressIndicator()
        }

        error?.let {
            Text(it, color = MaterialTheme.colorScheme.error)
            TextButton(onClick = { attempt++ }) { Text("Повторить") }
        }

        OutlinedButton(onClick = {
            scope.launch {
                withContext(Dispatchers.IO) { session.signOut() }
                onSignedOut(null)
            }
        }) { Text("Выйти") }
    }
}
