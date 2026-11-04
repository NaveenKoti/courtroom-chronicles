#!/usr/bin/env python3
"""Courtroom Chronicles: build the static site from data/episodes/*.json.

Run:  python3 build.py
Writes (into this folder): index.html, episodes/<slug>/index.html, laws/ (law finder),
assets/og/*.png (share images, needs Pillow), sitemap.xml, robots.txt, 404.html.
assets/style.css and assets/app.js are plain files you can edit.
Optional: data/audio.json (made by fetch_audio.py) supplies audio URLs from your RSS feed.
Standard library only (Pillow is optional, for share images).
"""
import glob, hashlib, html, json, os, re, shutil, sys
from datetime import date
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

# Short names used inside episode JSON ("url": "@IPC") so the same long link is not repeated.
# Any value that does not start with "@" is used as written.
URL_ALIASES = {
    "@IPC": "https://thc.nic.in/Central%20Governmental%20Acts/Indian%20Penal%20Code,%201860%20.pdf",
    "@BNS": "https://uppolice.gov.in/site/writereaddata/siteContent/Three%20New%20Major%20Acts/202406281710564823BNS_IPC_Comparative.pdf",
    "@BSA": "https://thc.nic.in/Central%20Governmental%20Acts/Bharatiya%20Sakshya%20Adhiniyam,%202023.pdf",
    "@BSACMP": "https://uppolice.gov.in/site/writereaddata/siteContent/Three%20New%20Major%20Acts/202407031507276576BSA2023-9-25.pdf",
    "@BNSSCMP": "https://uppolice.gov.in/site/writereaddata/siteContent/Three%20New%20Major%20Acts/202407031502194192BNSS2023-20-45.pdf",
    "@CRPC": "https://cdnbbsr.s3waas.gov.in/s3ec044a11654ad1e1e48352252859ff30/uploads/2023/11/2023110156.pdf",
    "@CONST": "https://cdnbbsr.s3waas.gov.in/s380537a945c7aaa788ccfcdf1b99b5d8f/uploads/2024/07/20240716890312078.pdf",
}

# Wording your Master Standard asks you to verify before publishing. Build only warns.
WATCH = re.compile(
    r"\b(landmark|historic|unprecedented|groundbreaking|ground-breaking|definitive|greatest|"
    r"most important|first[- ]ever|world'?s first|india'?s first|pioneering)\b", re.I)

# Law codes for the law finder.
ACT_CODES = [("penal code", "ipc"), ("nyaya", "bns"), ("criminal procedure", "crpc"), ("nagarik", "bnss"),
             ("evidence act", "iea"), ("sakshya", "bsa"), ("constitution", "constitution")]
ACT_SHORT = {"ipc": "IPC", "bns": "BNS", "crpc": "CrPC", "bnss": "BNSS", "iea": "Evidence Act",
             "bsa": "BSA", "constitution": "Constitution"}
ACT_ORDER = ["ipc", "crpc", "iea", "constitution", "bns", "bnss", "bsa"]

site = json.load(open("site.json", encoding="utf-8"))
BASE = site["baseUrl"].rstrip("/")
PLACEHOLDER = "YOUR-GITHUB-USERNAME" in BASE
LINKS = site.get("links", {})
e = html.escape


def esc(s):
    return e(str(s if s is not None else ""), quote=True)


def safe_url(u):
    if not u:
        return None
    u = URL_ALIASES.get(u, u)
    return u if re.match(r"^https?://", u) else None


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def slug_words(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower().replace("'", "").replace("’", "")).strip("-")


def slugify(title, n):
    out = []
    for w in slug_words(title).split("-"):
        if len("-".join(out + [w])) > 56:
            break
        out.append(w)
    return "ep%03d-%s" % (n, "-".join(out))


def short(s, n):
    s = " ".join(str(s).split())
    if len(s) <= n:
        return s
    return s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"


def jsonld(obj):
    return '<script type="application/ld+json">%s</script>' % json.dumps(
        obj, ensure_ascii=False).replace("</", "<\\/")


def act_code(act):
    a = (act or "").lower()
    for key, code in ACT_CODES:
        if key in a:
            return code
    return slug_words(act) or "other"


# ---------- load ----------
audio_map = {}
if os.path.exists("data/audio.json"):
    audio_map = json.load(open("data/audio.json", encoding="utf-8"))

def derive_case_name(feed_title):
    """Best-effort case name from a published title like 'EP06: Poetic title — The Jessica Lal Case and the ...'."""
    t = re.sub(r"^\s*(?:ep|episode)\s*\.?\s*\d+\s*[:\-–—]\s*", "", feed_title or "", flags=re.I)
    parts = re.split(r"\s*[—–]\s*", t, maxsplit=1)
    if len(parts) < 2:
        return ""
    sub = re.split(r"\s+and\s+(?:the|its|a)\s+", parts[1], maxsplit=1)[0]
    sub = re.sub(r"^the\s+", "", sub.strip(" .,:;"), flags=re.I).strip(" .,:;")
    return sub if 4 <= len(sub) <= 70 else ""


# Optional: data/seo.json maps an episode id to its plain case name (used when the episode JSON has no "caseName").
seo_map = {}
if os.path.exists("data/seo.json"):
    seo_map = json.load(open("data/seo.json", encoding="utf-8"))
# Optional: data/youtube.json (made by fetch_youtube.py) maps an episode id to its YouTube video.
youtube_map = {}
if os.path.exists("data/youtube.json"):
    youtube_map = json.load(open("data/youtube.json", encoding="utf-8"))

episodes = []
for p in sorted(glob.glob("data/episodes/ep*.json")):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("draft"):   # "draft": true keeps an episode off the site until its JSON is replaced/corrected
        print("Skipping draft episode %s" % d.get("id", p))
        continue
    m = re.match(r"ep(\d+)", d.get("id", ""), re.I)
    if not m:
        sys.exit("%s: 'id' must look like ep012" % p)
    d["n"] = int(m.group(1))
    d["slug"] = d.get("slug") or slugify(d["title"], d["n"])
    # Case name priority: episode JSON > data/seo.json (an empty "" there means "do not use one") >
    # derived from the published podcast title ("Poetic title — The Jessica Lal Case and ...") > none.
    cn = d.get("caseName")
    if not cn:
        cn = seo_map[d["id"]] if d["id"] in seo_map else derive_case_name((audio_map.get(d["id"]) or {}).get("feedTitle", ""))
    if not site.get("useCaseNames", False):   # off by default; set "useCaseNames": true in site.json to switch on
        cn = ""
    d["caseName"] = " ".join(str(cn or "").split())
    a = audio_map.get(d["id"], {})
    d["audio"] = {**a, **(d.get("audio") or {})}
    d["listen"] = {**LINKS, **(d.get("listen") or {})}
    yt = youtube_map.get(d["id"]) or {}
    if re.match(r"^https://(www\.)?youtube\.com/watch\?v=[\w-]{6,}$", yt.get("url", "")):
        d["listen"]["youtube"] = yt["url"]   # direct link to this episode's video, instead of the playlist
        d["ytUrl"] = yt["url"]
    episodes.append(d)
episodes.sort(key=lambda x: x["n"])
if len({x["n"] for x in episodes}) != len(episodes):
    sys.exit("Duplicate episode numbers")
nums = [x["n"] for x in episodes]


def ep_url(x):
    return "%s/episodes/%s/" % (BASE, x["slug"])


def fact(x, label):
    for f in x.get("facts", []):
        if f.get("label", "").lower() == label.lower():
            return f.get("value", "")
    return ""


def outcome(x):
    return (x.get("judgment") or {}).get("outcome") or x["hook"]


def page_title(x):
    """Search-friendly <title>: lead with the plain case name people actually search for."""
    if x.get("caseName"):
        return "%s: Judgment Explained | %s" % (x["caseName"], site["title"])
    return "EP%03d: %s | %s" % (x["n"], x["title"], site["title"])


def page_desc(x):
    if x.get("caseName"):
        return short("%s explained: %s" % (x["caseName"], x["hook"]), 158)
    return short(x["hook"], 158)


def label_with_case(x):
    return ("%s — %s" % (x["title"], x["caseName"])) if x.get("caseName") else x["title"]


# Topic pages: one page per tag in the episodes' "topics" lists.
TOPICS = {}
for _x in episodes:
    for _t in _x.get("topics", []):
        _s = slug_words(_t)
        if _s:
            TOPICS.setdefault(_s, {"slug": _s, "name": _t, "eps": []})["eps"].append(_x)


def read_minutes(x):
    parts = list(x.get("summary", [])) + list(x.get("takeaways", []))
    parts += [t.get("text", "") for t in x.get("timeline", [])]
    j = x.get("judgment") or {}
    parts += [j.get("outcome", "")] + list(j.get("points", []))
    for p in x.get("principles", []):
        parts += [p.get("meaning", ""), p.get("inThisCase", "")]
    return max(1, round(len(" ".join(parts).split()) / 210))


def warn_words(x):
    blob = json.dumps({k: v for k, v in x.items() if k in (
        "title", "hook", "summary", "judgment", "principles", "takeaways", "timeline")}, ensure_ascii=False)
    return sorted({m.group(0).lower() for m in WATCH.finditer(blob)})


# ---------- law finder data ----------
prov = {}
for x in episodes:
    for m in x.get("lawMapping", []):
        o = m.get("old") or {}
        sec = o.get("section", "")
        if not sec:
            continue
        code = act_code(o.get("act", ""))
        slug = "%s-%s" % (code, slug_words(sec))
        p = prov.setdefault(slug, {"slug": slug, "code": code, "act": o.get("act", ""), "section": sec,
                                   "title": o.get("title", ""), "url": o.get("url"), "news": [], "changes": [], "eps": []})
        n = m.get("new")
        if n:
            tup = (n.get("act", ""), n.get("section", ""), n.get("title", ""), n.get("url"))
            if tup not in p["news"]:
                p["news"].append(tup)
        ch = m.get("change")
        if ch and len(p["changes"]) < 2 and not any(norm(ch)[:30] == norm(c)[:30] for c in p["changes"]):
            p["changes"].append(ch)
        if x not in p["eps"]:
            p["eps"].append(x)
        m["_prov"] = slug
PAGES = {s: p for s, p in prov.items() if len(p["eps"]) >= 2}  # only these get their own page


def prov_label(p):
    s = "%s %s" % (p["section"], ACT_SHORT.get(p["code"], p["act"]))
    if p["news"]:
        a, sec = p["news"][0][0], p["news"][0][1]
        s += " (now %s %s)" % (sec, ACT_SHORT.get(act_code(a), a))
    return s


# ---------- share images ----------
FONTS_BOLD = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"]
FONTS_REG = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]


def _font(paths, size):
    from PIL import ImageFont
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return None


def make_og(x):
    """One 1200x630 share image per episode. Returns a site path, or None if Pillow/fonts are missing."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    court, year = fact(x, "Court"), fact(x, "Year")
    stamp = hashlib.md5(("%s|%s|%s" % (x["title"], court, year)).encode("utf-8")).hexdigest()[:6]
    path = "assets/og/%s-%s.png" % (x["id"], stamp)
    if os.path.exists(path):
        return path
    big, mid, small = _font(FONTS_BOLD, 66), _font(FONTS_REG, 34), _font(FONTS_REG, 28)
    if not (big and mid and small):
        return None
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), (122, 31, 43))
    d = ImageDraw.Draw(im)
    d.rectangle([36, 36, W - 36, H - 36], outline=(217, 178, 95), width=4)
    d.text((84, 84), "EPISODE %d" % x["n"], font=mid, fill=(217, 178, 95))
    lines, cur = [], ""
    for w in x["title"].split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=big) > W - 168 and cur:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    y = 150
    for ln in lines[:4]:
        d.text((84, y), ln, font=big, fill=(250, 248, 244))
        y += 84
    foot = " · ".join(v for v in (court, year) if v)
    if foot:
        d.text((84, H - 140), foot, font=small, fill=(240, 220, 180))
    d.text((84, H - 96), site["title"] + "  |  " + site["tagline"], font=small, fill=(250, 248, 244))
    os.makedirs("assets/og", exist_ok=True)
    im.save(path, optimize=True)
    return path


def make_thumb(x):
    """1280x720 YouTube thumbnail with the case name in big type -> assets/thumbs/<id>.png (upload it to the video).
    Returns the path, or None if Pillow/fonts are missing. Same input gives the same file, so no noisy commits."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    W, H = 1280, 720
    text = (x.get("caseName") or x["title"]).strip()
    text = text[0].upper() + text[1:]
    sub = " · ".join(v for v in (fact(x, "Court").split(" (")[0], fact(x, "Year")) if v)
    if not _font(FONTS_BOLD, 40):
        return None
    im = Image.new("RGB", (W, H), (122, 31, 43))
    d = ImageDraw.Draw(im)
    d.rectangle([28, 28, W - 28, H - 28], outline=(217, 178, 95), width=5)
    box_w, box_h = W - 180, 400
    lines = []
    for size in range(150, 55, -6):               # biggest type that fits in at most 4 lines
        f = _font(FONTS_BOLD, size)
        lines, cur = [], ""
        for w in text.split():
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) > box_w and cur:
                lines.append(cur)
                cur = w
            else:
                cur = t
        lines.append(cur)
        if len(lines) <= 4 and len(lines) * size * 1.12 <= box_h and all(d.textlength(l, font=f) <= box_w for l in lines):
            break
    lh = int(size * 1.12)
    y = 170 + max(0, (box_h - lh * len(lines)) // 2)
    for ln in lines:
        d.text((90, y), ln, font=f, fill=(250, 248, 244))
        y += lh
    badge = _font(FONTS_BOLD, 46)
    d.rounded_rectangle([90, 70, 90 + 230, 140], radius=14, fill=(217, 178, 95))
    d.text((112, 80), "EP %d" % x["n"], font=badge, fill=(122, 31, 43))
    small = _font(FONTS_REG, 38)
    d.text((90, H - 130), (sub + "  ·  " if sub else "") + "Judgment explained", font=small, fill=(240, 220, 180))
    d.text((90, H - 82), site["title"], font=small, fill=(250, 248, 244))
    os.makedirs("assets/thumbs", exist_ok=True)
    path = "assets/thumbs/%s.png" % x["id"]
    im.save(path, optimize=True)
    return path


# ---------- shared page shell ----------
def head(title, desc, canonical, depth, extra="", og_type="website", image_path=None, prev=None, nxt=None, noindex=False):
    root = "../" * depth
    img = ""
    ip = image_path or (site.get("ogImage") if site.get("ogImage") and os.path.exists(site.get("ogImage", "")) else None)
    if ip:
        img_url = "%s/%s" % (BASE, ip)
        img = ('<meta property="og:image" content="%s">\n<meta property="og:image:width" content="1200">\n'
               '<meta property="og:image:height" content="630">\n<meta name="twitter:image" content="%s">\n'
               % (esc(img_url), esc(img_url)))
    pn = ""
    if prev:
        pn += '<link rel="prev" href="%s">\n' % esc(ep_url(prev))
    if nxt:
        pn += '<link rel="next" href="%s">\n' % esc(ep_url(nxt))
    rss = LINKS.get("rss")
    rss_tag = ('<link rel="alternate" type="application/rss+xml" title="%s" href="%s">\n'
               % (esc(site["title"]), esc(rss))) if rss else ""
    robots = "noindex" if noindex else "index, follow, max-image-preview:large"
    return """<!doctype html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<meta name="robots" content="%(robots)s">
<meta name="theme-color" content="#7a1f2b">
<meta name="color-scheme" content="light dark">
<link rel="canonical" href="%(canon)s">
%(pn)s%(rss)s<meta property="og:site_name" content="%(site)s">
<meta property="og:type" content="%(ogt)s">
<meta property="og:title" content="%(title)s">
<meta property="og:description" content="%(desc)s">
<meta property="og:url" content="%(canon)s">
<meta property="og:locale" content="en_IN">
<meta name="twitter:card" content="%(card)s">
<meta name="twitter:title" content="%(title)s">
<meta name="twitter:description" content="%(desc)s">
%(img)s<link rel="icon" href="data:image/svg+xml,%%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%%3E%%3Ctext y='.9em' font-size='90'%%3E%%E2%%9A%%96%%EF%%B8%%8F%%3C/text%%3E%%3C/svg%%3E">
<link rel="stylesheet" href="%(root)sassets/style.css">
%(extra)s</head>
""" % dict(lang=site.get("lang", "en"), title=esc(title), desc=esc(desc), canon=esc(canonical), site=esc(site["title"]),
           ogt=og_type, card="summary_large_image" if img else "summary", img=img, pn=pn, rss=rss_tag,
           root=root, extra=extra, robots=robots)


def header(depth):
    root = "../" * depth
    return """<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap bar">
<a class="brand" href="%(r)s"><span class="mark" aria-hidden="true">⚖</span> %(t)s</a>
<nav aria-label="Main"><a href="%(r)s#episodes">Episodes</a><a href="%(r)slaws/">Law finder</a><a href="%(r)s#about">About</a></nav>
</div></header>
""" % dict(r=root or "./", t=esc(site["title"]))


def footer(extra_disclaimer=""):
    return """<footer class="foot"><div class="wrap">
<p class="foot-links">%s</p>
<p class="disc">%s</p>
<p class="small">© %s %s. Case notes are drawn from public court records.</p>
</div></footer>
""" % (platform_links(LINKS, plain=True), esc(extra_disclaimer or site.get("disclaimer", "")), date.today().year, esc(site["title"]))


PLATFORMS = [("spotify", "Spotify"), ("apple", "Apple Podcasts"), ("youtube", "YouTube"), ("rss", "RSS")]


def platform_links(ln, primary=False, plain=False):
    out = []
    for key, label in PLATFORMS:
        u = ln.get(key)
        if not u:
            continue
        if plain:
            out.append('<a href="%s" rel="noopener" target="_blank">%s</a>' % (esc(u), label))
        else:
            out.append('<a class="btn %s p-%s" href="%s" rel="noopener" target="_blank">%s</a>' % (
                "" if primary else "ghost", key, esc(u), ("Listen on " + label) if (primary and key != "rss") else label))
    return "".join(out)


def apple_embed(ln):
    u = ln.get("apple") or ""
    m = re.match(r"^https://podcasts\.apple\.com/(.+)$", u)
    return ("https://embed.podcasts.apple.com/" + m.group(1).split("?")[0]) if m else ""


# ---------- episode page ----------
def player_block(x):
    a = x.get("audio") or {}
    url = safe_url(a.get("url"))
    ln = x["listen"]
    parts = ['<section class="player" id="listen" aria-label="Listen to this episode" '
             'data-title="%s" data-num="%d" data-rss="%s" data-spotify="%s" data-apple="%s" data-id="%s">'
             % (esc(norm(x["title"])), x["n"], esc(LINKS.get("rss") or ""), esc(ln.get("spotifyShowId") or ""),
                esc(apple_embed(ln)), esc(x["id"]))]
    parts.append('<h2>Listen</h2>')
    parts.append('<audio controls preload="none"%s></audio>' % ((' src="%s"' % esc(url)) if url else " hidden"))
    parts.append('<div class="pbar"><span class="pstat" aria-live="polite"></span>'
                 '<button type="button" class="btn ghost speed" hidden aria-label="Playback speed">1×</button></div>')
    parts.append('<div class="embed" hidden></div>')
    parts.append('<div class="btns">%s</div>' % platform_links(ln))
    parts.append('<noscript><p class="small">Turn on JavaScript to play here, or use the links above.</p></noscript></section>')
    return "".join(parts)


def section(id_, title, body):
    return '<section class="sec" id="%s"><h2>%s</h2>%s</section>\n' % (id_, esc(title), body)


def ul(items):
    return "<ul>%s</ul>" % "".join("<li>%s</li>" % esc(i) for i in items)


def map_cell(side):
    if not side:
        return '<div class="mc none">—</div>'
    u = safe_url(side.get("url"))
    sec = esc(side.get("section", ""))
    sec_html = ('<a href="%s" rel="noopener" target="_blank">%s</a>' % (esc(u), sec)) if u else sec
    return ('<div class="mc"><span class="act">%s</span><strong>%s</strong><span class="ttl">%s</span></div>'
            % (esc(side.get("act", "")), sec_html, esc(side.get("title", ""))))


def yt_id(x):
    m = re.search(r"[?&]v=([\w-]{6,})$", x.get("ytUrl", ""))
    return m.group(1) if m else ""


def card_thumb(x, big=False):
    """Episode YouTube thumbnail for lists (public, free). mqdefault always exists; maxres only for the big 'latest' tile."""
    v = yt_id(x)
    if not v:
        return ""
    src = "maxresdefault" if big else "mqdefault"
    fb = "" if not big else ' onerror="this.onerror=null;this.src=\'https://i.ytimg.com/vi/%s/mqdefault.jpg\'"' % v
    return ('<img class="thumb" src="https://i.ytimg.com/vi/%s/%s.jpg" width="%d" height="%d" loading="%s" alt="" '
            'referrerpolicy="no-referrer"%s>' % (v, src, 1280 if big else 320, 720 if big else 180, "eager" if big else "lazy", fb))


def render_episode(x, prev, nxt):
    url = ep_url(x)
    desc = page_desc(x)
    title = page_title(x)
    topics = x.get("topics", [])
    court, year = fact(x, "Court"), fact(x, "Year")
    mins = read_minutes(x)
    og = make_og(x)
    make_thumb(x)
    kw = ([x["caseName"]] if x.get("caseName") else []) + list(topics)

    graph = [
        {"@type": "PodcastEpisode", "@id": url + "#episode", "url": url, "name": x["title"],
         "description": x["hook"], "episodeNumber": x["n"], "inLanguage": site.get("lang", "en"),
         "keywords": ", ".join(kw),
         "partOfSeries": {"@type": "PodcastSeries", "name": site["title"], "url": BASE + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": site["title"], "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "EP%03d" % x["n"], "item": url}]},
    ]
    if og:
        graph[0]["image"] = "%s/%s" % (BASE, og)
    if x.get("ytUrl"):
        graph[0]["sameAs"] = [x["ytUrl"]]
    a = x.get("audio") or {}
    if a.get("date"):
        graph[0]["datePublished"] = a["date"]
    if safe_url(a.get("url")):
        graph[0]["associatedMedia"] = {"@type": "AudioObject", "contentUrl": safe_url(a["url"]), "encodingFormat": "audio/mpeg"}
    ld = jsonld({"@context": "https://schema.org", "@graph": graph})
    out = [head(title, desc, url, 2, extra=ld + "\n", og_type="article", image_path=og, prev=prev, nxt=nxt)]
    out.append("<body>\n" + header(2))
    out.append('<main id="main" class="wrap ep">\n')
    out.append('<nav class="crumbs" aria-label="Breadcrumb"><a href="../../">%s</a> › <span>EP%03d</span></nav>\n'
               % (esc(site["title"]), x["n"]))
    meta = " · ".join(v for v in (court, year, "%d min read" % mins) if v)
    out.append('<article>\n<header class="eph"><p class="kicker">Episode %d%s%s</p><h1>%s</h1><p class="hook">%s</p>'
               '<p class="meta">%s</p>' % (x["n"], (" · " + esc(a["date"])) if a.get("date") else "",
                                           (" · " + esc(x["caseName"])) if x.get("caseName") else "", esc(x["title"]),
                                           esc(x["hook"]), esc(meta)))
    if topics:
        out.append('<p class="chips">%s</p>' % "".join(
            '<a class="chip" href="../../topics/%s/">%s</a>' % (esc(slug_words(t)), esc(t)) for t in topics))
    out.append('</header>\n')
    vid = re.search(r"[?&]v=([\w-]{6,})$", x.get("ytUrl", ""))
    if vid and og:
        # The episode's own YouTube thumbnail (public, free). Falls back: HD -> standard size -> generated card.
        v = vid.group(1)
        out.append(
            '<a class="epimg-link" href="%s" rel="noopener" target="_blank" aria-label="Watch EP%03d on YouTube">'
            '<img class="epimg" src="https://i.ytimg.com/vi/%s/maxresdefault.jpg" width="1280" height="720" '
            'style="aspect-ratio:16/9;object-fit:cover" alt="Episode %d thumbnail: %s" fetchpriority="high" '
            'referrerpolicy="no-referrer" onerror="if(!this.dataset.f){this.dataset.f=1;'
            'this.src=\'https://i.ytimg.com/vi/%s/hqdefault.jpg\'}else{this.onerror=null;this.src=\'../../%s\';'
            'this.style.aspectRatio=\'1200/630\'}"></a>\n'
            % (esc(x["ytUrl"]), x["n"], v, x["n"], esc(x["title"]), v, esc(og)))
    elif og:
        out.append('<img class="epimg" src="../../%s" width="1200" height="630" alt="Episode %d: %s%s" fetchpriority="high">\n'
                   % (esc(og), x["n"], esc(x["title"]), esc(" (%s)" % x["caseName"]) if x.get("caseName") else ""))

    if (x.get("judgment") or {}).get("outcome"):
        out.append('<aside class="verdict"><strong>The decision in one line</strong><p>%s</p></aside>\n' % esc(x["judgment"]["outcome"]))

    out.append(player_block(x) + "\n")
    share_text = "%s: %s" % (x["title"], url)
    out.append('<p class="share"><a class="btn ghost" rel="noopener" target="_blank" href="https://wa.me/?text=%s">Share on WhatsApp</a>'
               '<button type="button" class="btn ghost" data-copy="%s">Copy link</button>'
               '<button type="button" class="btn ghost" data-share="%s" data-url="%s" hidden>Share…</button></p>\n'
               % (quote(share_text), esc(url), esc(x["title"]), esc(url)))

    if x.get("facts"):
        out.append('<dl class="facts">%s</dl>\n' % "".join(
            "<div><dt>%s</dt><dd>%s</dd></div>" % (esc(f.get("label")), esc(f.get("value"))) for f in x["facts"]))

    toc, body = [], []
    if x.get("takeaways"):
        toc.append(("takeaways", "Key takeaways"))
        body.append('<section class="sec learn" id="takeaways"><h2>Key takeaways</h2>%s</section>\n' % ul(x["takeaways"]))
    if x.get("summary"):
        toc.append(("summary", "The case in brief"))
        body.append(section("summary", "The case in brief", "".join("<p>%s</p>" % esc(p) for p in x["summary"])))
    if x.get("timeline"):
        toc.append(("timeline", "Timeline"))
        items = "".join('<li%s><time>%s</time><div><strong>%s</strong><p>%s</p></div></li>' % (
            ' class="key"' if t.get("key") else "", esc(t.get("date")), esc(t.get("title")), esc(t.get("text")))
            for t in x["timeline"])
        body.append(section("timeline", "Timeline", '<ol class="tl">%s</ol>' % items))
    j = x.get("judgment")
    if j:
        toc.append(("judgment", "What the court decided"))
        b = '<p class="outcome">%s</p>' % esc(j.get("outcome", ""))
        if j.get("points"):
            b += "<h3>Key holdings</h3>" + ul(j["points"])
        body.append(section("judgment", "What the court decided", b))
    if x.get("principles"):
        toc.append(("principles", "Legal principles"))
        items = ""
        for p in x["principles"]:
            lat = ' <em class="latin">%s</em>' % esc(p["latin"]) if p.get("latin") else ""
            items += ('<div class="pr"><h3>%s%s</h3><p>%s</p><p class="case"><strong>In this case:</strong> %s</p></div>'
                      % (esc(p.get("name")), lat, esc(p.get("meaning")), esc(p.get("inThisCase"))))
        body.append(section("principles", "Legal principles", items))
    if x.get("lawMapping") or x.get("lawNote"):
        toc.append(("law", "The law then and now"))
        b = ""
        if x.get("lawNote"):
            b += '<p class="note">%s</p>' % esc(x["lawNote"])
        rows = ""
        for m in x.get("lawMapping", []):
            more = ""
            if m.get("_prov") in PAGES:
                pg = PAGES[m["_prov"]]
                more = ' <a class="more" href="../../laws/%s/">See all %d episodes on this provision →</a>' % (esc(pg["slug"]), len(pg["eps"]))
            rows += ('<li class="map">%s<span class="arrow" aria-hidden="true">→</span>%s<p class="chg">%s%s</p></li>'
                     % (map_cell(m.get("old")), map_cell(m.get("new")), esc(m.get("change", "")), more))
        if rows:
            b += ('<p class="small">Left: the law applied to this case. Right: the matching provision today '
                  '(the new criminal codes apply only to offences on or after 1 July 2024).</p>'
                  '<ul class="maps">%s</ul>' % rows)
        body.append(section("law", "The law then and now", b))
    if x.get("sources"):
        toc.append(("sources", "Sources"))
        items = ""
        for s in x["sources"]:
            u = safe_url(s.get("url"))
            items += '<li>%s</li>' % (('<a href="%s" rel="noopener" target="_blank">%s</a>' % (esc(u), esc(s.get("label")))) if u else esc(s.get("label")))
        body.append(section("sources", "Sources", "<ul class='src'>%s</ul>" % items))

    if toc:
        out.append('<nav class="toc" aria-label="On this page"><strong>On this page</strong> %s</nav>\n' %
                   " ".join('<a href="#%s">%s</a>' % (i, esc(t)) for i, t in toc))
    out.extend(body)

    related = sorted((r for r in episodes if r is not x),
                     key=lambda r: (-len(set(r.get("topics", [])) & set(topics)), abs(r["n"] - x["n"])))[:3]
    related = [r for r in related if set(r.get("topics", [])) & set(topics)]
    if related:
        out.append('<section class="sec"><h2>More episodes on these topics</h2><ul class="rel">%s</ul></section>\n' % "".join(
            '<li><a href="../%s/"><span class="num">EP%03d</span> %s</a></li>' % (esc(r["slug"]), r["n"], esc(r["title"]))
            for r in related))

    out.append('<nav class="pn" aria-label="Episode navigation">')
    out.append(('<a class="prev" href="../%s/"><small>← Previous</small><span>EP%03d · %s</span></a>' % (esc(prev["slug"]), prev["n"], esc(prev["title"]))) if prev else "<span></span>")
    out.append(('<a class="next" href="../%s/"><small>Next →</small><span>EP%03d · %s</span></a>' % (esc(nxt["slug"]), nxt["n"], esc(nxt["title"]))) if nxt else "<span></span>")
    out.append('</nav>\n</article>\n</main>\n')
    out.append(footer(x.get("disclaimer", "")))
    out.append('<script src="../../assets/app.js" defer></script>\n</body>\n</html>\n')
    return "".join(out)


# ---------- law finder ----------
def ep_list(eps, depth):
    root = "../" * depth
    return '<ul class="rel">%s</ul>' % "".join(
        '<li><a href="%sepisodes/%s/"><span class="num">EP%03d</span> %s</a></li>' % (root, esc(r["slug"]), r["n"], esc(label_with_case(r)))
        for r in sorted(eps, key=lambda r: r["n"]))


def render_topic(t):
    url = "%s/topics/%s/" % (BASE, t["slug"])
    n = len(t["eps"])
    cases = [x["caseName"] for x in sorted(t["eps"], key=lambda r: r["n"]) if x.get("caseName")][:4]
    desc = short("%s: %d Indian court case%s explained in plain English%s." % (
        t["name"], n, "" if n == 1 else "s", (", including " + ", ".join(cases)) if cases else ""), 158)
    title = "%s cases in India: judgments explained | %s" % (t["name"], site["title"])
    ld = jsonld({"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "name": "%s cases" % t["name"], "url": url, "description": desc,
         "inLanguage": site.get("lang", "en")},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": site["title"], "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": t["name"], "item": url}]}]})
    out = [head(title, desc, url, 2, extra=ld + "\n")]
    out.append("<body>\n" + header(2) + '<main id="main" class="wrap ep">\n')
    out.append('<nav class="crumbs" aria-label="Breadcrumb"><a href="../../">%s</a> › <span>%s</span></nav>\n' % (esc(site["title"]), esc(t["name"])))
    out.append('<article><header class="eph"><p class="kicker">Topic</p><h1>%s cases</h1><p class="hook">%d episode%s on this topic.</p></header>\n'
               % (esc(t["name"]), n, "" if n == 1 else "s"))
    out.append(section("episodes", "Episodes", ep_list(t["eps"], 2)))
    others = [o for o in TOPICS.values() if o is not t]
    if others:
        out.append('<section class="sec"><h2>Other topics</h2><p class="chips">%s</p></section>\n' % "".join(
            '<a class="chip" href="../%s/">%s</a>' % (esc(o["slug"]), esc(o["name"])) for o in sorted(others, key=lambda o: o["name"])))
    out.append('<p class="note">%s</p>\n</article></main>\n' % esc(site.get("disclaimer", "")))
    out.append(footer() + '<script src="../../assets/app.js" defer></script>\n</body>\n</html>\n')
    return "".join(out)


def render_alias(x):
    """Short, stable link /go/ep021/ for YouTube/Spotify descriptions: no need to know the long page slug."""
    u = esc(ep_url(x))
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><title>Redirecting…</title>'
            '<meta name="robots" content="noindex"><link rel="canonical" href="%s">'
            '<meta http-equiv="refresh" content="0; url=%s"></head>'
            '<body><p>Taking you to <a href="%s">%s</a>…</p></body></html>\n' % (u, u, u, esc(x["title"])))


def render_prov(p):
    label = prov_label(p)
    url = "%s/laws/%s/" % (BASE, p["slug"])
    title = "%s: %s | %s" % (label, p["title"], site["title"])
    act_s = ACT_SHORT.get(p["code"], p["act"])
    if p["news"]:
        nw = ", ".join("%s of the %s" % (s, a) for a, s, _t, _u in p["news"])
        now_txt = "The matching provision today is %s." % nw
    else:
        now_txt = "It has not been replaced; the same provision applies today."
    n = len(p["eps"])
    desc = short("%s of the %s: %s. %s Seen in %d Courtroom Chronicles cases." % (p["section"], p["act"], p["title"], now_txt, n), 158)
    ld = jsonld({"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "name": label + ": " + p["title"], "url": url, "description": desc, "inLanguage": site.get("lang", "en")},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": site["title"], "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Law finder", "item": BASE + "/laws/"},
            {"@type": "ListItem", "position": 3, "name": label, "item": url}]}]})
    out = [head(title, desc, url, 2, extra=ld + "\n")]
    out.append("<body>\n" + header(2) + '<main id="main" class="wrap ep">\n')
    out.append('<nav class="crumbs" aria-label="Breadcrumb"><a href="../../">%s</a> › <a href="../">Law finder</a> › <span>%s</span></nav>\n'
               % (esc(site["title"]), esc(p["section"] + " " + act_s)))
    out.append('<article><header class="eph"><p class="kicker">Law finder</p><h1>%s</h1><p class="hook">%s</p></header>\n' % (esc(label), esc(p["title"])))
    mapcard = '<ul class="maps"><li class="map">%s<span class="arrow" aria-hidden="true">→</span>%s</li></ul>' % (
        map_cell({"act": p["act"], "section": p["section"], "title": p["title"], "url": p["url"]}),
        "".join(map_cell({"act": a, "section": s, "title": t, "url": u}) for a, s, t, u in p["news"]) if p["news"] else '<div class="mc none">Unchanged</div>')
    out.append('<section class="sec"><h2>Then and now</h2><p>%s of the %s covers: %s. %s</p>%s'
               '<p class="small">The new criminal codes apply only to offences on or after 1 July 2024. Older cases are still decided under the old law.</p></section>\n'
               % (esc(p["section"]), esc(p["act"]), esc(p["title"].lower() if p["title"] else "this provision"), esc(now_txt), mapcard))
    if p["changes"]:
        out.append(section("changes", "What changed", "<ul>%s</ul>" % "".join("<li>%s</li>" % esc(c) for c in p["changes"])))
    out.append(section("episodes", "Cases on this site where it mattered (%d)" % n, ep_list(p["eps"], 2)))
    out.append('<p class="note">%s</p>\n</article></main>\n' % esc(site.get("disclaimer", "")))
    out.append(footer() + '<script src="../../assets/app.js" defer></script>\n</body>\n</html>\n')
    return "".join(out)


def render_laws_index():
    url = BASE + "/laws/"
    nprov = len(prov)
    desc = short("Look up Indian criminal and constitutional provisions (IPC, CrPC, Evidence Act, Constitution) and what replaced them "
                 "(BNS, BNSS, BSA), with the real cases where each one mattered.", 158)
    out = [head("Law finder: old and new Indian law, with cases | " + site["title"], desc, url, 1)]
    out.append("<body>\n" + header(1) + '<main id="main" class="wrap">\n')
    out.append('<nav class="crumbs" aria-label="Breadcrumb"><a href="../">%s</a> › <span>Law finder</span></nav>\n' % esc(site["title"]))
    out.append('<h1>Law finder</h1><p class="lead">%d provisions that came up in the cases, shown as the law then and the law today.</p>\n'
               '<div class="tools"><label class="sr" for="lq">Filter provisions</label>'
               '<input id="lq" type="search" placeholder="Filter (e.g. 302, evidence, remission)" autocomplete="off"></div>\n' % nprov)
    groups = {}
    for p in prov.values():
        groups.setdefault(p["code"], []).append(p)
    order = [c for c in ACT_ORDER if c in groups] + [c for c in groups if c not in ACT_ORDER]

    def secnum(p):
        m = re.search(r"(\d+)", p["section"])
        return (int(m.group(1)) if m else 9999, p["section"])
    for code in order:
        ps = sorted(groups[code], key=secnum)
        out.append('<section class="sec lawgroup"><h2>%s</h2><ul class="lawlist">' % esc(ps[0]["act"]))
        for p in ps:
            if p["slug"] in PAGES:
                link = '<a href="%s/">%s</a>' % (esc(p["slug"]), esc(prov_label(p)))
                cases = "%d cases" % len(p["eps"])
            else:
                r = p["eps"][0]
                link = '<a href="../episodes/%s/#law">%s</a>' % (esc(r["slug"]), esc(prov_label(p)))
                cases = "EP%03d" % r["n"]
            out.append('<li data-s="%s"><span class="ls">%s</span> <span class="lt">%s</span> <span class="lc">%s</span></li>' % (
                esc(norm(prov_label(p) + " " + p["title"])), link, esc(p["title"]), esc(cases)))
        out.append("</ul></section>\n")
    out.append('<p class="note">%s</p></main>\n' % esc(site.get("disclaimer", "")))
    out.append(footer() + '<script src="../assets/app.js" defer></script>\n</body>\n</html>\n')
    return "".join(out)


# ---------- index ----------
def render_index():
    n = len(episodes)
    latest = episodes[-1]
    topics_all = sorted({t for x in episodes for t in x.get("topics", [])})
    desc = short("%s. %d episodes with plain-English case notes, timelines, legal principles and sources." % (site["tagline"], n), 158)
    ld = jsonld({"@context": "https://schema.org", "@graph": [
        {"@type": "PodcastSeries", "name": site["title"], "url": BASE + "/", "description": site["about"],
         "inLanguage": site.get("lang", "en"), "webFeed": LINKS.get("rss"),
         "sameAs": [u for u in (LINKS.get("spotify"), LINKS.get("apple"), LINKS.get("youtube")) if u]},
        {"@type": "WebSite", "name": site["title"], "url": BASE + "/"},
        {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": ep_url(x), "name": x["title"]} for i, x in enumerate(episodes)]}]})
    verify = ('<meta name="google-site-verification" content="%s">\n' % esc(site["googleSiteVerification"])
              if site.get("googleSiteVerification") else "")
    out = [head("%s | %s" % (site["title"], site["tagline"]), desc, BASE + "/", 0, extra=verify + ld + "\n")]
    out.append("<body>\n" + header(0) + "<main id=\"main\">\n")
    out.append('<section class="hero"><div class="wrap herogrid"><div>'
               '<p class="kicker">Podcast · case notes · law finder</p><h1>%s</h1><p class="lead">%s</p>'
               '<div class="btns">%s</div>'
               '<ul class="stats"><li><strong>%d</strong> episodes</li><li><strong>%d</strong> topics</li><li><strong>%d</strong> provisions explained</li></ul>'
               '</div>'
               '<a class="latest" href="episodes/%s/">%s<span class="kicker">Latest · EP%03d</span><strong>%s</strong>'
               '<span class="lo">%s</span><span class="go">Read the case notes →</span></a></div></section>\n'
               % (esc(site["title"]), esc(site["tagline"]), platform_links(LINKS, primary=True), n, len(topics_all), len(prov),
                  esc(latest["slug"]), card_thumb(latest, True), latest["n"], esc(latest["title"]), esc(short(outcome(latest), 170))))
    out.append('<section class="wrap how" aria-label="How it works"><ol>'
               '<li><span>1</span><div><strong>Listen to the story</strong>Each case is told as an episode you can play anywhere.</div></li>'
               '<li><span>2</span><div><strong>Read the case notes</strong>Timeline, key holdings and plain-English principles.</div></li>'
               '<li><span>3</span><div><strong>Learn the law</strong>See the old provision next to what replaced it.</div></li></ol></section>\n')
    out.append('<section class="wrap" id="episodes"><h2>Episodes</h2>'
               '<div class="tools"><label class="sr" for="q">Search episodes</label>'
               '<input id="q" type="search" placeholder="Search cases, laws, topics (e.g. dying declaration, section 302, DNA)" autocomplete="off">'
               '<label class="sr" for="sort">Sort</label><select id="sort"><option value="new">Newest first</option><option value="old">Oldest first</option></select></div>'
               '<p class="chips" id="topics">%s</p><p class="small" id="count" aria-live="polite">%d episodes</p>'
               '<ul class="cards" id="list">\n' % (
                   '<button type="button" class="chip on" data-t="">All</button>' + "".join(
                       '<button type="button" class="chip" data-t="%s">%s</button>' % (esc(t.lower()), esc(t)) for t in topics_all), n))
    for x in sorted(episodes, key=lambda z: -z["n"]):
        blob = " ".join([x["title"], x.get("caseName", ""), x["hook"], " ".join(x.get("topics", [])), " ".join(x.get("laws", [])),
                         " ".join(f.get("value", "") for f in x.get("facts", [])), " ".join(x.get("takeaways", [])),
                         " ".join(p.get("name", "") for p in x.get("principles", [])),
                         " ".join("%s %s %s" % ((m.get("old") or {}).get("section", ""), (m.get("old") or {}).get("title", ""),
                                                (m.get("new") or {}).get("section", "")) for m in x.get("lawMapping", [])),
                         " ".join(x.get("summary", [])[:1])])
        meta = " · ".join(v for v in (x.get("caseName"), fact(x, "Court"), fact(x, "Year")) if v)
        out.append('<li class="card" data-n="%d" data-s="%s" data-t="|%s|"><a href="episodes/%s/">%s'
                   '<span class="num">EP%03d</span><h3>%s</h3></a><p>%s</p><p class="meta">%s</p></li>\n' % (
                       x["n"], esc(norm(blob)), esc("|".join(t.lower() for t in x.get("topics", []))), esc(x["slug"]), card_thumb(x), x["n"],
                       esc(x["title"]), esc(short(outcome(x), 150)), esc(meta)))
    out.append('</ul><p id="none" class="small" hidden>No episodes match. Try fewer words.</p></section>\n')
    if TOPICS:
        out.append('<section class="wrap" id="topics-browse"><h2>Browse by topic</h2><p class="chips">%s</p></section>\n' % "".join(
            '<a class="chip" href="topics/%s/">%s <small>(%d)</small></a>' % (esc(t["slug"]), esc(t["name"]), len(t["eps"]))
            for t in sorted(TOPICS.values(), key=lambda t: (-len(t["eps"]), t["name"]))))
    top = sorted(PAGES.values(), key=lambda p: -len(p["eps"]))[:8]
    if top:
        out.append('<section class="wrap" id="laws"><h2>Browse by law</h2><p>Jump to a provision and see the old and new law with the cases behind it.</p>'
                   '<p class="chips">%s<a class="chip" href="laws/">All provisions →</a></p></section>\n' % "".join(
                       '<a class="chip" href="laws/%s/">%s</a>' % (esc(p["slug"]), esc("%s %s" % (p["section"], ACT_SHORT.get(p["code"], "")))) for p in top))
    out.append('<section class="wrap" id="about"><h2>About</h2><p>%s</p></section>\n</main>\n' % esc(site["about"]))
    out.append(footer())
    out.append('<script src="assets/app.js" defer></script>\n</body>\n</html>\n')
    return "".join(out)


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def clean(dirname, keep):
    if os.path.isdir(dirname):
        for d in os.listdir(dirname):
            if d not in keep and os.path.isdir(os.path.join(dirname, d)):
                shutil.rmtree(os.path.join(dirname, d))


def main():
    clean("episodes", {x["slug"] for x in episodes})
    clean("laws", set(PAGES))
    clean("topics", set(TOPICS))
    clean("go", {x["id"] for x in episodes})
    write("index.html", render_index())
    for i, x in enumerate(episodes):
        prev = episodes[i - 1] if i > 0 else None
        nxt = episodes[i + 1] if i < len(episodes) - 1 else None
        write("episodes/%s/index.html" % x["slug"], render_episode(x, prev, nxt))
        write("go/%s/index.html" % x["id"], render_alias(x))
    for s, t in TOPICS.items():
        write("topics/%s/index.html" % s, render_topic(t))
    write("laws/index.html", render_laws_index())
    for s, p in PAGES.items():
        write("laws/%s/index.html" % s, render_prov(p))
    # remove share images that no longer match an episode
    if os.path.isdir("assets/og"):
        live = set()
        for x in episodes:
            for f in glob.glob("assets/og/%s-*.png" % x["id"]):
                live.add(os.path.basename(f))
        # keep only the newest per episode
        for x in episodes:
            fs = sorted(glob.glob("assets/og/%s-*.png" % x["id"]), key=os.path.getmtime)
            for f in fs[:-1]:
                os.remove(f)
    urls = [(BASE + "/", "1.0", None), (BASE + "/laws/", "0.7", None)]
    urls += [(ep_url(x), "0.8", (x.get("audio") or {}).get("date")) for x in episodes]
    urls += [("%s/laws/%s/" % (BASE, s), "0.6", None) for s in PAGES]
    urls += [("%s/topics/%s/" % (BASE, s), "0.6", None) for s in TOPICS]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join("  <url><loc>%s</loc>%s<priority>%s</priority></url>\n" % (
              esc(u), ("<lastmod>%s</lastmod>" % d) if d else "", pr) for u, pr, d in urls) + "</urlset>\n")
    write("robots.txt", "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE)
    write("404.html", head("Page not found | " + site["title"], "That page does not exist.", BASE + "/404.html", 0, noindex=True) +
          "<body>\n" + header(0) + '<main id="main" class="wrap ep"><h1>Page not found</h1>'
          '<p>That page does not exist. <a href="/">Go to all episodes</a>.</p></main>\n' + footer() + "</body>\n</html>\n")
    write(".nojekyll", "")
    og_ok = sum(1 for x in episodes if glob.glob("assets/og/%s-*.png" % x["id"]))
    print("Built %d episode pages, %d law pages (+ law index), share images for %d episodes." % (len(episodes), len(PAGES), og_ok))
    if og_ok < len(episodes):
        print("  Share images need Pillow and a TrueType font (pip install pillow). Missing ones use assets/og.png.")
    if PLACEHOLDER:
        print("\nNOTE: set baseUrl in site.json to your real address, then run build.py again.")
    flagged = [(x["n"], warn_words(x)) for x in episodes if warn_words(x)]
    if flagged:
        print("\nWording to verify against your Master Standard (not errors):")
        for n, w in flagged:
            print("  EP%03d: %s" % (n, ", ".join(w)))


if __name__ == "__main__":
    main()
