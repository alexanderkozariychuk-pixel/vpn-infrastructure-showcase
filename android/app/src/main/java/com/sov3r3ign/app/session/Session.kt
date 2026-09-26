package com.sov3r3ign.app.session

import com.sov3r3ign.app.api.ApiClient
import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.api.Profile
import com.sov3r3ign.app.storage.Secrets

/**
 * Who is signed in, and the token that proves it.
 *
 * The password is used once and never stored. The token is: it lasts 24
 * hours and there is no refresh, so a 401 on a stored token means it expired,
 * and the session forgets it — the app then shows sign-in instead of failing
 * on every call.
 *
 * Blocking: network and disk. Call it off the main thread.
 */
class Session(private val api: ApiClient, private val secrets: Secrets) {

    val isSignedIn: Boolean
        get() = secrets.get(TOKEN) != null

    fun signIn(username: String, password: String): ApiResult<Unit> =
        when (val r = api.login(username.trim(), password)) {
            is ApiResult.Ok -> {
                secrets.put(TOKEN, r.value.accessToken)
                ApiResult.Ok(Unit)
            }
            is ApiResult.Failed -> r
        }

    /** Registration, then sign-in with the same details. */
    fun register(username: String, email: String, password: String): ApiResult<Unit> =
        when (val r = api.register(username.trim(), email.trim(), password)) {
            is ApiResult.Ok -> signIn(username, password)
            is ApiResult.Failed -> r
        }

    fun profile(): ApiResult<Profile> = authorized { api.profile(it) }

    /** Everything stored goes, including the key that could read it. */
    fun signOut() = secrets.clear()

    private fun <T> authorized(call: (String) -> ApiResult<T>): ApiResult<T> {
        val token = secrets.get(TOKEN) ?: return ApiResult.Failed(ApiError.Unauthorized)
        val result = call(token)
        if (result is ApiResult.Failed && result.error == ApiError.Unauthorized) {
            secrets.remove(TOKEN)
        }
        return result
    }

    companion object {
        const val TOKEN = "token"
    }
}
