import shutil
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont
from scripts.lib.manifest import all_styles
from scripts.lib.build_magic import build_magic
from scripts import config

_PFX = config.RELEASE_PACKAGE_PREFIX


# ── Helpers ───────────────────────────────────────────────────────────────────

def _compress_dir(dir_path: Path):
    for ttf in sorted(dir_path.glob("*.ttf")):
        font = TTFont(str(ttf))
        font.flavor = "woff2"
        font.save(str(ttf.with_suffix(".woff2")))


def _copy_pair(src_dir: Path, filename: str, dest_dir: Path, woff2: bool = True) -> bool:
    """Copy TTF (+ WOFF2 unless woff2=False) to dest_dir. Returns True if TTF was found."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(filename).stem
    found = False
    exts = (".ttf", ".woff2") if woff2 else (".ttf",)
    for ext in exts:
        src = src_dir / (stem + ext)
        if src.exists():
            shutil.copy2(src, dest_dir / src.name)
            if ext == ".ttf":
                found = True
    return found


def _strip_ss_cv(src_ttf: Path, dest_dir: Path, woff2: bool = True):
    """Write TTF (+ WOFF2 unless woff2=False) to dest_dir with ss/cv stylistic-set/
    character-variant features—and their now-unreferenced alternate glyphs—subset out."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    font = TTFont(str(src_ttf))

    feature_tags = set()
    for tag in ("GSUB", "GPOS"):
        if tag in font:
            feature_tags.update(fr.FeatureTag for fr in font[tag].table.FeatureList.FeatureRecord)
    # aalt ("access all alternates") points directly at ss/cv glyphs, so it
    # must go too or those glyphs survive subsetting via its closure
    keep_features = [t for t in feature_tags if t[:2].lower() not in ("ss", "cv") and t != "aalt"]

    options = subset.Options()
    options.layout_features = keep_features
    options.glyph_names = True
    options.notdef_outline = True
    options.recalc_bounds = True
    options.recalc_timestamp = False

    subsetter = subset.Subsetter(options=options)
    subsetter.populate(unicodes=font.getBestCmap().keys())
    subsetter.subset(font)

    dest_ttf = dest_dir / src_ttf.name
    font.save(str(dest_ttf))
    if woff2:
        font.flavor = "woff2"
        font.save(str(dest_ttf.with_suffix(".woff2")))


def _report(pkg_dir: Path, label: str):
    count = sum(1 for p in pkg_dir.rglob("*") if p.is_file()) if pkg_dir.exists() else 0
    print(f"   ✅ {label} ({count} files)")


# ── Public API ────────────────────────────────────────────────────────────────

def compress_build_outputs(build_dir: str):
    """Compress all TTFs in scripts/temp/variable and scripts/temp/static to WOFF2."""
    build_path = Path(build_dir)
    print("🗜  Compressing TTFs to WOFF2...")
    for sub in ("variable", "static"):
        d = build_path / sub
        if d.exists():
            _compress_dir(d)


def build_release_folders(build_dir: str, output_dir: str, build_italic: bool = False):
    build_path = Path(build_dir)
    out_path   = Path(output_dir)
    var_dir    = build_path / "variable"
    static_dir = build_path / "static"

    styles = all_styles(build_italic)

    if out_path.exists():
        shutil.rmtree(out_path)
    out_path.mkdir()

    print("📦 Building release folders...")
    missing = 0

    def copy_styles(subset: list, dest: Path, woff2: bool = True):
        nonlocal missing
        for s in subset:
            if not _copy_pair(static_dir, s["filename"], dest, woff2=woff2):
                missing += 1

    # ── Variable packages ─────────────────────────────────────────────────────

    pkg = out_path / f"{_PFX}-var-full"
    for ttf in sorted(var_dir.glob("*.ttf")):
        _copy_pair(var_dir, ttf.name, pkg)
    _report(pkg, f"{_PFX}-var-full")

    # var-magic: avar2 build — YTAS follows opsz, axis hidden from users
    pkg = out_path / f"{_PFX}-var-magic"
    pkg.mkdir(parents=True, exist_ok=True)
    for ttf in sorted(var_dir.glob("*.ttf")):
        build_magic(str(ttf), str(pkg))
    _report(pkg, f"{_PFX}-var-magic")

    for pkg_name in (f"{_PFX}-cossui", f"{_PFX}-gf-api"):
        pkg = out_path / pkg_name
        for ttf in sorted(var_dir.glob("*.ttf")):
            _strip_ss_cv(ttf, pkg)
        _report(pkg, pkg_name)

    # ── Static packages ───────────────────────────────────────────────────────

    # static-full: every static instance (192 roman, 384 with italic),
    # split into ttf/ and woff2/ subfolders.
    pkg = out_path / f"{_PFX}-static-full"
    ttf_dir, woff2_dir = pkg / "ttf", pkg / "woff2"
    ttf_dir.mkdir(parents=True, exist_ok=True)
    woff2_dir.mkdir(parents=True, exist_ok=True)
    for s in styles:
        stem = Path(s["filename"]).stem
        src_ttf, src_woff2 = static_dir / f"{stem}.ttf", static_dir / f"{stem}.woff2"
        if src_ttf.exists():
            shutil.copy2(src_ttf, ttf_dir / src_ttf.name)
        else:
            missing += 1
        if src_woff2.exists():
            shutil.copy2(src_woff2, woff2_dir / src_woff2.name)
    _report(pkg, f"{_PFX}-static-full")

    # per-GEOM: base YTAS/SHRP only → 12 roman now, 24 when italic is added
    for geom_id in config.PER_GEOM_PACKAGE_IDS:
        subset = [s for s in styles if s["geom"] == geom_id and s["ytas"] == "base" and s["shrp"] == "base"]
        pkg = out_path / f"{_PFX}-static-{geom_id}"
        copy_styles(subset, pkg)
        _report(pkg, f"{_PFX}-static-{geom_id}")

    # Cal Sans (Display/Base) + Cal Sans UI Text, base YTAS/SHRP, all 4 weights,
    # roman + italic → 8 roman / 16 with italic. Shared by essentials + gf-workspace.
    def is_text_family(s):
        if s["ytas"] != "base" or s["shrp"] != "base":
            return False
        return ((s["opsz"] == "display" and s["geom"] == "base") or
                (s["opsz"] == "text" and s["geom"] == "ui"))

    text_family_styles = [s for s in styles if is_text_family(s)]

    # static-essentials: the text family, ss/cv kept, TTF-only.
    pkg = out_path / f"{_PFX}-static-essentials"
    copy_styles(text_family_styles, pkg, woff2=False)
    _report(pkg, f"{_PFX}-static-essentials")

    # gf-workspace: same family for Google Fonts onboarding, but ss/cv (+ aalt and
    # their alternate glyphs) stripped like cossui/gf-api; TTF-only.
    pkg = out_path / f"{_PFX}-gf-workspace"
    pkg.mkdir(parents=True, exist_ok=True)
    for s in text_family_styles:
        src = static_dir / s["filename"]
        if src.exists():
            _strip_ss_cv(src, pkg, woff2=False)
        else:
            missing += 1
    _report(pkg, f"{_PFX}-gf-workspace")

    if not build_italic:
        print("⚠️  Built without italics (BUILD_ITALIC=False) — Cal Sans Display/Base "
              "italic styles are missing from calsans-static-essentials and calsans-gf-workspace")

    if missing:
        print(f"\n⚠️  {missing} expected static files not found in {static_dir}/")
        print(f"   Run fontmake first, or check style_name_to_filename() in scripts/manifest.py")

    print(f"\n✅ Release folders written to {output_dir}/")
