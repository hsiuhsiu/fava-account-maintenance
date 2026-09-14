# Changelog

## 0.3.0+personal.1 - 2026-09-13

- Rebase the personal Balance freshness workflow onto public version 0.3.0.
- Preserve perpetual-zero guards, next-day Balance checkpoints, and account-copy
  controls while inheriting the public tracking-policy metadata.

## 0.3.0 - 2026-09-13

- Add `transactions_complete_from` account metadata for explicitly accepted
  historical cutovers while continuing to flag Pads on or after the boundary.
- Add `tracking_mode: "balance-only"` for accounts intentionally maintained from
  source-backed balance snapshots without complete transaction detail.
- Show tracking-policy badges, boundary validation, and account/group counts in
  the maintenance report.

## 0.2.2 - 2026-09-13

- Preserve colon separators in client-generated account URLs so Fava's frontend
  router receives the real Beancount account name.

## 0.2.1+personal.3 - 2026-09-10

- Accept a next-day Balance assertion as a current freshness checkpoint, matching
  Beancount's beginning-of-day processing order.
- Keep Balance assertions more than one day ahead out of freshness calculations.

## 0.2.1+personal.2 - 2026-09-10

- Treat a zero Balance assertion dated in 2099 as a perpetual-zero guard when
  the account/currency is currently zero and has no known future postings.
- Remove guarded account/currency pairs from the Balance freshness queue.
- Add one-click account-name copying to the Balance tables.

## 0.2.1+personal.1 - 2026-08-31

- Rebase the personal variant onto the public 0.2.1 release while preserving
  the ledger-specific Balance 更新 workflow.
- Count Balance assertions, including future-dated assertions, as account
  activity for dormant-account detection.
- Keep future Balance assertions out of current balance-freshness calculations.

## 0.2.1 - 2026-08-31

- Count Balance assertions as account activity for dormant-account detection.
- Let future-dated Balance assertions refresh activity without changing the
  report's as-of inventory, price, or balance-freshness calculations.
- Clamp inactivity to zero when the latest activity is future-dated.

## 0.2.0+personal.1 - 2026-08-30

- Preserve the ledger-specific Balance 更新 queue on the `personal` branch.
- Install this variant directly from GitHub rather than PyPI.

## 0.2.0 - 2026-08-30

- Keep the public package focused on reusable account-audit views.
- Remove the ledger-specific `balance_frequency` policy and Balance 更新 queue.
- Open the account-tree overview by default.

## 0.1.1 - 2026-08-30

- Publish the package through PyPI for a one-command installation.
- Add a dedicated Trusted Publishing workflow with short-lived OIDC credentials.
- Make the PyPI installation command the primary README path.

## 0.1.0 - 2026-08-30

- Initial public GitHub release.
- Add account-tree, balance-freshness, lifecycle, Pad, buffer, and historical-boundary views.
- Add configurable account conventions, synthetic examples, tests, and package metadata.
