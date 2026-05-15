"""
cleaning.py
===========
Data-quality pipeline: normalise → impute → deduplicate.
All functions are pure transforms (DataFrame in → DataFrame out).
"""

import re
import logging
from typing import Optional

import numpy as np
import pandas as pd
from rapidfuzz import fuzz

from constants import (
    NULL_STRINGS,
    TEXT_COLUMNS,
    FUZZY_ADDRESS_THRESHOLD,
    FUZZY_NAME_CITY_THRESHOLD,
)

logger = logging.getLogger(__name__)


# ── Normalisation ─────────────────────────────────────────────────────────────

def normalise_nulls(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace(NULL_STRINGS, np.nan)


def normalise_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in TEXT_COLUMNS:
        if col in df.columns:
            df[col] = df[col].str.strip()
    return df


def _clean_name(name: str) -> str:
    name = name.strip()
    is_all_lower = name == name.lower()
    is_all_upper = name == name.upper()
    # Short ALL-CAPS tokens (≤5 chars) are intentional brand abbreviations — leave them.
    if is_all_upper and len(name.replace(" ", "")) <= 5:
        return name
    if is_all_lower or is_all_upper:
        return name.title()
    return name


def normalise_names(df: pd.DataFrame) -> pd.DataFrame:
    df["name"] = df["name"].apply(lambda x: _clean_name(str(x)) if pd.notna(x) else x)
    return df


def normalise_price_point(df: pd.DataFrame) -> pd.DataFrame:
    df["price_point"] = df["price_point"].str.lower().str.strip()
    return df


def normalise_primary_type(df: pd.DataFrame) -> pd.DataFrame:
    df["primary_type"] = df["primary_type"].str.lower().str.strip()
    return df


def normalise_website(df: pd.DataFrame) -> pd.DataFrame:
    df["website"] = df["website"].str.strip().str.rstrip("/")
    # Fewer than 8 characters cannot be a valid URL (scheme + domain minimum).
    df.loc[df["website"].str.len().fillna(0) < 8, "website"] = np.nan
    return df


# ── Imputation ────────────────────────────────────────────────────────────────

def impute_price_point(df: pd.DataFrame) -> pd.DataFrame:
    # price_point is ordinal categorical — using the column mean would produce
    # a fractional label (e.g. "2.7") with no semantic meaning.
    TYPE_PRICE_MAP: dict[str, str] = {
        "fine_dining_restaurant": "high",
        "kaiseki_restaurant":     "high",
        "diner":                  "low",
        "fast_food_restaurant":   "budget",
    }
    URL_HIGH_TOKENS: list[str] = [
        "bellagio", "aria", "mgmgrand", "waldorf", "peninsula",
        "fourseasons", "ritz", "trump", "mandalaybay", "venetian",
        "wynn", "encore", "themirage",
    ]

    def _infer(row: pd.Series) -> Optional[str]:
        if pd.notna(row["price_point"]):
            return row["price_point"]
        if pd.notna(row["primary_type"]):
            mapped = TYPE_PRICE_MAP.get(str(row["primary_type"]).strip())
            if mapped:
                return mapped
        if pd.notna(row["website"]):
            url_flat = re.sub(r"[^a-z0-9]", "", str(row["website"]).lower())
            if any(tok in url_flat for tok in URL_HIGH_TOKENS):
                return "high"
        return np.nan

    df["price_point"] = df.apply(_infer, axis=1)
    return df


def impute_city(df: pd.DataFrame) -> pd.DataFrame:
    # Deliberately best-effort: leaving NaN is preferable to assigning a wrong
    # city, which would corrupt the city-scoped fuzzy deduplication pass.
    KNOWN_CITIES: list[str] = [
        "New York City", "Los Angeles", "Chicago", "Houston", "San Francisco Bay Area",
        "San Francisco", "Seattle", "Denver", "Washington, DC", "Nashville",
        "New Orleans", "Atlanta", "San Diego", "Miami", "Philadelphia",
        "Minneapolis-Saint Paul", "Minneapolis", "Austin", "Boston", "Dallas",
        "Las Vegas", "Brooklyn", "Queens", "Bronx", "Manhattan",
        "Oakland", "Berkeley", "San Jose", "Sacramento", "Portland",
        "Phoenix", "Tucson", "Scottsdale", "Baltimore", "Arlington",
        "Alexandria", "Bethesda", "Coral Gables", "Fort Lauderdale",
        "Long Beach", "Anaheim", "Santa Monica", "Beverly Hills",
        "West Hollywood", "Culver City", "Costa Mesa", "Plano", "Fort Worth",
        "Charlotte", "Raleigh", "Durham", "Indianapolis", "Columbus",
        "Cleveland", "Cincinnati", "Pittsburgh", "Louisville", "Memphis",
        "Oklahoma City", "Baton Rouge", "Salt Lake City", "Albuquerque",
        "Milwaukee", "Madison", "St. Louis", "Kansas City", "Saint Paul",
        "Omaha", "Lincoln", "Richmond", "Norfolk", "Hartford", "Providence",
        "Detroit", "Grand Rapids",
    ]
    # Longest names first so "San Francisco Bay Area" matches before "San Francisco".
    pattern = "|".join(re.escape(c) for c in sorted(KNOWN_CITIES, key=len, reverse=True))

    def _extract(row: pd.Series) -> Optional[str]:
        if pd.notna(row["city"]):
            return row["city"]
        if pd.notna(row["display_address"]):
            m = re.search(pattern, str(row["display_address"]), re.IGNORECASE)
            if m:
                return m.group(0)
        return np.nan

    df["city"] = df.apply(_extract, axis=1)
    return df


# ── Deduplication helpers ─────────────────────────────────────────────────────

def _completeness_score(row: pd.Series) -> int:
    return int(row.notna().sum())


def _merge_two_rows(primary: pd.Series, secondary: pd.Series) -> pd.Series:
    """
    ┌──────────────────┬────────────────────────────────────────────────────┐
    │ Field            │ Rule                                               │
    ├──────────────────┼────────────────────────────────────────────────────┤
    │ Any field        │ Null in primary → fill from secondary.             │
    │ display_address  │ Both non-null → keep the longer string.            │
    │ primary_type     │ Both non-null → prefer anything over "restaurant". │
    │ website          │ Both non-null → prefer the shorter URL (no UTM).   │
    │ name             │ Both non-null → prefer mixed-case over all-lower/  │
    │                  │ all-upper (indicates better data-entry quality).   │
    │ latitude /       │ Both non-null → average (values differ by <0.001°) │
    │ longitude        │                                                    │
    └──────────────────┴────────────────────────────────────────────────────┘
    """
    merged = primary.copy()

    for col in secondary.index:
        try:
            pv, sv = primary[col], secondary[col]
        except KeyError:
            continue

        p_missing = pd.isna(pv) or str(pv).strip() == ""
        s_missing = pd.isna(sv) or str(sv).strip() == ""

        if p_missing and not s_missing:
            merged[col] = sv
        elif not p_missing and not s_missing:
            if col == "display_address":
                if len(str(sv)) > len(str(pv)):
                    merged[col] = sv
            elif col == "primary_type":
                if str(pv).strip().lower() == "restaurant":
                    merged[col] = sv
            elif col == "website":
                if len(str(sv)) < len(str(pv)):
                    merged[col] = sv
            elif col == "name":
                pv_s, sv_s = str(pv), str(sv)
                p_mixed = pv_s != pv_s.upper() and pv_s != pv_s.lower()
                s_mixed = sv_s != sv_s.upper() and sv_s != sv_s.lower()
                if not p_mixed and s_mixed:
                    merged[col] = sv

    for coord in ("latitude", "longitude"):
        try:
            pc, sc = primary[coord], secondary[coord]
        except KeyError:
            continue
        if pd.notna(pc) and pd.notna(sc):
            try:
                merged[coord] = (float(pc) + float(sc)) / 2.0
            except (ValueError, TypeError):
                pass

    return merged


def _merge_group(group: pd.DataFrame) -> pd.Series:
    ordered = group.loc[group.apply(_completeness_score, axis=1).sort_values(ascending=False).index]
    merged = ordered.iloc[0].copy()
    for _, row in ordered.iloc[1:].iterrows():
        merged = _merge_two_rows(merged, row)
    return merged


# ── Deduplication: google_place_id exact match ────────────────────────────────

def deduplicate_by_place_id(df: pd.DataFrame) -> pd.DataFrame:
    has_id = df[df["google_place_id"].notna()].copy()
    no_id  = df[df["google_place_id"].isna()].copy()

    id_counts = has_id["google_place_id"].value_counts()
    dup_ids   = id_counts[id_counts > 1].index.tolist()

    merged_list: list[pd.Series] = [
        _merge_group(has_id[has_id["google_place_id"] == pid])
        for pid in dup_ids
    ]

    parts: list[pd.DataFrame] = [has_id[~has_id["google_place_id"].isin(dup_ids)], no_id]
    if merged_list:
        parts.insert(1, pd.DataFrame(merged_list))

    return pd.concat(parts, ignore_index=True)


# ── Deduplication: rapidfuzz fuzzy matching ───────────────────────────────────

def _normalise_for_matching(text) -> str:
    if pd.isna(text):
        return ""
    return re.sub(r"\s+", " ", str(text).lower().strip())


def _find_fuzzy_duplicate_clusters(
    addresses: list[str],
    name_cities: list[str],
    city_to_indices: dict[str, list[int]],
) -> list[list[int]]:
    """
    Return index clusters whose members are fuzzy duplicates of each other.

    token_sort_ratio is used over simple ratio because sorting tokens before
    comparing makes it robust to word-order and casing differences in addresses
    (e.g. "229 South 4th St, Brooklyn" vs "229 SOUTH 4TH STREET, BROOKLYN").

    Two thresholds are intentional:
    - Address (85): longer strings tolerate more character-level variation.
    - Name+city (90): short strings reach high similarity scores by accident;
      a stricter threshold reduces false merges.

    Union-Find with path compression gives correct transitive closure — if A≈B
    and B≈C, all three land in the same cluster even if A and C were never
    directly compared.
    """
    n = len(addresses)
    parent = list(range(n))

    def _find(x: int) -> int:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def _union(x: int, y: int) -> None:
        parent[_find(x)] = _find(y)

    for indices in city_to_indices.values():
        if len(indices) < 2:
            continue
        for i_pos, i in enumerate(indices):
            for j in indices[i_pos + 1:]:
                if _find(i) == _find(j):
                    continue
                if addresses[i] and addresses[j]:
                    if fuzz.token_sort_ratio(addresses[i], addresses[j]) >= FUZZY_ADDRESS_THRESHOLD:
                        _union(i, j)
                        continue
                if name_cities[i] and name_cities[j]:
                    if fuzz.token_sort_ratio(name_cities[i], name_cities[j]) >= FUZZY_NAME_CITY_THRESHOLD:
                        _union(i, j)

    clusters: dict[int, list[int]] = {}
    for idx in range(n):
        clusters.setdefault(_find(idx), []).append(idx)

    return [members for members in clusters.values() if len(members) > 1]


def deduplicate_by_fuzzy_match(df: pd.DataFrame) -> pd.DataFrame:
    # Comparisons are city-scoped to avoid O(n²) global pairs and cross-city
    # false positives (e.g. "100 Main St" exists in hundreds of US cities).
    no_id_mask = df["google_place_id"].isna()
    no_id_df   = df[no_id_mask].copy().reset_index(drop=True)
    has_id_df  = df[~no_id_mask].copy()

    if no_id_df.empty:
        return df

    addresses: list[str] = [_normalise_for_matching(v) for v in no_id_df["display_address"]]
    name_cities: list[str] = [
        _normalise_for_matching(
            f"{row['name'] if pd.notna(row['name']) else ''} "
            f"{row['city'] if pd.notna(row['city']) else ''}"
        )
        for _, row in no_id_df.iterrows()
    ]

    city_to_indices: dict[str, list[int]] = {}
    for idx, city in enumerate(no_id_df["city"].fillna("__unknown__")):
        city_to_indices.setdefault(str(city), []).append(idx)

    dup_clusters = _find_fuzzy_duplicate_clusters(addresses, name_cities, city_to_indices)

    dup_indices  = {idx for cluster in dup_clusters for idx in cluster}
    singleton_df = no_id_df[~no_id_df.index.isin(dup_indices)]
    merged_rows  = pd.DataFrame([_merge_group(no_id_df.iloc[cluster]) for cluster in dup_clusters])

    return pd.concat([has_id_df, singleton_df, merged_rows], ignore_index=True)


# ── Pipeline entry point ──────────────────────────────────────────────────────

def run_cleaning(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ordering is significant:
    - Null normalisation before everything — downstream functions rely on pd.isna().
    - Text normalisation before deduplication — whitespace differences cause false non-matches.
    - Imputation before deduplication — city fill is needed to scope fuzzy comparison.
    - place_id dedup before fuzzy — authoritative matches are removed first so they
      don't re-enter the fuzzier (less certain) comparison pool.
    """
    original_len = len(df)

    df = normalise_nulls(df)
    df = normalise_text_columns(df)
    df = normalise_names(df)
    df = normalise_price_point(df)
    df = normalise_primary_type(df)
    df = normalise_website(df)
    df = impute_price_point(df)
    df = impute_city(df)
    df = deduplicate_by_place_id(df)
    df = deduplicate_by_fuzzy_match(df)
    df = df.reset_index(drop=True)

    logger.info(
        "Cleaning complete — %d → %d rows (%d duplicates removed).",
        original_len, len(df), original_len - len(df),
    )
    return df
