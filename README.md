This repository contains open source tools to access data from the Time Atlas app: https://apps.apple.com/us/app/time-atlas-life-tracker/id6738783076.


# Accessing data of the Time Atlas app
Time Atlas stores its data for syncing in iCloud, see `Library/Mobile Documents/iCloud~com~timeatlaslabs~Pat/Documents/` on your Apple Mac computer. On Windows the folder lives under `%USERPROFILE%\iCloudDrive\iCloud~com~timeatlaslabs~Pat\Documents`.

# About the Code
The code has been developed in an AI-driven manner with the Claude Code, see CLAUDE.md for its instructions.

We encourage users to "vibe code" their own tools. Please submit pull requests for improvements and cool tools!

Join our Discord channel: https://discord.gg/zwJEYNdsPE

# Getting started

## 1. Create and activate a virtual environment

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

## 2. Install dependencies

```bash
pip install -r requirements.txt
```

## 3. Run sync.py to create the database and sync from iCloud

```bash
python sync.py
```

This creates `timeatlas.db` in the repository root and imports any Time Atlas files
that have not been synced yet. Re-run it at any time to pick up new data.

# Tools

The `tools/` directory contains small scripts that read the synced database.

Note: always run "sync.py" first to sync the data. Consider adding this to an automatically running cronjob
to ensure your data is always in sync.

## date_query.py

List events for a date or a range of dates, grouped by date. Sleeps are summarised
at the bottom of each day instead of listed inline; movement events include per-
activity distances and non-zero step counts. Books finished, movies/TV watched and
Last.fm tracks played on the day are listed too (with `--show-notes` book and
movie reviews are shown as well).

```bash
# Single day.
python tools/date_query.py 2026-04-20

# Range (inclusive).
python tools/date_query.py 2026-04-01 2026-04-07

# Include journal entry notes attached to the date event and to place visits.
python tools/date_query.py 2026-04-20 --show-notes

# Hide the end-of-day totals (sleep, distance per activity).
python tools/date_query.py 2026-04-20 --no-summary
```

## knownplaces.py

For each known place with the given name, print its address/location and every
place-visit event tied to it.

```bash
python tools/knownplaces.py "Starbucks"

# Include any journal entries attached to each place visit.
python tools/knownplaces.py "Gym" --show-notes
```

## geojson.py

Export place visits (Point features) and movement trajectories (LineString
features) for a date range as GeoJSON. Each feature carries the start time in
ISO8601; place visits get the place name, movement trajectories get the
activity type.

```bash
# Single day, printed to stdout.
python tools/geojson.py 2026-04-20

# Inclusive date range, printed to stdout.
python tools/geojson.py 2026-04-01 2026-04-07

# Write a whole week to a file (loadable in https://geojson.io).
python tools/geojson.py 2026-04-01 2026-04-07 -o april.geojson

# Filter by activity (short code). Place visits are excluded.
python tools/geojson.py 2025-01-15 --activity ski

# Filter by activity (full name) and write to a file.
python tools/geojson.py 2025-01-10 2025-01-20 --activity cycling -o rides.geojson

# Filter walks for a single day.
python tools/geojson.py 2025-03-01 --activity wlk
```

## addnote.py

Capture a note and write it as `note_<timestamp-in-millis>.json` directly into
the Time Atlas iCloud directory so the app picks it up on its next sync.

```bash
# Interactive: type the note, finish with two empty lines.
python tools/addnote.py

# Read the note body from a file.
python tools/addnote.py -f note.txt

# Open $EDITOR (or vi / notepad) in a window to compose the note.
python tools/addnote.py -w

# Attach the note to a specific date instead of today.
python tools/addnote.py -d 2026-04-15 -f note.txt
```

## insert_log.py

Insert a tally (log entry) into Time Atlas. The entry is written as a protobuf
file into the iCloud directory so the app picks it up on its next sync.

```bash
# Log 200 ml of water for today.
python tools/insert_log.py water 200 ml

# Log with a category.
python tools/insert_log.py wine 2 glass --category white

# Log for a specific date and person.
python tools/insert_log.py weight 4.3 kg --who baby --date 2026-04-20
```

## add_movie.py

Add a watched movie or TV show. Required: `--title`, `--year`, `--watched-at`
(`now` or a unix timestamp) and either `--imdb-id` or `--tmdb-id`. `--stars`
(1–5) is optional. Entries are stored as type `movie` unless you pass
`--type tv`, which stores them as `episode`. Entries are tagged with source `oss`.

```bash
# Add a movie watched right now.
python tools/add_movie.py --title "Dune: Part Two" --year 2024 --stars 4.5 \
    --watched-at now --imdb-id tt15239678

# Add a TV episode watched at a given time.
python tools/add_movie.py --title "Severance" --year 2022 --stars 5 \
    --watched-at 1739980800 --tmdb-id 95396 --type tv --season 2 --episode 10

# Batch import from CSV (validate first with --dry-run).
python tools/add_movie.py --csv movies.csv --dry-run
python tools/add_movie.py --csv movies.csv
```

The CSV needs a header row. Columns use the option names: `title`, `year`,
`stars`, `watched_at`, `imdb_id`, `tmdb_id`, `type`, `season`, `episode`,
`review`, `url`. `type` is `movie` (the default) or `tv`; TV entries are stored
with type `episode`. All rows are checked before anything is written. If any row is
invalid, the tool lists the errors by line number and writes nothing.

Example `movies.csv`:

```csv
title,year,stars,watched_at,imdb_id,tmdb_id,type,season,episode,review
Heat,1995,4.5,1731283200,tt0113277,,movie,,,"Great shootout scene"
Severance,2022,5,1739980800,,95396,tv,2,10,
Dune: Part Two,2024,,now,tt15239678,,movie,,,
```

## delete_movie.py

Delete a movie or TV show entry by title (case-insensitive) or IMDb ID. The
tool looks the entry up in the local database and writes an update with
`deleted_at` set. If several entries match, such as rewatches or episodes of a
series, it lists them and asks which ones to delete.

```bash
# Delete by title (asks for confirmation).
python tools/delete_movie.py --title "Heat"

# Delete every entry with this IMDb ID without asking.
python tools/delete_movie.py --imdb-id tt0113277 --yes
```

The entry is removed from `timeatlas.db` on the next `python sync.py`.

## add_book.py

Add a book you have read. Required: `--title`, at least one `--author` (repeat
for co-authors), `--read-date` (`today` or `YYYY-mm-dd`) and either `--isbn` or
`--isbn13`. `--stars` (1–5), `--pages`, `--year`, `--original-year` and
`--review` are optional. Books are tagged with source `oss`.

```bash
# Add a book finished today.
python tools/add_book.py --title "Four Thousand Weeks" --author "Oliver Burkeman" \
    --stars 4 --read-date today --isbn13 9780374159122

# Multiple authors and extra details.
python tools/add_book.py --title "Good Omens" --author "Terry Pratchett" \
    --author "Neil Gaiman" --stars 4.5 --read-date 2026-10-01 --isbn 0060853980 \
    --pages 432 --year 2006 --original-year 1990

# Batch import from CSV (validate first with --dry-run).
python tools/add_book.py --csv books.csv --dry-run
python tools/add_book.py --csv books.csv
```

The CSV columns are `title`, `authors`, `stars`, `read_date`, `isbn`, `isbn13`,
`pages`, `year`, `original_year` and `review`. Separate multiple authors with `;`.
As with movies, all rows are checked before anything is written.

Example `books.csv`:

```csv
title,authors,stars,read_date,isbn,isbn13,pages
Good Omens,Terry Pratchett;Neil Gaiman,4.5,2026-10-01,0060853980,,432
Maniac,Benjamín Labatut,,today,,9788433911001,
```

## delete_book.py

Delete a book by title (case-insensitive) or ISBN (ISBN-10 or ISBN-13). Works
like `delete_movie.py`: it asks for confirmation, or which ones to delete if
several books match.

```bash
python tools/delete_book.py --title "Four Thousand Weeks"
python tools/delete_book.py --isbn 9780374159122 --yes
```

The book is removed from `timeatlas.db` on the next `python sync.py`.

## activity_replace.py

Interactively replace one activity type with another across a date range. The
tool presents a numbered list of activities to choose from, shows how many
activities and total distance will be affected, and asks for confirmation
before writing the update.

```bash
python tools/activity_replace.py
```

The tool will prompt you for:
1. A date range (from / to)
2. The activity to change **from** (e.g. `trp` — Transport)
3. The activity to change **to** (e.g. `bus` — Bus)
4. Confirmation before writing the update

## weather.py

Query the weather table for a date range. For each date prints the temperature
min/max and top observed conditions, then shows an overall histogram of
conditions across the range.

```bash
# Single day.
python tools/weather.py 2026-04-20

# Date range (inclusive).
python tools/weather.py 2026-04-01 2026-04-07
```

With `-v` the tool plots temperature over time using matplotlib — requires
`pip install matplotlib`. Without `-o` a window is opened; with `-o` the plot
is saved to the given file (window-less, so it works over SSH too).

```bash
# Open a plot window.
python tools/weather.py 2026-04-01 2026-04-07 -v

# Save to a PNG instead.
python tools/weather.py 2026-04-01 2026-04-07 -v -o april-weather.png
```

# Using Claude Code

To generate the main code, I used this prompt: "Study CLAUDE.md, and create the discussed scripts in python."
I think I forgot to add please!
