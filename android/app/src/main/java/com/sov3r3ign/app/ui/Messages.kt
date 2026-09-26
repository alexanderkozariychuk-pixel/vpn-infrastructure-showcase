package com.sov3r3ign.app.ui

import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.Profile
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/*
 * Everything the screens say, in one place and free of Android, so it can be
 * tested on a laptop and translated later without hunting through layouts.
 */

/** What the customer was doing when the error came back; the same code means different things. */
enum class Action { SIGN_IN, REGISTER, LOAD }

/**
 * At least this long for accounts created in the app. The server does not
 * enforce a minimum yet; with one login shared across a family's phones, the
 * app should not wait for it to.
 */
const val MIN_PASSWORD = 8

private val EMAIL = Regex("[^@\\s]+@[^@\\s]+\\.[^@\\s]+")

fun validateSignIn(username: String, password: String): String? =
    if (username.isBlank() || password.isEmpty()) "Введите имя пользователя и пароль" else null

fun validateRegistration(username: String, email: String, password: String, confirm: String): String? =
    when {
        username.isBlank() -> "Введите имя пользователя"
        !EMAIL.matches(email.trim()) -> "Проверьте email"
        password.length < MIN_PASSWORD -> "Пароль — не короче $MIN_PASSWORD символов"
        password != confirm -> "Пароли не совпадают"
        else -> null
    }

fun describe(error: ApiError, action: Action): String = when (error) {
    ApiError.Unauthorized ->
        if (action == Action.SIGN_IN) "Неверное имя пользователя или пароль"
        else "Сессия истекла — войдите снова"

    ApiError.SubscriptionLapsed -> "Подписка закончилась. Продлить её можно на сайте."

    // The server's reasons are in English and name the field; the app says
    // it in Russian rather than showing them raw.
    is ApiError.Conflict -> when {
        action != Action.REGISTER -> "В тарифе нет свободных мест — удалите одно из устройств"
        error.message.contains("email", ignoreCase = true) -> "Этот email уже зарегистрирован"
        else -> "Такое имя пользователя уже занято"
    }

    is ApiError.Rejected -> when (action) {
        // The only refusal sign-in produces: an account that is not a customer's.
        Action.SIGN_IN -> "Этот аккаунт нельзя использовать в приложении"
        Action.REGISTER -> "Проверьте email и остальные поля"
        Action.LOAD -> "Сервер отклонил запрос"
    }

    is ApiError.Network -> "Нет связи с сервером. Проверьте интернет."
    is ApiError.Server -> "Сервер временно недоступен (${error.code}). Попробуйте позже."
    is ApiError.Malformed -> "Сервер ответил неожиданно — возможно, пора обновить приложение."
}

private val DATE = DateTimeFormatter.ofPattern("d MMMM yyyy", Locale.forLanguageTag("ru"))

/**
 * Read the way the server's own gate reads it (has_active_subscription): the
 * flag *and* an end date still ahead. /api/client/me returns the raw flag,
 * which a periodic sweep clears some time after the date passes, so the flag
 * alone can say "subscribed" about a period that is over. A missing date
 * counts as no subscription, as it does on the server.
 *
 * Dates are shown in the phone's own time zone. The server's are UTC: a period
 * that ends at 22:30 UTC ends at 01:30 the next day in Moscow, and printing
 * the UTC date would put the end a day off.
 */
fun subscriptionLine(
    profile: Profile,
    zone: ZoneId = ZoneId.systemDefault(),
    now: Instant = Instant.now(),
): String {
    val raw = profile.subscribedUntilRaw
    val until = profile.subscribedUntil
    return when {
        !profile.isSubscribed || raw == null -> "Подписки нет"
        until == null -> "Подписка есть, но дату окончания не удалось прочитать"
        !until.isAfter(now) -> "Подписка закончилась " + DATE.withZone(zone).format(until)
        else -> "Подписка до " + DATE.withZone(zone).format(until)
    }
}
