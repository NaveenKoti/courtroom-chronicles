# Courtroom Chronicles website

A static site (plain HTML, no framework) built from your episode JSON files.
It has a searchable home page, one page per episode, an audio player fed by your RSS feed,
previous/next links, and SEO tags (title, description, canonical, Open Graph, schema.org, sitemap).

Long statute links can be written as short names in the JSON (`"url": "@IPC"`); the list is at the top of `build.py`.
