"""Central configuration for the Cal Sans build pipeline.
"""

# ── Paths ─────────────────────────────────────────────────────────────────
SOURCE_PATH        = "sources/CalSans.glyphspackage"
OUTPUT_PATH        = "sources/CalSans_READY.glyphspackage"
OUTPUT_PATH_STATIC = "sources/CalSans_READY_static.glyphspackage"
BUILD_DIR    = "scripts/temp"
RELEASE_DIR  = "fonts"
BUILD_ITALIC = False  # True → 384 styles (roman + italic); False → 192 roman


# ── Static style manifest (scripts/lib/manifest.py) ─────────────────────
# (id, name-label) tokens for each axis, in the order they combine into style names.
STATIC_GEOM_TOKENS = [("a11y", "A11y"), ("ui", "UI"), ("base", ""), ("geo", "Geo")]
STATIC_OPSZ_TOKENS = [("display", ""), ("text", "Text"), ("micro", "Micro")]
STATIC_WGHT_TOKENS = [("regular", "Regular"), ("medium", "Medium"), ("semibold", "SemiBold"), ("bold", "Bold")]
STATIC_YTAS_TOKENS = [("base", ""), ("tall", "Tall")]
STATIC_SHRP_TOKENS = [("base", ""), ("sharp", "Sharp")]
STATIC_ITAL_TOKENS = [("roman", ""), ("italic", "Italic")]

# Axis user-space coordinates for fontTools instancer, keyed by the same ids above.
STATIC_AXIS_VALUES = {
    "geom":  {"a11y": 0,   "ui": 25,  "base": 50,  "geo": 100},
    "opsz":  {"display": 32, "text": 10, "micro": 8},
    "wght":  {"regular": 400, "medium": 500, "semibold": 600, "bold": 700},
    "ytas":  {"base": 720, "tall": 800},
    "shrp":  {"base": 0,   "sharp": 100},
    # The font's italic axis is `ital` (0–1), NOT a slnt degree axis. Roman=0, Italic=1.
    "ital":  {"roman": 0,  "italic": 1},
}


# ── Release packaging (step5_release) ────
RELEASE_PACKAGE_PREFIX = "calsans"
PER_GEOM_PACKAGE_IDS = ("a11y", "ui", "base", "geo")


# ── Magic build / avar2 ───────
MAGIC_FAMILY_NAME = "Cal Sans Magic"
MAGIC_STYLE_NAME  = "Regular"
# (input opsz, output YTAS) calibration points for the avar2 axis mapping
MAGIC_OPSZ_TO_YTAS = [(16.0, 720.0), (10.0, 750.0), (8.0, 800.0)]


# ── Expected source shape (pre-flight validation) ────────────────────────
EXPECTED_AXES         = ["opsz", "GEOM", "wght", "YTAS", "SHRP", "ital"]
EXPECTED_MASTER_COUNT = 8
EXPECTED_OPSZ_VALUES  = [10, 32]


# ── Dialect translation: Glyphs app → feaLib (prepare_for_fontmake) ──────
RCLT_FEATURE_TAG       = "rclt"
VARIATIONS_PREFIX_NAME = "VARIATIONS"
ALL_CLASS_NAME         = "All"
RENAME_GLYPHS_PARAM    = "Rename Glyphs"
CV_PARAM_PLATFORM_LANG = (3, 1, 0x0409)  # Windows, English (US) — used in cvParameters rewrite


# ── GSUB FeatureVariations merge (merge_gsub_feature_variations) ─────────
GEOM_AXIS_TAG = "GEOM"


# ── Shipping axis defaults (shift_axis_defaults / build_magic.shift_defaults) ─
# Pinned post-compile so the shipped default coordinate differs from the
# masters' authored default while keeping the full axis range available.
SHIPPING_DEFAULTS = {"opsz": 14, "GEOM": 25}


# ── YTAS accent-rise  ─────────────────────────────────────────────────────
# Lowercase base glyphs whose stacked top-marks (acute, grave, circumflex,
# dieresis, ring, dot-above, etc.) should rise with the YTAS axis — "the way
# i and j were, only moving the top anchor". idotless/jdotless from the
# issue's list are dotlessi/uni0237 in this font.
YTAS_ACCENT_RISE_BASES = (
    "a", "a.alt", "a.rcltA11y", "a.rcltBase", "ae", "ae.rcltBase", "c", "c.rcltGeo", "dotlessi", "e",
    "g", "g.rcltA11y", "m", "n", "o", "oe", "p", "r", "s", "u", "u.rcltGeo", "uhorn", "uhorn.rcltGeo",
    "uni0237", "uni0237.rcltBase", "uni0237.rcltGeo", "w", "y", "y.rcltBase", "y.rcltGeo", "z",
)
YTAS_ACCENT_RISE_DY = 30   # vertical drift (font units) at YTAS=800
ITALIC_SLANT_DEGREES = 9.5  # used to derive the italic horizontal compensation (dx = dy·tan(angle))


