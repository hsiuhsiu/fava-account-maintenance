# Changelog

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
