"""Helpers for looking up Time Atlas Media objects in the Apple Photos library."""

import sys
from datetime import datetime, timezone

import osxphotos

import timeatlas_pb2

_photosdb = None


def _get_photosdb() -> osxphotos.PhotosDB:
    global _photosdb
    if _photosdb is None:
        print("Loading Apple Photos database...", file=sys.stderr)
        _photosdb = osxphotos.PhotosDB()
        print("Photos database loaded.", file=sys.stderr)
    return _photosdb


def getPhotoForMedia(media: timeatlas_pb2.Media) -> osxphotos.PhotoInfo | None:
    """Find an Apple Photos asset matching the given Media object.

    Matches by original filename first, then narrows by modified timestamp
    (within 2 seconds tolerance) if the Media has one.  Returns the best
    match, or None if nothing is found.
    """
    if not media.HasField("filename"):
        return None

    db = _get_photosdb()
    candidates = db.photos(images=True, movies=True)
    by_name = [p for p in candidates if p.original_filename == media.filename]

    if not by_name:
        return None

    if len(by_name) == 1:
        return by_name[0]

    # Multiple matches — try to disambiguate using modified_timestamp
    if media.HasField("modified_timestamp") and media.modified_timestamp.seconds:
        media_dt = datetime.fromtimestamp(
            media.modified_timestamp.seconds + media.modified_timestamp.nanos / 1e9,
            tz=timezone.utc,
        )
        best = None
        best_delta = None
        for photo in by_name:
            if photo.date_modified is not None:
                mod = photo.date_modified
                if mod.tzinfo is None:
                    mod = mod.replace(tzinfo=timezone.utc)
                delta = abs((mod - media_dt).total_seconds())
                if best_delta is None or delta < best_delta:
                    best = photo
                    best_delta = delta
        if best is not None and best_delta <= 2.0:
            return best

    # Fall back to first filename match
    return by_name[0]
