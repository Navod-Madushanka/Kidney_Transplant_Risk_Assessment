# app/extraction/tiling.py
"""
Row-band image tiling for the bead specificity chart. A single-shot prompt
over the whole ~150-200 row table causes qwen3-vl to degenerate into
hallucinated repetition well before finishing (see the migration plan's
Phase 1 Results in claude/ocr-to-local-llm-migration-plan.md) — splitting
into overlapping horizontal bands and prompting each independently keeps
each call's effective task size within what the model reliably handles.

Ported from llm-migration-spike/run_eval.py's make_row_band_tiles. 8 tiles
is what Phase 1 validated as the better tradeoff over an initial 4-tile
attempt — narrower bands substantially reduced a duplicate-row-collapse
scoring issue, though they don't eliminate the hallucination failure mode
entirely (roughly 1-in-8 tiles still degenerated in Phase 1 testing).

TRIED AND REVERTED 2026-08-03: lowered 8 -> 6 for a session chasing full
end-to-end extraction speed (individual tile calls were observed taking
1-3 minutes each on the dev RTX 2060, and 8 sequential tiles reliably
pushed a bead-specificity page past kidney-backend's OCR timeout). 6
tiles did cut per-page time by roughly 25% in isolation (402s vs an
implied ~536s for 8, measured against sample_mfi_page1.jpg's anchors) --
but cost real row coverage (7/13 anchors matched, 60 rows, vs the
project's established 8-tile range) and didn't produce a reliably faster
full 4-image batch once real run-to-run variance was accounted for.
Reverted to 8. The actual fix for the timeout problem was raising
kidney-backend's ocr_service_timeout_seconds instead (see its config.py),
not shrinking tile count. If revisiting this, measure against
bead_specificity_anchor.json before changing the default again -- see
test_bead_specificity_live.py.
"""
import io

from PIL import Image

DEFAULT_NUM_TILES = 8
DEFAULT_OVERLAP_FRAC = 0.12


def make_row_band_tiles(
    image_bytes: bytes,
    num_tiles: int = DEFAULT_NUM_TILES,
    overlap_frac: float = DEFAULT_OVERLAP_FRAC,
) -> list[bytes]:
    """Splits the image into num_tiles horizontal bands (full width, with
    vertical overlap so a row straddling a cut line still appears whole in
    at least one tile), returned as PNG bytes."""
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    band_h = h / num_tiles
    overlap = band_h * overlap_frac
    tiles = []
    for i in range(num_tiles):
        top = max(0, i * band_h - overlap)
        bottom = min(h, (i + 1) * band_h + overlap)
        crop = img.crop((0, int(top), w, int(bottom)))
        buf = io.BytesIO()
        crop.save(buf, format="PNG")
        tiles.append(buf.getvalue())
    return tiles
