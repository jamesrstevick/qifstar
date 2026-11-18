###########################################
# AMAZON CC RULE TRAINER
###########################################
# Match reconciled QIF to Order History and
# write amazon_rules.json for the reviewer.
###########################################

from __future__ import print_function

import argparse
import sys

from amazon_cc.matching import match_qif_to_orders, summarize_match_report
from amazon_cc.rules import DEFAULT_RULES_PATH, save_rules, train_rules


DEFAULT_QIF = "amazon/5144_2025_2026.QIF"
DEFAULT_ORDERS = "amazon/Your Orders/Your Amazon Orders/Order History.csv"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Train Amazon category/memo rules from QIF + Order History."
    )
    parser.add_argument("--qif", default=DEFAULT_QIF, help="Training CCard QIF path")
    parser.add_argument(
        "--orders", default=DEFAULT_ORDERS, help="Order History.csv path"
    )
    parser.add_argument(
        "--rules", default=DEFAULT_RULES_PATH, help="Output rules JSON path"
    )
    parser.add_argument("--card", default="5144", help="Card last-4 filter")
    parser.add_argument(
        "--window", type=int, default=7, help="Date window days for matching"
    )
    parser.add_argument(
        "--show-unmatched",
        type=int,
        default=15,
        help="Print up to N unmatched sample rows",
    )
    args = parser.parse_args(argv)

    result = match_qif_to_orders(
        args.qif,
        order_history_path=args.orders,
        last4=args.card,
        window_days=args.window,
    )
    print(summarize_match_report(result))
    print()

    rules = train_rules(result["train_pairs"])
    save_rules(rules, args.rules)
    print(
        "Wrote {} (from {} unique matches)".format(
            args.rules, rules.get("trained_pairs", 0)
        )
    )
    print(
        "  ship-to fingerprints: {}".format(len(rules.get("ship_to_category") or {}))
    )
    print("  keyword rules: {}".format(len(rules.get("keyword_category") or {})))

    if args.show_unmatched:
        print()
        print("Unmatched samples:")
        n = 0
        for row in result["rows"]:
            if row["status"] != "unmatched":
                continue
            txn = row["txn"]
            d = txn["date"].strftime("%m/%d/%Y") if txn["date"] else "?"
            print(
                "  {}  ${:.2f}  {!r}  {!r}".format(
                    d, abs(txn["amount"] or 0), txn.get("payee"), txn.get("memo")
                )
            )
            n += 1
            if n >= args.show_unmatched:
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
