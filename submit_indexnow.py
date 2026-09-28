"""Tell Bing and the other IndexNow search engines that the site's pages changed.

    python3 submit_indexnow.py            # submit every URL in sitemap.xml
    python3 submit_indexnow.py --dry-run  # show what would be sent

IndexNow is a shared protocol: one submission reaches Bing, Yandex, Seznam,
Naver and Yep. Bing's index also backs DuckDuckGo, Ecosia, Copilot and ChatGPT
search, so for a new site this is the fastest route into most search surfaces.
Google does not take part; it needs Search Console (see README).

Ownership is proven by hosting a key file: the <32 hex chars>.txt file at the
repository root, served by GitHub Pages at https://nilpdf.com/<key>.txt, whose
contents are the key itself. The key is public by design, since anyone can
fetch it from the site; it only shows that whoever submits controls the host.
The file must be deployed before submitting, so run this after a deploy, not
before. Submit when pages actually change rather than on every deploy, since
the engines throttle hosts that resubmit unchanged URLs.
"""
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
HOST = "nilpdf.com"
ENDPOINT = "https://api.indexnow.org/indexnow"


def find_key():
    keys = [p for p in ROOT.iterdir() if re.fullmatch(r"[0-9a-f]{32}\.txt", p.name)]
    if len(keys) != 1:
        sys.exit(f"Expected exactly one <32 hex>.txt IndexNow key file at the repo root, found {len(keys)}")
    key = keys[0].read_text().strip()
    if key != keys[0].stem:
        sys.exit(f"{keys[0].name} must contain exactly its own name ({keys[0].stem}), found {key!r}")
    return key


def sitemap_urls():
    urls = re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text())
    stray = [u for u in urls if not u.startswith(f"https://{HOST}/")]
    if stray:
        sys.exit(f"sitemap.xml has URLs outside https://{HOST}/, which IndexNow rejects: {stray}")
    return urls


def key_is_live(key):
    try:
        with urllib.request.urlopen(f"https://{HOST}/{key}.txt", timeout=20) as r:
            return r.status == 200 and r.read().decode().strip() == key
    except urllib.error.URLError:
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    key = find_key()
    urls = sitemap_urls()
    payload = {"host": HOST, "key": key, "keyLocation": f"https://{HOST}/{key}.txt", "urlList": urls}
    print(f"{len(urls)} URLs from sitemap.xml, key {key}")
    if dry_run:
        print(json.dumps(payload, indent=2))
        return

    if not key_is_live(key):
        sys.exit(f"https://{HOST}/{key}.txt is not live with the right contents yet. Deploy first, then rerun.")

    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"IndexNow accepted the submission: HTTP {r.status}")
    except urllib.error.HTTPError as e:
        # 403: key file not found or wrong; 422: URLs don't belong to the host;
        # 429: too many submissions, back off.
        sys.exit(f"IndexNow rejected the submission: HTTP {e.code} {e.read().decode(errors='replace')[:300]}")


if __name__ == "__main__":
    main()
