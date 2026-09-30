package com.sov3r3ign.app.ui

import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.DEVICE_NAME
import com.sov3r3ign.app.api.MAX_DEVICE_NAME
import com.sov3r3ign.app.api.Profile
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
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

fun validateDeviceName(name: String): String? = when {
    name.isBlank() -> "Введите название устройства"
    name.trim().length > MAX_DEVICE_NAME -> "Название — не длиннее $MAX_DEVICE_NAME символов"
    !DEVICE_NAME.matches(name.trim()) -> "Только латинские буквы, цифры, - и _"
    else -> null
}

/**
 * Said beside the list, because nothing else will warn about it: a config in
 * use on two devices at once makes both connections drop in turn, and until
 * the server records which installation holds which config, the app cannot
 * see the other device.
 */
const val ONE_DEVICE_PER_CONFIG =
    "Один конфиг работает на одном устройстве за раз. Если выбрать конфиг, " +
        "который уже включён на другом телефоне, связь будет пропадать на обоих."

fun describe(error: ApiError, action: Action): String = when (error) {
    ApiError.Unauthorized ->
        if (action == Action.SIGN_IN) "Неверное имя пользователя или пароль"
        else "Сессия истекла — войдите снова"

    ApiError.SubscriptionLapsed -> "Подписка закончилась. Продлить её можно на сайте."

    ApiError.NotFound -> "Устройство не найдено — возможно, его удалили на сайте. Список обновлён."

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
 * The status line under the account name. Whether the period runs is
 * Profile.activeAt: the server's `active` when it sends one, otherwise the
 * same rule applied here (see there).
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
    val until = profile.subscribedUntil
    val date = until?.let { DATE.withZone(zone).format(it) }
    return when (profile.activeAt(now)) {
        // The server's word stands even when the phone's clock disagrees.
        true -> if (date != null) "Подписка до $date" else "Подписка действует"
        null -> "Подписка есть, но дату окончания не удалось прочитать"
        false -> when {
            profile.subscribedUntilRaw == null -> "Подписки нет"
            until != null && !until.isAfter(now) -> "Подписка закончилась $date"
            // A date still ahead that the server does not count: say it is not
            // running, not when it "ends".
            else -> "Подписка не активна"
        }
    }
}

/**
 * "basic-1m" -> "Базовый · 1 месяц", as the portal shows it. A key the app
 * does not know (a retired plan on an old account) is shown as it is.
 */
fun planLabel(key: String): String {
    val m = Regex("(basic|ext)-(\\d+)m").matchEntire(key) ?: return key
    val tier = if (m.groupValues[1] == "ext") "Расширенный" else "Базовый"
    val months = m.groupValues[2].toLong()
    return "$tier · $months ${plural(months, "месяц", "месяца", "месяцев")}"
}

/** The plan is only named while it runs; after that the portal says "no subscription" too. */
fun planLine(profile: Profile, now: Instant = Instant.now()): String? =
    if (profile.activeAt(now) == true) profile.plan?.let { "Тариф: " + planLabel(it) } else null

/**
 * Days before the end when the app starts saying so. Warned after the end,
 * the customer finds out from a tunnel that stopped working.
 */
const val WARN_DAYS = 3L

/**
 * Said while the period still runs and ends within [warnDays]. Days are
 * counted by the calendar in the phone's zone: an end at 01:30 tomorrow is
 * "tomorrow", not "today" because it is under 24 hours away.
 */
fun expiryWarning(
    profile: Profile,
    zone: ZoneId = ZoneId.systemDefault(),
    now: Instant = Instant.now(),
    warnDays: Long = WARN_DAYS,
): String? {
    if (profile.activeAt(now) != true) return null
    val until = profile.subscribedUntil ?: return null
    val left = ChronoUnit.DAYS.between(now.atZone(zone).toLocalDate(), until.atZone(zone).toLocalDate())
    val tail = " Продлите на сайте, чтобы связь не прервалась."
    return when {
        left > warnDays -> null
        // The server still says active past the phone's date: its clock is behind ours.
        left <= 0L -> "Подписка заканчивается сегодня." + tail
        left == 1L -> "Подписка заканчивается завтра." + tail
        else -> "Подписка заканчивается через $left ${plural(left, "день", "дня", "дней")}." + tail
    }
}

/** The renewal button shows when the period is not running, or is about to end. */
fun needsPayment(
    profile: Profile,
    zone: ZoneId = ZoneId.systemDefault(),
    now: Instant = Instant.now(),
): Boolean = profile.activeAt(now) != true || expiryWarning(profile, zone, now) != null

/** Asked before a device is removed; what removal does depends on whose it is. */
fun deleteQuestion(name: String, onThisPhone: Boolean): String =
    if (onThisPhone) {
        "«$name» — устройство этого телефона. Подключение выключится, ключ будет удалён; " +
            "чтобы подключиться снова, выберите другое устройство или добавьте этот телефон."
    } else {
        "Если «$name» включено на другом телефоне или компьютере, связь там пропадёт. " +
            "Место в тарифе освободится."
    }

/** Said once, when the list shows this phone's device is gone from the account. */
const val DEVICE_GONE =
    "Устройство этого телефона удалено с аккаунта, подключение выключено. " +
        "Выберите другое устройство или добавьте этот телефон."

/** Payment is on the site, never in the app; the portal opens on sign-in. */
const val PAYMENT_URL = "https://sov3r3ign.com/app"

private fun plural(n: Long, one: String, few: String, many: String): String {
    val mod100 = n % 100
    val mod10 = n % 10
    return when {
        mod100 in 11L..14L -> many
        mod10 == 1L -> one
        mod10 in 2L..4L -> few
        else -> many
    }
}

/** Beyond this the tunnel is up but the server has stopped answering. The
 *  handshake renews every two minutes while traffic flows. */
const val STALE_HANDSHAKE_SECONDS = 180L

/**
 * The status line under the switch. "Connected" is only said when the server
 * has answered recently: a tunnel can be up on the phone and carry nothing,
 * and a customer told they are connected will blame the sites, not us.
 */
fun connectionLine(up: Boolean, busy: Boolean, handshakeUnixSeconds: Long?, nowUnixSeconds: Long): String {
    if (busy) return "Подключение…"
    if (!up) return "Отключено"
    val h = handshakeUnixSeconds
    if (h == null || h <= 0L) return "Подключено, ждём ответа сервера"
    val age = (nowUnixSeconds - h).coerceAtLeast(0L)
    return if (age <= STALE_HANDSHAKE_SECONDS) "Подключено · сервер отвечал $age с назад"
    else "Сервер не отвечает уже ${age / 60} мин. Проверьте интернет или переподключитесь."
}
