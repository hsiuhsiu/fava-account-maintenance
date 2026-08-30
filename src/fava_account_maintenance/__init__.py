from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from beancount.core import data
from fava.ext import FavaExtensionBase

__version__ = "0.1.0"

DEFAULT_INVESTMENT_KINDS = frozenset(
    {"Brokerage", "Education", "Edu", "Exchange", "Fund", "Investment", "Retirement"}
)
DEFAULT_BUFFER_COMPONENTS = frozenset({"Buffer"})
EQUITY_ROLES = frozenset(
    {
        "technical",
        "modeled_asset",
        "opening_history",
        "untraceable",
        "dust",
        "revaluation",
        "buffer",
        "other",
    }
)
SOURCE_MODES = frozenset({"hidden", "basename", "relative"})


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a positive integer") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a non-negative integer") from error
    if parsed < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return parsed


def _string_set(value: Any, name: str) -> frozenset[str]:
    if isinstance(value, str) or not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError(f"{name} must be a list of strings")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{name} must be a list of strings")
    return frozenset(item.strip() for item in value if item.strip())


@dataclass(frozen=True)
class AccountMaintenanceConfig:
    """Validated configuration for the account-maintenance model."""

    dormant_days: int = 365
    kind_component_index: int = 2
    investment_kinds: frozenset[str] = DEFAULT_INVESTMENT_KINDS
    buffer_components: frozenset[str] = DEFAULT_BUFFER_COMPONENTS
    equity_roles: tuple[tuple[str, str], ...] = ()
    source_mode: str = "basename"
    source_root: str | None = None

    @classmethod
    def from_value(
        cls,
        value: Mapping[str, Any] | AccountMaintenanceConfig | None,
    ) -> AccountMaintenanceConfig:
        if isinstance(value, cls):
            return value
        if value is None:
            return cls()
        if not isinstance(value, Mapping):
            raise ValueError("Account Maintenance configuration must be a mapping")

        supported = {
            "dormant_days",
            "kind_component_index",
            "investment_kinds",
            "buffer_components",
            "equity_roles",
            "source_mode",
            "source_root",
        }
        unknown = sorted(str(key) for key in value if key not in supported)
        if unknown:
            raise ValueError(
                f"Unknown Account Maintenance option(s): {', '.join(unknown)}"
            )

        dormant_days = _positive_int(value.get("dormant_days", 365), "dormant_days")
        kind_index = _nonnegative_int(
            value.get("kind_component_index", 2),
            "kind_component_index",
        )
        investment_kinds = (
            _string_set(value["investment_kinds"], "investment_kinds")
            if "investment_kinds" in value
            else DEFAULT_INVESTMENT_KINDS
        )
        buffer_components = (
            _string_set(value["buffer_components"], "buffer_components")
            if "buffer_components" in value
            else DEFAULT_BUFFER_COMPONENTS
        )

        raw_roles = value.get("equity_roles", {})
        if not isinstance(raw_roles, Mapping):
            raise ValueError("equity_roles must map account prefixes to roles")
        roles: list[tuple[str, str]] = []
        for prefix, role in raw_roles.items():
            prefix_text = str(prefix).strip().rstrip(":")
            role_text = str(role).strip()
            if not prefix_text:
                raise ValueError("equity_roles contains an empty account prefix")
            if role_text not in EQUITY_ROLES:
                allowed = ", ".join(sorted(EQUITY_ROLES))
                raise ValueError(
                    f"Unknown equity role {role_text!r}; choose one of: {allowed}"
                )
            roles.append((prefix_text, role_text))
        roles.sort(key=lambda item: (-len(item[0]), item[0]))

        source_mode = str(value.get("source_mode", "basename")).strip()
        if source_mode not in SOURCE_MODES:
            allowed = ", ".join(sorted(SOURCE_MODES))
            raise ValueError(f"source_mode must be one of: {allowed}")
        source_root_value = value.get("source_root")
        source_root = str(source_root_value) if source_root_value else None

        return cls(
            dormant_days=dormant_days,
            kind_component_index=kind_index,
            investment_kinds=investment_kinds,
            buffer_components=buffer_components,
            equity_roles=tuple(roles),
            source_mode=source_mode,
            source_root=source_root,
        )


def _iso(value: dt.date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _format_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    whole, dot, fraction = text.partition(".")
    sign = ""
    if whole.startswith("-"):
        sign, whole = "-", whole[1:]
    grouped = f"{int(whole):,}" if whole else "0"
    return f"{sign}{grouped}{dot}{fraction}"


def _short_filename(
    filename: Any,
    config: AccountMaintenanceConfig,
) -> str | None:
    """Return a display-safe source path that never exposes an absolute path."""

    if not filename or config.source_mode == "hidden":
        return None
    path = Path(str(filename))
    if config.source_mode == "basename":
        return path.name
    if not path.is_absolute():
        if ".." in path.parts:
            return path.name
        return path.as_posix()
    if config.source_root:
        try:
            return path.relative_to(Path(config.source_root)).as_posix()
        except ValueError:
            pass
    return path.name


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _safe_frequency(value: Any) -> tuple[int | None, bool]:
    if value is None:
        return None, False
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None, True
    if parsed <= 0:
        return None, True
    return parsed, False


def _is_generated_transaction(entry: data.Transaction) -> bool:
    return entry.flag == "P" or bool(entry.meta.get("__automatic__"))


def _account_kind(
    account: str,
    meta: Mapping[str, Any],
    roots: tuple[str, ...],
    config: AccountMaintenanceConfig,
) -> str:
    override = _optional_string(meta.get("maintenance_kind"))
    if override:
        return override
    parts = account.split(":")
    if len(parts) > config.kind_component_index and parts[0] in {roots[0], roots[1]}:
        return parts[config.kind_component_index]
    return parts[1] if len(parts) >= 2 else parts[0]


def _metadata_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _is_buffer(
    account: str,
    meta: Mapping[str, Any],
    config: AccountMaintenanceConfig,
) -> bool:
    override = _metadata_bool(meta.get("maintenance_buffer"))
    if override is not None:
        return override
    return any(part in config.buffer_components for part in account.split(":"))


def _equity_role(
    account: str,
    meta: Mapping[str, Any],
    buffer_account: bool,
    config: AccountMaintenanceConfig,
) -> str:
    override = _optional_string(meta.get("maintenance_role"))
    if override in EQUITY_ROLES:
        return override
    for prefix, role in config.equity_roles:
        if account == prefix or account.startswith(f"{prefix}:"):
            return role
    if buffer_account:
        return "buffer"
    return "other"


def _inventory_rows(totals: dict[str, Decimal]) -> list[dict[str, str]]:
    return [
        {"currency": currency, "number": _format_decimal(number)}
        for currency, number in sorted(totals.items())
        if number != 0
    ]


def _visible_account(account: str, roots: tuple[str, ...]) -> bool:
    return any(account == root or account.startswith(f"{root}:") for root in roots)


def build_account_maintenance(
    entries: Iterable[data.Directive],
    options: dict[str, Any] | None = None,
    today: dt.date | None = None,
    config: Mapping[str, Any] | AccountMaintenanceConfig | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe account-maintenance model from loaded entries.

    The input must be the fully loaded entry stream, including plugin-generated
    padding transactions. Generated transactions affect inventory but are not
    counted as user activity.
    """

    today = today or dt.date.today()
    settings = AccountMaintenanceConfig.from_value(config)
    options = options or {}
    roots = (
        str(options.get("name_assets", "Assets")),
        str(options.get("name_liabilities", "Liabilities")),
        str(options.get("name_equity", "Equity")),
    )
    operating = options.get("operating_currency", ["USD"])
    if isinstance(operating, str):
        operating_currencies = {operating}
    else:
        operating_currencies = {str(currency) for currency in operating or ["USD"]}

    all_entries = list(entries)
    as_of_entries = [entry for entry in all_entries if entry.date <= today]

    opens_by_account: dict[str, list[tuple[int, data.Open]]] = defaultdict(list)
    lifecycle_events: dict[str, list[tuple[dt.date, int, str]]] = defaultdict(list)

    for index, entry in enumerate(all_entries):
        if isinstance(entry, data.Open) and _visible_account(entry.account, roots):
            opens_by_account[entry.account].append((index, entry))
            lifecycle_events[entry.account].append((entry.date, index, "open"))
        elif isinstance(entry, data.Close) and _visible_account(entry.account, roots):
            lifecycle_events[entry.account].append((entry.date, index, "close"))

    account_names = sorted(opens_by_account)

    activity_count: Counter[str] = Counter()
    first_activity: dict[str, dt.date] = {}
    last_activity: dict[str, dt.date] = {}
    first_transaction: dict[str, data.Transaction] = {}
    first_activity_currencies: dict[str, set[str]] = defaultdict(set)
    posting_currencies: dict[str, set[str]] = defaultdict(set)
    recent_counterparts: dict[str, list[str]] = {}

    running_totals: dict[str, dict[str, Decimal]] = defaultdict(
        lambda: defaultdict(Decimal)
    )
    last_zero_date: dict[str, dt.date] = {}
    nonzero_since: dict[str, dt.date | None] = defaultdict(lambda: None)

    for entry in as_of_entries:
        if not isinstance(entry, data.Transaction):
            continue

        grouped: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: defaultdict(Decimal)
        )
        for posting in entry.postings:
            if posting.units is None:
                continue
            grouped[posting.account][posting.units.currency] += posting.units.number

        for account, changes in grouped.items():
            was_zero = all(number == 0 for number in running_totals[account].values())
            for currency, number in changes.items():
                running_totals[account][currency] += number
            now_zero = all(number == 0 for number in running_totals[account].values())
            if now_zero:
                last_zero_date[account] = entry.date
                nonzero_since[account] = None
            elif was_zero:
                nonzero_since[account] = entry.date

        if _is_generated_transaction(entry):
            continue

        transaction_accounts = {
            posting.account for posting in entry.postings if posting.units is not None
        }
        for posting in entry.postings:
            if posting.units is None:
                continue
            account = posting.account
            posting_currencies[account].add(posting.units.currency)
            activity_count[account] += 1
            if account not in first_activity:
                first_activity[account] = entry.date
                first_transaction[account] = entry
                first_activity_currencies[account].add(posting.units.currency)
            elif (
                first_activity[account] == entry.date
                and first_transaction.get(account) is entry
            ):
                first_activity_currencies[account].add(posting.units.currency)
            last_activity[account] = entry.date
            recent_counterparts[account] = sorted(transaction_accounts - {account})

    balances_by_account: dict[str, dict[str, list[data.Balance]]] = defaultdict(
        lambda: defaultdict(list)
    )
    pads_by_account: dict[str, list[data.Pad]] = defaultdict(list)
    latest_prices: dict[str, data.Price] = {}

    for entry in as_of_entries:
        if isinstance(entry, data.Balance):
            balances_by_account[entry.account][entry.amount.currency].append(entry)
        elif isinstance(entry, data.Pad):
            pads_by_account[entry.account].append(entry)
        elif isinstance(entry, data.Price):
            previous = latest_prices.get(entry.currency)
            if previous is None or previous.date <= entry.date:
                latest_prices[entry.currency] = entry

    latest_balances: dict[str, dict[str, data.Balance]] = {}
    for account, by_currency in balances_by_account.items():
        latest_balances[account] = {
            currency: directives[-1]
            for currency, directives in by_currency.items()
            if directives
        }

    account_rows: dict[str, dict[str, Any]] = {}
    for account in account_names:
        opens = opens_by_account[account]
        past_opens = [(index, entry) for index, entry in opens if entry.date <= today]
        future_opens = [(index, entry) for index, entry in opens if entry.date > today]
        open_entry = past_opens[-1][1] if past_opens else future_opens[0][1]

        past_events = sorted(
            event for event in lifecycle_events[account] if event[0] <= today
        )
        if not past_events:
            lifecycle = "future"
            close_date = None
        elif past_events[-1][2] == "close":
            lifecycle = "closed"
            close_date = past_events[-1][0]
        else:
            lifecycle = "open"
            close_date = None

        allowed_currencies = {str(currency) for currency in open_entry.currencies or ()}
        frequency, invalid_frequency = _safe_frequency(
            open_entry.meta.get("balance_frequency")
        )
        kind = _account_kind(account, open_entry.meta, roots, settings)
        buffer_account = _is_buffer(account, open_entry.meta, settings)
        equity_role = (
            _equity_role(account, open_entry.meta, buffer_account, settings)
            if account.startswith(f"{roots[2]}:")
            else None
        )
        trackable = (
            account.startswith((f"{roots[0]}:", f"{roots[1]}:"))
            or frequency is not None
            or buffer_account
        )

        totals = dict(running_totals.get(account, {}))
        inventory = _inventory_rows(totals)
        nonzero = bool(inventory)
        inventory_currencies = {row["currency"] for row in inventory}

        latest_by_currency = latest_balances.get(account, {})
        if kind in settings.investment_kinds:
            expected_currencies = set(inventory_currencies)
            known_currencies = (
                allowed_currencies
                | posting_currencies.get(account, set())
                | set(latest_by_currency)
            )
            expected_currencies |= operating_currencies & known_currencies
        else:
            expected_currencies = set(allowed_currencies)
            if not expected_currencies:
                expected_currencies = set(inventory_currencies)
            if not expected_currencies:
                expected_currencies = set(posting_currencies.get(account, set()))
            if not expected_currencies:
                expected_currencies = set(latest_by_currency)

        balance_units: list[dict[str, Any]] = []
        missing_balance_units: list[str] = []
        overdue_balance_units: list[str] = []
        for currency in sorted(expected_currencies):
            directive = latest_by_currency.get(currency)
            if directive is None:
                missing_balance_units.append(currency)
                balance_units.append(
                    {
                        "currency": currency,
                        "date": None,
                        "days_since": None,
                        "amount": None,
                        "status": "missing",
                    }
                )
                continue
            days_since = (today - directive.date).days
            status = (
                "overdue"
                if frequency is not None and days_since > frequency
                else "current"
            )
            if status == "overdue":
                overdue_balance_units.append(currency)
            balance_units.append(
                {
                    "currency": currency,
                    "date": _iso(directive.date),
                    "days_since": days_since,
                    "amount": _format_decimal(directive.amount.number),
                    "status": status,
                }
            )

        if lifecycle == "closed":
            balance_status = "closed"
        elif lifecycle == "future" or not trackable:
            balance_status = "not_applicable"
        elif invalid_frequency:
            balance_status = "invalid_frequency"
        elif frequency is None:
            balance_status = "unset"
        elif not latest_by_currency:
            balance_status = "never"
        elif missing_balance_units:
            balance_status = "partial"
        elif overdue_balance_units:
            balance_status = "overdue"
        else:
            balance_status = "current"

        pads = sorted(pads_by_account.get(account, []), key=lambda entry: entry.date)
        first_date = first_activity.get(account)
        late_pads = [
            pad for pad in pads if first_date is not None and pad.date > first_date
        ]
        if not pads:
            pad_status = "none"
        elif late_pads and len(pads) > 1:
            pad_status = "multiple"
        elif late_pads:
            pad_status = "late"
        elif len(pads) > 1:
            pad_status = "multiple_initial"
        else:
            pad_status = "initial_only"

        pre_first_latest: dict[str, data.Balance] = {}
        if first_date is not None:
            for currency, directives in balances_by_account.get(account, {}).items():
                for directive in directives:
                    if directive.date <= first_date:
                        pre_first_latest[currency] = directive

        start_currencies = set(first_activity_currencies.get(account, set()))
        if not start_currencies:
            start_currencies = set(allowed_currencies)
        explicit_zero = bool(start_currencies) and all(
            currency in pre_first_latest
            and pre_first_latest[currency].amount.number == 0
            for currency in start_currencies
        )

        equity_counterparts: list[str] = []
        first_txn = first_transaction.get(account)
        if first_txn is not None:
            equity_counterparts = sorted(
                {
                    posting.account
                    for posting in first_txn.postings
                    if posting.account != account
                    and posting.account.startswith(f"{roots[2]}:")
                }
            )

        if account.startswith(f"{roots[2]}:") and not trackable:
            history_boundary = "equity_role"
        elif pad_status in {"late", "multiple"}:
            history_boundary = "late_pad"
        elif pad_status in {"initial_only", "multiple_initial"}:
            history_boundary = "opening_pad"
        elif first_date is None:
            history_boundary = "unused"
        elif explicit_zero:
            history_boundary = "explicit_zero"
        elif equity_counterparts:
            history_boundary = "equity_seeded"
        else:
            history_boundary = "implicit_zero"

        days_inactive = (
            (today - last_activity[account]).days if account in last_activity else None
        )
        if lifecycle == "closed":
            activity_status = "closed"
        elif lifecycle == "future":
            activity_status = "future"
        elif first_date is None:
            activity_status = "never"
        elif days_inactive is not None and days_inactive > settings.dormant_days:
            activity_status = "dormant_nonzero" if nonzero else "dormant_zero"
        else:
            activity_status = "active"

        reasons: list[str] = []
        if lifecycle == "closed" and nonzero:
            reasons.append("closed_nonzero")
        if lifecycle == "open" and trackable:
            if activity_status == "never":
                reasons.append("never_used")
            elif activity_status in {"dormant_zero", "dormant_nonzero"}:
                reasons.append(activity_status)
            if balance_status in {
                "invalid_frequency",
                "never",
                "overdue",
                "partial",
            }:
                reasons.append(f"balance_{balance_status}")
        if buffer_account and lifecycle == "open" and nonzero:
            reasons.append("buffer_nonzero")
        if pad_status in {"late", "multiple", "multiple_initial"}:
            reasons.append("pad_gap")
        if (
            equity_role in {"opening_history", "untraceable"}
            and lifecycle == "open"
            and days_inactive is not None
            and days_inactive <= settings.dormant_days
        ):
            reasons.append("equity_recent_usage")

        backfill_candidate = history_boundary in {
            "equity_seeded",
            "late_pad",
            "opening_pad",
        }

        price_units: list[dict[str, Any]] = []
        if kind in settings.investment_kinds:
            for currency in sorted(inventory_currencies - operating_currencies):
                price = latest_prices.get(currency)
                price_units.append(
                    {
                        "currency": currency,
                        "date": _iso(price.date) if price is not None else None,
                        "days_since": (today - price.date).days
                        if price is not None
                        else None,
                        "quote": price.amount.currency if price is not None else None,
                        "number": _format_decimal(price.amount.number)
                        if price is not None
                        else None,
                    }
                )

        lifecycle_timeline = [
            {"date": _iso(date_value), "event": event}
            for date_value, _, event in sorted(lifecycle_events[account])
            if date_value <= today
        ]

        account_rows[account] = {
            "type": "account",
            "account": account,
            "root": account.split(":", 1)[0],
            "kind": kind,
            "nickname": _optional_string(open_entry.meta.get("nickname")),
            "purpose": _optional_string(open_entry.meta.get("purpose")),
            "source_file": _short_filename(open_entry.meta.get("filename"), settings),
            "source_line": (
                open_entry.meta.get("lineno")
                if settings.source_mode != "hidden"
                else None
            ),
            "open_date": _iso(open_entry.date),
            "close_date": _iso(close_date),
            "lifecycle": lifecycle,
            "lifecycle_timeline": lifecycle_timeline,
            "inventory": inventory,
            "inventory_text": " · ".join(
                f"{row['number']} {row['currency']}" for row in inventory
            )
            or "0",
            "nonzero": nonzero,
            "first_activity": _iso(first_date),
            "last_activity": _iso(last_activity.get(account)),
            "days_inactive": days_inactive,
            "activity_count": activity_count.get(account, 0),
            "activity_status": activity_status,
            "balance_frequency": frequency,
            "balance_status": balance_status,
            "balance_units": balance_units,
            "pad_status": pad_status,
            "pads": [
                {"date": _iso(pad.date), "source_account": pad.source_account}
                for pad in pads
            ],
            "history_boundary": history_boundary,
            "equity_counterparts": equity_counterparts,
            "equity_role": equity_role,
            "is_buffer": buffer_account,
            "last_zero_date": _iso(last_zero_date.get(account) or open_entry.date),
            "nonzero_since": _iso(nonzero_since.get(account)),
            "recent_counterparts": recent_counterparts.get(account, []),
            "price_units": price_units,
            "reasons": reasons,
            "needs_review": bool(reasons),
            "backfill_candidate": backfill_candidate,
        }

    tree_root: dict[str, Any] = {"children": {}}
    for account in account_names:
        node = tree_root
        path_parts: list[str] = []
        for part in account.split(":"):
            path_parts.append(part)
            path = ":".join(path_parts)
            node = node["children"].setdefault(
                part,
                {
                    "name": part,
                    "path": path,
                    "children": {},
                    "direct_account": None,
                },
            )
        node["direct_account"] = account

    node_data: dict[str, dict[str, Any]] = {
        f"account:{account}": row for account, row in account_rows.items()
    }

    def finish_node(
        node: dict[str, Any], depth: int
    ) -> tuple[dict[str, Any], list[str]]:
        child_results: list[dict[str, Any]] = []
        descendant_accounts: list[str] = []
        for child in sorted(node["children"].values(), key=lambda value: value["name"]):
            child_result, child_accounts = finish_node(child, depth + 1)
            child_results.append(child_result)
            descendant_accounts.extend(child_accounts)

        direct_account = node.get("direct_account")
        if direct_account is not None:
            descendant_accounts.insert(0, direct_account)

        rows = [account_rows[account] for account in descendant_accounts]
        counts = {
            "total": len(rows),
            "open": sum(row["lifecycle"] == "open" for row in rows),
            "closed": sum(row["lifecycle"] == "closed" for row in rows),
            "future": sum(row["lifecycle"] == "future" for row in rows),
            "needs_review": sum(row["needs_review"] for row in rows),
            "backfill": sum(row["backfill_candidate"] for row in rows),
            "nonzero": sum(row["nonzero"] for row in rows),
            "zero": sum(not row["nonzero"] for row in rows),
        }
        reason_counts = Counter(
            reason for row in rows for reason in row.get("reasons", [])
        )
        modes = ["all"]
        if counts["needs_review"]:
            modes.append("needs")
        if counts["backfill"]:
            modes.append("backfill")
        if counts["closed"]:
            modes.append("closed")

        has_children = bool(child_results)
        if has_children:
            key = f"group:{node['path']}"
            node_data[key] = {
                "type": "group",
                "path": node["path"],
                "name": node["name"],
                "counts": counts,
                "reason_counts": dict(reason_counts.most_common()),
                "direct_account": direct_account,
            }
        else:
            key = f"account:{direct_account}"

        result = {
            "name": node["name"],
            "path": node["path"],
            "depth": depth,
            "key": key,
            "children": child_results,
            "direct_account": direct_account,
            "counts": counts,
            "modes": modes,
        }
        if not has_children and direct_account is not None:
            row = account_rows[direct_account]
            result["leaf"] = {
                "lifecycle": row["lifecycle"],
                "needs_review": row["needs_review"],
                "backfill_candidate": row["backfill_candidate"],
                "nickname": row["nickname"],
            }
        return result, descendant_accounts

    tree: list[dict[str, Any]] = []
    for root_name in roots:
        root_node = tree_root["children"].get(root_name)
        if root_node is not None:
            result, _ = finish_node(root_node, 0)
            tree.append(result)

    rows = list(account_rows.values())

    # Keep the original operational "what should I balance next?" queue as a
    # separate view from the broader account-audit reasons.  An account enters
    # this queue only when its current Open directive has a valid, explicit
    # balance_frequency.  For multi-commodity accounts the oldest assertion is
    # the limiting one; a missing commodity takes priority over every dated row.
    balance_queue: list[dict[str, Any]] = []
    for row in rows:
        frequency = row["balance_frequency"]
        if row["lifecycle"] != "open" or frequency is None:
            continue

        units = row["balance_units"]
        missing_units = [
            unit["currency"] for unit in units if unit["status"] == "missing"
        ]
        dated_units = [unit for unit in units if unit["date"] is not None]

        if not units or missing_units:
            freshness_status = "never" if not dated_units else "partial"
            limiting_date = None
            days_since = None
            delta = None
            status_ratio = None
            overdue = True
        else:
            limiting_unit = max(
                dated_units,
                key=lambda unit: int(unit["days_since"]),
            )
            limiting_date = limiting_unit["date"]
            days_since = int(limiting_unit["days_since"])
            delta = days_since - frequency
            status_ratio = days_since / frequency
            overdue = days_since > frequency
            freshness_status = "overdue" if overdue else "current"

        balance_queue.append(
            {
                "account": row["account"],
                "nickname": row["nickname"],
                "frequency": frequency,
                "last_balance": limiting_date,
                "days_since": days_since,
                "delta": delta,
                "status_ratio": status_ratio,
                "overdue": overdue,
                "status": freshness_status,
                "missing_units": missing_units,
                "units": units,
            }
        )

    def balance_queue_key(row: dict[str, Any]) -> tuple[int, int, str]:
        if row["status"] in {"never", "partial"}:
            return (0, 0, row["account"])
        if row["overdue"]:
            return (1, -int(row["delta"]), row["account"])
        # Current accounts nearest their due date come first.
        return (2, -int(row["delta"]), row["account"])

    balance_queue.sort(key=balance_queue_key)

    missing_guidance: list[dict[str, Any]] = []
    for row in rows:
        if (
            row["lifecycle"] != "open"
            or row["root"] not in roots[:2]
            or row["balance_frequency"] is not None
        ):
            continue
        dated_units = [
            unit for unit in row["balance_units"] if unit["date"] is not None
        ]
        latest_unit = (
            max(dated_units, key=lambda unit: unit["date"]) if dated_units else None
        )
        missing_guidance.append(
            {
                "account": row["account"],
                "nickname": row["nickname"],
                "last_balance": latest_unit["date"] if latest_unit else None,
                "days_since": latest_unit["days_since"] if latest_unit else None,
                "invalid": row["balance_status"] == "invalid_frequency",
            }
        )

    missing_guidance.sort(
        key=lambda row: (
            not row["invalid"],
            row["last_balance"] is not None,
            -(int(row["days_since"]) if row["days_since"] is not None else 0),
            row["account"],
        )
    )

    balance_due = sum(row["status"] != "current" for row in balance_queue)
    summary = {
        "total": len(rows),
        "open": sum(row["lifecycle"] == "open" for row in rows),
        "closed": sum(row["lifecycle"] == "closed" for row in rows),
        "future": sum(row["lifecycle"] == "future" for row in rows),
        "needs_review": sum(row["needs_review"] for row in rows),
        "backfill": sum(row["backfill_candidate"] for row in rows),
        "nonzero_buffers": sum(
            row["is_buffer"] and row["lifecycle"] == "open" and row["nonzero"]
            for row in rows
        ),
        "balance_tracked": len(balance_queue),
        "balance_due": balance_due,
        "balance_missing_frequency": len(missing_guidance),
    }

    default_key = f"group:{tree[0]['path']}" if tree else None
    return {
        "today": _iso(today),
        "dormant_days": settings.dormant_days,
        "summary": summary,
        "tree": tree,
        "node_data": node_data,
        "default_key": default_key,
        "balance_queue": balance_queue,
        "missing_guidance": missing_guidance,
    }


class UpdateGuidance(FavaExtensionBase):
    """Explain account lifecycle, maintenance, and historical boundaries."""

    report_title = "Account Maintenance"
    has_js_module = True

    def after_load_file(self) -> None:
        self._account_maintenance_cache = None
        self._account_maintenance_date = None

    def compute(self) -> dict[str, Any]:
        today = dt.date.today()
        if (
            getattr(self, "_account_maintenance_cache", None) is None
            or getattr(self, "_account_maintenance_date", None) != today
        ):
            self._account_maintenance_cache = build_account_maintenance(
                self.ledger.all_entries,
                self.ledger.options,
                today,
                self.config,
            )
            self._account_maintenance_date = today
        return self._account_maintenance_cache
