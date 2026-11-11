#!/usr/bin/env python3
"""Delete a movie or TV show entry from Time Atlas.

Finds matching entries in the local database by title (case-insensitive) or
IMDb ID, then writes an update with meta.deleted_at set. If several entries
match (e.g. rewatches or episodes), you are asked which ones to delete.

Usage:
    python tools/delete_movie.py --title TITLE [--yes]
    python tools/delete_movie.py --imdb-id ID [--yes]

Examples:
    python tools/delete_movie.py --title "Heat"
    python tools/delete_movie.py --imdb-id tt0113277 --yes
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas

from add_movie import describe


def choose(movies: list, describe=describe) -> list:
    """Ask which of several matching entries to delete."""
    for i, m in enumerate(movies, 1):
        print(f"  {i}. {describe(m)}")
    answer = input("Delete which? (numbers separated by commas, 'a' for all, empty to cancel): ").strip().lower()
    if not answer:
        return []
    if answer in ("a", "all"):
        return movies
    chosen = []
    for part in answer.split(","):
        part = part.strip()
        if not part.isdigit() or not 1 <= int(part) <= len(movies):
            raise ValueError(f"invalid choice: {part!r}")
        m = movies[int(part) - 1]
        if m not in chosen:
            chosen.append(m)
    return chosen


def main():
    parser = argparse.ArgumentParser(description="Delete a movie or TV show entry from Time Atlas")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--title", "-t", help="Title to delete (case-insensitive exact match)")
    group.add_argument("--imdb-id", help="IMDb ID to delete, e.g. tt0111161")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Delete all matches without asking")
    args = parser.parse_args()

    movies = timeatlas.findMoviesAndTv(title=args.title, imdb_id=args.imdb_id)
    if not movies:
        what = f"title {args.title!r}" if args.title else f"IMDb ID {args.imdb_id}"
        print(f"No movie found with {what}. Try running 'python sync.py' first.", file=sys.stderr)
        sys.exit(1)

    try:
        if args.yes:
            to_delete = movies
            for m in movies:
                print(f"  {describe(m)}")
        elif len(movies) == 1:
            print(f"  {describe(movies[0])}")
            confirm = input("Delete this entry? [y/N]: ").strip().lower()
            to_delete = movies if confirm in ("y", "yes") else []
        else:
            print(f"Found {len(movies)} matching entries:")
            to_delete = choose(movies)
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
    print(f"Deleted {len(to_delete)} entr{'y' if len(to_delete) == 1 else 'ies'}.")
    print(f"  Written to: {filepath}")


if __name__ == "__main__":
    main()
