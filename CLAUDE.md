This repository contains tools to deal with data by Time Atlas app.

App stores it files in iCloud, in a folder that can be accessed by $HOME/Library/Mobile Documents/iCloud~com~timeatlaslabs~Pat/Documents/

This folder contains a FORMAT.txt and timeline.proto which explain the data model which is based on files containing protobuffer message FullDirectory.

#1 Basic setup

Generate python protobuffer code for the timeline.proto and store in this repository.

#2 Database schema

For each type of message in FullDirectory, such as event, media or known place, create its own table which has an primary key id (string) and a data column as blob. Each protobuffer message would be then inserted as-is to the table to id corresponding to message.meta.id.

In addition, study the protobuffer definition and create a column for each timestamp field, and store the unix timestamp in there. For example, meta.created_at of each message, and start_at and end_at of the Event message.

Messages which have meta.deleted_at should be deleted from the database.

#2 Database sync

Create a script setup.py which creates an SQLite3 database "timeatlas.db" unless it exists, using the schema defined above. Create an additional sync state table that contains list of already synchronized prefixes. The prefixes are unix timestamps in second and the files the icloud folder have that prefix.

Then create a sync function which loads the files that are not imported yet from the icloud folder. Note that some files are zip files that contain protobufferfiles inside. Open the zip files in-memory (i.e do not extract on the file system).
