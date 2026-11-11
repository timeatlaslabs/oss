#!/usr/bin/env python3
"""Add a read book into Time Atlas.

Usage:
    python tools/add_book.py --title TITLE --author AUTHOR [--author AUTHOR ...] \\
        --read-date (today|YYYY-mm-dd) (--isbn ISBN | --isbn13 ISBN13) [--stars STARS] [options]
    python tools/add_book.py --csv FILE [--dry-run]

Examples:
    python tools/add_book.py --title "Four Thousand Weeks" --author "Oliver Burkeman" \\
        --stars 4 --read-date today --isbn13 9780374159122
    python tools/add_book.py --title "Good Omens" --author "Terry Pratchett" \\
        --author "Neil Gaiman" --stars 4.5 --read-date 2026-10-01 --isbn 0060853980 \\
        --pages 432 --year 2006 --original-year 1990
    python tools/add_book.py --csv books.csv

CSV format: a header row with column names matching the long option names
(underscores or dashes both accepted). Required columns: title, authors, read_date
and at least one of isbn / isbn13. Separate multiple authors with ';'.
Optional columns: stars, pages, year, original_year, review.
"""

import argparse
import csv
import os
import re
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas
import timeatlas_pb2

SOURCE = "oss"
CSV_COLUMNS = {
    "title", "authors", "stars", "read_date", "isbn", "isbn13",
    "pages", "year", "original_year", "review",
}


def parse_read_date(value: str) -> str:
    value = (value or "").strip()
    if value.lower() == "today":
        return date.today().strftime("%Y-%m-%d")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"read_date must be 'today' or YYYY-mm-dd, got {value!r}")
    return value


def parse_isbn(value: str, length: int, name: str) -> str:
    isbn = re.sub(r"[\s-]", "", value or "").upper()
    if isbn and not re.fullmatch(rf"\d{{{length - 1}}}[\dX]" if length == 10 else rf"\d{{{length}}}", isbn):
        raise ValueError(f"{name} must be {length} digits, got {value!r}")
    return isbn


def parse_int(value: str, name: str) -> int:
    if not value:
        return 0
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {value!r}")


def build_book(fields: dict) -> timeatlas_pb2.Book:
    """Build a Book message from a dict of field values.

    'authors' may be a list or a ';'-separated string. Raises ValueError if a
    required field is missing or malformed.
    """
    def get(name):
        v = fields.get(name)
        return "" if v is None else str(v).strip()

    title = get("title")
    if not title:
        raise ValueError("title is required")
    authors = fields.get("authors") or []
    if isinstance(authors, str):
        authors = authors.split(";")
    authors = [a.strip() for a in authors if a and a.strip()]
    if not authors:
        raise ValueError("at least one author is required")
    try:
        stars = float(get("stars") or 0)
    except ValueError:
        raise ValueError(f"stars must be a number, got {get('stars')!r}")
    if stars and not 1 <= stars <= 5:
        raise ValueError(f"stars must be between 1 and 5, got {stars}")
    isbn = parse_isbn(get("isbn"), 10, "isbn")
    isbn13 = parse_isbn(get("isbn13"), 13, "isbn13")
    if not isbn and not isbn13:
        raise ValueError("either isbn or isbn13 is required")

    book = timeatlas_pb2.Book()
    book.title = title
    book.authors.extend(authors)
    book.stars = stars
    book.isbn = isbn
    book.isbn13 = isbn13
    book.read_date = parse_read_date(get("read_date"))
    book.number_of_pages = parse_int(get("pages"), "pages")
    book.publication_year = parse_int(get("year"), "year")
    book.original_publication_year = parse_int(get("original_year"), "original_year")
    book.my_review = get("review")
    book.source = SOURCE
    return book


def load_csv(path: str) -> list[timeatlas_pb2.Book]:
    books, errors = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{path}: empty CSV file")
        header = [h.strip().lower().replace("-", "_") for h in reader.fieldnames]
        unknown = set(header) - CSV_COLUMNS
        if unknown:
            raise ValueError(f"{path}: unknown columns: {', '.join(sorted(unknown))}")
        reader.fieldnames = header
        for row in reader:
            if not any((v or "").strip() for v in row.values()):
                continue  # skip blank lines
            try:
                book = build_book(row)
                timeatlas.validateBook(book)
                books.append(book)
            except (ValueError, timeatlas.ValidationError) as e:
                errors.append(f"  line {reader.line_num}: {e}")
    if errors:
        raise ValueError(f"{path}: {len(errors)} invalid row(s):\n" + "\n".join(errors))
    return books


def describe(book: timeatlas_pb2.Book) -> str:
    authors = ", ".join(book.authors) or "unknown author"
    rating = f"{book.stars:g}★" if book.stars else "unrated"
    ident = f"isbn13 {book.isbn13}" if book.isbn13 else f"isbn {book.isbn}" if book.isbn else "no isbn"
    return f"{book.title} by {authors}  {rating}  read {book.read_date or '?'}  [{ident}]"


def main():
    parser = argparse.ArgumentParser(
        description="Add a read book into Time Atlas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="CSV format:" + __doc__.split("CSV format:", 1)[1],
    )
    parser.add_argument("--csv", help="Batch import books from a CSV file")
    parser.add_argument("--title", "-t", help="Title (required)")
    parser.add_argument("--author", "-a", dest="authors", action="append",
                        help="Author (required, repeat for multiple authors)")
    parser.add_argument("--stars", "-s", help="Rating 1-5, decimals allowed (optional)")
    parser.add_argument("--read-date", "-r", help="'today' or YYYY-mm-dd (required)")
    parser.add_argument("--isbn", help="ISBN-10 (this or --isbn13 required)")
    parser.add_argument("--isbn13", help="ISBN-13 (this or --isbn required)")
    parser.add_argument("--pages", help="Number of pages")
    parser.add_argument("--year", help="Publication year of this edition")
    parser.add_argument("--original-year", help="Original publication year")
    parser.add_argument("--review", help="Free-form review text")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Validate and print books without writing")
    args = parser.parse_args()

    single_fields = ["title", "authors", "stars", "read_date", "isbn", "isbn13",
                     "pages", "year", "original_year", "review"]
    try:
        if args.csv:
            used = [f for f in single_fields if getattr(args, f) is not None]
            if used:
                parser.error("--csv cannot be combined with "
                             + ", ".join("--" + f.replace("_", "-") for f in used))
            books = load_csv(args.csv)
            if not books:
                print(f"No books found in {args.csv}", file=sys.stderr)
                sys.exit(1)
        else:
            missing = [f for f in ("title", "authors", "read_date")
                       if getattr(args, f) is None]
            if missing:
                parser.error("missing required: "
                             + ", ".join("--" + {"authors": "author"}.get(f, f).replace("_", "-")
                                         for f in missing))
            book = build_book({f: getattr(args, f) for f in single_fields})
            timeatlas.validateBook(book)
            books = [book]
    except (ValueError, OSError, timeatlas.ValidationError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    for b in books:
        print(f"  {describe(b)}")

    if args.dry_run:
        print(f"Dry run: {len(books)} book{'' if len(books) == 1 else 's'} validated, nothing written.")
        return

    try:
        filepath = timeatlas.insertBooks(books)
    except timeatlas.ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Added {len(books)} book{'' if len(books) == 1 else 's'}.")
    print(f"  Written to: {filepath}")


if __name__ == "__main__":
    main()
