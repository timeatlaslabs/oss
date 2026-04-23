This repository contains tools to deal with data by Time Atlas app.

App stores it files in iCloud, in a folder that can be accessed on Mac from $HOME/Library/Mobile Documents/iCloud~com~timeatlaslabs~Pat/Documents/. On windows it is in "C:\Users\YourUsername\iCloudDrive", if user has iCloud installed.
 
This folder contains a FORMAT.txt and timeline.proto which explain the data model which is based on files containing protobuffer message FullDirectory.

#1 Basic setup

Generate python protobuffer code for the timeline.proto and store in this repository.

#2 Database schema

For each type of message in FullDirectory, such as event, media or known place, create its own table which has an primary key id (string) and a data column as blob. Each protobuffer message would be then inserted as-is to the table to id corresponding to message.meta.id.

For each event type, create a own table like events_place_visits, events_movements, and do not create a events table. Store the whole event message, but choose the table based on the event type.

In addition, study the protobuffer definition and create a column for each timestamp field, and store the unix timestamp in there. For example, meta.created_at of each message, and start_at and end_at of the Event message. Have indices for the event start_at and end_at.

For all the tables, create columns for all simple fields of the event submessage, like event.place_visit would have "name", "secondary_name" and "known_place_id". Do not create columns for repeated fields or structure typed fields.

Furthermore, for events, make a column for event_type, which is a string based on the enum name for the event type. This is to make it easier to read.

Messages which have meta.deleted_at should be deleted from the database.

#2 Database sync

Create a script setup.py which creates an SQLite3 database "timeatlas.db" unless it exists, using the schema defined above. Create an additional sync state table that contains list of already synchronized prefixes. The prefixes are unix timestamps in second and the files the icloud folder have that prefix.

Then create a sync function which loads the files that are not imported yet from the icloud folder. Note that some files are zip files that contain protobufferfiles inside. Open the zip files in-memory (i.e do not extract on the file system).

#3 Startup instructions

Modify README.md to have instructions how to run setup.py, including setting up virtual environment and installing dependencies.

#4 Python tools

Let's write some python tools, place them in directory tools.  Before that, let's specify some helper functions that would be a shared timeatlas.py module:
- getDatabasePath() -- returns path to the timeatlas.db
- getDateDateRange(date) which loads from database a date event with the date (format YYYY-mm-dd), checks its start and end times and returns a tuple of datetime objects (start-datetime, end-datetime) corresponding to those times. The date times should have correct timezone based on the utcOffset.
- getDates(from, to) would return all dates withing the range and list of tuple (date-string yyyy-mm-dd, start-datetime, end-datetime)
- getEvents(type, from-datetime, to-datetime) would load events of type (such as "placevisit", "movement") from the correct table whose start-time-end-time overlaps with the given query. Sort by start time ascending. The events would be the protobuffer messages stored in db.
- getKnownPlace(id) returns the known place with the given id, i.e the protobuffer message. 
- getKnownPlace(name) returns the list of known places with the given name, i.e the protobuffer message. 

Then create following tools:
- date_query.py which takes a range of dates (or just one date) and prints their events in a nice grouped manner.
- knownplaces.py which takes a known place name and for each known place with the name prints their address and lists all place visit events to the known place (query by placevisit known-place-id)


#5 Python Tools -- additional features

For both date_query.py and knownplaces.py, add a flag "--show-notes" to include notes as well. This means loading journal entry's for each event ID encountered (date events, place visits). If there is no note for an event, do not show anything. 

In date_query.py, show the distances and non-zero steps for all movement activities.
Do not print sleeps in details. Instead, at the end print the daily total of sleep in hours and minutes.
Also print the total distance, duration and steps for each activity (wlk, run, etc...). Add a flag "--no-summary" to prevent showing the total details.


#6 More tools: GeoJSON

Add a tool geojson.py, which takes a date range and outputs the events (place visits and movement activity trajectories) in GeoJSON format. Each place visit or movement activity is a "Feature" in GeoJSON. For GeoJSON, add to the properties activity type for movements and place name for place visits. In addition, add the start time in ISO8601 format to the feature for both types.

For activities, add a "stroke" property with a hex color for different activity types. Read in code the activity types from data/activity_colors.json (map activity-type: color in hex), and use that, by using "trp" color if not found.

Add a flag for the output file, otherwise print in stdout the json.


#7 More tools: Adding notes

Add a tool addnote.json which either takes an input file (given with -f or --file) or adds a prompt to enter text (two empty lines finishes a note). With -w open a window to enter a text. 

After user has finished with the text, or it was provided as an input file, create a JSON file with structure:
 { "text": text,
      "source": "user:oss",
      "timestamp": iso8601-formatter current timestamp
      "date": date in yyyy-mm-dd,
 }

The date is the current date or user can pass a flag -d to specify date.

The file should be stored with name "note_<timestamp-in-millis>.json" to the icloud directory.

#8 More tools: Weather

Add a tool to query the weather table. Given a date range, print the temperature range and conditions for each date and in the summary write a simple histogram.

If user specifies -v, use matplotlib to plot the weather and open it in a window or store in a file (flag).


#9 Tools to README.md

Add instructions on how to use the tools to the README.md by providing examples.
