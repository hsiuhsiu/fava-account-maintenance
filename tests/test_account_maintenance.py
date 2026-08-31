from __future__ import annotations

import datetime as dt
import unittest
from decimal import Decimal
from importlib.resources import files

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

    def test_future_account_is_visible_but_not_needing_review(self):
        account = "Assets:Household:Checking:Future"
        result = model([open_account(dt.date(2027, 1, 1), account)])
        row = result["node_data"][f"account:{account}"]

        self.assertEqual(row["lifecycle"], "future")
        self.assertFalse(row["needs_review"])
        self.assertEqual(result["summary"]["future"], 1)

    def test_public_model_does_not_apply_balance_frequency_policy(self):
        account = "Assets:Household:Checking:Example"
        entries = [
            open_account(
                dt.date(2020, 1, 1),
                account,
                balance_frequency=1,
            ),
            balance(dt.date(2020, 1, 1), account, 0),
        ]

        result = model(entries)
        row = result["node_data"][f"account:{account}"]

        self.assertNotIn("balance_frequency", row)
        self.assertNotIn("balance_queue", result)
        self.assertFalse(
            any(reason.startswith("balance_") for reason in row["reasons"])
        )

    def test_public_template_opens_account_tree_without_balance_view(self):
        template = (
            files("fava_account_maintenance")
            .joinpath("templates", "UpdateGuidance.html")
            .read_text(encoding="utf-8")
        )

        self.assertIn('data-am-default-view="all"', template)
        self.assertNotIn("Balance 更新", template)
        self.assertNotIn("balance_frequency", template)

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
