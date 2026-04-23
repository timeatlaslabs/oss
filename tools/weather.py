#!/usr/bin/env python3
"""Query the Time Atlas weather table for a date range.

For each date prints the temperature range and observed conditions, then shows
an overall histogram of conditions. With -v plots temperature over time using
matplotlib (pip install matplotlib); -o saves the plot to a file instead of
opening a window.
"""

import argparse
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas


def _fetch_weather(from_ts: float, to_ts: float) -> list[tuple[float, float, str]]:
    with sqlite3.connect(timeatlas.getDatabasePath()) as conn:
        cur = conn.execute(
            "SELECT observed_at, temperature_celsius, condition_description "
            "FROM weather "
            "WHERE observed_at IS NOT NULL AND observed_at >= ? AND observed_at <= ? "
            "ORDER BY observed_at ASC",
            (from_ts, to_ts),
        )
        return cur.fetchall()


def _histogram(counts: Counter, width: int = 40) -> list[str]:
    if not counts:
        return []
    max_count = max(counts.values())
    label_w = max(len(k) for k in counts)
    lines = []
    for label, count in counts.most_common():
        bar_len = max(1, int(round(count / max_count * width)))
        lines.append(f"  {label.ljust(label_w)}  {'#' * bar_len} {count}")
    return lines


def _describe_temps(temps: list[float]) -> str:
    if not temps:
        return "temperature n/a"
    return f"{min(temps):5.1f}°C – {max(temps):5.1f}°C"


def _print_per_date(dates):
    all_conditions = Counter()
    all_rows = []

    for date_str, start, end in dates:
        if start is None or end is None:
            print(f"{date_str}  (no date range)")
            continue
        rows = _fetch_weather(start.timestamp(), end.timestamp())
        if not rows:
            print(f"{date_str}  (no weather)")
            continue

        temps = [t for _, t, _ in rows if t is not None]
        conds = [c for _, _, c in rows if c]
        cond_counts = Counter(conds)
        all_conditions.update(cond_counts)
        tz = start.tzinfo
        all_rows.extend((ts, t, c, tz) for ts, t, c in rows)

        top_conds = ", ".join(
            f"{c} ({n})" for c, n in cond_counts.most_common(3)
        )
        print(f"{date_str}  {_describe_temps(temps)}  {top_conds}")

    return all_conditions, all_rows


def _plot(rows, output: str | None):
    try:
        import matplotlib

        if output:
            matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print(
            "matplotlib is required for -v. Install with: pip install matplotlib",
            file=sys.stderr,
        )
        sys.exit(1)

    if not rows:
        print("No weather data to plot.", file=sys.stderr)
        return

    times = [datetime.fromtimestamp(ts, tz) for ts, _, _, tz in rows]
    temps = [t for _, t, _, _ in rows]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(times, temps, marker=".", linewidth=1)
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("Time Atlas — temperature over time")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()

    if output:
        fig.savefig(output)
        print(f"Saved plot to {output}", file=sys.stderr)
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="Query weather observations for a date range."
    )
    parser.add_argument("from_date", help="Start date YYYY-mm-dd (or single date)")
    parser.add_argument(
        "to_date",
        nargs="?",
        help="End date YYYY-mm-dd (inclusive). Omit for a single date.",
    )
    parser.add_argument(
        "-v",
        "--visualize",
        action="store_true",
        help="Plot the temperatures with matplotlib.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Path to save the plot. With -v but without -o, a window opens.",
    )
    args = parser.parse_args()

    to_date = args.to_date or args.from_date
    dates = timeatlas.getDates(args.from_date, to_date)
    if not dates:
        print(f"No date entries between {args.from_date} and {to_date}.")
        return

    all_conditions, all_rows = _print_per_date(dates)

    print()
    print("Conditions histogram:")
    hist_lines = _histogram(all_conditions)
    if hist_lines:
        for line in hist_lines:
            print(line)
    else:
        print("  (no conditions recorded)")

    if args.visualize:
        _plot(all_rows, args.output)


if __name__ == "__main__":
    main()
