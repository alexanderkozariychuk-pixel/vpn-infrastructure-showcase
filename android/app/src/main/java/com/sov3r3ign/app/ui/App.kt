package com.sov3r3ign.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.sov3r3ign.app.api.ApiClient
import com.sov3r3ign.app.api.HttpTransport
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.storage.SecureStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Signed out → sign-in form; signed in → the account. Nothing else yet. */
@Composable
fun App() {
    val context = LocalContext.current
    val session = remember {
        Session(ApiClient(HttpTransport()), SecureStore(context.applicationContext))
    }
    // null until the stored token has been looked for: reading it is disk I/O.
    var signedIn by remember { mutableStateOf<Boolean?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(Unit) {
        signedIn = withContext(Dispatchers.IO) { session.isSignedIn }
    }

    when (signedIn) {
        null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        false -> AuthScreen(session, notice) {
            notice = null
            signedIn = true
        }
        true -> AccountScreen(session) { reason ->
            notice = reason
            signedIn = false
        }
    }
}
