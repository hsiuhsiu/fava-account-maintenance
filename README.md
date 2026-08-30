# Fava Account Maintenance

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
- Whether an account explicitly started at zero, was seeded from Equity, or
  began with Pad.
- Late or repeated Pad directives that may indicate a historical gap.
- Configurable investment, buffer, and Equity-role conventions.

The extension does not edit the ledger and does not make network requests.

## Compatibility

Version 0.1.0 is tested with Fava 1.30.12, Beancount 3.2, and Python 3.12.
The dependency is intentionally limited to Fava 1.30.x until newer versions are
tested. Fava describes its extension API as unstable, so test upgrades before
deploying them to a production ledger.

## Install

Install the package into the same Python environment that runs Fava:

```sh
python -m pip install \
  "git+https://github.com/hsiuhsiu/fava-account-maintenance.git@v0.1.0"
```

For a local checkout:

```sh
python -m pip install ./fava-account-maintenance
```

If Fava was installed with `pipx`, inject the extension into that environment:

```sh
pipx inject fava \
  "git+https://github.com/hsiuhsiu/fava-account-maintenance.git@v0.1.0"
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
