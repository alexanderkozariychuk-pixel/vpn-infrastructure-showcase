package com.sov3r3ign.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
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
import com.sov3r3ign.app.state.AccountModel
import com.sov3r3ign.app.storage.SecureStore
import com.sov3r3ign.app.tunnel.AppTunnel
import com.sov3r3ign.app.ui.main.MainScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Signed out → sign-in form; signed in → the main screen, and the devices page from it. */
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
        // A new model for each signed-in session: nothing of the last account's
        // state may show on the next one's screen.
        true -> {
            val model = remember { AccountModel(session, AppTunnel(context)) }
            val ui by model.ui.collectAsState()
            var devicesOpen by remember { mutableStateOf(false) }
            LaunchedEffect(ui.signedOut) {
                ui.signedOut?.let {
                    notice = it.notice
                    signedIn = false
                }
            }
            if (devicesOpen) {
                BackHandler { devicesOpen = false }
                DevicesScreen(model, onBack = { devicesOpen = false })
            } else {
                MainScreen(session, model, onOpenDevices = { devicesOpen = true })
            }
        }
    }
}
