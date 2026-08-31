from __future__ import annotations

import datetime as dt
import unittest
from decimal import Decimal

from beancount.core import data
from beancount.core.amount import Amount

from fava_account_maintenance import (
    AccountMaintenanceConfig,
    build_account_maintenance,
)

TODAY = dt.date(2026, 8, 28)
OPTIONS = {
    "name_assets": "Assets",
    "name_liabilities": "Liabilities",
    "name_equity": "Equity",
    "operating_currency": ["USD"],
}


def metadata(line: int = 1, **values):
    return {"filename": "/srv/example-ledger/accounts.bean", "lineno": line, **values}


def open_account(date_value, account, currencies=("USD",), **meta_values):
    return data.Open(
        metadata(**meta_values),
        date_value,
        account,
        currencies,
        None,
    )


def close_account(date_value, account):
    return data.Close(metadata(), date_value, account)


def balance(date_value, account, number, currency="USD"):
    return data.Balance(
        metadata(),
        date_value,
        account,
        Amount(Decimal(str(number)), currency),
        None,
        None,
    )


def pad(date_value, account, source="Equity:Opening-Balances"):
    return data.Pad(metadata(), date_value, account, source)


def transaction(date_value, postings, flag="*"):
    return data.Transaction(
        metadata(__automatic__=(flag == "P")),
        date_value,
        flag,
        None,
        "test",
        frozenset(),
        frozenset(),
        [
            data.Posting(
                account,
                Amount(Decimal(str(number)), currency),
                None,
                None,
                None,
                None,
            )
            for account, number, currency in postings
        ],
    )


def model(entries, config=None):
    return build_account_maintenance(entries, OPTIONS, TODAY, config)


class AccountMaintenanceModelTest(unittest.TestCase):
    def test_future_balance_does_not_make_partial_brokerage_current(self):
        account = "Assets:Household:Brokerage:Example"
        entries = [
            open_account(
                dt.date(2020, 1, 1),
                account,
                ("USD", "AAA"),
                balance_frequency=30,
            ),
            open_account(dt.date(2020, 1, 1), "Equity:Opening-Balances"),
            transaction(
                dt.date(2026, 8, 1),
                [
                    (account, 1, "AAA"),
                    (account, 0, "USD"),
                    ("Equity:Opening-Balances", -1, "AAA"),
                ],
            ),
            balance(dt.date(2026, 8, 25), account, 0, "USD"),
            balance(dt.date(2099, 1, 1), account, 1, "AAA"),
        ]

        row = model(entries)["node_data"][f"account:{account}"]

        self.assertEqual(row["balance_status"], "partial")
        self.assertEqual(
            [
                unit["currency"]
                for unit in row["balance_units"]
                if unit["status"] == "missing"
            ],
            ["AAA"],
        )

    def test_explicit_zero_boundary_and_clean_close(self):
        account = "Liabilities:Household:CreditCard:ClosedCard"
        entries = [
            open_account(dt.date(2020, 1, 1), account),
            open_account(dt.date(2020, 1, 1), "Expenses:Ignored"),
            balance(dt.date(2020, 1, 1), account, 0),
            transaction(
                dt.date(2020, 1, 2),
                [(account, -10, "USD"), ("Expenses:Ignored", 10, "USD")],
            ),
            transaction(
                dt.date(2020, 1, 3),
                [(account, 10, "USD"), ("Assets:Ignored", -10, "USD")],
            ),
            balance(dt.date(2020, 1, 4), account, 0),
            close_account(dt.date(2020, 1, 4), account),
        ]

        row = model(entries)["node_data"][f"account:{account}"]

        self.assertEqual(row["lifecycle"], "closed")
        self.assertFalse(row["nonzero"])
        self.assertEqual(row["history_boundary"], "explicit_zero")
        self.assertNotIn("closed_nonzero", row["reasons"])

    def test_initial_padding_is_not_counted_as_activity(self):
        account = "Assets:Household:Checking:Imported"
        entries = [
            open_account(dt.date(2020, 1, 1), account),
            open_account(dt.date(2020, 1, 1), "Equity:Opening-Balances"),
            pad(dt.date(2020, 1, 1), account),
            transaction(
                dt.date(2020, 1, 1),
                [(account, 50, "USD"), ("Equity:Opening-Balances", -50, "USD")],
                flag="P",
            ),
            transaction(
                dt.date(2020, 2, 1),
                [(account, -10, "USD"), ("Expenses:Ignored", 10, "USD")],
            ),
        ]

        row = model(entries)["node_data"][f"account:{account}"]

        self.assertEqual(row["first_activity"], "2020-02-01")
        self.assertEqual(row["activity_count"], 1)
        self.assertEqual(row["pad_status"], "initial_only")
        self.assertEqual(row["history_boundary"], "opening_pad")
        self.assertTrue(row["backfill_candidate"])

    def test_late_pad_and_nonzero_buffer_are_review_reasons(self):
        checking = "Assets:Household:Checking:Gap"
        buffer_account = "Assets:Household:Buffer:Transfer"
        entries = [
            open_account(dt.date(2020, 1, 1), checking),
            open_account(dt.date(2020, 1, 1), buffer_account),
            open_account(dt.date(2020, 1, 1), "Equity:Opening-Balances"),
            transaction(
                dt.date(2020, 1, 2),
                [(checking, 10, "USD"), ("Equity:Opening-Balances", -10, "USD")],
            ),
            pad(dt.date(2020, 2, 1), checking),
            transaction(
                dt.date(2020, 2, 1),
                [(checking, 5, "USD"), ("Equity:Opening-Balances", -5, "USD")],
                flag="P",
            ),
            transaction(
                dt.date(2026, 8, 1),
                [(buffer_account, 12, "USD"), (checking, -12, "USD")],
            ),
        ]

        result = model(entries)
        checking_row = result["node_data"][f"account:{checking}"]
        buffer_row = result["node_data"][f"account:{buffer_account}"]

        self.assertEqual(checking_row["history_boundary"], "late_pad")
        self.assertIn("pad_gap", checking_row["reasons"])
        self.assertIn("buffer_nonzero", buffer_row["reasons"])
        self.assertEqual(buffer_row["nonzero_since"], "2026-08-01")
        self.assertEqual(result["summary"]["nonzero_buffers"], 1)

    def test_open_zero_dormant_is_only_a_review_candidate(self):
        account = "Liabilities:Household:CreditCard:Dormant"
        entries = [
            open_account(dt.date(2020, 1, 1), account),
            transaction(
                dt.date(2020, 1, 2),
                [(account, -1, "USD"), ("Expenses:Ignored", 1, "USD")],
            ),
            transaction(
                dt.date(2020, 1, 3),
                [(account, 1, "USD"), ("Assets:Ignored", -1, "USD")],
            ),
        ]

        row = model(entries)["node_data"][f"account:{account}"]

        self.assertEqual(row["lifecycle"], "open")
        self.assertEqual(row["activity_status"], "dormant_zero")
        self.assertIn("dormant_zero", row["reasons"])

    def test_recent_balance_assertion_counts_as_activity(self):
        account = "Assets:Household:Checking:Maintained"
        entries = [
            open_account(dt.date(2020, 1, 1), account),
            transaction(
                dt.date(2020, 1, 2),
                [(account, 10, "USD"), ("Equity:Opening-Balances", -10, "USD")],
            ),
            balance(dt.date(2026, 8, 20), account, 10),
        ]

        row = model(entries)["node_data"][f"account:{account}"]

        self.assertEqual(row["activity_status"], "active")
        self.assertEqual(row["last_activity"], "2026-08-20")
        self.assertEqual(row["days_inactive"], 8)
        self.assertEqual(row["activity_count"], 2)
        self.assertNotIn("dormant_nonzero", row["reasons"])

    def test_future_balance_assertion_counts_as_current_activity(self):
        account = "Liabilities:Household:CreditCard:Maintained"
        entries = [
            open_account(dt.date(2020, 1, 1), account),
            transaction(
                dt.date(2020, 1, 2),
                [(account, -1, "USD"), ("Expenses:Ignored", 1, "USD")],
            ),
            transaction(
                dt.date(2020, 1, 3),
                [(account, 1, "USD"), ("Assets:Ignored", -1, "USD")],
            ),
            balance(dt.date(2026, 9, 30), account, 0),
        ]

        row = model(entries)["node_data"][f"account:{account}"]

        self.assertEqual(row["activity_status"], "active")
        self.assertEqual(row["last_activity"], "2026-09-30")
        self.assertEqual(row["days_inactive"], 0)
        self.assertEqual(row["activity_count"], 3)
        self.assertNotIn("dormant_zero", row["reasons"])

    def test_future_account_is_visible_but_not_needing_review(self):
        account = "Assets:Household:Checking:Future"
        result = model([open_account(dt.date(2027, 1, 1), account)])
        row = result["node_data"][f"account:{account}"]

        self.assertEqual(row["lifecycle"], "future")
        self.assertFalse(row["needs_review"])
        self.assertEqual(result["summary"]["future"], 1)

    def test_balance_queue_prioritizes_missing_then_overdue_then_nearest_due(self):
        prefix = "Assets:Household:Checking"
        never = f"{prefix}:Never"
        partial = f"{prefix}:Partial"
        overdue = f"{prefix}:Overdue"
        due_today = f"{prefix}:DueToday"
        near_due = f"{prefix}:NearDue"
        fresh = f"{prefix}:Fresh"
        entries = [
            open_account(dt.date(2020, 1, 1), never, balance_frequency=30),
            open_account(
                dt.date(2020, 1, 1),
                partial,
                ("USD", "EUR"),
                balance_frequency=30,
            ),
            balance(dt.date(2026, 8, 27), partial, 10, "USD"),
            open_account(dt.date(2020, 1, 1), overdue, balance_frequency=30),
            balance(dt.date(2026, 6, 28), overdue, 10),
            open_account(dt.date(2020, 1, 1), due_today, balance_frequency=30),
            balance(dt.date(2026, 7, 29), due_today, 10),
            open_account(dt.date(2020, 1, 1), near_due, balance_frequency=30),
            balance(dt.date(2026, 8, 1), near_due, 10),
            open_account(dt.date(2020, 1, 1), fresh, balance_frequency=30),
            balance(dt.date(2026, 8, 20), fresh, 10),
        ]

        result = model(entries)
        queue = result["balance_queue"]

        self.assertEqual(
            [row["account"] for row in queue],
            [never, partial, overdue, due_today, near_due, fresh],
        )
        self.assertEqual(
            [row["status"] for row in queue],
            ["never", "partial", "overdue", "current", "current", "current"],
        )
        self.assertEqual(queue[1]["missing_units"], ["EUR"])
        self.assertIsNone(queue[1]["last_balance"])
        self.assertEqual(queue[2]["delta"], 31)
        self.assertEqual(queue[3]["delta"], 0)
        self.assertFalse(queue[3]["overdue"])
        self.assertEqual(result["summary"]["balance_tracked"], 6)
        self.assertEqual(result["summary"]["balance_due"], 3)

    def test_balance_guidance_excludes_closed_and_future_accounts(self):
        tracked = "Assets:Household:Checking:Tracked"
        closed = "Liabilities:Household:CreditCard:Closed"
        future = "Assets:Household:Checking:Future"
        missing = "Assets:Household:Checking:MissingFrequency"
        invalid = "Liabilities:Household:CreditCard:InvalidFrequency"
        equity = "Equity:Uncategorized"
        entries = [
            open_account(dt.date(2020, 1, 1), tracked, balance_frequency=30),
            balance(dt.date(2026, 8, 20), tracked, 10),
            open_account(dt.date(2020, 1, 1), closed, balance_frequency=30),
            close_account(dt.date(2026, 1, 1), closed),
            open_account(dt.date(2027, 1, 1), future, balance_frequency=30),
            open_account(dt.date(2020, 1, 1), missing),
            open_account(
                dt.date(2020, 1, 1),
                invalid,
                balance_frequency="monthly",
            ),
            open_account(dt.date(2020, 1, 1), equity),
        ]

        result = model(entries)

        self.assertEqual(
            [row["account"] for row in result["balance_queue"]],
            [tracked],
        )
        self.assertEqual(
            [row["account"] for row in result["missing_guidance"]],
            [invalid, missing],
        )
        self.assertTrue(result["missing_guidance"][0]["invalid"])
        self.assertEqual(result["summary"]["balance_missing_frequency"], 2)

    def test_source_paths_are_private_by_default_and_can_be_hidden(self):
        account = "Assets:Household:Checking:Example"
        entries = [open_account(dt.date(2020, 1, 1), account)]

        visible_row = model(entries)["node_data"][f"account:{account}"]
        relative_row = model(
            entries,
            {"source_mode": "relative", "source_root": "/srv"},
        )["node_data"][f"account:{account}"]
        hidden_row = model(entries, {"source_mode": "hidden"})["node_data"][
            f"account:{account}"
        ]

        self.assertEqual(visible_row["source_file"], "accounts.bean")
        self.assertNotIn("/srv/", visible_row["source_file"])
        self.assertEqual(relative_row["source_file"], "example-ledger/accounts.bean")
        self.assertIsNone(hidden_row["source_file"])
        self.assertIsNone(hidden_row["source_line"])

    def test_account_conventions_are_configurable(self):
        buffer_account = "Assets:Team:Clearing:Transfers"
        history_account = "Equity:Legacy-Imports"
        entries = [
            open_account(dt.date(2020, 1, 1), buffer_account),
            open_account(dt.date(2020, 1, 1), history_account),
            transaction(
                dt.date(2026, 8, 1),
                [(buffer_account, 10, "USD"), (history_account, -10, "USD")],
            ),
        ]
        config = AccountMaintenanceConfig.from_value(
            {
                "buffer_components": ["Clearing"],
                "equity_roles": {history_account: "opening_history"},
            }
        )

        result = model(entries, config)
        buffer_row = result["node_data"][f"account:{buffer_account}"]
        history_row = result["node_data"][f"account:{history_account}"]

        self.assertTrue(buffer_row["is_buffer"])
        self.assertIn("buffer_nonzero", buffer_row["reasons"])
        self.assertEqual(history_row["equity_role"], "opening_history")
        self.assertIn("equity_recent_usage", history_row["reasons"])

    def test_open_metadata_can_override_kind_buffer_and_equity_role(self):
        asset = "Assets:Team:Other:Example"
        equity = "Equity:Imported-History"
        entries = [
            open_account(
                dt.date(2020, 1, 1),
                asset,
                maintenance_kind="Brokerage",
                maintenance_buffer=True,
            ),
            open_account(
                dt.date(2020, 1, 1),
                equity,
                maintenance_role="untraceable",
            ),
        ]

        result = model(entries)

        self.assertEqual(result["node_data"][f"account:{asset}"]["kind"], "Brokerage")
        self.assertTrue(result["node_data"][f"account:{asset}"]["is_buffer"])
        self.assertEqual(
            result["node_data"][f"account:{equity}"]["equity_role"],
            "untraceable",
        )


if __name__ == "__main__":
    unittest.main()
