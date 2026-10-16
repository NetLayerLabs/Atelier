"""Rebuild the real mood boards in static/moodboards/ from openly licensed sources.

Reads scripts/moodboards_spec.json (Wikimedia Commons file names and Met Open Access object ids), checks each
file's licence (Commons: the file page's licence must be CC0 / CC BY / CC BY-SA / public domain; Met: the object
must be Open Access, i.e. CC0), downloads it, downsizes it to a 1200 px long edge, and writes
static/moodboards/manifest.json and static/moodboards/ATTRIBUTION.md.

    cd backend && uv run python scripts/build_moodboards.py
    uv run python scripts/build_moodboards.py --attribution-only   # rewrite ATTRIBUTION.md from manifest.json

No analysis is written here: a board is only images + a factual title. The vision model analyses it live.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = os.path.join(HERE, "moodboards_spec.json")
OUT = os.path.join(HERE, "..", "static", "moodboards")

UA = {"User-Agent": "AtelierHackathon/1.0 (moodboard sourcing; https://github.com/NetLayerLabs)"}
LONG_EDGE = 1200
QUALITY = 80
ALLOWED = {"CC0", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0", "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0", "Public domain"}


def fetch(url, binary=False):
    for attempt in range(4):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read()
            return data if binary else json.loads(data)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(4 * (attempt + 1))


def strip(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def save(data, path):
    im = Image.open(io.BytesIO(data)).convert("RGB")
    w0, h0 = im.size
    scale = min(1.0, LONG_EDGE / max(w0, h0))
    if scale < 1:
        im = im.resize((round(w0 * scale), round(h0 * scale)), Image.LANCZOS)
    im.save(path, "JPEG", quality=QUALITY, optimize=True, progressive=True)  # no EXIF carried over
    return (w0, h0), im.size


def commons(title):
    api = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query", "format": "json", "titles": "File:" + title, "prop": "imageinfo|categories",
        "iiprop": "url|size|extmetadata", "cllimit": 50})
    page = next(iter(fetch(api)["query"]["pages"].values()))
    ii = page["imageinfo"][0]
    md = {k: v.get("value") for k, v in ii["extmetadata"].items()}
    cats = [c["title"] for c in page.get("categories", [])]
    lic = strip(md.get("LicenseShortName"))
    if lic not in ALLOWED:
        raise SystemExit(f"licence not allowed for {title}: {lic}")
    reviewed = any("reviewed" in c.lower() for c in cats)
    return {
        "src": ii["url"],
        "meta": {
            "title": title.rsplit(".", 1)[0],
            "creator": strip(md.get("Artist")),
            "sourceUrl": ii["descriptionurl"],
            "originalSourceUrl": re.search(r'href="([^"]+)"', md.get("Credit", "") or "").group(1)
            if re.search(r'href="([^"]+)"', md.get("Credit", "") or "") else None,
            "date": strip(md.get("DateTimeOriginal"))[:10] or None,
            "license": lic,
            "licenseUrl": md.get("LicenseUrl"),
            "licenseReviewed": reviewed,
            "repository": "Wikimedia Commons",
        },
    }


def met(oid):
    o = fetch(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
    if not o.get("isPublicDomain"):
        raise SystemExit(f"Met object {oid} is not Open Access")
    maker = o.get("artistDisplayName") or ""
    title = f'{o["title"]}, {o.get("objectDate")}' + (f" ({maker})" if maker else "")
    return {
        "src": o["primaryImage"],
        "meta": {
            "title": title,
            "creator": "The Metropolitan Museum of Art",  # the object maker, if known, is in the title
            "sourceUrl": o["objectURL"],
            "originalSourceUrl": None,
            "date": o.get("objectDate"),
            "license": "CC0 1.0 (Met Open Access)",
            "licenseUrl": "https://creativecommons.org/publicdomain/zero/1.0/",
            "licenseReviewed": True,
            "repository": "The Metropolitan Museum of Art Open Access",
            "medium": o.get("medium"),
            "creditLine": o.get("creditLine"),
            "accessionNumber": o.get("accessionNumber"),
        },
    }


def write_attribution(out: str) -> None:
    m = json.load(open(os.path.join(out, "manifest.json"), encoding="utf-8"))
    lines = [
        "# Mood-board image credits",
        "",
        "The preset mood boards are real, openly licensed photographs. Atelier sends them to the vision model on",
        "AMD every time a board is analysed; nothing about them is pre-written. Machine-readable version:",
        "[manifest.json](manifest.json). Rebuild with `backend/scripts/build_moodboards.py`.",
        "",
        "Licences:",
        "- **CC BY 2.0** (https://creativecommons.org/licenses/by/2.0/): reuse and modification allowed, including",
        "  commercially, with attribution, a link to the licence, and an indication of changes. No share-alike.",
        "- **CC0 1.0** (https://creativecommons.org/publicdomain/zero/1.0/): The Met Open Access, no restrictions;",
        "  credited here as a courtesy.",
        "",
        "All images were downscaled and re-encoded as JPEG (details per image below); none were cropped or edited.",
        "Logos and garments shown may be trademarks of their owners; the runway photos show professional models",
        "at public fashion-week shows. The licences cover the photographs' copyright only.",
        "",
    ]
    for b in m["boards"]:
        lines += [f"## {b['title']}", ""]
        for im in b["images"]:
            orig = f" (originally {im['originalSourceUrl']})" if im.get("originalSourceUrl") else ""
            lines.append(f"- `{im['file']}` - *{im['title']}* by **{im['creator']}**, "
                         f"[{im['license']}]({im['licenseUrl']}), source: {im['sourceUrl']}{orig}. "
                         f"{im['modifications']}")
        lines.append("")
    with open(os.path.join(out, "ATTRIBUTION.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    out = os.path.normpath(OUT)
    if "--attribution-only" in sys.argv:
        write_attribution(out)
        return
    spec = json.load(open(SPEC, encoding="utf-8"))
    boards = []
    for b in spec["boards"]:
        os.makedirs(os.path.join(out, b["id"]), exist_ok=True)
        items = [commons(f) for f in b.get("files", [])] + [met(o) for o in b.get("objects", [])]
        images = []
        for n, it in enumerate(items, 1):
            rel = f'{b["id"]}/{n:02d}.jpg'
            (w0, h0), (w, h) = save(fetch(it["src"], binary=True), os.path.join(out, rel))
            m = it["meta"]
            images.append({"file": rel, **{k: v for k, v in m.items() if v is not None},
                           "width": w, "height": h,
                           "modifications": f"Downscaled from {w0}×{h0} to {w}×{h} px and re-encoded as JPEG "
                                            f"(quality {QUALITY}); metadata stripped. No other changes."})
            print(rel, m["license"], m["creator"][:40], m["sourceUrl"])
            time.sleep(0.5)
        boards.append({"id": b["id"], "title": b["title"], "images": images})
    json.dump({"version": 1, "boards": boards}, open(os.path.join(out, "manifest.json"), "w"),
              indent=2, ensure_ascii=False)
    write_attribution(out)


if __name__ == "__main__":
    main()
