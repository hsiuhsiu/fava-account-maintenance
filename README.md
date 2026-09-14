# Fava Account Maintenance

Fava Account Maintenance is a read-only Fava extension for understanding a
large Beancount chart of accounts. It combines an account tree with operational
views for dormant or unused accounts, account lifecycle, historical boundaries,
Pad usage, and temporary buffer accounts.

The report UI is currently written in Traditional Chinese. The source and the
example ledger contain only synthetic account names and amounts.

## What it shows

- A collapsible tree built from the ledger's Assets, Liabilities, and Equity
  roots.
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

Version 0.2.2 is tested with Fava 1.30.12, Beancount 3.2, and Python 3.12.
The dependency is intentionally limited to Fava 1.30.x until newer versions are
tested. Fava describes its extension API as unstable, so test upgrades before
deploying them to a production ledger.

## Install

Install the package into the same Python environment that runs Fava:

```sh
python -m pip install fava-account-maintenance
```

If Fava was installed with `pipx`, inject the extension into that environment:

```sh
pipx inject fava fava-account-maintenance
```

To install a tagged GitHub version directly:

```sh
python -m pip install \
  "git+https://github.com/hsiuhsiu/fava-account-maintenance.git@v0.2.2"
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

```beancount
2020-01-01 open Assets:Household:Checking:Example USD
  nickname: "Daily checking"
  purpose: "Household cash flow"
```

Supported `open` metadata:

| Key | Meaning |
| --- | --- |
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
