#!/usr/bin/env python3
"""
Cal Sans Magic — avar2 experimental build.

Usage:
    python scripts/build_magic.py input.ttf [output_dir]

Outputs:
    CalSansMagic-Regular.ttf
    CalSansMagic-Regular.woff2

Pipeline order (critical — do not reorder):
    1. instancer  (shift defaults — must be first)
    2. avar2      (reads post-shift fvar ranges)
    3. hide YTAS  (logically follows avar2)
    4. rename     (last — no interaction with above)
"""

import os
import sys
import tempfile

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.designspaceLib import DesignSpaceDocument, AxisDescriptor, AxisMappingDescriptor
from fontTools.varLib.avar.build import build as build_avar

from scripts import config

_AXIS_NAMES = {
    "opsz": "Optical size",
    "wght": "Weight",
    "GEOM": "Geometric Form",
    "YTAS": "Ascender Height",
    "SHRP": "Sharp",
}


def shift_defaults(font):
    fvar = font["fvar"]
    coords = {}
    for tag, default in config.SHIPPING_DEFAULTS.items():
        axis = next(a for a in fvar.axes if a.axisTag == tag)
        coords[tag] = (axis.minValue, default, axis.maxValue)
    return instantiateVariableFont(font, coords, inplace=False, optimize=True)


def _build_avar2_ds(font):
    ds = DesignSpaceDocument()
    info = {}
    for a in font["fvar"].axes:
        ax = AxisDescriptor()
        ax.tag     = a.axisTag
        ax.name    = _AXIS_NAMES.get(a.axisTag, a.axisTag)
        ax.minimum = a.minValue
        ax.default = a.defaultValue
        ax.maximum = a.maxValue
        ds.addAxis(ax)
        info[a.axisTag] = {"min": a.minValue, "default": a.defaultValue, "max": a.maxValue}

    def make_loc(opsz_val, ytas_val):
        return {
            ax.name: (opsz_val if ax.tag == "opsz" else ytas_val if ax.tag == "YTAS" else ax.default)
            for ax in ds.axes
        }

    ytas_default = info["YTAS"]["default"]
    for opsz_val, ytas_out in config.MAGIC_OPSZ_TO_YTAS:
        m = AxisMappingDescriptor()
        m.inputLocation  = make_loc(opsz_val, ytas_default)
        m.outputLocation = make_loc(opsz_val, ytas_out)
        ds.axisMappings.append(m)

    return ds


def inject_avar2(font):
    ds = _build_avar2_ds(font)
    with tempfile.NamedTemporaryFile(suffix=".designspace", delete=False) as f:
        ds_path = f.name
    try:
        ds.write(ds_path)
        build_avar(font, ds_path)
    finally:
        os.unlink(ds_path)
    return font


def hide_ytas(font):
    for axis in font["fvar"].axes:
        if axis.axisTag == "YTAS":
            axis.flags |= 0x0001  # HIDDEN_AXIS — axis still functions via avar2
            break
    return font


def rename_font(font, family=config.MAGIC_FAMILY_NAME, style=config.MAGIC_STYLE_NAME):
    name = font["name"]
    fvar = font["fvar"]

    # Detach named instances from nameIDs 2/17 before we overwrite them
    max_id = max(r.nameID for r in name.names)
    for inst in fvar.instances:
        if inst.subfamilyNameID in (2, 17):
            max_id += 1
            orig = name.getDebugName(inst.subfamilyNameID)
            name.setName(orig, max_id, 3, 1, 0x409)
            inst.subfamilyNameID = max_id

    ps_family = family.replace(" ", "")
    for nameID, value in {
        1: family, 2: style, 4: f"{family} {style}",
        6: f"{ps_family}-{style}", 16: family, 17: style,
    }.items():
        for r in name.names:
            if r.nameID == nameID:
                name.setName(value, nameID, r.platformID, r.platEncID, r.langID)

    return font


def _verify(font):
    print("\n=== Verification ===")
    for a in font["fvar"].axes:
        hidden = " [HIDDEN]" if a.flags & 0x0001 else ""
        print(f"  {a.axisTag}: {a.minValue} → {a.defaultValue} → {a.maxValue}{hidden}")
    avar = font.get("avar")
    has_v2 = avar and hasattr(avar, "table") and avar.table is not None
    print(f"  avar2: {'present ✓' if has_v2 else 'MISSING ✗'}")
    for r in font["name"].names:
        if r.nameID in (1, 4, 6) and r.platformID == 3:
            print(f"  nameID {r.nameID}: {r.toUnicode()}")


def build_magic(input_path: str, output_dir: str = ".") -> tuple[str, str]:
    print(f"Loading {input_path}...")
    font = TTFont(input_path)

    shifted = ", ".join(f"{tag}→{default}" for tag, default in config.SHIPPING_DEFAULTS.items())
    print(f"Shifting defaults ({shifted})...")
    font = shift_defaults(font)

    print("Injecting avar2 (YTAS follows opsz)...")
    font = inject_avar2(font)

    print("Hiding YTAS axis...")
    font = hide_ytas(font)

    print(f"Renaming to {config.MAGIC_FAMILY_NAME}...")
    font = rename_font(font)

    _verify(font)

    stem = f"{config.MAGIC_FAMILY_NAME.replace(' ', '')}-{config.MAGIC_STYLE_NAME}"
    ttf_path   = os.path.join(output_dir, f"{stem}.ttf")
    woff2_path = os.path.join(output_dir, f"{stem}.woff2")

    font.save(ttf_path)
    print(f"\nTTF:   {os.path.getsize(ttf_path):,} bytes → {ttf_path}")

    font.flavor = "woff2"
    font.save(woff2_path)
    print(f"WOFF2: {os.path.getsize(woff2_path):,} bytes → {woff2_path}")

    return ttf_path, woff2_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/build_magic.py <input.ttf> [output_dir]")
        sys.exit(1)
    build_magic(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else ".")
