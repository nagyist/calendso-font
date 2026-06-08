import sys
import os
import time
from pathlib import Path
from contextlib import contextmanager
import glyphsLib

from scripts import config
from scripts.config import (
    SOURCE_PATH, OUTPUT_PATH, OUTPUT_PATH_STATIC, BUILD_DIR, RELEASE_DIR, BUILD_ITALIC,
)
from scripts.lib.metrics import export_metrics
from scripts.lib.validate import validate_font_setup
from scripts.lib.prepare import patch_smart_components, remove_non_exported_glyphs, prepare_for_fontmake
from scripts.lib.compile_variable import run_fontmake_variable
from scripts.lib.instance_statics import run_instancer_statics
from scripts.lib.release import compress_build_outputs, build_release_folders


# ── Build step progress ───────────────────────────────────────────────────────
_STEP = {"n": 0, "total": 0}

@contextmanager
def step(label):
    """Print a numbered, timed step header around a build phase."""
    _STEP["n"] += 1
    print(f"\n▶ [{_STEP['n']}/{_STEP['total']}] {label}")
    t0 = time.time()
    yield
    print(f"   ⏱  {time.time() - t0:.1f}s")


class _Ctx:
    """Carries state (the in-memory font, compiled paths, run options) between stages."""
    def __init__(self, build_italic=BUILD_ITALIC, verbose=False):
        self.font = None
        self.var_ttf = None
        self.build_italic = build_italic
        self.verbose = verbose


def stage_metrics(ctx):
    export_metrics(SOURCE_PATH)


def stage_load(ctx):
    ctx.font = glyphsLib.load(SOURCE_PATH)
    ctx.font.filepath = SOURCE_PATH


def stage_validate(ctx):
    validate_font_setup(ctx.font)


def stage_prepare(ctx):
    patch_smart_components(ctx.font)
    remove_non_exported_glyphs(ctx.font, verbose=ctx.verbose)
    prepare_for_fontmake(ctx.font, verbose=ctx.verbose)


def stage_save_sources(ctx):
    font = ctx.font
    print(f"💾 Saving to {OUTPUT_PATH}...")
    font.save(OUTPUT_PATH)
    os.makedirs(BUILD_DIR, exist_ok=True)
    fea_path = os.path.join(BUILD_DIR, "compiled_features_debug.fea")
    with open(fea_path, "w") as f:
        for prefix in getattr(font, "featurePrefixes", []):
            if not prefix.disabled:
                f.write(f"# PREFIX: {prefix.name}\n{prefix.code}\n\n")
        for feat in getattr(font, "features", []):
            if not feat.disabled:
                f.write(f"# FEATURE: {feat.name}\n{feat.code}\n\n")
    print(f"   📄 Feature code dumped to {fea_path}")

    for p in getattr(font, "featurePrefixes", []):
        if p.name == config.VARIATIONS_PREFIX_NAME:
            p.disabled = True
    font.save(OUTPUT_PATH_STATIC)
    for p in getattr(font, "featurePrefixes", []):
        if p.name == config.VARIATIONS_PREFIX_NAME:
            p.disabled = False


def stage_compile_variable(ctx):
    run_fontmake_variable(OUTPUT_PATH, BUILD_DIR)
    ctx.var_ttf = sorted(Path(f"{BUILD_DIR}/variable").glob("*.ttf"))[0]


def stage_instance_statics(ctx):
    run_instancer_statics(str(ctx.var_ttf), BUILD_DIR, build_italic=ctx.build_italic)


def stage_compress(ctx):
    compress_build_outputs(BUILD_DIR)


def stage_package(ctx):
    build_release_folders(BUILD_DIR, RELEASE_DIR, build_italic=ctx.build_italic)


# Ordered (name, function, step-header) — the subset a runner can select from.
STAGES = [
    ("metrics",          stage_metrics,          "Extracting metrics"),
    ("load",             stage_load,             "Loading source (glyphsLib)"),
    ("validate",         stage_validate,         "Validating font setup"),
    ("prepare",          stage_prepare,          "Pre-processing for fontmake"),
    ("save_sources",     stage_save_sources,     "Saving variable/static-ready sources"),
    ("compile_variable", stage_compile_variable, "Compiling variable font (fontmake)"),
    ("instance_statics", stage_instance_statics, "Instancing static styles"),
    ("compress",         stage_compress,         "Compressing to WOFF2"),
    ("package",          stage_package,          "Packaging release folders"),
]

# A run that stops here produces just the variable font — no statics/packaging.
VARIABLE_ONLY_STAGES = ("metrics", "load", "validate", "prepare", "save_sources", "compile_variable")


def run(only=None, build_italic=None, verbose=False):
    """Run the named subset of STAGES in order (default: all of them).

    build_italic, if given, overrides config.BUILD_ITALIC for this run.
    verbose enables full glyph/instance name listings in the prepare stage.
    """
    stages = [s for s in STAGES if only is None or s[0] in only]

    print("🚀 Starting build")
    print(f"   Source: {SOURCE_PATH}")

    if not os.path.exists(SOURCE_PATH):
        print(f"❌ File not found: {SOURCE_PATH}")
        sys.exit(1)

    _STEP["n"] = 0
    _STEP["total"] = len(stages)
    ctx = _Ctx(build_italic=BUILD_ITALIC if build_italic is None else build_italic, verbose=verbose)
    for _, fn, label in stages:
        with step(label):
            fn(ctx)


def _parse_args(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description="Cal Sans build pipeline")
    parser.add_argument(
        "--variable-only", action="store_true",
        help="Compile only the variable font; skip instancing, compression, and packaging",
    )
    parser.add_argument(
        "--italic", dest="italic", action="store_const", const=True, default=None,
        help="Build italic styles too (overrides config.BUILD_ITALIC for this run)",
    )
    parser.add_argument(
        "--no-italic", dest="italic", action="store_const", const=False,
        help="Build roman styles only (overrides config.BUILD_ITALIC for this run)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show full glyph/instance name lists in the pre-processing stage "
             "(default: just the counts and first few names)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    only = VARIABLE_ONLY_STAGES if args.variable_only else None
    run(only=only, build_italic=args.italic, verbose=args.verbose)

if __name__ == "__main__":
    main()
