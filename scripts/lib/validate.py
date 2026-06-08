import sys

from scripts import config


def validate_font_setup(font):
    print("🔎 Running pre-flight validation...")
    actual_axes = [a.axisTag for a in font.axes]
    if actual_axes != config.EXPECTED_AXES:
        print(f"❌ Axis order wrong. Found: {actual_axes}")
        sys.exit(1)

    opsz_values = sorted(set(round(m.axes[0]) for m in font.masters))
    if opsz_values != config.EXPECTED_OPSZ_VALUES:
        print(f"❌ Expected opsz values {config.EXPECTED_OPSZ_VALUES}. Found: {opsz_values}")
        sys.exit(1)

    if len(font.masters) != config.EXPECTED_MASTER_COUNT:
        print(f"❌ Expected {config.EXPECTED_MASTER_COUNT} masters, found {len(font.masters)}.")
        sys.exit(1)

    print(f"   ✅ {config.EXPECTED_MASTER_COUNT} masters: {[m.name for m in font.masters]}")
