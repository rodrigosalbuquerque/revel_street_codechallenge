"""
enrichment.py
=============
Adds cuisine_category, romantic_score, romantic_label, and six score_*
breakdown columns to the cleaned restaurant DataFrame.
"""

import logging
import re

import numpy as np
import pandas as pd

from constants import (
    PRIMARY_TYPE_TO_CUISINE,
    NAME_KEYWORDS_TO_CUISINE,
    WEBSITE_KEYWORDS_TO_CUISINE,
    ROMANTIC_SCORE_WEIGHTS,
    FANCY_PRIMARY_TYPES,
    ROMANTIC_NAME_KEYWORDS_HIGH,
    ROMANTIC_NAME_KEYWORDS_MEDIUM,
    CUISINE_ROMANCE_SCORE,
    HIGH_TICKET_ADDRESS_TOKENS,
    PRICE_POINT_NUMERIC,
    PRICE_POINT_DEFAULT,
)

logger = logging.getLogger(__name__)


# ── Cuisine classification ────────────────────────────────────────────────────

def add_cuisine_category(df: pd.DataFrame) -> pd.DataFrame:
    """
    Three-tier waterfall, fully vectorized across all rows.

    Tier 1 — primary_type dict lookup covers most rows in one pass.
    Tier 2 — name keyword scan fills rows where tier 1 returned None or
              "Contemporary" (the generic "restaurant" API label carries no
              cuisine information and is treated as a signal to fall through).
    Tier 3 — website URL scan fills any rows still unresolved after tier 2.

    Within tiers 2 and 3, keywords are ordered most-to-least specific in
    constants.py. A rolling `unfilled` mask enforces first-match semantics
    without iterating per row — once a row is filled it is excluded from
    all subsequent keyword checks.
    """
    df = df.copy()

    # Tier 1: vectorized dict lookup via Series.map
    tier1 = df["primary_type"].str.lower().map(PRIMARY_TYPE_TO_CUISINE)
    needs_fallback = tier1.isna() | (tier1 == "Contemporary")

    # Tier 2: name keyword scan
    name_lower = df["name"].str.lower().fillna("")
    tier2 = pd.Series(pd.NA, index=df.index, dtype="object")
    unfilled = needs_fallback.copy()
    for keyword, cuisine in NAME_KEYWORDS_TO_CUISINE:
        hit = unfilled & name_lower.str.contains(keyword, regex=False, na=False)
        tier2 = tier2.where(~hit, cuisine)
        unfilled = unfilled & tier2.isna()

    # Tier 3: website URL keyword scan
    url_lower = df["website"].str.lower().fillna("")
    tier3 = pd.Series(pd.NA, index=df.index, dtype="object")
    unfilled = needs_fallback & tier2.isna()
    for keyword, cuisine in WEBSITE_KEYWORDS_TO_CUISINE:
        hit = unfilled & url_lower.str.contains(keyword, regex=False, na=False)
        tier3 = tier3.where(~hit, cuisine)
        unfilled = unfilled & tier3.isna()

    # Assembly: tier2 takes precedence over tier1 for fallback rows;
    # tier3 fills what tier2 missed; remaining NaNs default to "Contemporary".
    result = tier1.copy()
    result = result.where(~(needs_fallback & tier2.notna()), tier2)
    result = result.where(~(needs_fallback & tier2.isna() & tier3.notna()), tier3)
    df["cuisine_category"] = result.fillna("Contemporary")

    return df


# ── Romantic scoring ──────────────────────────────────────────────────────────

def add_romantic_score(df: pd.DataFrame, weights: dict[str, float]) -> pd.DataFrame:
    """
    Six-signal weighted ensemble, fully vectorized.

    Weights are injected as a parameter so callers can substitute alternative
    configurations (A/B testing, tuning) without modifying source files.

    ┌──────────────┬──────────────────────────────────────────────────────────┐
    │ Signal       │ Vectorisation strategy                                   │
    ├──────────────┼──────────────────────────────────────────────────────────┤
    │ price_point  │ Series.map(PRICE_POINT_NUMERIC) + min-max arithmetic     │
    │ address      │ str.contains with one combined regex (single data pass)  │
    │ fancy_type   │ Series.isin(FANCY_PRIMARY_TYPES)                         │
    │ name_keyword │ str.contains per keyword with rolling mask (first-match) │
    │ cuisine      │ Series.map(CUISINE_ROMANCE_SCORE)                        │
    │ has_website  │ notna() + str.len() comparison                           │
    └──────────────┴──────────────────────────────────────────────────────────┘
    """
    df = df.copy()

    # price_point → 0.0 – 1.0  (budget=0.0, low=0.33, medium=0.67, high=1.0)
    # Null rows receive the neutral mid-point rather than the column mean —
    # price_point is ordinal categorical; a statistical mean is meaningless.
    price_default = (PRICE_POINT_DEFAULT - 1.0) / 3.0
    s_price = (
        (df["price_point"].map(PRICE_POINT_NUMERIC) - 1.0) / 3.0
    ).fillna(price_default).clip(0.0, 1.0)

    # address → binary 1.0 / 0.0
    # All tokens are combined into a single regex so the column is scanned once.
    addr_pattern = "|".join(re.escape(t) for t in HIGH_TICKET_ADDRESS_TOKENS)
    s_address = (
        df["display_address"].str.lower()
        .str.contains(addr_pattern, regex=True, na=False)
        .astype(float)
    )

    # fancy_type → binary 1.0 / 0.0
    s_fancy_type = df["primary_type"].str.lower().isin(FANCY_PRIMARY_TYPES).astype(float)

    # name_keyword → 0.0 / 0.5 / 1.0  (max across matches — presence, not frequency)
    name_lower = df["name"].str.lower().fillna("")
    s_name = pd.Series(0.0, index=df.index)
    for kw in ROMANTIC_NAME_KEYWORDS_HIGH:
        s_name = s_name.where(~name_lower.str.contains(kw, regex=False, na=False), 1.0)
    no_high = s_name < 1.0
    for kw in ROMANTIC_NAME_KEYWORDS_MEDIUM:
        hit = no_high & name_lower.str.contains(kw, regex=False, na=False)
        s_name = s_name.where(~hit, 0.5)

    # cuisine → romance affinity of the classified cuisine family
    s_cuisine = df["cuisine_category"].map(CUISINE_ROMANCE_SCORE).fillna(0.3)

    # has_website → binary 1.0 / 0.0
    s_website = (
        df["website"].notna() & df["website"].str.strip().str.len().gt(0)
    ).astype(float)

    # Weighted sum scaled to 0 – 10
    raw = (
        weights["price_point"]  * s_price      +
        weights["address"]      * s_address     +
        weights["fancy_type"]   * s_fancy_type  +
        weights["name_keyword"] * s_name        +
        weights["cuisine"]      * s_cuisine     +
        weights["has_website"]  * s_website
    )

    df["score_price"]      = s_price.round(3)
    df["score_address"]    = s_address.round(3)
    df["score_fancy_type"] = s_fancy_type.round(3)
    df["score_name"]       = s_name.round(3)
    df["score_cuisine"]    = s_cuisine.round(3)
    df["score_website"]    = s_website.round(3)
    df["romantic_score"]   = (raw * 10.0).round(1)

    # pd.cut is vectorized and avoids a per-row if/elif chain
    df["romantic_label"] = pd.cut(
        df["romantic_score"],
        bins=[-np.inf, 2.0, 4.0, 6.0, 8.0, np.inf],
        labels=["Not Romantic", "Casual", "Somewhat Romantic", "Romantic", "Highly Romantic"],
    ).astype(str)

    logger.info(
        "Enrichment complete — romantic_score mean=%.2f, median=%.2f.",
        df["romantic_score"].mean(),
        df["romantic_score"].median(),
    )
    return df


# ── Pipeline entry point ──────────────────────────────────────────────────────

def run_enrichment(df: pd.DataFrame, weights: dict[str, float] = ROMANTIC_SCORE_WEIGHTS) -> pd.DataFrame:
    # cuisine_category must precede romantic scoring — add_romantic_score reads
    # the column for the CUISINE_ROMANCE_SCORE signal lookup.
    df = add_cuisine_category(df)
    df = add_romantic_score(df, weights)
    return df
