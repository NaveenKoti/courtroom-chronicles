# Courtroom Chronicles website

A static site (plain HTML, no framework) built from your episode JSON files.
It has a searchable home page, one page per episode, an audio player fed by your RSS feed,
previous/next links, and SEO tags (title, description, canonical, Open Graph, schema.org, sitemap).

## Deploy in 5 minutes

1. Open `site.json` and replace `YOUR-GITHUB-USERNAME` in `baseUrl` with your GitHub username
   (and the repo name if it is not `courtroom-chronicles`). Then run `python3 build.py` once
   (or skip: the GitHub Action rebuilds it for you in step 4).
2. Create a new GitHub repo and upload everything in this folder.
3. Repo > Settings > Pages > Source: **Deploy from a branch**, branch **main**, folder **/ (root)**.
4. Repo > Actions > "Rebuild site" > Run workflow. This pulls audio from your RSS feed and rebuilds.
5. Open `https://YOUR-USERNAME.github.io/REPO-NAME/`. Then add the site in Google Search Console
   and submit `sitemap.xml`.

## Add an episode

Put the new `epNNN.json` into `data/episodes/` and commit it. The Action rebuilds the site.
(Run `python3 fetch_audio.py && python3 build.py` yourself to preview locally.)

## How the player finds audio

`fetch_audio.py` reads your RSS feed and matches each episode by title (or "EP 12" in the feed title).
The audio file goes into the player. If no match is found, the page tries the RSS feed in the browser,
and if that fails it shows the Spotify player. Check the Action log for `NO MATCH` lines.

## Files

- `data/episodes/epNNN.json`  your episode files (one per episode)
- `site.json`  site title, links, base URL
- `build.py`  makes the pages;  `fetch_audio.py`  reads the RSS feed
- `assets/style.css`, `assets/app.js`  look and behaviour
- `index.html`, `episodes/`, `sitemap.xml`, `robots.txt`, `404.html`  generated, do not edit by hand

Long statute links can be written as short names in the JSON (`"url": "@IPC"`); the list is at the top of `build.py`.
