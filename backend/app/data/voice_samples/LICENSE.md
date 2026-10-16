# Sample customer-voice data: attribution and licence

The three CSV files in this folder (`outerwear.csv`, `knits.csv`, `dresses_pants.csv`) are unedited rows from a
public dataset of real customer reviews:

- **Dataset:** "Women's E-Commerce Clothing Reviews" by Nick Brooks (Kaggle user *nicapotato*), 2018.
  23,486 anonymised reviews from a women's clothing e-commerce retailer. The publisher replaced the retailer's
  name in the text with "retailer".
- **Original:** https://www.kaggle.com/datasets/nicapotato/womens-ecommerce-clothing-reviews
- **Mirror used for download (no login needed):** OpenML dataset 43673, https://www.openml.org/d/43673
  (file `https://openml.org/data/v1/download/22102498/Womens-E-Commerce-Clothing-Reviews.arff`)
- **Licence:** CC0 1.0 Universal (public domain dedication), as stated on both Kaggle ("CC0: Public Domain") and
  OpenML. CC0 permits copying, modifying and redistributing without permission. We credit the source anyway.

## What was taken and how

`backend/scripts/fetch_voice_dataset.py` builds these files. It downloads the full dataset to a git-ignored cache
(`backend/.cache/voice/`), keeps rows that have review text, and draws a **seeded random sample** of 200 reviews per
garment group:

| File | Dataset `Class Name` values | Pool | Sampled |
|---|---|---|---|
| `outerwear.csv` | Jackets, Outerwear | 1,002 | 200 |
| `knits.csv` | Knits, Sweaters, Fine gauge | 7,065 | 200 |
| `dresses_pants.csv` | Dresses, Pants | 7,495 | 200 |

The review text, title, rating, recommendation flag and classes are unchanged. `review_id` is the dataset's
original row index, so every quote Atelier cites can be traced back to the source. The `Age` column was dropped
because Atelier doesn't use it. No reviews were written, edited or chosen by hand.
