"""Download the public "Women's E-Commerce Clothing Reviews" dataset and (re)build the committed samples.

    cd backend && uv run python scripts/fetch_voice_dataset.py            # download (cached) + rebuild samples
    uv run python scripts/fetch_voice_dataset.py --per-sample 200

Source: OpenML dataset 43673 (https://www.openml.org/d/43673), mirrored from the Kaggle dataset
"Women's E-Commerce Clothing Reviews" by Nick Brooks (nicapotato). Licence: CC0 1.0 (public domain).
23,486 real, anonymised customer reviews; the retailer's name was replaced with "retailer" by the publisher.

The full ARFF (~8.6 MB) is cached in backend/.cache/voice/ (git-ignored). The committed samples in
app/data/voice_samples/ are a seeded random draw (no cherry-picking, no editing of text) of reviews
that have review text, per garment group.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "voice"
ARFF_URL = "https://openml.org/data/v1/download/22102498/Womens-E-Commerce-Clothing-Reviews.arff"
ARFF = CACHE / "womens_ecommerce_clothing_reviews.arff"
OUT = ROOT / "app" / "data" / "voice_samples"

GROUPS = {  # sample key -> dataset "Class Name" values
    "outerwear": ("Jackets", "Outerwear"),
    "knits": ("Knits", "Sweaters", "Fine gauge"),
    "dresses_pants": ("Dresses", "Pants"),
}
COLUMNS = ["review_id", "clothing_id", "title", "review_text", "rating", "recommended",
           "positive_feedback_count", "division", "department", "class"]
SEED = 20180203  # the dataset's collection date (03-02-2018)


def download() -> Path:
    if ARFF.exists() and ARFF.stat().st_size > 1_000_000:
        return ARFF
    CACHE.mkdir(parents=True, exist_ok=True)
    print(f"downloading {ARFF_URL} …")
    with urllib.request.urlopen(ARFF_URL, timeout=120) as r:  # noqa: S310 - fixed https URL
        ARFF.write_bytes(r.read())
    return ARFF


def parse_arff(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    data = text[text.index("@DATA") + len("@DATA"):]
    rows = csv.reader(io.StringIO(data), quotechar="'", escapechar="\\", doublequote=False)
    out = []
    for r in rows:
        if len(r) != 11:
            continue
        clean = ["" if v == "?" else v for v in r]
        out.append({
            "review_id": clean[0], "clothing_id": clean[1], "title": clean[3], "review_text": clean[4],
            "rating": clean[5], "recommended": clean[6], "positive_feedback_count": clean[7],
            "division": clean[8], "department": clean[9], "class": clean[10],
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-sample", type=int, default=200)
    args = ap.parse_args()
    rows = parse_arff(download())
    print(f"parsed {len(rows):,} reviews")
    OUT.mkdir(parents=True, exist_ok=True)
    for key, classes in GROUPS.items():
        pool = [r for r in rows if r["class"] in classes and r["review_text"].strip()]
        pick = random.Random(f"{SEED}:{key}").sample(pool, min(args.per_sample, len(pool)))
        pick.sort(key=lambda r: int(r["review_id"]))
        with (OUT / f"{key}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(pick)
        print(f"{key}: {len(pick)} of {len(pool):,} reviews -> {OUT / f'{key}.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
