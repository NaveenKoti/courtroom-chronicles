"""Tell Bing and other IndexNow search engines about every page in sitemap.xml.

Run after a build that changed the site. Needs the key file <key>.txt at the site root.
Never fails the build: any error is printed and ignored.
"""
import json, re, sys, urllib.request, glob, os

site = json.load(open("site.json", encoding="utf-8"))
base = site["baseUrl"].rstrip("/")
host = re.sub(r"^https?://", "", base).split("/")[0]
keys = [os.path.basename(p)[:-4] for p in glob.glob("*.txt") if re.fullmatch(r"[0-9a-f]{32}\.txt", os.path.basename(p))]
if not keys:
    print("No IndexNow key file found; skipping."); sys.exit(0)
key = keys[0]
urls = re.findall(r"<loc>([^<]+)</loc>", open("sitemap.xml", encoding="utf-8").read())
body = json.dumps({"host": host, "key": key, "keyLocation": "%s/%s.txt" % (base, key), "urlList": urls[:10000]}).encode()
req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body, headers={"Content-Type": "application/json; charset=utf-8"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print("IndexNow: submitted %d URLs, HTTP %s" % (len(urls), r.status))
except Exception as e:
    print("IndexNow submit failed (ignored):", e)
