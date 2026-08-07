# app/extraction/preprocessing.py
"""
Corrects image orientation before it's sent to the vision model. Phone
photos carry rotation in EXIF metadata rather than baked into the pixel
data — nothing upstream of this corrects that today.

Part of the Phase 1 speed pass (2026-08-04) — see
claude/ocr-pipeline-optimization-plan.md's 1.B.

REDUCED SCOPE 2026-08-04: this originally also capped total pixel count via
downscale (MAX_PIXELS=1.1M, per the source plan's 1.B) to cut vision-token
prefill cost. Reverted after a real live test caught it causing a
reproducible clinical-data misread: test_hla_typing_full_extraction (a
64/64 exact-match regression guard with no prior observed run-to-run
variance) started failing at exactly the same field (donor HLA locus DQA1
allele_2: "01" misread as "05") on two consecutive real runs at
temperature=0 against sample_report.jpg (1131x1600, 1.81MP — above the
cap, so the downscale genuinely fired). The source plan's own Phase 0.4
principle is "you cannot trade accuracy for speed if you can't measure
accuracy" and calls for sweeping MAX_PIXELS against a real harness before
picking a value — that measurement was never done here, so shipping a
default value was the actual mistake, not the idea of capping pixels per
se. Re-introduce the resize (and figure out a per-document-type safe cap,
if one exists) only alongside that sweep, scored against
hla_typing_ground_truth.json / crossmatch_ground_truth.json /
bead_specificity_anchor.json — don't re-add a guessed default.
"""
import io

from PIL import Image, ImageOps

JPEG_QUALITY = 90


def orient_image(image_bytes: bytes) -> bytes:
    """EXIF-transpose + RGB convert. No resize. `tiling.py`'s
    make_row_band_tiles crops by raw pixel coordinates assuming the page is
    already upright, so this MUST run on the full bead-specificity page
    before it's tiled — an un-rotated source would make the horizontal-
    row-band assumption wrong regardless of anything else."""
    img = Image.open(io.BytesIO(image_bytes))
    corrected = ImageOps.exif_transpose(img).convert("RGB")

    buf = io.BytesIO()
    corrected.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()
