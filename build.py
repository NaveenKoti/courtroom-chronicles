#!/usr/bin/env python3
"""Courtroom Chronicles: build the static site from data/episodes/*.json.

Run:  python3 build.py
Writes (into this folder): index.html, episodes/<slug>/index.html, sitemap.xml,
robots.txt, 404.html.  assets/style.css and assets/app.js are plain files you can edit.
Optional: data/audio.json (made by fetch_audio.py) supplies audio URLs from your RSS feed.
Standard library only.
"""
import glob, html, json, os, re, sys
from urllib.parse import quote
from datetime import date

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


def slugify(title, n):
    words = re.sub(r"[^a-z0-9]+", "-", title.lower().replace("'", "").replace("’", "")).strip("-").split("-")
    out = []
    for w in words:
        if len("-".join(out + [w])) > 56:
            break
        out.append(w)
    return "ep%03d-%s" % (n, "-".join(out))


def short(s, n):
    s = " ".join(str(s).split())
    if len(s) <= n:
        return s
    cut = s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:- ")
    return cut + "…"


def jsonld(obj):
    return '<script type="application/ld+json">%s</script>' % json.dumps(
        obj, ensure_ascii=False).replace("</", "<\\/")


# ---------- load ----------
audio_map = {}
if os.path.exists("data/audio.json"):
    audio_map = json.load(open("data/audio.json", encoding="utf-8"))

episodes = []
for p in sorted(glob.glob("data/episodes/ep*.json")):
    d = json.load(open(p, encoding="utf-8"))
    m = re.match(r"ep(\d+)", d.get("id", ""), re.I)
    if not m:
        sys.exit("%s: 'id' must look like ep012" % p)
    d["n"] = int(m.group(1))
    d["slug"] = d.get("slug") or slugify(d["title"], d["n"])
    a = audio_map.get(d["id"], {})
    d["audio"] = {**a, **(d.get("audio") or {})}
    d["listen"] = {**LINKS, **(d.get("listen") or {})}
    episodes.append(d)
episodes.sort(key=lambda x: x["n"])
if len({x["n"] for x in episodes}) != len(episodes):
    sys.exit("Duplicate episode numbers")
by_n = {x["n"]: x for x in episodes}
nums = [x["n"] for x in episodes]


def ep_url(x):
    return "%s/episodes/%s/" % (BASE, x["slug"])


def ep_path(x, depth):
    return ("../" * depth) + "episodes/%s/" % x["slug"]


def fact(x, label):
    for f in x.get("facts", []):
        if f.get("label", "").lower() == label.lower():
            return f.get("value", "")
    return ""


def warn_words(x):
    blob = json.dumps({k: v for k, v in x.items() if k in (
        "title", "hook", "summary", "judgment", "principles", "takeaways", "timeline")}, ensure_ascii=False)
    return sorted({m.group(0).lower() for m in WATCH.finditer(blob)})


# ---------- shared page shell ----------
def head(title, desc, canonical, depth, extra="", og_type="website", image=True, prev=None, nxt=None):
    root = "../" * depth
    img = ""
    if image and site.get("ogImage") and os.path.exists(site["ogImage"]):
        img_url = "%s/%s" % (BASE, site["ogImage"])
        img = ('<meta property="og:image" content="%s">\n<meta name="twitter:image" content="%s">\n'
               % (esc(img_url), esc(img_url)))
    pn = ""
    if prev:
        pn += '<link rel="prev" href="%s">\n' % esc(ep_url(prev))
    if nxt:
        pn += '<link rel="next" href="%s">\n' % esc(ep_url(nxt))
    rss = LINKS.get("rss")
    rss_tag = ('<link rel="alternate" type="application/rss+xml" title="%s" href="%s">\n'
               % (esc(site["title"]), esc(rss))) if rss else ""
    return """<!doctype html>
<html lang="%(lang)s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<meta name="description" content="%(desc)s">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#7a1f2b">
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
           root=root, extra=extra)


def header(depth, active=""):
    root = "../" * depth
    return """<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap bar">
<a class="brand" href="%(r)s"><span class="mark" aria-hidden="true">⚖</span> %(t)s</a>
<nav aria-label="Main"><a href="%(r)s#episodes">Episodes</a><a href="%(r)s#about">About</a>%(sp)s</nav>
</div></header>
""" % dict(r=root or "./", t=esc(site["title"]),
           sp=('<a href="%s" rel="noopener" target="_blank">Spotify</a>' % esc(LINKS["spotify"])) if LINKS.get("spotify") else "")


def footer(depth, extra_disclaimer=""):
    return """<footer class="foot"><div class="wrap">
<p class="disc">%s</p>
<p class="small">© %s %s. Built with plain HTML; case notes are drawn from public court records.</p>
</div></footer>
""" % (esc(extra_disclaimer or site.get("disclaimer", "")), date.today().year, esc(site["title"]))


def listen_links(x):
    out = []
    ln = x["listen"]
    if ln.get("spotify"):
        out.append(("Spotify", ln["spotify"]))
    if ln.get("apple"):
        out.append(("Apple Podcasts", ln["apple"]))
    if ln.get("youtube"):
        out.append(("YouTube", ln["youtube"]))
    if ln.get("rss"):
        out.append(("RSS", ln["rss"]))
    return "".join('<a class="btn" href="%s" rel="noopener" target="_blank">%s</a>' % (esc(u), esc(n)) for n, u in out)


# ---------- episode page ----------
def player_block(x):
    a = x.get("audio") or {}
    url = safe_url(a.get("url"))
    spid = LINKS.get("spotifyShowId")
    parts = ['<section class="player" id="listen" aria-label="Listen to this episode" '
             'data-title="%s" data-num="%d" data-rss="%s" data-spotify="%s" data-id="%s">'
             % (esc(norm(x["title"])), x["n"], esc(LINKS.get("rss") or ""), esc(spid or ""), esc(x["id"]))]
    parts.append('<h2>Listen</h2>')
    if url:
        parts.append('<audio controls preload="none" src="%s"></audio>' % esc(url))
    else:
        parts.append('<audio controls preload="none" hidden></audio>')
    parts.append('<div class="pbar"><span class="pstat" aria-live="polite"></span>'
                 '<button type="button" class="btn ghost speed" hidden aria-label="Playback speed">1×</button></div>')
    parts.append('<div class="embed" hidden></div>')
    parts.append('<div class="btns">%s</div>' % listen_links(x))
    parts.append('<noscript><p class="small">Turn on JavaScript to play here, or use the links above.</p></noscript>')
    parts.append('</section>')
    return "".join(parts)


def section(id_, title, body):
    return '<section class="sec" id="%s"><h2>%s</h2>%s</section>\n' % (id_, esc(title), body)


def ul(items, cls=""):
    return '<ul%s>%s</ul>' % ((' class="%s"' % cls) if cls else "", "".join("<li>%s</li>" % esc(i) for i in items))


def map_cell(side):
    if not side:
        return '<div class="mc none">—</div>'
    u = safe_url(side.get("url"))
    sec = esc(side.get("section", ""))
    sec_html = ('<a href="%s" rel="noopener" target="_blank">%s</a>' % (esc(u), sec)) if u else sec
    return ('<div class="mc"><span class="act">%s</span><strong>%s</strong><span class="ttl">%s</span></div>'
            % (esc(side.get("act", "")), sec_html, esc(side.get("title", ""))))


def render_episode(x, prev, nxt):
    url = ep_url(x)
    desc = short(x["hook"], 158)
    title = "EP%03d: %s | %s" % (x["n"], x["title"], site["title"])
    topics = x.get("topics", [])
    court, year = fact(x, "Court"), fact(x, "Year")

    graph = [
        {"@type": "PodcastEpisode", "@id": url + "#episode", "url": url, "name": x["title"],
         "description": x["hook"], "episodeNumber": x["n"], "inLanguage": site.get("lang", "en"),
         "keywords": ", ".join(topics),
         "partOfSeries": {"@type": "PodcastSeries", "name": site["title"], "url": BASE + "/"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": site["title"], "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": "EP%03d" % x["n"], "item": url}]},
    ]
    a = x.get("audio") or {}
    if a.get("date"):
        graph[0]["datePublished"] = a["date"]
    if safe_url(a.get("url")):
        graph[0]["associatedMedia"] = {"@type": "AudioObject", "contentUrl": safe_url(a["url"]),
                                       "encodingFormat": "audio/mpeg"}
    ld = jsonld({"@context": "https://schema.org", "@graph": graph})
    out = [head(title, desc, url, 2, extra=ld + "\n", og_type="article", prev=prev, nxt=nxt)]
    out.append("<body>\n" + header(2))
    out.append('<main id="main" class="wrap ep">\n')
    out.append('<nav class="crumbs" aria-label="Breadcrumb"><a href="../../">%s</a> › <span>EP%03d</span></nav>\n'
               % (esc(site["title"]), x["n"]))
    out.append('<article>\n<header class="eph"><p class="kicker">Episode %d%s</p><h1>%s</h1><p class="hook">%s</p>'
               % (x["n"], (" · " + esc(a["date"])) if a.get("date") else "", esc(x["title"]), esc(x["hook"])))
    if topics:
        out.append('<p class="chips">%s</p>' % "".join(
            '<a class="chip" href="../../?topic=%s#episodes">%s</a>' % (quote(t.lower()), esc(t)) for t in topics))
    out.append('</header>\n')

    if x.get("facts"):
        out.append('<dl class="facts">%s</dl>\n' % "".join(
            "<div><dt>%s</dt><dd>%s</dd></div>" % (esc(f.get("label")), esc(f.get("value"))) for f in x["facts"]))

    out.append(player_block(x) + "\n")

    toc = []
    body = []
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
            rows += ('<li class="map">%s<span class="arrow" aria-hidden="true">→</span>%s<p class="chg">%s</p></li>'
                     % (map_cell(m.get("old")), map_cell(m.get("new")), esc(m.get("change", ""))))
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
    out.append(footer(2, x.get("disclaimer", "")))
    out.append('<script src="../../assets/app.js" defer></script>\n</body>\n</html>\n')
    return "".join(out)


# ---------- index ----------
def render_index():
    n = len(episodes)
    desc = short("%s. %d episodes with plain-English case notes, timelines, legal principles and sources." % (
        site["tagline"], n), 158)
    all_topics = sorted({t for x in episodes for t in x.get("topics", [])})
    ld = jsonld({"@context": "https://schema.org", "@graph": [
        {"@type": "PodcastSeries", "name": site["title"], "url": BASE + "/", "description": site["about"],
         "inLanguage": site.get("lang", "en"), "webFeed": LINKS.get("rss"),
         "sameAs": [u for u in (LINKS.get("spotify"), LINKS.get("apple"), LINKS.get("youtube")) if u]},
        {"@type": "WebSite", "name": site["title"], "url": BASE + "/"},
        {"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": ep_url(x), "name": x["title"]}
            for i, x in enumerate(episodes)]}]})
    out = [head("%s | %s" % (site["title"], site["tagline"]), desc, BASE + "/", 0, extra=ld + "\n")]
    out.append("<body>\n" + header(0))
    out.append('<main id="main">\n<section class="hero"><div class="wrap">'
               '<p class="kicker">A podcast and case-note library</p><h1>%s</h1><p class="lead">%s</p>'
               '<div class="btns">%s</div></div></section>\n' % (esc(site["title"]), esc(site["tagline"]), listen_links({"listen": LINKS})))
    out.append('<section class="wrap" id="episodes"><h2>Episodes</h2>'
               '<div class="tools"><label class="sr" for="q">Search episodes</label>'
               '<input id="q" type="search" placeholder="Search cases, laws, topics (e.g. dying declaration, section 302, DNA)" autocomplete="off">'
               '<label class="sr" for="sort">Sort</label><select id="sort"><option value="new">Newest first</option><option value="old">Oldest first</option></select></div>'
               '<p class="chips" id="topics">%s</p><p class="small" id="count" aria-live="polite">%d episodes</p>'
               '<ul class="cards" id="list">\n' % (
                   '<button type="button" class="chip on" data-t="">All</button>' + "".join(
                       '<button type="button" class="chip" data-t="%s">%s</button>' % (esc(t.lower()), esc(t)) for t in all_topics), n))
    for x in sorted(episodes, key=lambda z: -z["n"]):
        blob = " ".join([x["title"], x["hook"], " ".join(x.get("topics", [])), " ".join(x.get("laws", [])),
                         " ".join(f.get("value", "") for f in x.get("facts", [])),
                         " ".join(x.get("takeaways", [])), " ".join(p.get("name", "") for p in x.get("principles", [])),
                         " ".join(s for s in x.get("summary", [])[:1])])
        court, year = fact(x, "Court"), fact(x, "Year")
        out.append('<li class="card" data-n="%d" data-s="%s" data-t="|%s|"><a href="episodes/%s/">'
                   '<span class="num">EP%03d</span><h3>%s</h3></a><p>%s</p><p class="meta">%s</p></li>\n' % (
                       x["n"], esc(norm(blob)), esc("|".join(t.lower() for t in x.get("topics", []))), esc(x["slug"]), x["n"],
                       esc(x["title"]), esc(x["hook"]), esc(" · ".join(v for v in (court, year) if v))))
    out.append('</ul><p id="none" class="small" hidden>No episodes match. Try fewer words.</p></section>\n')
    out.append('<section class="wrap" id="about"><h2>About</h2><p>%s</p></section>\n</main>\n' % esc(site["about"]))
    out.append(footer(0))
    out.append('<script src="assets/app.js" defer></script>\n</body>\n</html>\n')
    return "".join(out)


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def main():
    import shutil
    keep = {x["slug"] for x in episodes}
    if os.path.isdir("episodes"):
        for d in os.listdir("episodes"):
            if d not in keep and os.path.isdir(os.path.join("episodes", d)):
                shutil.rmtree(os.path.join("episodes", d))
    write("index.html", render_index())
    for i, x in enumerate(episodes):
        prev = episodes[i - 1] if i > 0 else None
        nxt = episodes[i + 1] if i < len(episodes) - 1 else None
        write("episodes/%s/index.html" % x["slug"], render_episode(x, prev, nxt))
    today = date.today().isoformat()
    urls = [(BASE + "/", "1.0")] + [(ep_url(x), "0.8") for x in episodes]
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
          "".join("  <url><loc>%s</loc><lastmod>%s</lastmod><priority>%s</priority></url>\n" % (esc(u), today, p) for u, p in urls) +
          "</urlset>\n")
    write("robots.txt", "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % BASE)
    write("404.html", head("Page not found | " + site["title"], "That page does not exist.", BASE + "/404.html", 0, image=False)
          .replace('content="index, follow, max-image-preview:large"', 'content="noindex"') +
          "<body>\n" + header(0) + '<main id="main" class="wrap ep"><h1>Page not found</h1>'
          '<p>That page does not exist. <a href="/">Go to all episodes</a>.</p></main>\n' + footer(0) + "</body>\n</html>\n")
    write(".nojekyll", "")
    print("Built %d episode pages + index (%s)." % (len(episodes), ", ".join("EP%03d" % n for n in nums)))
    if PLACEHOLDER:
        print("\nNOTE: set baseUrl in site.json to your real address, then run build.py again.\n"
              "      Canonical links, sitemap and social previews use it.")
    flagged = [(x["n"], warn_words(x)) for x in episodes if warn_words(x)]
    if flagged:
        print("\nWording to verify against your Master Standard (not errors):")
        for n, w in flagged:
            print("  EP%03d: %s" % (n, ", ".join(w)))


if __name__ == "__main__":
    main()
