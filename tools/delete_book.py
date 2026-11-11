#!/usr/bin/env python3
"""Delete a book from Time Atlas.

Finds matching books in the local database by title (case-insensitive) or
ISBN (ISBN-10 or ISBN-13), then writes an update with meta.deleted_at set. If
several books match, you are asked which ones to delete.

Usage:
    python tools/delete_book.py --title TITLE [--yes]
    python tools/delete_book.py --isbn ISBN [--yes]

Examples:
    python tools/delete_book.py --title "Four Thousand Weeks"
    python tools/delete_book.py --isbn 9780374159122 --yes
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas

from add_book import describe
from delete_movie import choose


def main():
    parser = argparse.ArgumentParser(description="Delete a book from Time Atlas")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--title", "-t", help="Title to delete (case-insensitive exact match)")
    group.add_argument("--isbn", help="ISBN-10 or ISBN-13 to delete")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Delete all matches without asking")
    args = parser.parse_args()

    isbn = args.isbn.replace("-", "").replace(" ", "").upper() if args.isbn else None
    books = timeatlas.findBooks(title=args.title, isbn=isbn)
    if not books:
        what = f"title {args.title!r}" if args.title else f"ISBN {args.isbn}"
        print(f"No book found with {what}. Try running 'python sync.py' first.", file=sys.stderr)
        sys.exit(1)

    try:
        if args.yes:
            to_delete = books
            for b in books:
                print(f"  {describe(b)}")
        elif len(books) == 1:
            print(f"  {describe(books[0])}")
            confirm = input("Delete this book? [y/N]: ").strip().lower()
            to_delete = books if confirm in ("y", "yes") else []
        else:
            print(f"Found {len(books)} matching books:")
            to_delete = choose(books, describe)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except (KeyboardInterrupt, EOFError):
        print()
        to_delete = []

    if not to_delete:
        print("Cancelled, nothing deleted.")
        return

    filepath = timeatlas.deleteObjects(to_delete)
    print(f"Deleted {len(to_delete)} book{'' if len(to_delete) == 1 else 's'}.")
    print(f"  Written to: {filepath}")


if __name__ == "__main__":
    main()
