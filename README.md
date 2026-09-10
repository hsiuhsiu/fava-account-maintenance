# Fava Account Maintenance — personal branch

This branch keeps a ledger-specific **Balance 更新** workflow based on the
custom `balance_frequency` metadata. The reusable public package is maintained
on [`main`](https://github.com/hsiuhsiu/fava-account-maintenance/tree/main) and
published to PyPI without that workflow.

Fava Account Maintenance is a read-only Fava extension for understanding a
large Beancount chart of accounts. It combines an account tree with operational
views for balance freshness, dormant or unused accounts, account lifecycle,
historical boundaries, Pad usage, and temporary buffer accounts.

The report UI is currently written in Traditional Chinese. The source and the
example ledger contain only synthetic account names and amounts.

## What it shows

- A collapsible tree built from the ledger's Assets, Liabilities, and Equity
  roots.
- A default **Balance 更新** queue: never-balanced accounts first, then partial
  multi-commodity balances, overdue accounts, and accounts nearest their due
  date.
- Open, closed, future, unused, dormant-zero, and dormant-nonzero accounts.
- Activity includes ordinary transaction postings and Balance assertions.
  Future-dated Balance assertions count as maintenance activity without changing
  the report's as-of inventory or price calculations.
- Whether an account explicitly started at zero, was seeded from Equity, or
  began with Pad.
- Late or repeated Pad directives that may indicate a historical gap.
- Declared transaction-history cutovers and accounts intentionally maintained
  from balance snapshots rather than complete transaction detail.
- Configurable investment, buffer, and Equity-role conventions.

The extension does not edit the ledger and does not make network requests.

## Compatibility

Version 0.3.0+personal.1 is based on public version 0.3.0 and tested with Fava
1.30.12, Beancount 3.2, and Python 3.12.
The dependency is intentionally limited to Fava 1.30.x until newer versions are
tested. Fava describes its extension API as unstable, so test upgrades before
deploying them to a production ledger.

## Install

Install this branch into the same Python environment that runs Fava:

```sh
python -m pip install --upgrade --force-reinstall \
  "fava-account-maintenance @ git+https://github.com/hsiuhsiu/fava-account-maintenance.git@personal"
```

For a reproducible server deployment, replace `personal` with the exact commit
hash currently at the tip of that branch.

If Fava was installed with `pipx`, inject the extension into that environment:

```sh
pipx inject --force fava \
  "fava-account-maintenance @ git+https://github.com/hsiuhsiu/fava-account-maintenance.git@personal"
```

To install the reusable public version instead:

```sh
python -m pip install fava-account-maintenance
```

For a local checkout:

```sh
python -m pip install ./fava-account-maintenance
```

Then enable the extension in the main Beancount file:

```beancount
2000-01-01 custom "fava-extension" "fava_account_maintenance"
```

Fava also searches the directory containing the main Beancount file. For a
drop-in installation, copy the complete `fava_account_maintenance` package
directory next to that file; keep `UpdateGuidance.js` and the `templates`
directory inside the package.

### Docker

The extension and ledger can remain in separate repositories. Mount the source
directory read-only and add it to `PYTHONPATH`:

```yaml
services:
  fava:
    volumes:
      - ./ledger:/ledger
      - ./fava-account-maintenance/src:/extensions:ro
    environment:
      PYTHONPATH: /extensions
```

Recreate the container after changing the extension version. A production image
can instead install a tagged release during its build.

## Ledger metadata

Balance freshness is opt-in per account. The value is a number of days:

```beancount
2020-01-01 open Assets:Household:Checking:Example USD
  balance_frequency: 30
  nickname: "Daily checking"
  purpose: "Household cash flow"
```

Supported `open` metadata:

| Key | Meaning |
| --- | --- |
| `balance_frequency` | Expected number of days between Balance assertions. |
| `nickname` | Short label displayed beside the full account name. |
| `purpose` | Reminder of why the account exists. |
| `tracking_mode` | Omit for complete transaction tracking; use `"balance-only"` when source-backed balance snapshots are authoritative and individual activity may be incomplete. |
| `transactions_complete_from` | Native Beancount date for the first day whose transaction history is required to be complete. |
| `maintenance_kind` | Overrides the account-kind component for this account. |
| `maintenance_buffer` | `TRUE` or `FALSE` override for buffer detection. |
| `maintenance_role` | Equity role override; see the configuration section. |

For example:

```beancount
2020-01-01 open Equity:Opening-Balances
  maintenance_role: "opening_history"

2020-01-01 open Assets:Household:Clearing:Transfers USD
  maintenance_buffer: TRUE
```

### Historical cutovers and balance-only accounts

Use a declared cutover when older activity has been accepted as untraceable but
transactions must be complete from a known date onward:

```beancount
2015-04-16 open Assets:Household:Mileage:Hotel POINT
  transactions_complete_from: 2021-10-05

2021-10-04 pad Assets:Household:Mileage:Hotel Equity:Opening-Balances
2021-10-05 balance Assets:Household:Mileage:Hotel  94638 POINT
```

The cutover date is the first date covered by the completeness promise. Because
Beancount processes a Balance assertion before same-day transactions, a Balance
on that date anchors the prior history. Pads strictly before the date are treated
as accepted history; a Pad on or after the date remains a review issue. A past or
present cutover without a same-day Balance is also shown for review.

For an account whose ongoing source balance matters but whose individual
activity is intentionally incomplete, use balance-only tracking:

```beancount
2023-11-08 open Assets:Household:Mileage:Rewards POINT
  tracking_mode: "balance-only"
```

Known transactions may still be recorded, but repeated Pad directives are
expected and are not treated as history gaps. Balance-only does not disable
other lifecycle, dormancy, buffer, or balance-freshness checks supplied by a
deployment. Do not use it merely to hide unresolved ordinary bank or credit-card
activity; it explicitly means transaction-flow reports for that account may be
incomplete.

Both fields describe bookkeeping policy and should be set deliberately rather
than inferred automatically. `tracking_mode` defaults to `"transactions"` and
must not be combined with `transactions_complete_from` when set to
`"balance-only"`.

To mark an account/currency as permanently zero, use a zero Balance in year
2099:

```beancount
2099-01-01 balance Assets:Household:Checking:Finished  0 USD
```

The guard suppresses Balance freshness only while the current inventory remains
zero and the ledger contains no future transaction postings in that currency.
This lets a genuinely scheduled future account continue to appear until its
planned activity has finished.

## Extension configuration

Configuration is optional. Fava passes the last string in the custom directive
as a Python-literal mapping:

```beancount
2000-01-01 custom "fava-extension" "fava_account_maintenance" "{'dormant_days': 180, 'buffer_components': ['Buffer', 'Clearing'], 'equity_roles': {'Equity:Opening-Balances': 'opening_history'}, 'source_mode': 'basename'}"
```

| Option | Default | Meaning |
| --- | --- | --- |
| `dormant_days` | `365` | Inactivity threshold for dormant accounts. |
| `kind_component_index` | `2` | Zero-based account component used as kind; `Assets` is component 0. |
| `investment_kinds` | common investment labels | Kinds whose commodity balances and prices are checked individually. |
| `buffer_components` | `['Buffer']` | Exact account components treated as temporary buffers. |
| `equity_roles` | `{}` | Account-prefix to Equity-role mapping. Longest prefix wins. |
| `source_mode` | `'basename'` | Source display: `'hidden'`, `'basename'`, or `'relative'`. |
| `source_root` | unset | Root removed from source paths in `'relative'` mode. |

Allowed Equity roles are `technical`, `modeled_asset`, `opening_history`,
`untraceable`, `dust`, `revaluation`, `buffer`, and `other`.

The default kind index works for both `Assets:Bank:Checking` and
`Assets:Owner:Checking:Bank`. Use `maintenance_kind` when a particular account
does not follow the general convention.

## Privacy and deployment boundary

The repository does not need, include, or transmit a ledger. At runtime,
however, the report necessarily sends its derived model to the browser. That
model includes account names, native-currency inventories, lifecycle and
activity dates, Pad sources, counterpart accounts, and—unless hidden—source
basenames and line numbers.

Therefore:

- Protect the Fava instance with the same care as the ledger.
- Do not publish a saved report page, browser archive, screenshot, cache, or
  application log made from a real ledger.
- Do not expose the Fava server directly to the public internet.
- Use `{'source_mode': 'hidden'}` if source locations are not useful.

The source-path formatter never returns an absolute path. In `relative` mode,
paths outside `source_root` fall back to their basename.
These settings control this extension's model only; Fava itself may expose
ledger filenames in its standard page data, which is another reason the Fava
instance must remain private.

## Branch maintenance

`main` is the public branch and the only source of PyPI releases. `personal` is
a small private-use overlay that keeps the Balance 更新 workflow. After each
public release:

1. Rebase `personal` onto the released `main` commit.
2. Resolve only the personal Balance-workflow differences and bump the local
   version to `<public-version>+personal.<revision>`.
3. Run lint, tests, and a package build, then update `personal` with
   `--force-with-lease`.
4. Pin deployments to the resulting exact personal commit.

Do not create a `v*` release tag from `personal` or publish its local-version
build to PyPI.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m build
```

The wheel must contain both `UpdateGuidance.js` and
`templates/UpdateGuidance.html`; Fava loads those files directly without a Node
build step.

## License

MIT
