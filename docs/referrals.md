# Referrals and account credit — design

Not built yet. This is the design agreed on 2026-09-22, written down so the
decisions survive and so the reasoning is available when the code is written.

A paying customer generates a code. Someone new buys with it and pays less.
The customer who referred them gets credit toward their own renewal.

Credit is money the service owes. Everything below is shaped by that.

## Decisions

| | |
|---|---|
| Point value | 1 point = 1 ₽ |
| Referral reward | flat 175 points, any qualifying purchase |
| Qualifying purchase | more than one month — so 3m or 6m |
| Credit may cover | at most 50% of an order |
| Credit expires | 6 months after it vests |
| Invitee discount | 10% of the plan price |

## What a point is, precisely

A point is a promise to accept 1 ₽ less on a future order. It is not money:
it cannot be withdrawn, transferred, or refunded in cash. That has to be true
in the terms as well as in the code, or the service has created an obligation
it never meant to take on.

## Schema

### `credit_entries` — an append-only ledger

Balance is `SUM(delta)` over a customer's vested, unexpired entries. It is not
a column on `users`.

A stored balance is a number that can drift from the events that produced it,
and when a customer asks why they have 350 rather than 525 there is nothing to
answer with. A ledger answers that question by construction, and at this scale
the sum costs nothing.

| column | notes |
|---|---|
| `id` | |
| `user_id` | whose balance this affects |
| `delta` | signed; `+175` for a reward, negative for a spend |
| `reason` | `referral_reward` \| `spend` \| `expiry` (manual only) \| `adjustment` |
| `payment_id` | the order this entry was spent on, for `spend` |
| `source_payment_id` | the referred purchase that earned it, for `referral_reward` |
| `vests_at` | when it becomes spendable — see vesting |
| `expires_at` | `vests_at + 6 months` |
| `created_at` | |
| `note` | free text, for `adjustment` |

`UNIQUE (reason, source_payment_id)` makes the reward idempotent for free.
Gateway webhooks retry; a reward must be credited exactly once, and the
database should be what guarantees that rather than the code remembering to
check.

### `promo_codes`

| column | notes |
|---|---|
| `code` | short, unique, case-insensitive |
| `owner_user_id` | the referrer; `NULL` for a campaign code with no owner |
| `discount` | amount off in ₽ |
| `max_uses`, `uses` | a referral code is not exhausted by one use |
| `active`, `expires_at` | |

## Flows

### Generating a code

Offered only to a customer with at least one paid purchase. One active code
per customer; regenerating deactivates the previous one rather than
accumulating them.

### Buying with a code

1. Look up the code. Reject if inactive, expired, exhausted, or owned by the
   buyer — nobody refers themselves.
2. Compute `amount = plan price − discount`.
3. If the buyer also spends credit, subtract it, but never more than 50% of
   the amount after discount, and never below the gateway's minimum payment.
4. Write `Payment` with the computed `amount`. **That stored amount — not the
   plan price — is what the webhook verifies against.**
5. Write the negative `spend` entries against the specific entries being
   consumed, oldest first, so expiry stays predictable.

If the payment never completes, the spend entries are reversed. Simplest
correct approach: write them only when the webhook confirms payment, and hold
the intended spend on the `Payment` row until then.

### Earning the reward

On a confirmed payment that used a code with an owner, and whose plan is
longer than one month:

```
delta            = +175
vests_at         = now + 14 days
expires_at       = vests_at + 6 months
source_payment_id = the referred payment
```

The reward is calculated on the **cash part** of the referred purchase. A
purchase half-paid with credit does not earn a full reward — otherwise two
accounts can pass credit back and forth and grow it on every lap.

### Spending

Only vested, unexpired entries count toward the balance. Spending consumes
the oldest first.

### Expiry

Expiry is a condition on the sum, not a job. `balance()` counts entries whose
`expires_at` is still in the future, so credit stops being spendable the
moment it expires — nothing has to run, and there is no sweep that can fail
quietly and leave expired credit spendable.

The first draft did write a cancelling `expiry` entry as well, and
double-counted: the sum already excluded the expired entry, so the offsetting
one drove the balance to −175. The tests caught it. The ledger still explains
itself without that entry — the original carries the date it expired on,
which is what the customer needs to see.

`reason = 'expiry'` stays in the schema for a manual write-off; nothing
produces it automatically.

## The four holes, and what closes each

**Refund after reward.** The friend buys six months with my code, the reward
lands, the friend exercises their right to a refund the next day, and I keep
the credit. The terms allow that refund at any time, so this is not a corner
case.

Closed by vesting: credit is written immediately but spendable only after 14
days. A refunded purchase never vests. This prevents the loss rather than
chasing it afterwards, which matters because chasing it means a negative
balance on an account that may already have spent the credit.

**Self-referral.** Own code rejected against own purchase. Beyond that, the
economics are the real defence: the smallest qualifying purchase is 900 ₽ and
the reward is 175 points, capped at half an order and expiring in six months.
A fake account costs several times what it earns. Email registration cannot
keep sockpuppets out; making them unprofitable can, and it keeps working
without anyone watching.

**Stacked discounts.** Both a code and credit on one order could otherwise
drive the total to nothing. The 50% cap holds, and the result is floored at
the gateway's minimum. Every purchase stays a real transaction: months of zero
revenue against live server costs is not a thing this service can absorb.

**Credit earned on credit.** Rewards are computed on cash received, so credit
cannot breed.

## What changes in code that already exists

**The amount check must move.** Today the FreeKassa webhook compares the
reported amount against the plan price:

```python
# The amount comes from PLANS, never from the request.
expected = float(info["amount"]) if info else None
```

The intent — never trust the request — stays right. But once a discount
exists, the plan price is no longer what was asked for, and every discounted
payment would be rejected as `amount_mismatch`. The trusted value becomes
`payment.amount`: still server-computed, still not from the request, but now
the amount actually requested. `Payment.amount` already exists.

**Heleket invoices** are created from the plan price the same way and need the
same change.

**`Payment` gains** the promo code used and the credit intended, so a pending
order remembers what it was supposed to cost.

## Terms

None of this can ship before the offer says:

- credit is not money: no withdrawal, no transfer, no cash refund;
- it expires six months after it becomes available;
- it covers at most half an order;
- a reward is cancelled if the purchase that earned it is refunded;
- the service may cancel credit obtained by abuse, and say plainly what that
  means — self-referral and fake accounts.

Selling against a document that does not describe the credit is the same
mistake as selling plans against a document that quoted one price: the offer
is the contract.

## Deliberately not built

Withdrawal of credit as cash. Transfer between accounts. Multi-level rewards.
Percentage-based rewards that scale with the purchase. Each adds an
accounting or abuse surface that a service with no paying customers cannot
justify.

## What a referral costs

10% off the plan price, plus the 175-point reward:

| Purchase | Cash after discount | Discount | Total cost | Share of order |
|---|---|---|---|---|
| basic-3m — 900 | 810 | 90 | 265 | 29% |
| basic-6m — 1700 | 1530 | 170 | 345 | 20% |
| ext-3m — 1700 | 1530 | 170 | 345 | 20% |
| ext-6m — 3200 | 2880 | 320 | 495 | 15% |

A flat discount was considered first, on the reasoning that a percentage costs
most where the margin is thinnest. In absolute terms that is true — 320 ₽ off
the largest order against 90 ₽ off the smallest. As a share of the order it is
the other way round, because the flat 175-point reward dominates a small
purchase: a flat 150 ₽ discount would have cost 325 ₽ on a 900 ₽ order, more
than the percentage does.

The percentage is also the one that scales with what the buyer is committing
to, which is what a discount is supposed to do.

The reward is a liability rather than a cost until it is redeemed, is capped
at half an order, and expires six months after vesting — so the real figure
sits below the one in the table. Both numbers are constants and can move.
