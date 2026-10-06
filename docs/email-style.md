# Letters — how Sovereign writes to customers

Every letter is built in `pwa/services/mailer.py` from one set of components,
and `tests/test_letters.py` holds each of them to the rules below. To see them
all before a deploy:

```bash
python3 tools/preview_emails.py        # -> /tmp/sovrn-letters/index.html
```

## What a letter is for

A letter exists because something happened that the customer needs to know
or act on: an account was created, a payment arrived, a password reset was
asked for, a period is ending. No newsletters, no "we miss you", nothing sent
because it would be nice to remind people we exist. A letter that does not
need to be sent is the one that teaches people to ignore the next.

## Rules

1. **One letter, one action.** A single primary button. Anything secondary
   (the trial in the welcome letter) is a *callout* — information, never a
   second button competing with the first.
2. **The subject says what happened or what to do**, then `— Sovereign`:
   «Подтвердите почту — Sovereign», «Оплата получена — Sovereign». No
   exclamation marks, no emoji, no "Важно!".
3. **A preheader** — the grey line a mail list shows after the subject. It
   finishes the subject's thought: «Остался один шаг — подтвердите адрес.»
4. **Every button's address is spelled out** under a divider. Some clients
   drop button styling, and a careful reader checks where a link goes before
   following it — the more careful the reader, the more this matters for a
   service like ours.
5. **A plain-text part** with the same content and the same link.
6. **The footer says why this address got the letter.** «Вы получили это
   письмо, потому что…». A letter that does not say why it came is the one
   that gets marked as spam.
7. **Public wording.** Letters are public text: the same vocabulary rule as
   the site (`tests/test_public_wording.py` reads the mailer's source).
8. **Language** — the one the account was created in (`users.lang`).
9. **Nothing from a request goes into HTML unescaped.**

## Voice

- «Вы» with a lower-case «в». Calm, short sentences. Say what happened, then
  what to do, then anything worth knowing.
- Name the consequence, not the mechanism: «на него придут чек и ссылка для
  восстановления пароля», not «для верификации учётной записи».
- Time limits are stated plainly and once: «Ссылка действует 48 часов».
- If the customer might not have caused the letter (registration, reset),
  tell them what to do then — usually nothing: «просто удалите письмо».

## Anatomy

```
[mark] Sovereign                       ← header, links to the site
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ← accent edge
  РЕГИСТРАЦИЯ                          ← eyebrow: what kind of letter
  Добро пожаловать, ivan_1             ← heading
  One or two sentences.                ← body
  [ Подтвердить почту → ]              ← the one action
  ┌ 3 ДНЯ БЕСПЛАТНО ─────────────┐     ← callout (optional)
  └ secondary fact               ┘
  ЧТО ДАЛЬШЕ                           ← section label
  ① step  ② step  ③ step                ← steps (optional)
  ──────────────                       ← divider
  the link, spelled out                ← fallback
  validity, "if it wasn't you"         ← fine print
Личный кабинет · Поддержка · Соглашение  ← footer links
Why you got this. © Sovereign            ← reason
```

Components: `_wrap`, `_eyebrow`, `_h`, `_p`, `_button`, `_callout`,
`_section`, `_steps`, `_facts` (label/value rows, as on a receipt),
`_divider`, `_fallback_link`.

## Technical constraints

- Mail clients ignore `<style>`, CSS variables and most layout CSS. Layout is
  tables with inline styles; colours are written where they are used, with
  `bgcolor` attributes as well for Outlook.
- The palette is the portal's: background `#080c0f`, card `#0d1318`, border
  `#1e2d38`, text `#d8eaf6` / `#7a9fb5` / `#e8f4ff`, accent `#00d4ff`.
- The letters are dark by design and declare `color-scheme: dark`. Gmail's
  and Outlook's own dark modes may still recolour parts of them; check the
  welcome letter in Gmail (web and app) and in Yandex Mail after any change
  to the frame.
- The only image is the mark, loaded from `/static/icons/icon-192.png` on the
  live site. With images blocked the wordmark next to it still reads.
- Letters sent from a gateway callback go through `send_later`, so the
  gateway is answered without waiting on Resend.

## Letters today

| Letter | When | Action |
|---|---|---|
| Welcome + confirmation | registration | confirm email |
| Confirmation again | «отправить ещё раз» | confirm email |
| Receipt | payment activated | open account |
| Password reset | «забыли пароль» / settings | set a new password |

Planned with in-portal notifications: period ending in 3 days / 1 day /
ended, for both subscriptions and trials.
