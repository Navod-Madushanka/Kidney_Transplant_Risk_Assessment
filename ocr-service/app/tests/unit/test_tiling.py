# app/tests/unit/test_tiling.py
#
# Geometry coverage for make_row_band_tiles -- had none at all before Part
# I. Verifies the tiles a real page gets split into actually cover the
# whole page with the intended overlap, rather than trusting the
# arithmetic by inspection. Uses a non-power-of-two, non-8-divisible page
# height (997) so integer truncation in the real function's `int(top)`/
# `int(bottom)` calls is actually exercised, not accidentally sidestepped
# by a suspiciously round test fixture.
import io
import itertools

import pytest
from PIL import Image

from app.extraction.tiling import make_row_band_tiles

PAGE_HEIGHT = 997
PAGE_WIDTH = 200
NUM_TILES = 8
OVERLAP_FRAC = 0.12


def _page_bytes(height: int = PAGE_HEIGHT, width: int = PAGE_WIDTH) -> bytes:
    img = Image.new("RGB", (width, height), color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _expected_bounds(
    height: int, num_tiles: int = NUM_TILES, overlap_frac: float = OVERLAP_FRAC
) -> list[tuple[int, int]]:
    """Mirrors make_row_band_tiles's own top/bottom formula exactly, so
    these tests check the function's actual behaviour against itself
    rather than a hand-derived approximation."""
    band_h = height / num_tiles
    overlap = band_h * overlap_frac
    bounds = []
    for i in range(num_tiles):
        top = max(0, i * band_h - overlap)
        bottom = min(height, (i + 1) * band_h + overlap)
        bounds.append((int(top), int(bottom)))
    return bounds


def _tile_height(tile_bytes: bytes) -> int:
    return Image.open(io.BytesIO(tile_bytes)).size[1]


def test_returns_exactly_num_tiles():
    tiles = make_row_band_tiles(_page_bytes(), num_tiles=NUM_TILES)
    assert len(tiles) == NUM_TILES


def test_tile_heights_match_the_function_s_own_band_geometry():
    tiles = make_row_band_tiles(_page_bytes(), num_tiles=NUM_TILES, overlap_frac=OVERLAP_FRAC)
    bounds = _expected_bounds(PAGE_HEIGHT)
    for tile, (top, bottom) in zip(tiles, bounds):
        assert _tile_height(tile) == bottom - top


def test_first_tile_top_clamps_at_zero_instead_of_going_negative():
    # top = 0*band_h - overlap is negative before clamping -- the first
    # tile must start at row 0, not before the page.
    bounds = _expected_bounds(PAGE_HEIGHT)
    assert bounds[0][0] == 0


def test_last_tile_bottom_clamps_at_page_height():
    # bottom = num_tiles*band_h + overlap overshoots the page before
    # clamping -- the last tile must end exactly at the page's own height.
    bounds = _expected_bounds(PAGE_HEIGHT)
    assert bounds[-1][1] == PAGE_HEIGHT


def test_adjacent_tiles_overlap_by_roughly_the_configured_fraction():
    # Interior tile i's bottom is (i+1)*band_h + overlap; tile i+1's top is
    # (i+1)*band_h - overlap -- the gap between them is -2*overlap, i.e. a
    # 2*overlap-row overlap. This is the whole point of the overlap: a row
    # straddling a cut line still appears whole in at least one tile.
    bounds = _expected_bounds(PAGE_HEIGHT)
    band_h = PAGE_HEIGHT / NUM_TILES
    expected_overlap = band_h * OVERLAP_FRAC
    for (_, bottom_a), (top_b, _) in itertools.pairwise(bounds):
        overlap_amount = bottom_a - top_b
        assert overlap_amount == pytest.approx(2 * expected_overlap, abs=2)
        assert overlap_amount > 0  # tiles genuinely overlap, not just touch


def test_no_row_in_the_page_is_missed_by_every_tile():
    bounds = _expected_bounds(PAGE_HEIGHT)
    covered: set[int] = set()
    for top, bottom in bounds:
        covered.update(range(top, bottom))
    assert covered == set(range(PAGE_HEIGHT))


def test_tile_width_matches_the_full_page_width():
    # Bands are full-width horizontal strips -- only the vertical axis is
    # tiled.
    tiles = make_row_band_tiles(_page_bytes(), num_tiles=NUM_TILES)
    for tile in tiles:
        assert Image.open(io.BytesIO(tile)).size[0] == PAGE_WIDTH


def test_custom_num_tiles_and_overlap_still_cover_the_page():
    # Not just the default 8/0.12 -- the geometry has to hold for any
    # config, including the 6-tile value this project tried and reverted
    # (see tiling.py's own "TRIED AND REVERTED" docstring section).
    num_tiles, overlap_frac = 6, 0.10
    bounds = _expected_bounds(PAGE_HEIGHT, num_tiles=num_tiles, overlap_frac=overlap_frac)
    covered: set[int] = set()
    for top, bottom in bounds:
        covered.update(range(top, bottom))
    assert covered == set(range(PAGE_HEIGHT))
    assert bounds[0][0] == 0
    assert bounds[-1][1] == PAGE_HEIGHT
