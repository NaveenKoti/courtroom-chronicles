#!/usr/bin/env python3
"""Make a 16:9 YouTube video for one episode: cover art, moving waveform, title and optional chapter titles.

Usage:  python3 make_video.py ep064 [--audio file.mp3] [--cover file.png] [--out out.mp4]

Audio : --audio, else the episode's file from data/audio.json (your podcast RSS feed).
Cover : --cover, else the square episode art from the RSS feed, else the share image in assets/og.
Chapters (optional): data/chapters/ep064.txt, one per line like "12:30 Verdict: Absolute Liability".
Needs ffmpeg and Pillow. Output goes to video/<id>.mp4.
"""
import argparse, glob, json, os, re, subprocess, sys, tempfile, textwrap, urllib.request
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw, ImageFilter, ImageFont

os.chdir(os.path.dirname(os.path.abspath(__file__)))
W, H = 1920, 1080
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"]
FONT_SANS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Helvetica.ttc"]


def font(paths, size):
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def fetch(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "courtroom-chronicles-video/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)


def rss_cover(link, dest, feed):
    """Square episode art from the RSS feed item whose <link> matches."""
    try:
        raw = urllib.request.urlopen(urllib.request.Request(feed, headers={"User-Agent": "courtroom-chronicles-video/1.0"}), timeout=30).read()
        ns = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
        for it in ET.fromstring(raw).iter("item"):
            if it.findtext("link") == link:
                im = it.find(ns + "image")
                if im is not None and im.get("href"):
                    fetch(im.get("href"), dest)
                    return True
    except Exception as ex:
        print("RSS cover skipped:", ex)
    return False


def chapters_for(ep):
    p = "data/chapters/%s.txt" % ep
    out = []
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            m = re.match(r"\s*(?:(\d+):)?(\d+):(\d\d)\s+(.+)", line)
            if m:
                h, mi, s, title = m.groups()
                out.append((int(h or 0) * 3600 + int(mi) * 60 + int(s), title.strip()))
    return sorted(out)


ap = argparse.ArgumentParser()
ap.add_argument("episode")
ap.add_argument("--audio")
ap.add_argument("--cover")
ap.add_argument("--out")
a = ap.parse_args()
ep = a.episode.lower()
meta = json.load(open("data/episodes/%s.json" % ep, encoding="utf-8"))
site = json.load(open("site.json", encoding="utf-8"))
audio_info = (json.load(open("data/audio.json", encoding="utf-8")).get(ep) or {}) if os.path.exists("data/audio.json") else {}
tmp = tempfile.mkdtemp()

audio = a.audio
if not audio:
    if not audio_info.get("url"):
        sys.exit("No audio for %s: pass --audio or wait until it appears in the podcast feed." % ep)
    audio = os.path.join(tmp, "audio" + os.path.splitext(audio_info["url"].split("?")[0])[1][:5] if False else os.path.join(tmp, "audio.bin"))
    print("Downloading audio...")
    fetch(audio_info["url"], audio)

cover = a.cover
if not cover and audio_info.get("link") and site["links"].get("rss"):
    c = os.path.join(tmp, "cover.img")
    if rss_cover(audio_info["link"], c, site["links"]["rss"]):
        cover = c
if not cover:
    g = sorted(glob.glob("assets/og/%s-*.png" % ep))
    cover = g[0] if g else None
if not cover:
    sys.exit("No cover art found: pass --cover.")

# ---- background frame (Pillow) ----
art = Image.open(cover).convert("RGB")
bg = art.resize((W, int(W * art.height / art.width)) if art.width / art.height < W / H else (int(H * art.width / art.height), H))
bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
bg = bg.filter(ImageFilter.GaussianBlur(40))
dark = Image.new("RGB", (W, H), (0, 0, 0))
frame = Image.blend(bg, dark, 0.62)
side = 760
if abs(art.width - art.height) < 10:
    sq = art.resize((side, side))
else:  # not square (share-image fallback): fit whole picture inside the square on a dark card
    sq = Image.new("RGB", (side, side), (20, 14, 16))
    k = side / art.width if art.width >= art.height else side / art.height
    fit = art.resize((int(art.width * k), int(art.height * k)))
    sq.paste(fit, ((side - fit.width) // 2, (side - fit.height) // 2))
frame.paste(sq, (110, (H - side) // 2))
d = ImageDraw.Draw(frame)
x0 = 110 + side + 90
d.text((x0, 150), "COURTROOM CHRONICLES", font=font(FONT_SANS, 34), fill=(210, 190, 140))
m = re.match(r"ep0*(\d+)", ep)
n = int(m.group(1))
label = "EPISODE %d" % n if n < 64 else "SEASON 2 · EPISODE %d" % (n - 63)
d.text((x0, 200), label, font=font(FONT_SANS, 30), fill=(170, 170, 170))
title_font = font(FONTS, 62)
y = 270
maxw = W - x0 - 90
lines, cur = [], ""
for word in meta["title"].split():
    t = (cur + " " + word).strip()
    if d.textlength(t, font=title_font) <= maxw:
        cur = t
    else:
        lines.append(cur)
        cur = word
lines.append(cur)
for line in lines[:5]:
    d.text((x0, y), line, font=title_font, fill=(255, 255, 255))
    y += 78
d.text((x0, H - 90), "Indian court cases, explained in plain English", font=font(FONT_SANS, 28), fill=(170, 170, 170))
bgpath = os.path.join(tmp, "bg.png")
frame.save(bgpath)

# ---- ffmpeg ----
dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio]).decode().strip())
wave_w, wave_h = W - x0 - 110, 230
fc = ("[1:a]aformat=channel_layouts=mono,showwaves=s=%dx%d:mode=cline:rate=24:colors=gold:scale=sqrt:draw=full,format=rgba,colorkey=black:0.15:0.1[w];"
      "[0:v][w]overlay=%d:%d[v0]" % (wave_w, wave_h, x0, 790))
last = "v0"
chs = chapters_for(ep)
fontfile = next((p for p in FONT_SANS if os.path.exists(p)), None)
for i, (t0, name) in enumerate(chs):
    t1 = chs[i + 1][0] if i + 1 < len(chs) else dur + 1
    tf = os.path.join(tmp, "ch%d.txt" % i)
    open(tf, "w", encoding="utf-8").write(name)
    nxt = "v%d" % (i + 1)
    fc += (";[%s]drawtext=fontfile=%s:textfile=%s:fontsize=40:fontcolor=0xE6C97A:x=%d:y=720:enable='between(t,%s,%s)'[%s]"
           % (last, fontfile, tf, x0, t0, t1, nxt))
    last = nxt
out = a.out or "video/%s.mp4" % ep
os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
cmd = ["ffmpeg", "-y", "-loglevel", "error", "-stats", "-loop", "1", "-framerate", "24", "-i", bgpath, "-i", audio,
       "-filter_complex", fc, "-map", "[%s]" % last, "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", out]
print("Rendering %.1f minutes of video..." % (dur / 60))
subprocess.check_call(cmd)
print("Done:", out, "%.1f MB" % (os.path.getsize(out) / 1e6))
