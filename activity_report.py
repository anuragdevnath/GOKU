#!/usr/bin/env python3
"""
activity_report.py — command-line version.

USAGE:
    python activity_report.py --start 2026-09-20 --end 2026-09-25

For the browser-based version with a calendar picker, run app.py instead.
"""

import argparse

from fetchers import fetch_all


def print_report(report, start_date, end_date):
    print()
    print(f"Activity report: {start_date} to {end_date}")
    print("=" * 60)
    for day, info in report.items():
        weekend_tag = "  [WEEKEND / WEEK OFF]" if info["is_weekend"] else ""
        print(f"\n{day}{weekend_tag}  ({len(info['events'])} events)")
        print("-" * 40)
        if not info["events"]:
            print("  (nothing found)")
            continue
        by_type = {}
        for e in info["events"]:
            by_type.setdefault(e["type"], []).append(e)
        for etype, items in sorted(by_type.items()):
            print(f"  {etype} ({len(items)}):")
            for item in items:
                repo_bit = f" [{item['repo']}]" if item.get("repo") else ""
                print(f"    - {item['title']}{repo_bit}")


def main():
    parser = argparse.ArgumentParser(description="Daily GitHub + Gmail activity report")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--skip-github", action="store_true")
    parser.add_argument("--skip-gmail", action="store_true")
    parser.add_argument("--skip-slack", action="store_true")
    parser.add_argument("--skip-chat", action="store_true")
    args = parser.parse_args()

    report = fetch_all(
        args.start, args.end,
        skip_github=args.skip_github,
        skip_gmail=args.skip_gmail,
        skip_slack=args.skip_slack,
        skip_chat=args.skip_chat,
    )
    print_report(report, args.start, args.end)


if __name__ == "__main__":
    main()
