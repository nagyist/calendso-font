import math
import os
import re
import shutil
import subprocess
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

from scripts import config


def merge_gsub_feature_variations(ttf_path: str):
    """feaLib emits one FeatureVariation record per variation block, evaluated
    first-match-wins. Overlapping GEOM ranges mean only the first matching record
    fires. This rebuilds the table into NON-OVERLAPPING GEOM bands where each record
    carries ALL substitutions that should apply in that band (what the Glyphs app does
    internally). Without this, glyphs drop back to default when crossing a band edge."""
    font = TTFont(ttf_path)
    gsub = font["GSUB"].table
    fvar = font["fvar"]
    if not getattr(gsub, "FeatureVariations", None):
        return
    geom_idx = next(i for i, a in enumerate(fvar.axes) if a.axisTag == config.GEOM_AXIS_TAG)
    rclt_idx = next((i for i, fr in enumerate(gsub.FeatureList.FeatureRecord)
                     if fr.FeatureTag == config.RCLT_FEATURE_TAG), None)
    if rclt_idx is None:
        return

    # Parse existing records into (geom_min, geom_max, other_conditions, lookups)
    parsed = []
    for r in gsub.FeatureVariations.FeatureVariationRecord:
        gmin = gmax = None
        other = []
        for c in r.ConditionSet.ConditionTable:
            if c.AxisIndex == geom_idx:
                gmin, gmax = c.FilterRangeMinValue, c.FilterRangeMaxValue
            else:
                other.append(c)
        lookups = []
        for s in r.FeatureTableSubstitution.SubstitutionRecord:
            if s.FeatureIndex == rclt_idx:
                lookups = sorted(s.Feature.LookupListIndex)
        if gmin is not None:
            parsed.append((gmin, gmax, other, lookups))

    pts = sorted({v for gmin, gmax, _, _ in parsed for v in (gmin, gmax)})

    def make_cond(lo, hi):
        c = otTables.ConditionTable()
        c.Format = 1
        c.AxisIndex = geom_idx
        c.FilterRangeMinValue = lo
        c.FilterRangeMaxValue = hi
        return c

    def make_combined_lookup(lk_list):
        # Merge multiple SingleSubst lookups into one so HarfBuzz applies all mappings
        # (it only applies the first lookup referenced by a FeatureVariations feature).
        combined = {}
        for lk_idx in lk_list:
            lk = gsub.LookupList.Lookup[lk_idx]
            lk.ensureDecompiled(recurse=True)
            for st in lk.SubTable:
                if hasattr(st, "mapping"):
                    combined.update(st.mapping)
        st = otTables.SingleSubst()
        st.mapping = combined
        lk = otTables.Lookup()
        lk.LookupType = 1
        lk.LookupFlag = 0
        lk.SubTable = [st]
        lk.SubTableCount = 1
        lk.MarkFilterSet = None
        gsub.LookupList.Lookup.append(lk)
        return len(gsub.LookupList.Lookup) - 1

    def make_record(conds, lk_list):
        feat = otTables.Feature()
        feat.LookupListIndex = [make_combined_lookup(lk_list)]
        feat.LookupCount = 1
        feat.FeatureParams = None
        sub = otTables.FeatureTableSubstitutionRecord()
        sub.FeatureIndex = rclt_idx
        sub.Feature = feat
        fts = otTables.FeatureTableSubstitution()
        fts.Version = 0x00010000
        fts.SubstitutionRecord = [sub]
        fts.SubstitutionCount = 1
        cs = otTables.ConditionSet()
        cs.ConditionTable = conds
        cs.ConditionCount = len(conds)
        rec = otTables.FeatureVariationRecord()
        rec.ConditionSet = cs
        rec.FeatureTableSubstitution = fts
        return rec

    multi_records = []
    pure_records = []
    for i in range(len(pts) - 1):
        lo, hi = pts[i], pts[i + 1]
        mid = (lo + hi) / 2
        pure_lks = sorted({lk for gmin, gmax, other, lks in parsed
                           if not other and gmin <= mid <= gmax for lk in lks})
        if pure_lks:
            pure_records.append(make_record([make_cond(lo, hi)], pure_lks))
        for gmin, gmax, other, lks in parsed:
            if not other or not (gmin <= mid <= gmax):
                continue
            multi_records.append(make_record([make_cond(lo, hi)] + other,
                                             sorted(set(lks + pure_lks))))

    new_records = multi_records + pure_records
    gsub.FeatureVariations.FeatureVariationRecord = new_records
    gsub.FeatureVariations.FeatureVariationCount = len(new_records)
    font.save(ttf_path)
    print(f"   ✅ GSUB FeatureVariations merged: {len(parsed)} → {len(new_records)} non-overlapping records")


def shift_axis_defaults(ttf_path: str):
    """Pin the shipping defaults at opsz=14, GEOM=25 while keeping full axis ranges.
    instancer re-normalizes gvar/avar/GSUB FeatureVariations to the new default, so the
    conditional GEOM substitutions keep firing correctly."""
    from fontTools.varLib.instancer import instantiateVariableFont
    font = TTFont(ttf_path)
    fvar = font["fvar"]
    coords = {}
    for tag, default in config.SHIPPING_DEFAULTS.items():
        axis = next(a for a in fvar.axes if a.axisTag == tag)
        coords[tag] = (axis.minValue, default, axis.maxValue)
    instantiateVariableFont(font, coords, inplace=True, optimize=True)
    font.save(ttf_path)
    shifted = ", ".join(f"{tag}→{default}" for tag, default in config.SHIPPING_DEFAULTS.items())
    print(f"   ✅ Axis defaults shifted: {shifted}")


# These top-marks drift by YTAS_ACCENT_RISE_DY from their resting position at
# YTAS=800 (a gentle nudge, not a full ascender-height swing). The italic
# compensation keeps the shift aligned along the slant (dx = dy·tan(angle)).
YTAS_ACCENT_RISE_BASES = config.YTAS_ACCENT_RISE_BASES
YTAS_ACCENT_RISE_DY = config.YTAS_ACCENT_RISE_DY
YTAS_ACCENT_RISE_ITAL_DX = round(YTAS_ACCENT_RISE_DY * math.tan(math.radians(config.ITALIC_SLANT_DEGREES)))


def _is_top_mark(glyph_name: str) -> bool:
    """True if glyph_name is (or is built from) combining mark(s) that sit above
    their base — Unicode combining class 230: acute/grave/circumflex/dieresis/
    ring/caron/breve/macron/dot-above/hook-above/etc., including combo glyphs
    like uni03020309 (circumflex+hook-above) or uni006A0301 (j+acute) — as
    opposed to below-base marks like cedilla, ogonek, or dot-below, which
    shouldn't move with the "top anchor" YTAS rise."""
    import unicodedata
    from fontTools.agl import AGL2UV

    base = glyph_name.split(".")[0]
    if base in AGL2UV:
        cps = [AGL2UV[base]]
    else:
        m = re.fullmatch(r"uni((?:[0-9A-Fa-f]{4})+)", base)
        if m:
            hexstr = m.group(1)
            cps = [int(hexstr[i:i + 4], 16) for i in range(0, len(hexstr), 4)]
        else:
            m = re.fullmatch(r"u([0-9A-Fa-f]{4,6})", base)
            cps = [int(m.group(1), 16)] if m else []

    cccs = [c for c in (unicodedata.combining(chr(cp)) for cp in cps) if c != 0]
    return bool(cccs) and all(c == 230 for c in cccs)


def add_ytas_accent_rise(ttf_path: str):
    """Post-compile gvar pass (issues #10 & #12): makes the stacked top-marks
    (acute, grave, circumflex, dieresis, dot-above, etc.) on the targeted base
    letters — including the i/j dots — drift +30 with the YTAS axis, mirroring
    "the top anchor" rise the source can't express directly (anchor edits on
    brace layers get discarded by glyphsLib — see VISION.md §6). Only above-base
    marks (combining class 230) are shifted — cedilla/ogonek/dot-below stay put,
    since those don't sit on the "top anchor"."""
    from fontTools.ttLib.tables.TupleVariation import TupleVariation

    font = TTFont(ttf_path)
    glyf, gvar = font["glyf"], font["gvar"]

    updated = 0
    for name in glyf.keys():
        g = glyf[name]
        if not g.isComposite():
            continue
        comps = g.components
        if comps[0].glyphName not in YTAS_ACCENT_RISE_BASES:
            continue
        mark_indices = [i for i, c in enumerate(comps) if i > 0 and _is_top_mark(c.glyphName)]
        if not mark_indices:
            continue

        n_deltas = len(comps) + 4  # one (x,y) delta per component, then 4 phantom points

        def make_coords(dx, dy):
            coords = [(0, 0)] * n_deltas
            for i in mark_indices:
                coords[i] = (dx, dy)
            return coords

        variations = gvar.variations.setdefault(name, [])
        variations.append(TupleVariation({"YTAS": (0.0, 1.0, 1.0)}, make_coords(0, YTAS_ACCENT_RISE_DY)))
        variations.append(TupleVariation(
            {"YTAS": (0.0, 1.0, 1.0), "ital": (0.0, 1.0, 1.0)},
            make_coords(YTAS_ACCENT_RISE_ITAL_DX, 0),
        ))
        updated += 1

    font.save(ttf_path)
    print(f"   ✅ YTAS accent-rise: updated {updated} glyph(s) so top-marks drift +{YTAS_ACCENT_RISE_DY}u with ascender height")


def run_fontmake_variable(ready_path: str, build_dir: str):
    # Start clean so stale outputs from a prior run (e.g. an old output name)
    # don't get re-globbed and duplicated through post-processing/packaging.
    shutil.rmtree(f"{build_dir}/variable", ignore_errors=True)
    os.makedirs(f"{build_dir}/variable", exist_ok=True)

    print("🔨 Building variable font...")
    result = subprocess.run(
        ["fontmake", "-g", ready_path, "-o", "variable",
         "--output-dir", f"{build_dir}/variable",
         "--master-dir", f"{build_dir}/master_ufo",
         "--filter", "FlattenComponentsFilter",
         "--debug-feature-file", f"{build_dir}/debug_features.fea"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise subprocess.CalledProcessError(result.returncode, result.args)
    print("   ✅ Variable font built")

    for ttf in Path(f"{build_dir}/variable").glob("*.ttf"):
        merge_gsub_feature_variations(str(ttf))
        add_ytas_accent_rise(str(ttf))
        shift_axis_defaults(str(ttf))
