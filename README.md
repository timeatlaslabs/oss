This repository contains open source tools to access data from the Time Atlas app.
Time Atlas stores its data for syncing in iCloud, see Library/Mobile Documents/iCloud~com~timeatlaslabs~Pat/Documents/
on your Apple Mac computer. On Windows the folder lives under `%USERPROFILE%\iCloudDrive\iCloud~com~timeatlaslabs~Pat\Documents`.

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
activity distances and non-zero step counts.

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
