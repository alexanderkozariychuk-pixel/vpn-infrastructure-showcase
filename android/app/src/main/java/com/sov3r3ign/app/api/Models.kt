package com.sov3r3ign.app.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneOffset

/*
 * The shapes the portal API sends and accepts, as recorded in
 * docs/api-contract.md. Fields the app does not use are left out on purpose:
 * the decoder ignores unknown keys, so the server can add fields without
 * breaking installed apps.
 */

/** The server enforces this (422 above it); the app checks first to say why. */
const val MAX_DEVICE_NAME = 6

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class RegisterRequest(
    val username: String,
    val email: String,
    val password: String,
    val lang: String = "ru",
)

@Serializable
data class NewDeviceRequest(val name: String)

@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    val role: String,
)

@Serializable
data class Profile(
    val username: String,
    val email: String? = null,
    @SerialName("is_subscribed") val isSubscribed: Boolean,
    @SerialName("subscribed_until") val subscribedUntilRaw: String? = null,
) {
    /**
     * The server stores UTC and writes it without an offset
     * ("2026-10-12T09:26:42.848714"). Parsing it as local time would move
     * every expiry date by three hours in Moscow.
     */
    val subscribedUntil: Instant?
        get() = subscribedUntilRaw?.let { LocalDateTime.parse(it).toInstant(ZoneOffset.UTC) }
}

@Serializable
data class Device(
    val id: String,
    val name: String,
    @SerialName("peer_ip") val peerIp: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class DeviceList(
    val plan: String? = null,
    val limit: Int,
    val used: Int,
    val configs: List<Device>,
) {
    val hasRoom: Boolean get() = used < limit
}

@Serializable
data class AddedDevice(val config: Device, val used: Int, val limit: Int)
