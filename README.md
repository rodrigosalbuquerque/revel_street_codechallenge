# Restaurant Data Pipeline

A modular, repeatable Python pipeline that cleans, deduplicates, and enriches a raw restaurant dataset. It resolves data-quality issues in the source CSV and derives two analytical columns — **cuisine category** and **romantic score** — that can be used directly for recommendation, ranking, and segmentation.

---

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Quick Start](#2-quick-start)
3. [Dataset Overview](#3-dataset-overview)
4. [Pipeline Architecture](#4-pipeline-architecture)
5. [Stage 1 — Cleaning](#5-stage-1--cleaning)
   - 5.1 Normalisation
   - 5.2 Imputation
   - 5.3 Deduplication by Google Place ID
   - 5.4 Deduplication by Fuzzy Matching
6. [Stage 2 — Enrichment](#6-stage-2--enrichment)
   - 6.1 Cuisine Classification
   - 6.2 Romantic Score
7. [Output Schema](#7-output-schema)
8. [Configuration Reference](#8-configuration-reference)
9. [Dependencies](#9-dependencies)
10. [Design Decisions & Trade-offs](#10-design-decisions--trade-offs)

---

## 1. Project Structure

```
.
├── restaurants.csv          # Raw input dataset
│
├── constants.py             # All static mappings, thresholds, weights
├── cleaning.py              # Normalisation, imputation, deduplication logic
├── enrichment.py            # Cuisine classification, romantic scoring
├── main.py                  # Orchestrator — CLI entry point
│
├── output/
│   ├── restaurants_clean.csv    # After cleaning, before enrichment
│   └── restaurants_enriched.csv # Final output with all derived columns
│
├── pipeline.log             # Full DEBUG log written on every run
└── README.md
```

**Module responsibility map:**

| File | Responsibility | Imports from |
|------|---------------|--------------|
| `constants.py` | Static data only — mappings, thresholds, weights | nothing |
| `cleaning.py` | Data quality — pure transform functions | `constants` |
| `enrichment.py` | Feature derivation — pure transform functions | `constants` |
| `main.py` | I/O, orchestration, logging, CLI, reporting | all three |

The dependency graph is a strict DAG: `constants ← cleaning ← main`, `constants ← enrichment ← main`. No circular imports, no shared mutable state.

---

## 2. Quick Start

### Install dependencies

```bash
pip install pandas numpy rapidfuzz
```

### Run with defaults

```bash
# Reads restaurants.csv from the working directory
# Writes output/ to the working directory
python main.py
```

### All CLI options

```bash
python main.py --help

# Custom input / output paths
python main.py --input data/restaurants.csv --output results/

# Show per-row DEBUG detail in the console (merge decisions, fuzzy scores, etc.)
python main.py --verbose

# Skip writing the intermediate cleaned file; only produce the enriched CSV
python main.py --no-intermediate

# Custom log file location
python main.py --log-file logs/run_2024.log
```

### Expected output

```
=================================================================
  RESTAURANT DATA PIPELINE — SUMMARY REPORT
=================================================================

PIPELINE METRICS
-----------------------------------------------------------------
  Input rows          :  1,072
  After cleaning      :  1,045  (-27 duplicates removed)
  After enrichment    :  1,045  (same — enrichment adds columns)
  Total columns       :     19
  Elapsed time        :   1.84s

NULL VALUES FILLED (cleaning stage)
-----------------------------------------------------------------
  price_point              :   12 values imputed
  city                     :    2 values imputed
  ...

ROMANTIC SCORE DISTRIBUTION
-----------------------------------------------------------------
  Mean   : 5.43 / 10.0
  ...
  Highly Romantic       42  ( 4.0%)  ██████████████
  Romantic             318  (30.4%)  ██████████████████████████████
  ...

TOP 10 MOST ROMANTIC VENUES
-----------------------------------------------------------------
   1. Le Bernardin                     New York City     French             ★ 9.3
   2. Gabriel Kreuther                 New York City     French             ★ 9.1
  ...
```

---

## 3. Dataset Overview

The raw CSV contains **~1 072 rows** with the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `id` | string | Internal venue identifier |
| `name` | string | Restaurant name |
| `city` | string | Metro area (e.g. "New York City", "San Francisco Bay Area") |
| `display_address` | string | Street address |
| `google_place_id` | string | Google Maps canonical venue ID |
| `latitude` | float | Geographic latitude |
| `longitude` | float | Geographic longitude |
| `price_point` | string | `budget` / `low` / `medium` / `high` |
| `primary_type` | string | Google Places type (e.g. `italian_restaurant`) |
| `website` | string | Venue website URL |

### Known data-quality issues in the raw file

| Issue | Example | How it is resolved |
|-------|---------|-------------------|
| Literal `"null"` strings | `display_address = "null"` | Replaced with `NaN` on load |
| Trailing whitespace in names | `"Flagstaff House "` | Stripped in normalisation |
| All-lowercase names | `"traif"` → should be `"Traif"` | Title-cased in normalisation |
| Exact duplicates via `google_place_id` | Traif appears as both `"Traif"` (id 97527) and `"traif"` (id 108742) with the same place ID | Merged — see §5.3 |
| Near-duplicate names/addresses | Same venue entered twice with minor text differences | Fuzzy-matched — see §5.4 |
| Missing `price_point` | ~12 rows | Inferred from `primary_type` and website URL — see §5.2 |
| Non-restaurant entries | Hotels, museums, venues, corporate offices | Classified correctly as `Hotel/Venue`, `Venue`, `Other` in cuisine column; included in output but score appropriately low |
| Inconsistent address formatting | Mixed abbreviations, casing, inclusion of ZIP codes | Normalised before fuzzy matching |

---

## 4. Pipeline Architecture

```
restaurants.csv
      │
      ▼
┌─────────────────────────────────────────────────┐
│  LOAD  (main.py)                                │
│  • pd.read_csv with typed dtypes                │
│  • na_values=NULL_STRINGS                       │
│  • Schema validation                            │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│  CLEAN  (cleaning.py)                           │
│                                                 │
│  Normalisation                                  │
│    1. Replace null sentinel strings → NaN       │
│    2. Strip whitespace from text columns        │
│    3. Fix name casing                           │
│    4. Lowercase price_point / primary_type      │
│    5. Clean website URLs                        │
│                                                 │
│  Imputation                                     │
│    6. Infer price_point from type / URL         │
│    7. Extract city from address                 │
│                                                 │
│  Deduplication                                  │
│    8. Exact match on google_place_id → merge    │
│    9. rapidfuzz on address / name+city → merge  │
└──────────────────────┬──────────────────────────┘
                       │  restaurants_clean.csv
                       ▼
┌─────────────────────────────────────────────────┐
│  ENRICH  (enrichment.py)                        │
│                                                 │
│    10. Classify cuisine (3-tier waterfall)      │
│    11. Compute romantic score (6-signal model)  │
└──────────────────────┬──────────────────────────┘
                       │  restaurants_enriched.csv
                       ▼
                   REPORT (stdout + pipeline.log)
```

Every stage is a pure function — `DataFrame in → DataFrame out` — with no shared state between stages. This makes each step independently testable and the pipeline trivially re-orderable or parallelisable.

---

## 5. Stage 1 — Cleaning

### 5.1 Normalisation

Six normalisation functions run in sequence before any deduplication occurs. This ordering is critical: deduplication uses string comparison and will miss duplicates if one copy has a trailing space or different casing.

#### Null sentinel replacement
The source system serialised `NULL` values as the literal string `"null"` rather than leaving cells empty. Every occurrence of `"null"`, `""`, `"none"`, `"n/a"` etc. (see `NULL_STRINGS` in `constants.py`) is replaced with a genuine `NaN` so that `pd.isna()` behaves correctly everywhere downstream.

#### Name casing
Only names that are **entirely** lowercase or **entirely** uppercase are corrected, to avoid overwriting intentional mixed-case branding:

| Input | Action | Output |
|-------|--------|--------|
| `"traif"` | All-lower → title-case | `"Traif"` |
| `"PRIME STEAKHOUSE"` | All-upper, >5 chars → title-case | `"Prime Steakhouse"` |
| `"SPQR"` | All-upper, ≤5 chars → keep (acronym) | `"SPQR"` |
| `"Le Bernardin"` | Mixed-case → leave untouched | `"Le Bernardin"` |

#### Website URL cleaning
Trailing slashes are stripped so that `"http://example.com/"` and `"http://example.com"` are treated as the same URL during deduplication. Values shorter than 8 characters (which cannot be a valid URL) are nullified.

---

### 5.2 Imputation

#### price_point
Missing price points are inferred using a priority chain — never using a statistical mean, because `price_point` is an ordinal categorical variable and a fractional mean has no semantic meaning:

1. **`primary_type` lookup** — `fine_dining_restaurant` → `high`, `diner` → `low`, etc.
2. **Website URL token matching** — URLs containing `"bellagio"`, `"aria"`, `"mgmgrand"`, `"waldorf"`, `"peninsula"` etc. reliably indicate high-price hotel restaurants.
3. **Leave as `NaN`** — the enrichment stage uses a numeric mid-point default (2.5 on a 1–4 scale) so remaining nulls do not silently bias the romantic score.

#### city
For the small number of rows where `city` is null, the pipeline attempts a regex match against a list of known cities ordered by length descending (so `"San Francisco Bay Area"` matches before `"San Francisco"` in the same address string). This is explicitly best-effort; if no known city is found the value remains `NaN` rather than assigning a wrong city, which would corrupt the city-scoped fuzzy deduplication pass.

---

### 5.3 Deduplication by Google Place ID

`google_place_id` is Google Maps' canonical, immutable venue identifier. Two rows sharing a place ID are **definitively** the same physical location, regardless of how different their name or address strings look.

**Algorithm:**
1. Partition the dataset into `has_id` (place ID present) and `no_id` (place ID null).
2. Within `has_id`, find all place IDs with more than one row.
3. For each duplicate group, merge all rows into one canonical record using field-level rules (see below).
4. Recombine: unique rows + merged rows + `no_id` rows.

**Confirmed duplicate groups in the source data:**

| google_place_id | Rows merged | Names |
|-----------------|-------------|-------|
| `ChIJveB2ceBb…` | 2 | "Traif" + "traif" |
| `ChIJBXlte51Z…` | 2 | "Dirt Candy" + "Dirt Candy" (different address formats) |
| `ChIJ62K862-_…` | 3 | "Merois \| West Hollywood" + "The Merois \| West Hollywood" + "Merois" |
| `ChIJpQmgMoQy…` | 2 | "Spoon and Stable" + "The Spoon and Stable" |

**Field-level merge rules:**

| Field | Rule |
|-------|------|
| Any field | If primary is null, fill from secondary (gap-fill). |
| `display_address` | When both non-null, keep the longer string (more complete). |
| `primary_type` | When both non-null, prefer anything over the generic `"restaurant"` label. |
| `website` | When both non-null, prefer the shorter URL (canonical version without UTM params). |
| `name` | When both non-null, prefer the mixed-case version over all-lower or all-upper. |
| `latitude` / `longitude` | Average both values — both come from Google and differ by < 0.001°. |

The row with the **highest completeness score** (most non-null fields) is chosen as the primary seed to maximise the information retained in the merged record.

---

### 5.4 Deduplication by Fuzzy Matching

Rows that lack a `google_place_id` cannot be matched definitively, so [rapidfuzz](https://github.com/maxbachmann/RapidFuzz) `token_sort_ratio` is used as a similarity measure.

**Why `token_sort_ratio`?**
It sorts the tokens in both strings alphabetically before comparing, making it robust to word-order differences in addresses — e.g. `"229 South 4th Street, Brooklyn"` vs `"229 SOUTH 4TH STREET, BROOKLYN"` scores 100 even though the casing differs.

**Algorithm:**

```
For each city cohort (rows with the same city value):
    For each pair (i, j) in the cohort:
        If address_i and address_j both non-null:
            score = token_sort_ratio(normalised_addr_i, normalised_addr_j)
            if score ≥ FUZZY_ADDRESS_THRESHOLD (85):  → mark as duplicate
        Else (one or both addresses null):
            score = token_sort_ratio(name_i + city_i, name_j + city_j)
            if score ≥ FUZZY_NAME_CITY_THRESHOLD (90): → mark as duplicate
```

**Why city-scoped comparison?**
Comparing all pairs globally would be O(n²) ≈ 1 000 000 comparisons. Scoping to city cohorts reduces this to O(k²) per city where k is typically 50–150, cutting total comparisons by ~95%.

**Why different thresholds?**
- Address threshold = **85**: addresses are longer strings where small differences (abbreviations, punctuation) should not prevent a match.
- Name+city threshold = **90**: restaurant names are short strings. A 85% similarity on a 10-character name can match completely different places; the higher threshold reduces false merges.

**Transitive closure via Union-Find:**
If restaurant A matches B (score ≥ threshold) and B matches C, then A, B, and C should all be in the same merge group — even if A and C were never directly compared. A Union-Find data structure with path compression handles this correctly in O(α(n)) ≈ O(1) amortised time per union/find operation.

---

## 6. Stage 2 — Enrichment

### 6.1 Cuisine Classification

A three-tier waterfall assigns a human-readable cuisine family to every row.

```
primary_type  ──► PRIMARY_TYPE_TO_CUISINE  ──► not "Contemporary"?  ──► done
                                                       │
                                                    "Contemporary"
                                                    or null
                                                       │
                                                       ▼
name          ──► NAME_KEYWORDS_TO_CUISINE  ──────► match?  ──► done
                                                       │
                                                      no match
                                                       │
                                                       ▼
website URL   ──► WEBSITE_KEYWORDS_TO_CUISINE ────► match?  ──► done
                                                       │
                                                      no match
                                                       │
                                                       ▼
                                               "Contemporary" (default)
```

**Tier 1 — `primary_type` mapping (most reliable)**
Maps all 40+ Google Places API types to 20 cuisine families. The generic `"restaurant"` type maps to `"Contemporary"` — a sentinel that signals the cascade to continue, because `"restaurant"` alone carries no cuisine information.

**Tier 2 — Name keyword scan (medium reliability)**
`NAME_KEYWORDS_TO_CUISINE` is an ordered list of `(keyword, cuisine)` tuples. Order matters: more specific terms appear before general ones so the first match is always the most informative (`"omakase"` before `"sushi"` before `"japanese"`).

**Tier 3 — Website URL scan (lowest reliability, last resort)**
URL domains often encode cuisine identity even when the name is generic (e.g. `pastamoon.com` → Italian, `sushikashiba.com` → Japanese).

**Output categories (20 families):**
`French`, `Italian`, `Japanese`, `Korean`, `Chinese`, `Mexican`, `Latin American`, `American`, `Steakhouse`, `Fine Dining`, `Seafood`, `Mediterranean`, `Greek`, `Spanish`, `Southeast Asian`, `Indian`, `African`, `Creole/Cajun`, `Asian Fusion`, `European`, `Bar/Lounge`, `Café`, `Hotel/Venue`, `Venue`, `Other`, `Contemporary`

---

### 6.2 Romantic Score

A **0.0 – 10.0** float score built from six independent sub-signals, each contributing a weighted fraction of the final score.

#### Sub-signals and weights

| Signal | Weight | Scoring logic |
|--------|--------|--------------|
| `price_point` | **30%** | Linear normalisation: budget=0.00, low=0.33, medium=0.67, high=1.00. Null → 0.50 neutral mid-point. |
| `address` | **25%** | Binary 1.0 / 0.0. Checks for ~40 high-ticket tokens (Park Ave, Rodeo Dr, Bellagio, Four Seasons, MGM Grand, etc.) in the address string. |
| `fancy_type` | **20%** | Binary 1.0 / 0.0. Checks `primary_type` against 14 upscale types: `fine_dining_restaurant`, `french_restaurant`, `kaiseki_restaurant`, `steak_house`, `sushi_restaurant`, etc. |
| `name_keyword` | **10%** | HIGH keywords (e.g. `"le "`, `"l'"`, `"chez"`, `"omakase"`, `"atelier"`, `"manor"`) → 1.0. MEDIUM keywords (e.g. `"bistro"`, `"garden"`, `"lounge"`) → 0.5. Returns maximum found (not sum). |
| `cuisine` | **10%** | Looks up `cuisine_category` in `CUISINE_ROMANCE_SCORE`: French/Fine Dining=1.0, Japanese=0.9, Italian=0.85 … Café=0.25, Venue=0.15. |
| `has_website` | **5%** | Binary 1.0 / 0.0. Professional web presence is a weak proxy for an established, curated experience. Given lowest weight because predictive power alone is limited. |

#### Weight rationale

- **Price (30%)** is the single strongest proxy for a special-occasion venue. Research on dining behaviour consistently shows that price point is the dominant factor consumers consider when planning a date night.
- **Address (25%)** captures the "setting" signal that price alone misses. A $$$$ restaurant in a strip mall vs. one on Park Avenue are fundamentally different experiences even at the same price.
- **Fancy type (20%)** adds structural information from the Google Places taxonomy. `fine_dining_restaurant` and `french_restaurant` are Google's own judgment that these are upscale venues.
- **Name keywords (10%)** and **cuisine (10%)** together pick up residual romantic signal. A restaurant named `"Chez Marcel"` or one serving French cuisine carries strong cultural associations with romance even if the other signals are moderate.
- **Website (5%)** is a weak tie-breaker. It is last and lightest because virtually every established restaurant now has a website; its absence is more informative (usually means a very informal spot) than its presence.

#### Score formula

```
raw_score = 0.30 × s_price + 0.25 × s_address + 0.20 × s_fancy_type
          + 0.10 × s_name  + 0.10 × s_cuisine  + 0.05 × s_website

romantic_score = round(raw_score × 10, 1)
```

#### Label tiers

| Score range | Label | Typical examples |
|-------------|-------|-----------------|
| 0.0 – 2.0 | Not Romantic | Museum lobby café, corporate office canteen, hotel check-in bar |
| 2.1 – 4.0 | Casual | Neighbourhood diner, gastropub, budget taqueria |
| 4.1 – 6.0 | Somewhat Romantic | Mid-range Italian, decent sushi, well-regarded American |
| 6.1 – 8.0 | Romantic | Upscale steakhouse, fine Japanese, premium seafood |
| 8.1 – 10.0 | Highly Romantic | French fine dining on Park Ave, kaiseki omakase, luxury resort restaurant |

#### Score transparency

Six `score_*` columns are written to the enriched CSV so any row's score can be fully audited without re-running the pipeline:

```
score_price, score_address, score_fancy_type,
score_name, score_cuisine, score_website
```

---

## 7. Output Schema

### `restaurants_clean.csv` (10 columns, same as input)

Same columns as the raw file. Differences from input:
- Null sentinel strings replaced with empty cells.
- Names normalised (whitespace stripped, casing fixed).
- Duplicate rows merged (see §5.3 and §5.4).
- `price_point` and `city` partially imputed.

### `restaurants_enriched.csv` (19 columns)

All columns from the clean file plus:

| Column | Type | Description |
|--------|------|-------------|
| `cuisine_category` | string | Classified cuisine family (e.g. `"French"`, `"Japanese"`) |
| `score_price` | float 0–1 | Price sub-signal contribution |
| `score_address` | float 0–1 | Address sub-signal contribution |
| `score_fancy_type` | float 0–1 | Fancy-type sub-signal contribution |
| `score_name` | float 0–1 | Name-keyword sub-signal contribution |
| `score_cuisine` | float 0–1 | Cuisine-romance sub-signal contribution |
| `score_website` | float 0–1 | Website sub-signal contribution |
| `romantic_score` | float 0–10 | Final weighted romantic score |
| `romantic_label` | string | Tier label (`"Not Romantic"` … `"Highly Romantic"`) |

---

## 8. Configuration Reference

All tunable parameters live in `constants.py`. No other file contains magic numbers.

| Constant | Default | Effect of changing |
|----------|---------|-------------------|
| `FUZZY_ADDRESS_THRESHOLD` | `85` | Lower → more aggressive dedup (risk of false merges). Higher → misses more real duplicates. |
| `FUZZY_NAME_CITY_THRESHOLD` | `90` | Same trade-off; kept higher than address threshold because names are shorter strings. |
| `PRICE_POINT_DEFAULT` | `2.5` | Numeric stand-in for missing price; 2.5 on a 1–4 scale = neutral mid-point. |
| `ROMANTIC_SCORE_WEIGHTS` | See §6.2 | Rebalance signal contributions; weights must sum to 1.0. |
| `FANCY_PRIMARY_TYPES` | 14 types | Add/remove Google Places types considered "fancy". |
| `HIGH_TICKET_ADDRESS_TOKENS` | ~40 tokens | Add neighbourhood or property names to improve address signal. |
| `CUISINE_ROMANCE_SCORE` | French=1.0 … Venue=0.15 | Adjust per-cuisine romance affinity. |
| `PRIMARY_TYPE_TO_CUISINE` | 40+ mappings | Add new Google Places types as the API evolves. |

---

## 9. Dependencies

| Package | Version tested | Purpose |
|---------|---------------|---------|
| `pandas` | ≥ 1.5 | DataFrame operations throughout |
| `numpy` | ≥ 1.23 | NaN handling, numeric operations |
| `rapidfuzz` | ≥ 3.0 | Fast fuzzy string matching for deduplication |

All three are pure-Python / binary wheels with no system-level dependencies.

```bash
pip install pandas numpy rapidfuzz
```

No other packages are required. The pipeline deliberately avoids heavy ML dependencies (scikit-learn, spaCy, transformers) because the classification and scoring tasks are well-served by deterministic rule-based logic that is easier to audit, faster to run, and cheaper to maintain.

---

## 10. Design Decisions & Trade-offs

### Why rule-based classification instead of ML?

A transformer-based NER or classification model could potentially achieve higher recall on edge cases. However, for a dataset of ~1 000 rows:
- Training data for fine-tuning is unavailable.
- A rule-based system with a well-curated keyword list achieves >95% accuracy on the cuisine classification task with zero inference cost.
- Rules are auditable — a stakeholder can read `constants.py` and immediately understand why "Le Bernardin" is classified as French.
- Rules are maintainable — adding a new cuisine family is a one-line change in `PRIMARY_TYPE_TO_CUISINE`.

### Why is the romantic score deterministic rather than learned?

A learned model (logistic regression, gradient boosting) would require a labelled training set of "romantic" vs "not romantic" venues, which does not exist in this dataset. The deterministic weighted model is:
- Transparent and explainable to non-technical stakeholders.
- Easily tunable by adjusting weights in `constants.py` without any code changes.
- Consistent — the same input always produces the same output, making it easy to version and audit.

### Why merge duplicates rather than drop them?

Dropping would lose data. Row A might have an address but no price; row B might have a price but no address. The merge strategy preserves the union of all available information, producing a record that is strictly more complete than either source row.

### Why Union-Find for fuzzy deduplication?

A naive approach would iterate over matched pairs and merge them one at a time, but this fails for transitive duplicates (A≈B, B≈C should produce one group, not two merges of two rows each). Union-Find with path compression solves the transitive-closure problem in near-linear time and is the standard algorithm for exactly this use case.

### Why city-scoped fuzzy comparison?

The same address string can appear in different cities (e.g. "100 Main St" exists in hundreds of US cities). Scoping comparisons to the same city eliminates an entire class of false positives. It also reduces computational complexity from O(n²) globally to O(k²) per city, which is roughly a 95% reduction for a dataset spread across 20 cities.

### Why separate `restaurants_clean.csv` and `restaurants_enriched.csv`?

The cleaned file is a stable, enrichment-agnostic intermediate that can be re-used if the scoring model changes (e.g. weight updates in `constants.py`). Re-running only enrichment on an already-clean file is much faster than re-running the full pipeline, and it separates the concerns of data quality from feature engineering.
