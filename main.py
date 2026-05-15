"""
main.py
=======
Pipeline orchestrator: raw CSV → cleaning → enrichment → two output CSVs.
"""

import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

from cleaning import run_cleaning
from enrichment import run_enrichment
from constants import (
    NULL_STRINGS,
    INPUT_FILE,
    OUTPUT_DIR,
    CLEANED_FILENAME,
    ENRICHED_FILENAME,
)

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    # Root logger propagates to all module-level loggers (cleaning, enrichment)
    # without requiring any wiring in those modules.
    fmt = "%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)
    root.addHandler(console)

    # File handler always captures DEBUG so the full trace is available
    # post-run without needing to re-execute with a higher verbosity flag.
    file_handler = logging.FileHandler("pipeline.log", mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)


def load_csv(filepath: str) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Input file not found: {filepath}")

    df = pd.read_csv(
        filepath,
        dtype={
            # id and google_place_id are opaque identifiers — never numeric.
            # Explicit str prevents pandas from silently appending ".0" if nulls exist.
            "id":              str,
            "google_place_id": str,
            "name":            str,
            "city":            str,
            "display_address": str,
            "price_point":     str,
            "primary_type":    str,
            "website":         str,
        },
        na_values=NULL_STRINGS,
        keep_default_na=True,
    )

    null_counts = {col: int(n) for col, n in df.isnull().sum().items() if n > 0}
    logger.info("Loaded %d rows × %d columns. Nulls: %s", len(df), len(df.columns), null_counts)
    return df


def validate_schema(df: pd.DataFrame) -> None:
    required = {
        "id", "name", "city", "display_address",
        "google_place_id", "latitude", "longitude",
        "price_point", "primary_type", "website",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {missing}")


def save_output(df: pd.DataFrame, output_dir: str, filename: str) -> None:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    path = os.path.join(output_dir, filename)
    df.to_csv(path, index=False, encoding="utf-8")
    logger.info("Saved %d rows → %s", len(df), path)


def print_summary_report(
    raw_df:      pd.DataFrame,
    clean_df:    pd.DataFrame,
    enriched_df: pd.DataFrame,
    elapsed_sec: float,
) -> None:
    sep  = "=" * 65
    sep2 = "-" * 65

    duplicates_removed = len(raw_df) - len(clean_df)

    null_filled: dict[str, int] = {
        col: int(raw_df[col].isnull().sum()) - int(clean_df[col].isnull().sum())
        for col in raw_df.columns
        if col in clean_df.columns
        and raw_df[col].isnull().sum() > clean_df[col].isnull().sum()
    }

    remaining_nulls: dict[str, int] = {
        col: int(clean_df[col].isnull().sum())
        for col in clean_df.columns
        if clean_df[col].isnull().sum() > 0
    }

    score_col  = enriched_df["romantic_score"]
    label_dist = enriched_df["romantic_label"].value_counts()

    top10 = (
        enriched_df[["name", "city", "cuisine_category", "romantic_score"]]
        .sort_values("romantic_score", ascending=False)
        .drop_duplicates(subset="name")
        .head(10)
        .reset_index(drop=True)
    )

    bottom5 = (
        enriched_df[["name", "city", "cuisine_category", "romantic_score"]]
        .sort_values("romantic_score", ascending=True)
        .drop_duplicates(subset="name")
        .head(5)
        .reset_index(drop=True)
    )

    cuisine_dist = enriched_df["cuisine_category"].value_counts().head(10)

    print(f"\n{sep}")
    print("  RESTAURANT DATA PIPELINE — SUMMARY REPORT")
    print(sep)

    print(f"\nPIPELINE METRICS")
    print(sep2)
    print(f"  Input rows          : {len(raw_df):>6,}")
    print(f"  After cleaning      : {len(clean_df):>6,}  ({duplicates_removed:+d} duplicates removed)")
    print(f"  After enrichment    : {len(enriched_df):>6,}  (same — enrichment adds columns)")
    print(f"  Total columns       : {len(enriched_df.columns):>6}")
    print(f"  Elapsed time        : {elapsed_sec:.2f}s")

    print(f"\nNULL VALUES FILLED (cleaning stage)")
    print(sep2)
    if null_filled:
        for col, n in null_filled.items():
            print(f"  {col:<25}: {n:>4} values imputed")
    else:
        print("  None (data was already clean)")

    if remaining_nulls:
        print(f"\n  Remaining nulls after cleaning:")
        for col, n in remaining_nulls.items():
            print(f"  {col:<25}: {n:>4} still missing")

    print(f"\nROMANTIC SCORE DISTRIBUTION")
    print(sep2)
    print(f"  Mean   : {score_col.mean():.2f} / 10.0")
    print(f"  Median : {score_col.median():.2f} / 10.0")
    print(f"  Std    : {score_col.std():.2f}")
    print(f"  Min    : {score_col.min():.1f}   Max: {score_col.max():.1f}")
    print()
    for label, count in label_dist.items():
        bar = "█" * int(count / max(label_dist) * 30)
        pct = 100 * count / len(enriched_df)
        print(f"  {label:<20} {count:>4}  ({pct:4.1f}%)  {bar}")

    print(f"\nTOP 10 MOST ROMANTIC VENUES")
    print(sep2)
    for i, row in top10.iterrows():
        print(
            f"  {i+1:>2}. {row['name']:<35} "
            f"{str(row['city']):<28} "
            f"{row['cuisine_category']:<18} "
            f"★ {row['romantic_score']}"
        )

    print(f"\nLEAST ROMANTIC VENUES (bottom 5)")
    print(sep2)
    for i, row in bottom5.iterrows():
        print(
            f"  {i+1:>2}. {row['name']:<35} "
            f"{str(row['city']):<28} "
            f"{row['cuisine_category']:<18} "
            f"  {row['romantic_score']}"
        )

    print(f"\nTOP 10 CUISINE CATEGORIES")
    print(sep2)
    for cuisine, count in cuisine_dist.items():
        bar = "█" * int(count / cuisine_dist.max() * 25)
        print(f"  {cuisine:<22} {count:>4}  {bar}")

    print(f"\n{sep}\n")


def main() -> None:
    setup_logging()
    start = time.time()

    try:
        raw_df = load_csv(INPUT_FILE)
        validate_schema(raw_df)
        raw_snapshot = raw_df.copy()

        clean_df = run_cleaning(raw_df)
        save_output(clean_df, OUTPUT_DIR, CLEANED_FILENAME)

        enriched_df = run_enrichment(clean_df)
        save_output(enriched_df, OUTPUT_DIR, ENRICHED_FILENAME)

        print_summary_report(raw_snapshot, clean_df, enriched_df, time.time() - start)

    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        sys.exit(1)

    for handler in logging.getLogger().handlers:
        handler.flush()


if __name__ == "__main__":
    main()
