#!/usr/bin/env python3
"""Capture a note and write it to the Time Atlas iCloud directory.

Input options:
  (default)            Read from stdin; two consecutive empty lines finish the note.
  -f/--file PATH       Read the note body from PATH.
  -w                   Open the system editor ($EDITOR, fallback to vi / notepad) to compose.

The output JSON has the structure:
  {
    "text": <note body>,
    "source": "user:oss",
    "timestamp": <current time, ISO8601>,
    "date": <YYYY-mm-dd, today or --date/-d>
  }

The file is written as note_<timestamp-in-millis>.json into the Time Atlas
iCloud directory.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import date as date_cls, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas


def _read_from_prompt() -> str:
    print(
        "Enter your note. Finish with two empty lines (or Ctrl-D).",
        file=sys.stderr,
    )
    lines: list[str] = []
    blank_streak = 0
    try:
        for raw in sys.stdin:
            line = raw.rstrip("\n")
            if line == "":
                blank_streak += 1
                if blank_streak >= 2:
                    break
                lines.append(line)
            else:
                blank_streak = 0
                lines.append(line)
    except KeyboardInterrupt:
        print("", file=sys.stderr)
        sys.exit(1)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _read_from_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().rstrip("\n")


def _read_from_editor() -> str:
    editor = os.environ.get("EDITOR") or (
        "notepad" if sys.platform == "win32" else "vi"
    )
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".txt", delete=False, encoding="utf-8"
    ) as tf:
        path = tf.name
    try:
        subprocess.call([editor, path])
        with open(path, "r", encoding="utf-8") as f:
            return f.read().rstrip("\n")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _parse_date(s: str) -> str:
    datetime.strptime(s, "%Y-%m-%d")
    return s


def main():
    parser = argparse.ArgumentParser(
        description="Capture a note to the Time Atlas iCloud directory."
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("-f", "--file", help="Read note body from this file.")
    src.add_argument(
        "-w",
        "--window",
        action="store_true",
        help="Open the system editor to enter the note.",
    )
    parser.add_argument(
        "-d",
        "--date",
        type=_parse_date,
        default=date_cls.today().isoformat(),
        help="Date to associate with the note (YYYY-mm-dd). Defaults to today.",
    )
    args = parser.parse_args()

    if args.file:
        text = _read_from_file(args.file)
    elif args.window:
        text = _read_from_editor()
    else:
        text = _read_from_prompt()

    if not text.strip():
        print("No note text provided.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now().astimezone()
    record = {
        "text": text,
        "source": "user:oss",
        "timestamp": now.isoformat(),
        "date": args.date,
    }

    icloud_dir = timeatlas.getIcloudDir()
    if not os.path.isdir(icloud_dir):
        print(
            f"iCloud directory not found: {icloud_dir}\n"
            "Is iCloud installed and Time Atlas signed in?",
            file=sys.stderr,
        )
        sys.exit(1)

    ts_millis = int(time.time() * 1000)
    filename = f"note_{ts_millis}.json"
    output = os.path.join(icloud_dir, filename)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote note to {output}", file=sys.stderr)


if __name__ == "__main__":
    main()
