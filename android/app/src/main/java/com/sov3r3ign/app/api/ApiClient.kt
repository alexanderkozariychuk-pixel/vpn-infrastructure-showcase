package com.sov3r3ign.app.api

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.IOException

/**
 * HTTP as the client needs it: one call in, one status and body out.
 * Kept apart from the client so tests can answer with the responses recorded
 * in docs/api-contract.md instead of a network.
 */
fun interface Transport {
    @Throws(IOException::class)
    fun send(method: String, path: String, token: String?, jsonBody: String?): HttpReply
}

data class HttpReply(val code: Int, val body: String)

/**
 * Every way a call can fail that the screen has to tell apart. The contract
 * makes 401 and 402 different states on purpose: one means sign in again,
 * the other means renew — the same "something went wrong" for both would
 * send a paying customer to the login screen.
 */
sealed interface ApiError {
    /** 401 — no token, a bad one, or a wrong password. */
    data object Unauthorized : ApiError

    /** 402 — the paid period is over. */
    data object SubscriptionLapsed : ApiError

    /** 409 — the plan is full, or the username or email is taken. */
    data class Conflict(val message: String) : ApiError

    /** 400 or 422 — the request itself was refused. */
    data class Rejected(val message: String) : ApiError

    /** A 2xx whose body did not match the contract. */
    data class Malformed(val message: String) : ApiError

    /** 5xx, or a status the contract does not mention. */
    data class Server(val code: Int) : ApiError

    /** No answer at all: no network, DNS, timeout. */
    data class Network(val cause: IOException) : ApiError
}

sealed interface ApiResult<out T> {
    data class Ok<T>(val value: T) : ApiResult<T>
    data class Failed(val error: ApiError) : ApiResult<Nothing>
}

private val DEVICE_ID = Regex("[A-Za-z0-9-]{1,64}")

class ApiClient(private val transport: Transport) {

    private val json = Json { ignoreUnknownKeys = true }

    /**
     * The admin account signs in through the same endpoint. The app is for
     * customers, and an admin token in a phone's storage is a liability, so
     * any role but "client" is refused here rather than kept.
     */
    fun login(username: String, password: String): ApiResult<TokenResponse> {
        val body = json.encodeToString(LoginRequest.serializer(), LoginRequest(username, password))
        val result = call("POST", "/api/auth/token", null, body) {
            json.decodeFromString(TokenResponse.serializer(), it)
        }
        if (result is ApiResult.Ok && result.value.role != "client") {
            return ApiResult.Failed(ApiError.Rejected("This account cannot be used in the app"))
        }
        return result
    }

    /** Creates the account only; sign in afterwards with the same details. */
    fun register(username: String, email: String, password: String): ApiResult<Unit> {
        val body = json.encodeToString(
            RegisterRequest.serializer(),
            RegisterRequest(username, email, password),
        )
        return call("POST", "/api/client/register", null, body) { }
    }

    fun profile(token: String): ApiResult<Profile> =
        call("GET", "/api/client/me", token, null) {
            json.decodeFromString(Profile.serializer(), it)
        }

    fun devices(token: String): ApiResult<DeviceList> =
        call("GET", "/api/client/configs", token, null) {
            json.decodeFromString(DeviceList.serializer(), it)
        }

    fun addDevice(token: String, name: String): ApiResult<Device> {
        val trimmed = name.trim()
        if (trimmed.isEmpty() || trimmed.length > MAX_DEVICE_NAME) {
            return ApiResult.Failed(
                ApiError.Rejected("Device name must be 1 to $MAX_DEVICE_NAME characters")
            )
        }
        val body = json.encodeToString(NewDeviceRequest.serializer(), NewDeviceRequest(trimmed))
        return call("POST", "/api/client/configs", token, body) {
            json.decodeFromString(AddedDevice.serializer(), it).config
        }
    }

    /** The .conf text, handed to the tunnel as it is. */
    fun config(token: String, deviceId: String): ApiResult<String> {
        // Ids come from our own server and are UUIDs. Checked anyway: an id
        // is pasted into a URL path, and "x/../../other" would be too.
        if (!DEVICE_ID.matches(deviceId)) {
            return ApiResult.Failed(ApiError.Rejected("Not a device id"))
        }
        return call("GET", "/api/client/configs/$deviceId/raw", token, null) { it }
    }

    private inline fun <T> call(
        method: String,
        path: String,
        token: String?,
        body: String?,
        parse: (String) -> T,
    ): ApiResult<T> {
        val reply = try {
            transport.send(method, path, token, body)
        } catch (e: IOException) {
            return ApiResult.Failed(ApiError.Network(e))
        }
        return when (reply.code) {
            in 200..299 -> try {
                ApiResult.Ok(parse(reply.body))
            } catch (e: IllegalArgumentException) {
                // SerializationException is an IllegalArgumentException.
                ApiResult.Failed(ApiError.Malformed(e.message ?: "unreadable response"))
            }
            401 -> ApiResult.Failed(ApiError.Unauthorized)
            402 -> ApiResult.Failed(ApiError.SubscriptionLapsed)
            409 -> ApiResult.Failed(ApiError.Conflict(detail(reply.body)))
            400, 422 -> ApiResult.Failed(ApiError.Rejected(detail(reply.body)))
            else -> ApiResult.Failed(ApiError.Server(reply.code))
        }
    }

    /**
     * FastAPI puts the reason in "detail": a string for errors the handlers
     * raise, a list of objects for validation (422).
     */
    private fun detail(body: String): String = try {
        when (val d = json.parseToJsonElement(body).jsonObject["detail"]) {
            is JsonPrimitive -> d.content
            is JsonArray -> d.firstOrNull()?.jsonObject?.get("msg")?.jsonPrimitive?.content ?: body
            else -> body
        }
    } catch (e: IllegalArgumentException) {
        body
    }
}
