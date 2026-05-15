"""
constants.py
============
Single source of truth for all static mappings, thresholds, and weights used
across the pipeline.  Logic files import from here; no magic numbers elsewhere.
"""

# ── Data quality ──────────────────────────────────────────────────────────────
#
# The source CSV serialises missing values as the literal string "null" rather
# than leaving cells empty, so NULL_STRINGS covers all observed variants.
# TEXT_COLUMNS drives whitespace stripping before deduplication — stray spaces
# cause false non-matches in fuzzy address comparisons.

NULL_STRINGS: list[str] = ["null", "NULL", "Null", "none", "None", "NONE", "n/a", "N/A", ""]

TEXT_COLUMNS: list[str] = ["name", "city", "display_address", "website"]


# ── Deduplication thresholds ──────────────────────────────────────────────────
#
# Address threshold (85): longer strings naturally absorb formatting variation
# (abbreviations, casing, punctuation) without requiring an exact match.
# Name+city threshold (90): short strings reach high similarity scores by
# coincidence; the stricter threshold reduces false merges between distinct venues.

FUZZY_ADDRESS_THRESHOLD:    int = 85
FUZZY_NAME_CITY_THRESHOLD:  int = 90


# ── Price point ───────────────────────────────────────────────────────────────
#
# An ordinal 1–4 scale allows linear arithmetic in the romantic score.
# PRICE_POINT_DEFAULT sits at the numeric mid-point (2.5) so that missing
# values are neutral — they neither inflate nor deflate the final score.

PRICE_POINT_NUMERIC: dict[str, float] = {
    "budget": 1.0,
    "low":    2.0,
    "medium": 3.0,
    "high":   4.0,
}

PRICE_POINT_DEFAULT: float = 2.5


# ── Cuisine classification ────────────────────────────────────────────────────
#
# Three tiers resolve cuisine from coarse to fine:
#   Tier 1 — PRIMARY_TYPE_TO_CUISINE: Google Places API types (controlled vocab,
#             most reliable). The generic "restaurant" type maps to "Contemporary"
#             as a sentinel that signals the pipeline to continue to Tier 2.
#   Tier 2 — NAME_KEYWORDS_TO_CUISINE: ordered most-specific-to-least within each
#             cuisine family; first match wins so specificity order is preserved.
#   Tier 3 — WEBSITE_KEYWORDS_TO_CUISINE: URL domain/path as last resort for
#             venues whose name and type carry no cuisine signal.
#
# All three lists are organised alphabetically by cuisine family for maintainability.

PRIMARY_TYPE_TO_CUISINE: dict[str, str] = {
    "american_restaurant":       "American",
    "asian_fusion_restaurant":   "Asian Fusion",
    "bar":                       "Bar/Lounge",
    "brunch_restaurant":         "American",
    "cafe":                      "Café",
    "californian_restaurant":    "American",
    "chinese_restaurant":        "Chinese",
    "cocktail_bar":              "Bar/Lounge",
    "corporate_office":          "Other",
    "creole_restaurant":         "Creole/Cajun",
    "diner":                     "American",
    "event_venue":               "Venue",
    "fine_dining_restaurant":    "Fine Dining",
    "french_restaurant":         "French",
    "gastropub":                 "American",
    "greek_restaurant":          "Greek",
    "historical_landmark":       "Venue",
    "hotel":                     "Hotel/Venue",
    "indian_restaurant":         "Indian",
    "indonesian_restaurant":     "Southeast Asian",
    "italian_restaurant":        "Italian",
    "japanese_restaurant":       "Japanese",
    "kaiseki_restaurant":        "Japanese",
    "korean_restaurant":         "Korean",
    "live_music_bar":            "Bar/Lounge",
    "live_music_venue":          "Venue",
    "mediterranean_restaurant":  "Mediterranean",
    "mexican_restaurant":        "Mexican",
    "modern_art_museum":         "Venue",
    "new_american_restaurant":   "American",
    "pizza_restaurant":          "Italian",
    "ramen_restaurant":          "Japanese",
    "restaurant":                "Contemporary",
    "roman_restaurant":          "Italian",
    "seafood_restaurant":        "Seafood",
    "south_american_restaurant": "Latin American",
    "southern_restaurant_us":    "American",
    "spanish_restaurant":        "Spanish",
    "steak_house":               "Steakhouse",
    "sushi_restaurant":          "Japanese",
    "thai_restaurant":           "Southeast Asian",
    "ukrainian_restaurant":      "European",
    "vietnamese_restaurant":     "Southeast Asian",
    "west_african_restaurant":   "African",
}

NAME_KEYWORDS_TO_CUISINE: list[tuple[str, str]] = [
    # African
    ("african",       "African"),
    # American
    ("american",      "American"),
    ("barbecue",      "American"),
    ("bbq",           "American"),
    ("burger",        "American"),
    ("diner",         "American"),
    ("grill",         "American"),
    ("smokehouse",    "American"),
    # Bar/Lounge
    ("bar",           "Bar/Lounge"),
    # Café
    ("cafe",          "Café"),
    ("coffee",        "Café"),
    # Chinese
    ("dim sum",       "Chinese"),
    ("dumpling",      "Chinese"),
    ("peking",        "Chinese"),
    ("chinese",       "Chinese"),
    # Creole/Cajun
    ("cajun",         "Creole/Cajun"),
    ("creole",        "Creole/Cajun"),
    ("nola",          "Creole/Cajun"),      # shorthand for New Orleans
    # French
    ("brasserie",     "French"),
    ("patisserie",    "French"),
    ("bistro",        "French"),
    # Greek
    ("greek",         "Greek"),
    # Indian
    ("tandoor",       "Indian"),
    ("curry",         "Indian"),
    ("indian",        "Indian"),
    # Italian
    ("pizzeria",      "Italian"),
    ("trattoria",     "Italian"),
    ("osteria",       "Italian"),
    ("pasta",         "Italian"),
    ("pizza",         "Italian"),
    # Japanese — ordered most-specific first; "sake" is a known false-match risk
    ("omakase",       "Japanese"),
    ("kaiseki",       "Japanese"),
    ("yakitori",      "Japanese"),
    ("izakaya",       "Japanese"),
    ("kappo",         "Japanese"),
    ("sushi",         "Japanese"),
    ("ramen",         "Japanese"),
    ("tempura",       "Japanese"),
    ("tonkatsu",      "Japanese"),
    ("udon",          "Japanese"),
    ("soba",          "Japanese"),
    ("sake",          "Japanese"),
    # Korean
    ("korean",        "Korean"),
    # Latin American
    ("ceviche",       "Latin American"),
    ("peruvian",      "Latin American"),
    ("latin",         "Latin American"),
    # Mediterranean
    ("mediterranean", "Mediterranean"),
    ("falafel",       "Mediterranean"),
    ("hummus",        "Mediterranean"),
    # Mexican
    ("taqueria",      "Mexican"),
    ("cantina",       "Mexican"),
    ("burrito",       "Mexican"),
    ("tacos",         "Mexican"),           # "tacos" before "taco" — longer match first
    ("taco",          "Mexican"),
    ("mexican",       "Mexican"),
    # Seafood — "fish" is a known false-match risk
    ("seafood",       "Seafood"),
    ("oyster",        "Seafood"),
    ("lobster",       "Seafood"),
    ("fish",          "Seafood"),
    # Southeast Asian
    ("pho",           "Southeast Asian"),
    ("banh mi",       "Southeast Asian"),
    ("vietnamese",    "Southeast Asian"),
    ("thai",          "Southeast Asian"),
    # Spanish
    ("tapas",         "Spanish"),
    ("paella",        "Spanish"),
    ("spanish",       "Spanish"),
    # Steakhouse — "steakhouse" before "steak" to avoid partial-match ambiguity
    ("steakhouse",    "Steakhouse"),
    ("chophouse",     "Steakhouse"),
    ("steak",         "Steakhouse"),
    # Vegetarian
    ("vegan",         "Vegetarian"),
    ("vegetarian",    "Vegetarian"),
    ("plant",         "Vegetarian"),
]

WEBSITE_KEYWORDS_TO_CUISINE: list[tuple[str, str]] = [
    # African
    ("african",       "African"),
    # American
    ("bbq",           "American"),
    # Chinese
    ("chinese",       "Chinese"),
    # Creole/Cajun
    ("cajun",         "Creole/Cajun"),
    ("creole",        "Creole/Cajun"),
    ("nola",          "Creole/Cajun"),
    # French
    ("bistro",        "French"),
    ("french",        "French"),
    # Greek
    ("greek",         "Greek"),
    # Indian
    ("indian",        "Indian"),
    # Italian
    ("italian",       "Italian"),
    ("pasta",         "Italian"),
    ("pizza",         "Italian"),
    # Japanese
    ("izakaya",       "Japanese"),
    ("kaiseki",       "Japanese"),
    ("omakase",       "Japanese"),
    ("ramen",         "Japanese"),
    ("sushi",         "Japanese"),
    # Korean
    ("korean",        "Korean"),
    # Mediterranean
    ("mediterranean", "Mediterranean"),
    # Mexican
    ("mexican",       "Mexican"),
    ("taqueria",      "Mexican"),
    # Seafood
    ("seafood",       "Seafood"),
    # Southeast Asian
    ("thai",          "Southeast Asian"),
    ("vietnamese",    "Southeast Asian"),
    # Steakhouse
    ("steakhouse",    "Steakhouse"),
    ("steak",         "Steakhouse"),
    # Vegetarian
    ("vegan",         "Vegetarian"),
    ("vegetarian",    "Vegetarian"),
]


# ── Romantic scoring ──────────────────────────────────────────────────────────
#
# Six independent signals are combined as a weighted sum scaled to 0–10.
# Weights reflect signal reliability and specificity to romantic context;
# they must sum to 1.0. FANCY_PRIMARY_TYPES, ROMANTIC_NAME_KEYWORDS_*, and
# CUISINE_ROMANCE_SCORE define the lookup domains for each signal.

ROMANTIC_SCORE_WEIGHTS: dict[str, float] = {
    "price_point":  0.30,   # strongest single proxy — price directly filters date-night venues
    "address":      0.25,   # prestige neighbourhood removes ambiguity that price alone cannot
    "fancy_type":   0.20,   # Google's fine-dining taxonomy adds structural confirmation
    "name_keyword": 0.10,   # French branding and tasting-menu terms signal deliberate romance
    "cuisine":      0.10,   # cuisine family carries affinity beyond primary_type alone
    "has_website":  0.05,   # weakest signal — tie-breaker for establishment quality
}

FANCY_PRIMARY_TYPES: set[str] = {
    "californian_restaurant",
    "fine_dining_restaurant",
    "french_restaurant",
    "greek_restaurant",
    "italian_restaurant",
    "japanese_restaurant",
    "kaiseki_restaurant",
    "mediterranean_restaurant",
    "new_american_restaurant",
    "seafood_restaurant",
    "spanish_restaurant",
    "steak_house",
    "sushi_restaurant",
}

# HIGH keywords score 1.0; MEDIUM score 0.5. The scoring function takes the max
# across all matches — presence is measured, not frequency.
ROMANTIC_NAME_KEYWORDS_HIGH: list[str] = [
    "atelier",
    "chateau",
    "château",
    "chez",
    "garden",
    "hideaway",
    "kaiseki",
    "l'",
    "la ",
    "le ",
    "maison",
    "manor",
    "omakase",
    "secret",
    "terrace",
    "villa",
]

ROMANTIC_NAME_KEYWORDS_MEDIUM: list[str] = [
    "alley",
    "bistro",
    "bloom",
    "brasserie",
    "cellar",
    "flora",
    "grove",
    "lounge",
    "olive",
    "parlor",
    "petal",
    "rose",
]

# Scores reflect cultural association with special-occasion dining, not cuisine
# quality.  French and Fine Dining anchor the top; non-food venue types anchor
# the bottom.  "American" at 0.30 covers casual registers (diner, gastropub).
CUISINE_ROMANCE_SCORE: dict[str, float] = {
    "African":        0.40,
    "American":       0.30,
    "Asian Fusion":   0.65,
    "Bar/Lounge":     0.30,
    "Café":           0.25,
    "Chinese":        0.45,
    "Contemporary":   0.60,
    "Creole/Cajun":   0.45,
    "European":       0.55,
    "Fine Dining":    1.00,
    "French":         1.00,
    "Greek":          0.70,
    "Hotel/Venue":    0.20,
    "Indian":         0.40,
    "Italian":        0.85,
    "Japanese":       0.90,
    "Korean":         0.50,
    "Latin American": 0.55,
    "Mediterranean":  0.80,
    "Mexican":        0.35,
    "Other":          0.10,
    "Seafood":        0.75,
    "Southeast Asian":0.45,
    "Spanish":        0.75,
    "Steakhouse":     0.70,
    "Vegetarian":     0.40,
    "Venue":          0.15,
}

# Tokens are grouped by city/region; a match is binary (1.0 / 0.0) because
# there is no reliable basis for ranking prestige within the list.
HIGH_TICKET_ADDRESS_TOKENS: list[str] = [
    # Manhattan prestige corridors
    "park avenue",
    "park ave",
    "fifth avenue",
    "5th ave",
    "madison avenue",
    "madison ave",
    "central park",
    "rockefeller",
    "wall st",
    "tribeca",
    # NYC landmark properties
    "waldorf",
    "plaza",
    "trump",
    "lotte",
    "mercer",
    "1 hotel",
    # Los Angeles / Beverly Hills
    "rodeo dr",
    "rodeo drive",
    "beverly hills",
    "west hollywood",
    "sunset blvd",
    "bel air",
    "santa monica blvd",
    # Washington DC
    "pennsylvania ave",
    "k street",
    "georgetown",
    # Las Vegas luxury resorts
    "bellagio",
    "aria",
    "mgm grand",
    "mgm national",
    "mandalay bay",
    "venetian",
    "four seasons",
    "peninsula",
    "ritz",
    "wynn",
    "encore",
    # San Francisco prestige districts
    "nob hill",
    "pacific heights",
    "union square",
    # Cross-city luxury signals
    "resort & casino",
    "resort and casino",
    "luxury",
]


# ── I/O ───────────────────────────────────────────────────────────────────────

INPUT_FILE:        str = "restaurants.csv"
OUTPUT_DIR:        str = "output"
CLEANED_FILENAME:  str = "restaurants_clean.csv"
ENRICHED_FILENAME: str = "restaurants_enriched.csv"
