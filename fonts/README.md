# Cal Sans Build Pipeline

Automated "Single Build Pipeline" for Cal Sans — a 6-axis variable font (`opsz`,
`GEOM`, `wght`, `YTAS`, `SHRP`, `ital`). The `scripts` package takes the
hand-drawn Glyphs source and produces the variable font, ~192–384 static instances, and a set of
curated release packages — all without ever modifying the source file. See
[VISION.md](VISION.md) for the full design rationale and pipeline internals.

## Setup

You'll need Python 3.9+ and a virtual environment.

###MacOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
###Windows

```bash
python3 -m venv venv
source venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` installs:
- **glyphsLib** — reads the `.glyphspackage` source
- **fontTools** — low-level font table manipulation (instancing, avar2, etc.)
- **fontmake** — compiles UFOs/designspace into variable & static binaries
- **tqdm** — progress bars for the long-running steps
- **uharfbuzz** — gives fontTools access to HarfBuzz's `hb.repack` table
  packer, which is needed to correctly resolve GPOS table overflow during
  compilation (without it, fontTools falls back to a legacy packer that
  crashes on this font's large `@All`-class GPOS table — see VISION.md §6)
- **brotli** — required by fontTools to write `.woff2` files (step 8/9
  compresses the variable font and all static instances to WOFF2)

## Running the build

```bash
python3 -m scripts
```

This runs the entire pipeline end-to-end — source → packaged release folders —
printing a numbered, timed `[n/9]` header for each step. Expect it to take a
while: `glyphsLib.load` alone takes ~45s, and the instancing/compiling steps
are CPU-heavy (the full run can take well over ten minutes).

Useful flags:

- `--variable-only` — compile just the variable font and stop, skipping
  instancing, compression, and packaging.
- `--italic` / `--no-italic` — override `config.BUILD_ITALIC` for a single run.
- `--verbose` — show full glyph/instance name lists in the pre-processing
  stage (step 4); by default only counts and the first few names are printed.

### What it does

1. **Extract metrics** — dumps master metrics/stems to `sources/metrics.json`.
2. **Load source** — reads `sources/CalSans.glyphspackage` via glyphsLib.
3. **Validate** — checks axes, master count, and opsz values match expectations.
4. **Pre-process for fontmake** — translates the source from the Glyphs-app
   feature dialect to the fontmake/feaLib dialect entirely in memory.
5. **Save `_READY` packages** — writes disposable `CalSans_READY*.glyphspackage`
   intermediates that fontmake compiles from.
6. **Compile the variable font** — runs `fontmake`, then post-processes the
   result (merges overlapping GEOM feature variations, shifts axis defaults).
7. **Instance statics** — generates all static styles (192 roman, or 384 with
   italics) into `scripts/temp/static/`, baking the correct GEOM substitutions into
   each.
8. **Compress** — generates `.woff2` siblings for the variable font and statics.
9. **Package releases** — sorts the finished exports into the `fonts/` release
   folders (e.g. `calsans-var-full`, `calsans-static-essentials`,
   `calsans-gf-workspace`, etc.)

### Configuration

A few constants in `scripts/config.py` control the run:

- `BUILD_ITALIC` — `False` builds 192 roman-only styles; `True` builds the
  full 384 (roman + italic).
- `SOURCE_PATH` / `OUTPUT_PATH` / `BUILD_DIR` / `RELEASE_DIR` — paths for the
  source, intermediate `_READY` files, build artifacts, and final release
  folders, respectively.
- `STATIC_*_TOKENS` / `STATIC_AXIS_VALUES` — the per-axis style-name tokens
  and instancer coordinates that `scripts/lib/manifest.py` combines into the
  full static-style catalog.

## Output

There are two output locations, serving different purposes:

- **`scripts/temp/`** — raw/intermediate compiled output, the working area used
  before final packaging:
  - `scripts/temp/variable/` — compiled variable font(s)
  - `scripts/temp/static/` — all instanced static styles (TTF + WOFF2)
- **`fonts/`** — the final, curated, ready-to-ship release packages, sorted
  from `scripts/temp/`'s output by step 9/9. **This directory is wiped and
  regenerated from scratch on every run.** See VISION.md §7 for the full
  rationale; the packages are:

  | Package | Contents |
  |---------|----------|
  | `calsans-var-full` | The full variable font, all axes exposed |
  | `calsans-var-magic` | Avar2 "magic" build — YTAS hidden, follows `opsz` parametrically (see issue #2) |
  | `calsans-cossui` | Variable font with `ss*`/`cv*`/`aalt` features and their alternate glyphs subset out |
  | `calsans-gf-api` | Same subsetting as `cossui`, packaged for the Google Fonts API |
  | `calsans-static-full` | All static instances (192 roman-only, or 384 with `BUILD_ITALIC=True`) |
  | `calsans-static-{a11y,ui,base,geo}` | Per-GEOM-family static subsets (base YTAS/SHRP only) |
  | `calsans-static-essentials` | Curated minimal set: Text+UI (roman) and Display+Base (incl. italics), TTF-only |
  | `calsans-gf-workspace` | Same curated set as `static-essentials`, deployed without `opsz`-axis awareness |

## Troubleshooting

- **`fontmake: Error: ... Generating fonts from Designspace failed`** during
  step 6/9, with a `GPOS` `OTLOffsetOverflowError` in the log — make sure
  `uharfbuzz` is installed (`pip install uharfbuzz` or re-run
  `pip install -r requirements.txt`). Without it, fontTools uses a legacy
  table packer that can crash on this font's large GPOS table.
- **`ImportError: No module named brotli`** during step 8/9 (WOFF2
  compression) — install `brotli` (`pip install brotli` or re-run
  `pip install -r requirements.txt`).
- **`command not found: fontmake`** — the `fontmake` console script may have
  installed outside your `PATH` (commonly under
  `~/Library/Python/<version>/bin` on macOS if not using a venv). Activating
  the venv from Setup avoids this; otherwise add that directory to `PATH`.
