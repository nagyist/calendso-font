import re

from tqdm import tqdm

from scripts import config


def _format_names(names, verbose):
    """Render a glyph/instance name list — full list when verbose, else just
    the first 4 names plus a "(N more)" hint, per issue #17 feedback that the
    full lists made step 4's output too noisy to read by default."""
    if verbose or len(names) <= 4:
        return str(names)
    shown = ", ".join(repr(n) for n in names[:4])
    return f"[{shown}, ... ({len(names) - 4} more)]"


def patch_smart_components(font):
    """Diagnostic only — smart component pole mappings are defined in the source.
    Filling in missing axes causes duplicate variation model locations, so we leave them alone."""
    smart_glyphs = [g for g in font.glyphs if g.smartComponentAxes]
    print(f"   Found {len(smart_glyphs)} smart component glyph(s) — no patching applied")


def remove_non_exported_glyphs(font, verbose=False):
    """Remove non-exported glyphs not needed by any exported glyph.
    Walks component references transitively so glyphs only used by other
    non-exported glyphs are also removed."""
    # Collect all component references in the font for reporting
    referenced_by = {}
    for glyph in tqdm(font.glyphs, desc="   ↳ Scanning components", leave=False):
        for layer in glyph.layers:
            for component in layer.components:
                referenced_by.setdefault(component.name, set()).add(glyph.name)

    # Walk transitively from exported glyphs to find everything they need
    needed = set()
    to_check = [g.name for g in font.glyphs if g.export]
    while to_check:
        name = to_check.pop()
        if name in needed:
            continue
        needed.add(name)
        glyph = font.glyphs[name]
        if glyph:
            for layer in glyph.layers:
                for component in layer.components:
                    if component.name not in needed:
                        to_check.append(component.name)

    names = [g.name for g in font.glyphs if not g.export and g.name not in needed]
    kept = [g.name for g in font.glyphs if not g.export and g.name in needed]

    for name in names:
        del font.glyphs[name]
    if names:
        print(f"   ✅ Removed {len(names)} non-exported glyphs from build: {_format_names(sorted(names), verbose)}")
    if kept:
        print(f"   ℹ️  Kept {len(kept)} non-exported glyph(s) needed by exported glyphs", end="")
        if verbose:
            print(":")
            for name in kept:
                users = sorted(referenced_by.get(name, []))
                print(f"      {name} ← used by: {', '.join(users)}")
        else:
            print()


def prepare_for_fontmake(font, verbose=False):
    """Swap Glyphs dialect → feaLib dialect:
    - rclt: strip Glyphs-proprietary 'condition' lines; lookup bodies stay
    - VARIATIONS prefix: enable (now has correct top-level variation rclt syntax)
    """
    # REMOVE condition-based rclt features entirely (not just disable). Disabling leaves an
    # empty `feature rclt {}` shell in the compiled features.fea, which registers rclt under
    # DFLT only — so the VARIATIONS variation blocks attach to a DFLT-only feature and never
    # apply to latn text. Removing the shell lets feaLib auto-register rclt under all
    # languagesystems (DFLT + latn), matching the known-good exemplar.
    to_remove = [f for f in font.features
                 if getattr(f, "name", "").lower() == config.RCLT_FEATURE_TAG and re.search(r'\s*condition\s', f.code)]
    for f in to_remove:
        font.features.remove(f)
    print(f"   ✅ Removed {len(to_remove)} condition-based {config.RCLT_FEATURE_TAG} feature(s) — VARIATIONS prefix handles substitution")

    # Convert Glyphs shorthand cvParameters to AFDKO/feaLib format:
    #   cvParameters { FeatUILabelNameID { name "Label"; }; };
    # → cvParameters { FeatUILabelNameID { name 3 1 0x0409 "Label"; }; };
    # Also strip #ifdef VARIABLE ... #endif blocks (Glyphs preprocessor syntax feaLib can't parse).
    def _fix_cv_params(code):
        platform, lang, langid = config.CV_PARAM_PLATFORM_LANG
        code = re.sub(
            r'cvParameters\s*\{\s*FeatUILabelNameID\s*\{\s*name\s*"([^"]+)"\s*;\s*\}\s*;\s*\}',
            lambda m: (
                f'cvParameters {{\n'
                f'    FeatUILabelNameID {{\n'
                f'        name {platform} {lang} {hex(langid)} "{m.group(1)}";\n'
                f'    }};\n'
                f'}}'
            ),
            code
        )
        code = re.sub(r'#ifdef\s+VARIABLE.*?#endif', '', code, flags=re.DOTALL)
        return code

    fixed = 0
    for feat in font.features:
        if feat.disabled:
            continue
        new_code = _fix_cv_params(feat.code)
        if new_code != feat.code:
            feat.code = new_code
            fixed += 1
    print(f"   ✅ Fixed cvParameters + stripped #ifdef VARIABLE blocks in {fixed} feature(s)")

    # Filter the auto-generated All class to exported glyphs only.
    # SkipExportGlyphsIFilter removes non-exported glyphs from the glyph set
    # but the compiled @All class still references them, causing feature errors.
    exported = {g.name for g in font.glyphs if g.export}
    for cls in getattr(font, "classes", []):
        if cls.name == config.ALL_CLASS_NAME:
            before = len(cls.code.split())
            cls.code = " ".join(n for n in cls.code.split() if n in exported)
            after = len(cls.code.split())
            if before != after:
                print(f"   ✅ @{config.ALL_CLASS_NAME} class filtered ({before - after} non-exported glyphs removed, {after} remaining)")
            else:
                print(f"   @{config.ALL_CLASS_NAME} class unchanged — all {before} glyphs are exported")

    # Remove "Replace Glyph" instance parameters — rclt feature handles substitution,
    # and Replace Glyph causes cyclical component references when alternates use base as component.
    removed = 0
    affected = []
    for instance in getattr(font, "instances", []):
        if any(p.name == config.RENAME_GLYPHS_PARAM for p in instance.customParameters):
            affected.append(instance.name)
        params = [p for p in instance.customParameters if p.name != config.RENAME_GLYPHS_PARAM]
        if len(params) != len(instance.customParameters):
            removed += len(instance.customParameters) - len(params)
            instance.customParameters = params
    if removed:
        print(f"   ✅ Removed {config.RENAME_GLYPHS_PARAM} from {removed} instance(s): {_format_names(affected, verbose)}")
    else:
        print(f"   No {config.RENAME_GLYPHS_PARAM} parameters found in any instance")

    # Enable the VARIATIONS prefix. It is authored in correct top-level feaLib syntax
    # (variation rclt cond_X { <direct subs> } rclt;) but kept disabled in source so the
    # Glyphs app — which can't compile conditionset syntax — ignores it. fontmake needs it on.
    enabled = 0
    for prefix in getattr(font, "featurePrefixes", []):
        if getattr(prefix, "name", "") == config.VARIATIONS_PREFIX_NAME:
            prefix.disabled = False
            enabled += 1
    print(f"   ✅ Enabled {config.VARIATIONS_PREFIX_NAME} prefix ({enabled})")

    # Reorder prefixes so languagesystem declarations come FIRST. feaLib only registers a
    # feature under languagesystems declared BEFORE it; the VARIATIONS prefix (variation rclt
    # blocks) was emitted before the Languagesystems prefix, so rclt registered under DFLT
    # only and never applied to latn (Latin) text. Putting languagesystems first fixes it.
    prefixes = list(getattr(font, "featurePrefixes", []))
    lang = [p for p in prefixes if "languagesystem" in (getattr(p, "code", "") or "")]
    rest = [p for p in prefixes if "languagesystem" not in (getattr(p, "code", "") or "")]
    if lang and prefixes != lang + rest:
        font.featurePrefixes = lang + rest
        print(f"   ✅ Moved {len(lang)} languagesystem prefix(es) before variation blocks")
