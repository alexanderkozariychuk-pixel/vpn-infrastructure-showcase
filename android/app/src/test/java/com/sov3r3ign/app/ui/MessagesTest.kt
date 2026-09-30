package com.sov3r3ign.app.ui

import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.Profile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.ZoneId

class MessagesTest {

    private val moscow = ZoneId.of("Europe/Moscow")

    @Test
    fun `a full registration form passes`() {
        assertNull(validateRegistration("alex", "a@b.ru", "12345678", "12345678"))
    }

    @Test
    fun `registration catches what the server would not`() {
        assertEquals("Введите имя пользователя", validateRegistration(" ", "a@b.ru", "12345678", "12345678"))
        assertEquals("Проверьте email", validateRegistration("alex", "a@b", "12345678", "12345678"))
        assertEquals("Пароль — не короче 8 символов", validateRegistration("alex", "a@b.ru", "1234567", "1234567"))
        assertEquals("Пароли не совпадают", validateRegistration("alex", "a@b.ru", "12345678", "12345679"))
    }

    @Test
    fun `a device name is checked before the server sees it`() {
        assertNull(validateDeviceName("phone"))
        assertNull(validateDeviceName(" tab "))
        assertEquals("Введите название устройства", validateDeviceName("  "))
        assertEquals("Название — не длиннее 6 символов", validateDeviceName("Galaxy A71"))
    }

    @Test
    fun `a device name follows the portal's rule, since it becomes a file name`() {
        assertNull(validateDeviceName("a_b-1"))
        assertNull(validateDeviceName("A71"))
        assertEquals("Только латинские буквы, цифры, - и _", validateDeviceName("тел"))
        // Cyrillic "р" and "о" that look Latin are still refused.
        assertEquals("Только латинские буквы, цифры, - и _", validateDeviceName("рhоne"))
        assertEquals("Только латинские буквы, цифры, - и _", validateDeviceName("my ph"))
        assertEquals("Только латинские буквы, цифры, - и _", validateDeviceName("a.b"))
        // Too long is said first: shortening is the fix the customer needs.
        assertEquals("Название — не длиннее 6 символов", validateDeviceName("Телефон"))
    }

    @Test
    fun `sign-in needs both fields`() {
        assertEquals("Введите имя пользователя и пароль", validateSignIn("alex", ""))
        assertNull(validateSignIn("alex", "x"))
    }

    @Test
    fun `the same 401 reads differently at sign-in and later`() {
        assertEquals("Неверное имя пользователя или пароль", describe(ApiError.Unauthorized, Action.SIGN_IN))
        assertEquals("Сессия истекла — войдите снова", describe(ApiError.Unauthorized, Action.LOAD))
    }

    @Test
    fun `a registration conflict says which field is taken`() {
        assertEquals("Этот email уже зарегистрирован",
            describe(ApiError.Conflict("Email already registered"), Action.REGISTER))
        assertEquals("Такое имя пользователя уже занято",
            describe(ApiError.Conflict("Username 'alex' already exists"), Action.REGISTER))
    }

    @Test
    fun `a device that is gone says so, not that the server is down`() {
        assertEquals("Устройство не найдено — возможно, его удалили на сайте. Список обновлён.",
            describe(ApiError.NotFound, Action.LOAD))
    }

    @Test
    fun `a lapsed subscription points to renewal, not to sign-in`() {
        assertEquals("Подписка закончилась. Продлить её можно на сайте.",
            describe(ApiError.SubscriptionLapsed, Action.LOAD))
    }

    // A fixed "now", so the tests do not start failing when the calendar passes their dates.
    private val sept26 = Instant.parse("2026-09-26T12:00:00Z")

    @Test
    fun `the expiry date is shown in the phone's zone`() {
        val p = Profile("paid", null, true, "2026-10-12T09:26:42.848714")
        assertEquals("Подписка до 12 октября 2026", subscriptionLine(p, moscow, sept26))
    }

    @Test
    fun `late evening UTC is already tomorrow in Moscow`() {
        val p = Profile("paid", null, true, "2026-10-12T22:30:00")
        assertEquals("Подписка до 13 октября 2026", subscriptionLine(p, moscow, sept26))
        assertEquals("Подписка до 12 октября 2026", subscriptionLine(p, ZoneId.of("UTC"), sept26))
    }

    @Test
    fun `production's timestamp with an offset is read, not crashed on`() {
        // The exact value that crashed the first build on a real account.
        val p = Profile("alex", null, true, "2026-09-19T19:11:04.609756+00:00")
        assertEquals("Подписка закончилась 19 сентября 2026", subscriptionLine(p, moscow, sept26))
    }

    @Test
    fun `a flag the sweep has not cleared yet does not make a past period active`() {
        val p = Profile("alex", null, true, "2026-09-25T00:00:00+00:00")
        assertEquals("Подписка закончилась 25 сентября 2026", subscriptionLine(p, moscow, sept26))
    }

    @Test
    fun `no flag, or no end date, is no subscription — as on the server`() {
        assertEquals("Подписки нет", subscriptionLine(Profile("lapsed", null, false, null), moscow, sept26))
        assertEquals("Подписки нет", subscriptionLine(Profile("odd", null, true, null), moscow, sept26))
    }

    @Test
    fun `an unreadable date is said plainly instead of crashing the screen`() {
        val p = Profile("paid", null, true, "next Tuesday")
        assertEquals("Подписка есть, но дату окончания не удалось прочитать", subscriptionLine(p, moscow, sept26))
    }

    @Test
    fun `connected is only said while the server answers`() {
        val now = 1_790_418_984L
        assertEquals("Подключение…", connectionLine(up = false, busy = true, handshakeUnixSeconds = null, nowUnixSeconds = now))
        assertEquals("Отключено", connectionLine(false, false, null, now))
        assertEquals("Подключено, ждём ответа сервера", connectionLine(true, false, 0L, now))
        assertEquals("Подключено · сервер отвечал 32 с назад", connectionLine(true, false, now - 32, now))
        assertEquals("Подключено · сервер отвечал 180 с назад", connectionLine(true, false, now - 180, now))
        assertEquals("Сервер не отвечает уже 3 мин. Проверьте интернет или переподключитесь.",
            connectionLine(true, false, now - 181, now))
    }

    @Test
    fun `a phone clock behind the server does not show a negative age`() {
        assertEquals("Подключено · сервер отвечал 0 с назад", connectionLine(true, false, 1000L, 990L))
    }

    // --- plan, the server's answer, the warning before the end ---------------

    private fun paid(until: String?, active: Boolean? = true, plan: String? = "basic-1m") =
        Profile("paid", null, true, until, plan, active)

    @Test
    fun `the server's active wins over a date still ahead`() {
        assertEquals("Подписка не активна", subscriptionLine(paid("2026-10-12T09:26:42", active = false), moscow, sept26))
    }

    @Test
    fun `the server's active wins over the phone's clock`() {
        // The phone thinks the 25th has passed; the server, which decides, does not.
        assertEquals("Подписка до 25 сентября 2026",
            subscriptionLine(paid("2026-09-25T00:00:00+00:00", active = true), moscow, sept26))
    }

    @Test
    fun `active without a readable date still says it runs`() {
        assertEquals("Подписка действует", subscriptionLine(paid(null, active = true), moscow, sept26))
    }

    @Test
    fun `the plan key reads as the portal shows it`() {
        assertEquals("Базовый · 1 месяц", planLabel("basic-1m"))
        assertEquals("Расширенный · 3 месяца", planLabel("ext-3m"))
        assertEquals("Расширенный · 6 месяцев", planLabel("ext-6m"))
        assertEquals("Family", planLabel("Family"))
    }

    @Test
    fun `the plan is named only while it runs`() {
        assertEquals("Тариф: Базовый · 1 месяц", planLine(paid("2026-10-12T09:26:42"), sept26))
        assertNull(planLine(paid("2026-10-12T09:26:42", active = false), sept26))
        assertNull(planLine(paid("2026-10-12T09:26:42", plan = null), sept26))
    }

    @Test
    fun `the warning starts three calendar days before the end`() {
        assertNull(expiryWarning(paid("2026-09-30T09:00:00Z"), moscow, sept26))
        assertEquals("Подписка заканчивается через 3 дня. Продлите на сайте, чтобы связь не прервалась.",
            expiryWarning(paid("2026-09-29T09:00:00Z"), moscow, sept26))
        assertEquals("Подписка заканчивается через 2 дня. Продлите на сайте, чтобы связь не прервалась.",
            expiryWarning(paid("2026-09-28T09:00:00Z"), moscow, sept26))
        assertEquals("Подписка заканчивается завтра. Продлите на сайте, чтобы связь не прервалась.",
            expiryWarning(paid("2026-09-27T09:00:00Z"), moscow, sept26))
        assertEquals("Подписка заканчивается сегодня. Продлите на сайте, чтобы связь не прервалась.",
            expiryWarning(paid("2026-09-26T18:00:00Z"), moscow, sept26))
    }

    @Test
    fun `tomorrow is counted in the phone's zone`() {
        // 22:30 UTC on the 26th is 01:30 on the 27th in Moscow.
        val p = paid("2026-09-26T22:30:00Z")
        assertEquals("Подписка заканчивается завтра. Продлите на сайте, чтобы связь не прервалась.",
            expiryWarning(p, moscow, sept26))
        assertEquals("Подписка заканчивается сегодня. Продлите на сайте, чтобы связь не прервалась.",
            expiryWarning(p, ZoneId.of("UTC"), sept26))
    }

    @Test
    fun `a longer warning window declines the days`() {
        assertEquals("Подписка заканчивается через 5 дней. Продлите на сайте, чтобы связь не прервалась.",
            expiryWarning(paid("2026-10-01T09:00:00Z"), moscow, sept26, warnDays = 7))
    }

    @Test
    fun `no warning once the period is not running — the status line says it`() {
        assertNull(expiryWarning(paid("2026-09-27T09:00:00Z", active = false), moscow, sept26))
    }

    @Test
    fun `the pay button shows when the period ends soon or is not running`() {
        assertFalse(needsPayment(paid("2026-10-12T09:26:42"), moscow, sept26))
        assertTrue(needsPayment(paid("2026-09-28T09:00:00Z"), moscow, sept26))
        assertTrue(needsPayment(paid("2026-10-12T09:26:42", active = false), moscow, sept26))
        assertTrue(needsPayment(Profile("new", null, false, null), moscow, sept26))
    }

    @Test
    fun `the delete question says what happens to whose device`() {
        assertTrue(deleteQuestion("A71", onThisPhone = true).contains("устройство этого телефона"))
        assertTrue(deleteQuestion("lap", onThisPhone = false).contains("связь там пропадёт"))
    }
}
