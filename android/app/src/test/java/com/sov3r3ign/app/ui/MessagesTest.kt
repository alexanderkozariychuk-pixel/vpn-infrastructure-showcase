package com.sov3r3ign.app.ui

import com.sov3r3ign.app.api.ApiError
import com.sov3r3ign.app.api.Profile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
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
}
