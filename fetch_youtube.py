#!/usr/bin/env python3
"""Match YouTube videos to episodes and save data/youtube.json.

Reads the playlist's public Atom feed (no login, no API key, free). Each video whose title starts with
"EP12" / "EP012" / "Episode 12" is saved under its episode id ("ep012"), so a video is linked as soon as
its episode page exists. build.py then adds a direct "YouTube" link to that episode page.

YouTube feeds list only the 15 newest videos. This script keeps everything it saw before, so it
accumulates over time; run it daily (the GitHub workflow does) and nothing is lost.

Usage: python3 fetch_youtube.py [feed_url_or_local_file]   (default: the playlist in site.json links.youtube)
A feed outage never fails the run; the old youtube.json is kept.
"""
import json, os, re, sys, urllib.request
import xml.etree.ElementTree as ET

os.chdir(os.path.dirname(os.path.abspath(__file__)))
site = json.load(open("site.json", encoding="utf-8"))

src = sys.argv[1] if len(sys.argv) > 1 else None
if not src:
    m = re.search(r"[?&]list=([\w-]+)", site.get("links", {}).get("youtube", ""))
    if not m:
        sys.exit("No playlist: set links.youtube in site.json to a playlist URL")
    src = "https://www.youtube.com/feeds/videos.xml?playlist_id=" + m.group(1)

try:
    if os.path.exists(src):
        raw = open(src, "rb").read()
    else:
        req = urllib.request.Request(src, headers={"User-Agent": "courtroom-chronicles-site/1.0"})
        raw = urllib.request.urlopen(req, timeout=30).read()
    root = ET.fromstring(raw)
except Exception as ex:
    print("YouTube feed skipped (%s). Existing data/youtube.json kept." % ex)
    sys.exit(0)

NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
out = {}
if os.path.exists("data/youtube.json"):
    out = json.load(open("data/youtube.json", encoding="utf-8"))

found, seen = {}, {}
for e in root.findall("a:entry", NS):
    title = (e.findtext("a:title", "", NS) or "").strip()
    vid = (e.findtext("yt:videoId", "", NS) or "").strip()
    m = re.match(r"^\s*(?:ep|episode)\s*\.?\s*0*(\d+)\b", title, re.I)
    if not (m and re.fullmatch(r"[\w-]{6,}", vid)):
        print("Not matched to an episode: %s" % title[:80])
        continue
    key = "ep%03d" % int(m.group(1))
    seen.setdefault(key, []).append(vid)
    found[key] = {"videoId": vid, "url": "https://www.youtube.com/watch?v=" + vid, "title": title}

for key, vids in seen.items():
    if len(set(vids)) > 1:
        print("AMBIGUOUS %s: %d different videos start with that number; keeping the first listed." % (key, len(set(vids))))
        found[key]["videoId"] = vids[0]
        found[key]["url"] = "https://www.youtube.com/watch?v=" + vids[0]

out.update(found)
os.makedirs("data", exist_ok=True)
json.dump(dict(sorted(out.items())), open("data/youtube.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("youtube.json: %d episodes saved (%d seen in this feed)" % (len(out), len(found)))
