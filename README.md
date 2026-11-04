# Courtroom Chronicles website

A static site (plain HTML, no framework) built from your episode JSON files.
It has a searchable home page, one page per episode, an audio player fed by your RSS feed,
previous/next links, and SEO tags (title, description, canonical, Open Graph, schema.org, sitemap).


Long statute links can be written as short names in the JSON (`"url": "@IPC"`); the list is at the top of `build.py`.

## Optional episode fields and automatic extras

- `"caseName"` in an episode JSON (for example `"Uphaar cinema fire case"`) is the plain name people search for.
  `build.py` uses it to build the page title, description, tags, the YouTube thumbnail and the card on the home page.
  If it is missing, `data/seo.json` is checked, then the old title is used.
- `fetch_youtube.py` reads the YouTube playlist feed (free, no key) and saves `data/youtube.json`, so each episode page
  gets a direct YouTube link. The GitHub workflow runs it daily.
- `build.py` also writes topic pages (`/topics/...`), a short link for every episode (`/go/ep021/`), and a YouTube
  thumbnail for every episode (`assets/thumbs/ep021.png`; upload it to the video in YouTube Studio).
- `"googleSiteVerification"` in `site.json` adds the Google Search Console verification tag to the home page.
