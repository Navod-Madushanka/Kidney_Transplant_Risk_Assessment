# app/tests/unit/test_bead_reconciliation.py
#
# Covers app/extraction/bead_reconciliation.py -- the reconciliation step
# that replaced the old dedupe-by-(antigen, mfi) approach (see that
# module's own docstring for the three independent ways the old approach
# was wrong). No network.
from app.extraction.bead_reconciliation import (
    BeadObservation,
    coerce_bead_id,
    coerce_mfi,
    detect_degenerate_tiles,
    reconcile_bead_rows,
)

# Mirrors kidney-backend's app/reference_data/dsa_threshold.py
# (DSA_MFI_FLOOR=1000, moderate=2000, strong=5000) -- see
# bead_reconciliation._clinical_band's docstring for why this service
# never hardcodes these itself.
DSA_BAND_EDGES = [1000.0, 2000.0, 5000.0]


def _obs(bead, antigen, mfi, tile=0) -> BeadObservation:
    return BeadObservation(bead=bead, antigen=antigen, mfi=mfi, tile_index=tile)


# --- coerce_bead_id ---


def test_coerce_bead_id_zero_pads_and_strips_whitespace():
    assert coerce_bead_id("44") == "044"
    assert coerce_bead_id("044") == "044"
    assert coerce_bead_id(" 44 ") == "044"


def test_coerce_bead_id_rejects_out_of_range():
    assert coerce_bead_id("0") is None  # below _BEAD_ID_MIN
    assert coerce_bead_id("1044") is None  # 4 digits -- not a 3-digit code


def test_coerce_bead_id_rejects_non_numeric_or_missing():
    assert coerce_bead_id("") is None
    assert coerce_bead_id(None) is None
    assert coerce_bead_id("4A") is None


# --- coerce_mfi ---


def test_coerce_mfi_plain_number():
    assert coerce_mfi(23706.91) == 23706.91


def test_coerce_mfi_int():
    assert coerce_mfi(490) == 490.0


def test_coerce_mfi_american_formatted_string():
    assert coerce_mfi("23,706.91") == 23706.91


def test_coerce_mfi_rejects_european_formatted_string():
    # A comma AFTER the last dot ("23.706,91") means European decimal
    # notation -- stripping the comma alone would silently produce a
    # plausible-looking WRONG number ("23.70691") instead of failing to
    # parse. The prompt asks for a plain American-style number; reject
    # rather than guess which separator was meant as the decimal point.
    assert coerce_mfi("23.706,91") is None


def test_coerce_mfi_rejects_multiple_dots():
    assert coerce_mfi("1.234.567") is None


def test_coerce_mfi_none_stays_none():
    assert coerce_mfi(None) is None


def test_coerce_mfi_unparseable_string_returns_none():
    assert coerce_mfi("illegible") is None


# --- reconcile_bead_rows ---


def test_near_miss_same_bead_merges_without_conflict():
    # The whole finding: tile overlap re-reads the same physical bead with
    # a one-cent OCR difference. Must merge to one row, not create a
    # duplicate -- this is the case _dedupe_rows's exact-float-equality
    # key could never catch.
    observations = [_obs("011", "A24", 23706.91, tile=3), _obs("011", "A24", 23706.9, tile=4)]

    rows, report = reconcile_bead_rows(observations, num_tiles=8)

    assert len(rows) == 1
    assert rows[0].observations == 2
    assert rows[0].conflict is None
    assert report.conflicts == []


def test_close_but_clinically_irrelevant_gap_does_not_conflict():
    # Same worked example as implementation-prompt-part-i.md's I3: a
    # 23706-23709 disagreement is ~0.01% and both readings are deep in the
    # "strong" DSA band -- changes nothing clinically, so this must NOT be
    # flagged even though it isn't a byte-identical read.
    observations = [_obs("011", "A24", 23706.91), _obs("011", "A24", 23708.91)]

    rows, report = reconcile_bead_rows(observations, num_tiles=8, band_edges=DSA_BAND_EDGES)

    assert len(rows) == 1
    assert rows[0].conflict is None
    assert report.conflicts == []


def test_two_distinct_beads_same_antigen_same_mfi_both_survive():
    # The drop case -- unrepresentable without bead IDs. Beads 011/012 are
    # both "A24" on the real chart and can legitimately read the identical
    # MFI; they are two real beads, not a duplicate. The old dedupe
    # silently collapsed exactly this case to one row.
    observations = [_obs("011", "A24", 23582.08), _obs("012", "A24", 23582.08)]

    rows, _report = reconcile_bead_rows(observations, num_tiles=8)

    assert len(rows) == 2
    assert {row.bead for row in rows} == {"011", "012"}


def test_disagreeing_readings_keep_one_row_with_the_highest_value_flagged():
    observations = [_obs("051", "A1", 950.0), _obs("051", "A1", 1200.0)]

    rows, report = reconcile_bead_rows(observations, num_tiles=8, band_edges=DSA_BAND_EDGES)

    assert len(rows) == 1
    # Highest candidate, never silently averaged or first-wins -- the row
    # is flagged for mandatory review either way, so erring high puts the
    # residual risk on the recoverable side (see reconcile_bead_rows's
    # docstring).
    assert rows[0].mfi == 1200.0
    assert rows[0].conflict == (950.0, 1200.0)
    assert len(report.conflicts) == 1
    assert report.conflicts[0].key == "051"
    assert report.conflicts[0].candidates == (950.0, 1200.0)


def test_threshold_crossing_dominates_relative_tolerance():
    # 990 vs 1010 is only 2% apart but crosses DSA_MFI_FLOOR (1000) --
    # clinically decisive (invisible-vs-flagged-as-a-DSA), so it must be
    # flagged as a conflict despite the small relative gap. See I3's
    # worked example.
    observations = [_obs("020", "B7", 990.0), _obs("020", "B7", 1010.0)]

    rows, report = reconcile_bead_rows(observations, num_tiles=8, band_edges=DSA_BAND_EDGES)

    assert rows[0].conflict == (990.0, 1010.0)
    assert len(report.conflicts) == 1


def test_no_band_edges_degrades_to_plain_relative_tolerance():
    # Without band_edges (e.g. a direct caller that didn't provide them),
    # a 990/1010 pair still agrees on relative tolerance alone -- degrades
    # gracefully instead of guessing at the real clinical thresholds.
    observations = [_obs("020", "B7", 990.0), _obs("020", "B7", 1010.0)]

    rows, _report = reconcile_bead_rows(observations, num_tiles=8, band_edges=None)

    assert rows[0].conflict is None


def test_all_null_mfi_readings_for_one_bead_collapse_cleanly():
    observations = [_obs("077", "C4", None), _obs("077", "C4", None)]

    rows, report = reconcile_bead_rows(observations, num_tiles=8)

    assert len(rows) == 1
    assert rows[0].mfi is None
    assert rows[0].conflict is None
    assert report.unreadable_mfi == ["077"]


def test_bead_without_id_falls_back_to_antigen_mfi_key_and_is_counted():
    observations = [_obs(None, "DQ4", 179.54)]

    rows, report = reconcile_bead_rows(observations, num_tiles=8)

    assert len(rows) == 1
    assert rows[0].bead is None
    assert report.no_bead_id == 1


def test_gap_detection_reports_missing_ids_within_observed_range():
    beads = [f"{n:03d}" for n in range(1, 51) if n != 31]
    observations = [_obs(b, "X", 100.0) for b in beads]

    _rows, report = reconcile_bead_rows(observations, num_tiles=8)

    assert report.gaps == ["031"]
    assert report.observed_beads == 49


def test_no_gaps_when_observed_ids_are_contiguous():
    observations = [_obs(f"{n:03d}", "X", 100.0) for n in range(1, 6)]

    _rows, report = reconcile_bead_rows(observations, num_tiles=8)

    assert report.gaps == []


# --- detect_degenerate_tiles ---


def test_degenerate_tile_flagged_for_repeated_identical_mfi():
    # The exact hallucination tiling exists to fight (see
    # llm_extract.py's CONCURRENT_TILE_LIMIT comment for a real observed
    # instance) -- a tile that repeats one row dozens of times must be
    # flagged, not silently collapsed into one clean-looking row by
    # reconciliation. This is the I2 regression test.
    degenerate_rows = [{"bead": None, "antigen": "DP1", "mfi": 23706.91} for _ in range(40)]
    tile_rows = [
        [{"bead": "001", "antigen": "A1", "mfi": 100.0}],
        degenerate_rows,
        [{"bead": "002", "antigen": "A2", "mfi": 90.0}],
    ]

    assert detect_degenerate_tiles(tile_rows) == [1]


def test_degenerate_tile_flagged_for_excess_row_count():
    tile_rows = [
        [{"bead": f"{i:03d}", "antigen": "A1", "mfi": float(i)} for i in range(3)],
        [{"bead": f"{i:03d}", "antigen": "A2", "mfi": float(i)} for i in range(3)],
        [{"bead": f"{i:03d}", "antigen": "A3", "mfi": float(i)} for i in range(20)],
    ]

    assert detect_degenerate_tiles(tile_rows) == [2]


def test_normal_tiles_and_failed_tiles_are_not_flagged():
    tile_rows = [
        [{"bead": f"{i:03d}", "antigen": "A1", "mfi": float(i)} for i in range(12)],
        [{"bead": f"{i + 12:03d}", "antigen": "A2", "mfi": float(i)} for i in range(13)],
        None,  # a failed tile (LLMExtractionError) must not crash or be flagged
    ]

    assert detect_degenerate_tiles(tile_rows) == []
