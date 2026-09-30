package com.sov3r3ign.app.session

import com.sov3r3ign.app.api.ApiClient
import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.ApiResult
import com.sov3r3ign.app.api.Device
import com.sov3r3ign.app.api.DeviceList
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

    /**
     * The account's devices. The list is also where the name shown for this
     * phone's device is kept current: a rename on the site, or on another
     * phone, reaches this phone only this way. The config is not touched —
     * a rename changes only the label.
     */
    fun devices(): ApiResult<DeviceList> = authorized { api.devices(it) }.also { r ->
        if (r is ApiResult.Ok) {
            val id = secrets.get(DEVICE_ID)
            val current = r.value.configs.firstOrNull { it.id == id }
            if (current != null && secrets.get(DEVICE_NAME) != current.name) {
                secrets.put(DEVICE_NAME, current.name)
            }
        }
    }

    fun addDevice(name: String): ApiResult<Device> = authorized { api.addDevice(it, name) }

    /**
     * Renames a device on the account. When it is the one this phone uses,
     * the stored name follows; the stored config does not change, since the
     * server changes only the label.
     */
    fun renameDevice(deviceId: String, name: String): ApiResult<Device> = authorized { token ->
        val r = api.renameDevice(token, deviceId, name)
        if (r is ApiResult.Ok && secrets.get(DEVICE_ID) == deviceId) {
            secrets.put(DEVICE_NAME, r.value.name)
        }
        r
    }

    /**
     * Makes [device] the one this phone uses: downloads its .conf and keeps
     * it. The tunnel then starts from what is stored, with no network call —
     * the token may well have expired by the time the customer presses connect.
     *
     * The id is written last. It is what marks a selection as complete, so an
     * interruption part-way leaves the previous selection readable, or none.
     */
    fun select(device: Device): ApiResult<Unit> = authorized { token ->
        when (val r = api.config(token, device.id)) {
            is ApiResult.Ok -> {
                // A 200 that is not a config — a proxy's error page, say —
                // must not replace a working one.
                if (!r.value.contains("[Interface]") || !r.value.contains("PrivateKey")) {
                    ApiResult.Failed(ApiError.Malformed("not a WireGuard config"))
                } else {
                    secrets.put(CONF, r.value)
                    secrets.put(DEVICE_NAME, device.name)
                    secrets.put(DEVICE_ID, device.id)
                    ApiResult.Ok(Unit)
                }
            }
            is ApiResult.Failed -> r
        }
    }

    /** The device this phone uses, if one was chosen here. */
    fun selected(): Selected? {
        val id = secrets.get(DEVICE_ID) ?: return null
        val name = secrets.get(DEVICE_NAME) ?: return null
        if (secrets.get(CONF) == null) return null
        return Selected(id, name)
    }

    /** The stored .conf of the selected device; what the tunnel starts from. */
    fun storedConfig(): String? = if (selected() != null) secrets.get(CONF) else null

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

    data class Selected(val id: String, val name: String)

    companion object {
        const val TOKEN = "token"
        const val CONF = "conf"
        const val DEVICE_ID = "device_id"
        const val DEVICE_NAME = "device_name"
    }
}
