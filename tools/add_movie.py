#!/usr/bin/env python3
"""Add a movie or TV show entry into Time Atlas.

Usage:
    python tools/add_movie.py --title TITLE --year YEAR --watched-at (now|UNIX_TS) \\
        (--imdb-id ID | --tmdb-id ID) [--stars STARS] [options]
    python tools/add_movie.py --csv FILE [--dry-run]

Examples:
    python tools/add_movie.py --title "Dune: Part Two" --year 2024 --stars 4.5 \\
        --watched-at now --imdb-id tt15239678
    python tools/add_movie.py --title "Severance" --year 2022 --stars 5 \\
        --watched-at 1739980800 --tmdb-id 95396 --type tv --season 2 --episode 10
    python tools/add_movie.py --csv movies.csv

CSV format: a header row with column names matching the long option names
(underscores or dashes both accepted). Required columns: title, year, watched_at
and at least one of imdb_id / tmdb_id. Optional columns: stars, type
(movie or tv, default movie), season, episode, review, url.
"""

import argparse
import csv
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import timeatlas
import timeatlas_pb2

SOURCE = "oss"
CSV_COLUMNS = {
    "title", "year", "stars", "watched_at", "imdb_id", "tmdb_id",
    "type", "season", "episode", "review", "url",
}


def parse_watched_at(value: str) -> float:
    value = (value or "").strip()
    if value.lower() == "now":
        return time.time()
    try:
        ts = float(value)
    except ValueError:
        raise ValueError(f"watched_at must be 'now' or a unix timestamp, got {value!r}")
    if ts <= 0:
        raise ValueError(f"watched_at must be a positive unix timestamp, got {value!r}")
    return ts


TYPE_ALIASES = {"movie": "movie", "tv": "episode", "show": "episode", "episode": "episode"}


def parse_type(value: str) -> str:
    """Map a user-given type to the stored value: 'movie' (default) or 'episode'."""
    value = (value or "").strip().lower()
    if not value:
        return "movie"
    if value not in TYPE_ALIASES:
        raise ValueError(f"type must be movie or tv (also: show, episode), got {value!r}")
    return TYPE_ALIASES[value]


def build_movie(fields: dict) -> timeatlas_pb2.MovieAndTv:
    """Build a MovieAndTv message from a dict of field values (strings or numbers).

    Raises ValueError if a required field is missing or malformed.
    """
    def get(name):
        v = fields.get(name)
        return "" if v is None else str(v).strip()

    title = get("title")
    if not title:
        raise ValueError("title is required")
    try:
        year = int(get("year"))
    except ValueError:
        raise ValueError(f"year must be an integer, got {get('year')!r}")
    try:
        stars = float(get("stars") or 0)
    except ValueError:
        raise ValueError(f"stars must be a number, got {get('stars')!r}")
    if stars and not 1 <= stars <= 5:
        raise ValueError(f"stars must be between 1 and 5, got {stars}")
    imdb_id, tmdb_id = get("imdb_id"), get("tmdb_id")
    if not imdb_id and not tmdb_id:
        raise ValueError("either imdb_id or tmdb_id is required")
    watched_at = parse_watched_at(get("watched_at"))

    movie = timeatlas_pb2.MovieAndTv()
    movie.title = title
    movie.year = year
    movie.stars = stars
    movie.imdbId = imdb_id
    movie.tmdbId = tmdb_id
    secs = int(watched_at)
    movie.watched_at.seconds = secs
    movie.watched_at.nanos = int((watched_at - secs) * 1e9)
    movie.type = parse_type(get("type"))
    movie.season = get("season")
    movie.episode_number = get("episode")
    movie.review = get("review")
    movie.url = get("url")
    movie.source = SOURCE
    return movie


def load_csv(path: str) -> list[timeatlas_pb2.MovieAndTv]:
    movies, errors = [], []
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
                movie = build_movie(row)
                timeatlas.validateMovieAndTv(movie)
                movies.append(movie)
            except (ValueError, timeatlas.ValidationError) as e:
                errors.append(f"  line {reader.line_num}: {e}")
    if errors:
        raise ValueError(f"{path}: {len(errors)} invalid row(s):\n" + "\n".join(errors))
    return movies


def describe(movie: timeatlas_pb2.MovieAndTv) -> str:
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(movie.watched_at.seconds))
    ident = f"imdb {movie.imdbId}" if movie.imdbId else f"tmdb {movie.tmdbId}"
    extra = ""
    if movie.season or movie.episode_number:
        extra = f" S{movie.season or '?'}E{movie.episode_number or '?'}"
    rating = f"{movie.stars:g}★" if movie.stars else "unrated"
    return f"{movie.title} ({movie.year}){extra}  {rating}  watched {when}  [{ident}]"


def main():
    parser = argparse.ArgumentParser(
        description="Add a movie or TV show entry into Time Atlas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="CSV format:" + __doc__.split("CSV format:", 1)[1],
    )
    parser.add_argument("--csv", help="Batch import entries from a CSV file")
    parser.add_argument("--title", "-t", help="Title (required)")
    parser.add_argument("--year", "-y", help="Release year (required)")
    parser.add_argument("--stars", "-s", help="Rating 1-5, decimals allowed (optional)")
    parser.add_argument("--watched-at", "-w", help="'now' or a unix timestamp in seconds (required)")
    parser.add_argument("--imdb-id", help="IMDb ID, e.g. tt0111161 (this or --tmdb-id required)")
    parser.add_argument("--tmdb-id", help="TMDb ID (this or --imdb-id required)")
    parser.add_argument("--type", help="movie (default) or tv; tv is stored as 'episode'")
    parser.add_argument("--season", help="Season (for TV)")
    parser.add_argument("--episode", help="Episode number (for TV)")
    parser.add_argument("--review", help="Free-form review text")
    parser.add_argument("--url", help="Related URL")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Validate and print entries without writing")
    args = parser.parse_args()

    single_fields = ["title", "year", "stars", "watched_at", "imdb_id", "tmdb_id",
                     "type", "season", "episode", "review", "url"]
    try:
        if args.csv:
            used = [f for f in single_fields if getattr(args, f) is not None]
            if used:
                parser.error("--csv cannot be combined with "
                             + ", ".join("--" + f.replace("_", "-") for f in used))
            movies = load_csv(args.csv)
            if not movies:
                print(f"No entries found in {args.csv}", file=sys.stderr)
                sys.exit(1)
        else:
            missing = [f for f in ("title", "year", "watched_at")
                       if getattr(args, f) is None]
            if missing:
                parser.error("missing required: "
                             + ", ".join("--" + f.replace("_", "-") for f in missing))
            movie = build_movie({f: getattr(args, f) for f in single_fields})
            timeatlas.validateMovieAndTv(movie)
            movies = [movie]
    except (ValueError, OSError, timeatlas.ValidationError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    for m in movies:
        print(f"  {describe(m)}")

    if args.dry_run:
        print(f"Dry run: {len(movies)} entr{'y' if len(movies) == 1 else 'ies'} validated, nothing written.")
        return

    try:
        filepath = timeatlas.insertMoviesAndTvs(movies)
    except timeatlas.ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Added {len(movies)} entr{'y' if len(movies) == 1 else 'ies'}.")
    print(f"  Written to: {filepath}")


if __name__ == "__main__":
    main()
