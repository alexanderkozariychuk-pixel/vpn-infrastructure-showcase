package com.sov3r3ign.app.api

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import java.time.Instant
import java.time.LocalDateTime
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.format.DateTimeParseException

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
    /** Null when absent, and also when unreadable: a date must never crash a screen. */
    val subscribedUntil: Instant?
        get() = subscribedUntilRaw?.let { parseServerTime(it) }
}

/**
 * The server's timestamps come in two shapes. Production (PostgreSQL) writes
 * an offset — "2026-09-19T19:11:04.609756+00:00" — while the SQLite used to
 * record docs/api-contract.md wrote none — "2026-10-12T09:26:42.848714". The
 * first version read only the second and crashed on a real account. Both are
 * UTC; one without an offset is read as UTC, not as the phone's local time.
 */
internal fun parseServerTime(text: String): Instant? =
    try {
        OffsetDateTime.parse(text).toInstant()
    } catch (e: DateTimeParseException) {
        try {
            LocalDateTime.parse(text).toInstant(ZoneOffset.UTC)
        } catch (e: DateTimeParseException) {
            null
        }
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
