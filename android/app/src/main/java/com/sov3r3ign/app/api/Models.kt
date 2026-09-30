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

/**
 * The portal's rule, stricter than the server's: the name becomes the file
 * name of the downloaded .conf, and the portal lets through only these
 * characters. A name the app accepted and the portal would not — Cyrillic,
 * a space — would reach the site as a mangled file name. Names already on
 * the account (the server's own "device-1" is eight characters) are shown
 * as they are; the rule is for names typed in the app.
 */
val DEVICE_NAME = Regex("[A-Za-z0-9_-]{1,$MAX_DEVICE_NAME}")

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
    /** The plan key, "basic-1m" … "ext-6m". Sent since 2026-09-29. */
    val plan: String? = null,
    /** The server's own gate, has_active_subscription. Sent since 2026-09-29. */
    val active: Boolean? = null,
) {
    /** Null when absent, and also when unreadable: a date must never crash a screen. */
    val subscribedUntil: Instant?
        get() = subscribedUntilRaw?.let { parseServerTime(it) }

    /**
     * Whether the paid period is running. The server's `active` wins when it
     * is sent: it is the same check that lets the portal hand out configs, and
     * it does not depend on the phone's clock. A server older than 2026-09-29
     * does not send it, and then the app applies that check itself — the flag
     * *and* an end date still ahead, a missing date being no subscription.
     *
     * Null only in that fallback, when the flag is set and the date cannot be
     * read: the app does not know, and says so rather than guessing.
     */
    fun activeAt(now: Instant): Boolean? {
        active?.let { return it }
        if (!isSubscribed || subscribedUntilRaw == null) return false
        val until = subscribedUntil ?: return null
        return until.isAfter(now)
    }
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
