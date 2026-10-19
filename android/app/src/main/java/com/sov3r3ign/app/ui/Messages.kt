package com.sov3r3ign.app.ui

import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.DEVICE_NAME
import com.sov3r3ign.app.api.MAX_DEVICE_NAME
import com.sov3r3ign.app.api.Profile
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import javax.net.ssl.SSLException
import java.util.Locale

/*
 * Everything the screens say, in one place and free of Android, so it can be
 * tested on a laptop and translated later without hunting through layouts.
 */

/** What the customer was doing when the error came back; the same code means different things. */
enum class Action { SIGN_IN, REGISTER, LOAD, TRIAL, RESEND, DELETE }

/** The server's own minimum (pwa/api/register.py, PASSWORD_MIN). */
const val MIN_PASSWORD = 8

/**
 * The server's rule for a username (pwa/api/register.py, USERNAME_RE): it
 * becomes part of the peer's name on the entry node. Checked here first, so
 * the form says why instead of the server's English.
 */
val USERNAME = Regex("[A-Za-z0-9_-]{3,27}")

private val EMAIL = Regex("[^@\\s]+@[^@\\s]+\\.[^@\\s]+")

fun validateSignIn(username: String, password: String): String? =
    if (username.isBlank() || password.isEmpty()) "Введите имя пользователя и пароль" else null

fun validateRegistration(username: String, email: String, password: String, confirm: String): String? =
    when {
        username.isBlank() -> "Введите имя пользователя"
        !USERNAME.matches(username.trim()) -> "Имя пользователя — от 3 до 27 символов: латинские буквы, цифры, - и _"
        !EMAIL.matches(email.trim()) -> "Проверьте email"
        password.length < MIN_PASSWORD -> "Пароль — не короче $MIN_PASSWORD символов"
        password != confirm -> "Пароли не совпадают"
        else -> null
    }

fun validateDeviceName(name: String): String? = when {
    name.isBlank() -> "Введите название профиля"
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
    "В случае подключения больше одного устройства к выбранному выше профилю " +
        "работоспособность сервиса не гарантируется."

/**
 * [tunnelUp]: the VPN was on when the call failed. The portal is reached
 * through the tunnel then, and a tunnel whose server stopped answering makes
 * the site look down while the phone's internet is fine.
 */
fun describe(error: ApiError, action: Action, tunnelUp: Boolean = false): String = when (error) {
    ApiError.Unauthorized ->
        if (action == Action.SIGN_IN) "Неверное имя пользователя или пароль"
        else "Сессия истекла — войдите снова"

    ApiError.SubscriptionLapsed -> "Подписка закончилась. Продлить её можно на сайте."

    ApiError.NotFound -> "Профиль не найден — возможно, его удалили на сайте. Список обновлён."

    // The windows are the portal's (services/ratelimit.py): sign-in 15 minutes,
    // registration and the letter an hour, the trial a day.
    ApiError.TooMany -> when (action) {
        Action.SIGN_IN -> "Слишком много попыток. Подождите 15 минут и попробуйте снова."
        Action.REGISTER -> "Слишком много регистраций с этого адреса. Попробуйте через час."
        Action.RESEND -> "Письмо уже отправляли несколько раз. Попробуйте через час."
        Action.TRIAL -> "Слишком много попыток. Попробуйте завтра."
        else -> "Слишком много запросов. Попробуйте позже."
    }

    is ApiError.Forbidden -> when {
        error.message == "email_not_verified" ->
            "Сначала подтвердите почту — ссылка в письме, которое пришло после регистрации."
        error.message == "trial_off" -> "Пробный период сейчас недоступен. Оформить подписку можно на сайте."
        error.message == "trial_unavailable" ->
            "Для этой почты пробный период недоступен. Оформить подписку можно на сайте."
        error.message.contains("disabled", ignoreCase = true) -> "Аккаунт отключён. Напишите в поддержку на сайте."
        else -> "Сервер отказал в доступе. Попробуйте позже."
    }

    // The server's reasons are in English and name the field; the app says
    // it in Russian rather than showing them raw.
    is ApiError.Conflict -> when {
        error.message == "trial_device" ->
            "Пробный профиль нельзя удалить — он закончится вместе с пробным периодом."
        error.message == "trial_used" -> "Пробный период уже был на этом аккаунте или этой почте."
        error.message == "trial_active" -> "Пробный период уже идёт."
        action != Action.REGISTER -> "В тарифе больше нет мест."
        error.message.contains("email", ignoreCase = true) -> "Этот email уже зарегистрирован"
        else -> "Такое имя пользователя уже занято"
    }

    is ApiError.Rejected -> when (action) {
        // The only refusal sign-in produces: an account that is not a customer's.
        Action.SIGN_IN -> "Этот аккаунт нельзя использовать в приложении"
        Action.REGISTER -> if (error.message.contains("reserved", ignoreCase = true)) {
            "Это имя пользователя занято — выберите другое"
        } else {
            "Проверьте имя пользователя, email и пароль"
        }
        else -> "Сервер отклонил запрос"
    }

    is ApiError.Network -> networkLine(error.cause) + if (tunnelUp) {
        " Запрос шёл через VPN: если выше написано, что сервер не отвечает, отключите VPN и повторите."
    } else {
        ""
    }
    is ApiError.Server -> if (action == Action.TRIAL && error.code == 503) {
        "Сейчас нет свободных мест для пробного периода. Попробуйте позже."
    } else {
        "Сервер временно недоступен (${error.code}). Попробуйте позже."
    }
    is ApiError.Malformed -> "Сервер ответил неожиданно — возможно, пора обновить приложение."
}

/** No answer at all, by what kind of no answer it was. */
private fun networkLine(cause: java.io.IOException): String = when (cause) {
    is UnknownHostException -> "Не удаётся найти сайт. Проверьте, что интернет работает."
    is SocketTimeoutException -> "Сайт не ответил вовремя. Проверьте интернет или повторите позже."
    // A Wi-Fi that wants a sign-in page answers HTTPS with its own
    // certificate; the handshake fails before anything reaches the site.
    is SSLException -> "Не удалось установить защищённое соединение с сайтом. " +
        "Если это Wi-Fi в кафе, гостинице или транспорте, сначала откройте браузер и войдите в сеть."
    else -> "Нет связи с сайтом. Проверьте интернет."
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
    // A trial is said only while no paid period runs; paying ends the trial anyway.
    if (profile.activeAt(now) != true && profile.trialActiveAt(now)) {
        val end = profile.trialUntil?.let { DATE.withZone(zone).format(it) }
        return if (end != null) "Пробный период до $end" else "Пробный период"
    }
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
    if (profile.activeAt(now) != true) {
        // A trial lasts days, not months: three days' notice would be the whole
        // trial. Its end is said only on its last day and the one before.
        if (!profile.trialActiveAt(now)) return null
        val end = profile.trialUntil ?: return null
        val left = ChronoUnit.DAYS.between(now.atZone(zone).toLocalDate(), end.atZone(zone).toLocalDate())
        val tail = " Оформите подписку на сайте, чтобы связь не прервалась."
        return when {
            left > 1L -> null
            left == 1L -> "Пробный период заканчивается завтра." + tail
            else -> "Пробный период заканчивается сегодня." + tail
        }
    }
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

/** What the pay button says: someone who never paid subscribes, a customer renews. */
fun paymentLabel(profile: Profile, now: Instant = Instant.now()): String =
    if (profile.subscribedUntilRaw == null || profile.trialActiveAt(now)) "Оформить подписку на сайте"
    else "Продлить на сайте"

/** What the app offers someone with no access, from the trial's state. */
enum class TrialOfferKind { START, CONFIRM_EMAIL, NONE }

/**
 * A trial is offered only to someone with no access at all, and only in the
 * two states that can lead to one; [enabled] is the site's switch
 * (/api/public/trial). Anything else — used, off, a state this app does not
 * know — offers nothing and leaves the pay button.
 */
fun trialOffer(profile: Profile, enabled: Boolean, now: Instant = Instant.now()): TrialOfferKind = when {
    !enabled || profile.hasAccessAt(now) -> TrialOfferKind.NONE
    profile.trial?.state == "available" -> TrialOfferKind.START
    profile.trial?.state == "needs_verify" -> TrialOfferKind.CONFIRM_EMAIL
    else -> TrialOfferKind.NONE
}

fun trialButton(days: Int): String =
    if (days > 0) "Попробовать бесплатно — ${days.toLong().let { "$it ${plural(it, "день", "дня", "дней")}" }}"
    else "Попробовать бесплатно"

/** After the confirmation letter went out again. */
const val LETTER_SENT = "Письмо отправлено ещё раз. Откройте ссылку из него, затем нажмите «Я подтвердил почту»."

const val CONFIRM_EMAIL_TEXT =
    "Чтобы начать пробный период, подтвердите почту — ссылка в письме, которое пришло после регистрации."

/** On the profiles page during a trial alone: one profile is the whole allowance, and adding is paid. */
const val TRIAL_ONE_PROFILE =
    "На пробном периоде доступен один профиль. Чтобы подключить больше устройств, оформите подписку на сайте."

/** A trial and nothing paid: the profiles page shows the trial's one profile and no adding. */
fun trialOnly(profile: Profile, now: Instant = Instant.now()): Boolean =
    profile.activeAt(now) != true && profile.trialActiveAt(now)

/** The profiles page of an account with no access: the server lists nothing then. */
const val NO_ACCESS_PROFILES =
    "Профили появятся после оформления подписки или начала пробного периода."

/** The site's page for the APK; the app never follows a link the server sends. */
const val DOWNLOAD_URL = "https://sov3r3ign.com/download/android"

/** In the sheet of the trial's profile, in place of removal. */
const val TRIAL_PROFILE_NOTE = "Пробный профиль удалится сам, когда закончится пробный период."

/**
 * Whether the site offers a newer APK than this one. Compared by versionCode,
 * which grows with every release; a release that is not available, or reads
 * as zero, is never newer.
 */
fun updateAvailable(currentCode: Int, release: com.sov3r3ign.app.api.AppRelease?): Boolean =
    release != null && release.available && release.versionCode > currentCode

fun updateLine(release: com.sov3r3ign.app.api.AppRelease): String =
    "Доступна новая версия приложения ${release.versionName}"

/*
 * What the app calls the account's configs: "профиль" (decided 2026-09-30 on
 * the design canvas). The API and the code keep "device"; the words people
 * read say профиль.
 */

/** Asked before a profile is removed. */
const val DELETE_QUESTION = "Вы уверены, что хотите удалить этот профиль?"

/** Under the question; what removal does depends on whose profile it is. */
fun deleteExplanation(onThisPhone: Boolean): String =
    if (onThisPhone) {
        "Подключение будет разорвано. Чтобы подключиться снова — выберите другой профиль или добавьте заново."
    } else {
        "Если этот профиль включён на другом телефоне или компьютере, связь там пропадёт."
    }

/** Said once, when the list shows this phone's profile is gone from the account. */
const val DEVICE_GONE =
    "Профиль этого телефона удалён с аккаунта, подключение разорвано. " +
        "Выберите другой профиль или добавьте новый."

/**
 * What to do when the plan has no room. Moving to the extended plan is advice
 * only for the basic one: on the extended plan all five places are taken, and
 * the same advice would read as a mistake. An unknown plan gets the advice
 * that is true on every plan.
 */
fun planFullAdvice(plan: String?): String =
    if (plan != null && plan.lowercase().startsWith("basic")) {
        "Воспользуйтесь тарифом «Расширенный», чтобы подключить до 5 устройств."
    } else {
        "Удалите один из профилей, чтобы добавить новый."
    }

/** The landing's plans, for "Тарифы на сайте". */
const val PLANS_URL = "https://sov3r3ign.com/#tariffs"

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
 * No first handshake this long after the tunnel came up. It normally takes
 * well under a second (65 ms measured at stage 0), and the tunnel retries
 * every 5 s; 20 s without one is not a slow network.
 */
const val NO_FIRST_ANSWER_SECONDS = 20L

/** What the main screen draws: the route lit, dark, or broken, and the button's job. */
enum class Link { OFF, CONNECTING, ON, NO_ANSWER }

data class ConnectionStatus(val link: Link, val title: String, val detail: String, val action: String)

/**
 * The status under the button, and what the button does next. "Connected" is
 * only said while the server has answered recently: a tunnel can be up on the
 * phone and carry nothing, and a customer told they are connected will blame
 * the sites, not us.
 */
fun connectionStatus(
    up: Boolean,
    busy: Boolean,
    handshakeUnixSeconds: Long?,
    nowUnixSeconds: Long,
    upSinceUnixSeconds: Long? = null,
): ConnectionStatus {
    if (busy) return ConnectionStatus(Link.CONNECTING, "Подключение…", "", "Подождите")
    if (!up) return ConnectionStatus(
        Link.OFF, "Отключено", "Нажмите «Подключить», чтобы включить защищённое соединение.", "Подключить",
    )
    val h = handshakeUnixSeconds
    if (h == null || h <= 0L) {
        // Never answered since connecting: the path to the server is shut in
        // this network (seen on some mobile networks and public Wi-Fi), or
        // the key is no longer on the server. Another network tells which.
        val since = upSinceUnixSeconds
        return if (since != null && nowUnixSeconds - since > NO_FIRST_ANSWER_SECONDS) {
            ConnectionStatus(
                Link.NO_ANSWER, "Нет связи с сервером",
                "Сервер не отвечает с момента подключения. Возможно, эта сеть не пропускает VPN — " +
                    "попробуйте другую: Wi-Fi или мобильный интернет.",
                "Переподключить",
            )
        } else {
            ConnectionStatus(Link.CONNECTING, "Подключение…", "Ждём ответа сервера", "Отключить")
        }
    }
    val age = (nowUnixSeconds - h).coerceAtLeast(0L)
    return if (age <= STALE_HANDSHAKE_SECONDS) {
        ConnectionStatus(Link.ON, "Подключено", "Сервер ответил $age с назад", "Отключить")
    } else {
        // It answered, then stopped: most often the mobile network dropped the
        // path (the journal's incidents), and a reconnect restores it.
        ConnectionStatus(
            Link.NO_ANSWER, "Нет связи с сервером",
            "Связь пропала ${age / 60} мин назад. Переподключитесь; если не поможет — смените сеть.",
            "Переподключить",
        )
    }
}

/** Why the tunnel would not start, by the library's reason name, kept apart from the library for tests. */
fun tunnelFailure(reason: String?): String = when (reason) {
    // Also what another app's always-on VPN looks like from here.
    "VPN_NOT_AUTHORIZED" -> "Android не дал этому приложению включить VPN. Нажмите «Подключить» и разрешите; " +
        "если в настройках включён постоянный VPN другого приложения, выключите его."
    "TUN_CREATION_ERROR", "UNABLE_TO_START_VPN" ->
        "Android не запустил VPN. Если работает другое VPN-приложение, выключите его и попробуйте снова."
    "DNS_RESOLUTION_FAILURE" -> "Не удалось найти адрес сервера VPN. Проверьте, что интернет работает."
    "BAD_CONFIG", "TUNNEL_MISSING_CONFIG" -> "Сохранённый профиль не читается. Выберите профиль заново."
    null -> "Не удалось включить VPN"
    else -> "Не удалось включить VPN ($reason)"
}

/** The tunnel went down, and not because of this app. */
const val STOPPED_FROM_OUTSIDE =
    "VPN выключен системой или другим VPN-приложением. Нажмите «Подключить», чтобы включить снова."
