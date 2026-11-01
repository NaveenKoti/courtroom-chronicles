#!/usr/bin/env python3
"""Match each episode to its item in your podcast RSS feed and save data/audio.json.

build.py then puts the audio file in each episode's player and the publish date in its markup.
Matching: the episode title appears in the feed item's title (ignoring case and punctuation),
else the feed item's title says "EP 12" / "Episode 12". Unmatched episodes still work: the page
falls back to the Spotify player.

Usage:  python3 fetch_audio.py [feed_url_or_local_file]     (default: links.rss in site.json)
A feed outage never fails the run; the old audio.json is kept.
"""
import glob, json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))
site = json.load(open("site.json", encoding="utf-8"))
src = sys.argv[1] if len(sys.argv) > 1 else site["links"].get("rss")
if not src:
    sys.exit("No feed: set links.rss in site.json")

try:
    if os.path.exists(src):
        raw = open(src, "rb").read()
    else:
        req = urllib.request.Request(src, headers={"User-Agent": "courtroom-chronicles-site/1.0"})
        raw = urllib.request.urlopen(req, timeout=30).read()
    root = ET.fromstring(raw)
except Exception as ex:
    print("Feed skipped (%s). Existing data/audio.json kept." % ex)
    sys.exit(0)

IT = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


items = []
for it in root.iter("item"):
    enc = it.find("enclosure")
    pub = it.findtext("pubDate")
    try:
        when = parsedate_to_datetime(pub).date().isoformat() if pub else None
    except Exception:
        when = None
    items.append({"raw": it.findtext("title") or "", "t": norm(it.findtext("title")),
                  "url": enc.get("url") if enc is not None else None, "date": when,
                  "duration": it.findtext(IT + "duration"), "link": it.findtext("link")})

out = {}
if os.path.exists("data/audio.json"):
    out = json.load(open("data/audio.json", encoding="utf-8"))
used = set()
for p in sorted(glob.glob("data/episodes/ep*.json")):
    d = json.load(open(p, encoding="utf-8"))
    n = int(re.match(r"ep(\d+)", d["id"], re.I).group(1))
    key = norm(d["title"])
    hits = [i for i, it in enumerate(items) if key and (key in it["t"] or (it["t"] in key and len(it["t"]) > 12))]
    if len(hits) != 1:
        pat = re.compile(r"\b(ep|episode)\s*0*%d\b" % n)
        hits = [i for i, it in enumerate(items) if pat.search(it["t"])]
    if len(hits) != 1:
        print(("AMBIGUOUS" if hits else "NO MATCH") + " %s: %s" % (d["id"], d["title"]))
        continue
    it = items[hits[0]]
    used.add(hits[0])
    if it["url"]:
        out[d["id"]] = {k: v for k, v in {"url": it["url"], "date": it["date"], "duration": it["duration"],
                                          "link": it["link"], "feedTitle": it["raw"]}.items() if v}

for i, it in enumerate(items):
    if i not in used:
        print("Feed item not matched to any episode JSON: %s" % it["raw"])
os.makedirs("data", exist_ok=True)
json.dump(out, open("data/audio.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("audio.json: %d episodes matched, %d feed items read" % (len(out), len(items)))
