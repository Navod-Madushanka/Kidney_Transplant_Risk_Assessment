# app/extraction/bead_reconciliation.py
"""
Reconciles bead-specificity rows extracted from multiple overlapping
row-band tiles (see tiling.py) into one row per physical bead — replaces
the old dedupe-by-(antigen, mfi) approach, which was wrong in three
independent ways:

  - A one-cent OCR difference on the SAME bead (tile 3 reads 23706.91,
    tile 4 reads 23706.9) created two rows instead of one, since exact
    float equality was the dedupe key.
  - Two DIFFERENT beads legitimately sharing a Sero value (the normal
    case on this panel, not an edge case -- e.g. beads 011/012 are both
    "A24" at different MFIs) that happened to get OCR'd at the SAME MFI
    collapsed into one row, silently dropping a real bead with no trace.
  - A tile that degenerated into repeating one row dozens of times (the
    exact hallucination tiling exists to fight -- see llm_extract.py's
    CONCURRENT_TILE_LIMIT comment for a real observed instance: "six
    different labels all reported as the same 23706.91") collapsed to one
    clean-looking row, indistinguishable from a tile that only ever saw
    one row. The dedupe was erasing its own regression signal.

The Bead column (a 3-digit code, unique within one page's panel) is the
row identity the source document already carries — the old prompt
explicitly told the model to ignore it (see llm/prompts.py). reconcile_bead_rows
groups by bead ID where present, falling back to (antigen, mfi) only for
rows the model couldn't attach one to, and returns both the merged rows
AND a report of what happened, so a collapse or a drop is never silent.
"""
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field

MFI_AGREEMENT_FRAC = 0.02
_BEAD_ID_MIN = 1
_BEAD_ID_MAX = 120
_DEGENERATE_MIN_REPEATED_MFI = 5
_DEGENERATE_ROW_COUNT_RATIO = 3


@dataclass(frozen=True)
class BeadObservation:
    bead: str | None
    antigen: str
    mfi: float | None
    tile_index: int


@dataclass(frozen=True)
class ReconciledRow:
    bead: str | None
    antigen: str
    mfi: float | None
    observations: int
    conflict: tuple[float | None, ...] | None = None


@dataclass(frozen=True)
class BeadConflict:
    key: str  # bead ID, or the antigen name when no bead ID was available
    candidates: tuple[float | None, ...]


@dataclass(frozen=True)
class BeadReconciliationReport:
    observed_beads: int
    gaps: list[str] = field(default_factory=list)
    conflicts: list[BeadConflict] = field(default_factory=list)
    unreadable_mfi: list[str] = field(default_factory=list)
    no_bead_id: int = 0
    degenerate_tiles: list[int] = field(default_factory=list)


def coerce_bead_id(value) -> str | None:
    """Zero-pads to 3 digits (`"44"`, `"044"`, `" 44 "` all unify to
    `"044"`) and range-checks against a single-antigen panel (1..120).
    Returns None — never raises, never guesses — for anything else, so a
    misread bead code degrades to the (antigen, mfi) fallback key instead
    of silently keying on garbage. A row with an unreadable bead ID is
    kept by the caller, not dropped — see reconcile_bead_rows."""
    if value is None:
        return None
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,3}", text):
        return None
    number = int(text)
    if not (_BEAD_ID_MIN <= number <= _BEAD_ID_MAX):
        return None
    return f"{number:03d}"


def coerce_mfi(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value)
    last_dot = raw.rfind(".")
    last_comma = raw.rfind(",")
    if last_dot != -1 and last_comma != -1 and last_comma > last_dot:
        # A comma AFTER the last dot means European-style decimal notation
        # ("23.706,91") -- stripping the comma alone (the old behaviour)
        # silently produced a plausible-looking WRONG number ("23.70691")
        # instead of failing to parse. The prompt already asks for a plain
        # American-style number ("23,706.91" -> 23706.91, comma as
        # thousands separator, dot as decimal point); this shape means the
        # model didn't follow it. Reject rather than guess which separator
        # was meant as the decimal point.
        return None
    cleaned = re.sub(r"[^\d.]", "", raw)
    if cleaned.count(".") > 1:
        return None
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


def _clinical_band(mfi: float | None, band_edges: list[float] | None) -> int:
    """Buckets `mfi` by a list of ascending thresholds (e.g. [1000.0,
    2000.0, 5000.0] for the weak/moderate/strong DSA bands — see kidney-
    backend's app/reference_data/dsa_threshold.py, which OWNS these
    numbers). Deliberately NOT hardcoded here: ocr-service and
    kidney-backend are separately deployed services with no shared
    package, so there's no way to `import` the real module, and
    copy-pasting the literal values in would let this drift from the real
    clinical thresholds with no test to catch it. kidney-backend passes
    its current values on every bead-specificity request instead (see
    routes.py's dsa_band_edges parameter) — if band_edges is empty or
    missing, every MFI falls in band 0, which makes the threshold-crossing
    rule in _agree() below a no-op rather than risk using stale numbers;
    the 2% relative-tolerance rule still applies on its own either way.
    """
    if not band_edges or mfi is None:
        return 0
    band = 0
    for edge in band_edges:
        if mfi >= edge:
            band += 1
    return band


def _agree(a: float | None, b: float | None, band_edges: list[float] | None) -> bool:
    """Two observations of the same bead 'agree' if they're both null, or
    both non-null, land in the same clinical band, AND are within 2% of
    each other (floor 1.0, so tiny MFIs near zero aren't over-strict).

    The band check comes FIRST and short-circuits the tolerance check: a
    990-vs-1010 disagreement is only 2% apart but crosses DSA_MFI_FLOOR
    (1000) — clinically decisive (invisible vs. flagged as a DSA), so it
    must never be waved off as noise even though the raw percentage gap is
    tiny. A 23706-vs-23709 disagreement is a similar absolute gap but
    changes nothing clinically, so it's treated as noise. Which side of a
    threshold an MFI error lands on matters far more than its magnitude.
    """
    if a is None or b is None:
        return a is None and b is None
    if _clinical_band(a, band_edges) != _clinical_band(b, band_edges):
        return False
    return abs(a - b) <= max(1.0, MFI_AGREEMENT_FRAC * max(a, b))


def reconcile_bead_rows(
    observations: list[BeadObservation],
    num_tiles: int,
    band_edges: list[float] | None = None,
) -> tuple[list[ReconciledRow], BeadReconciliationReport]:
    """Groups observations by bead ID where present, falling back to
    (antigen, mfi) where the model couldn't attach a bead ID — see
    coerce_bead_id. Within a group: one observation is taken as-is;
    several that agree (see _agree) merge to one row; several that
    disagree keep ONE row using the HIGHEST candidate MFI, with every
    candidate preserved in `conflict` and the bead added to the report's
    conflict list. A disagreement is never silently resolved.

    Why the highest value on conflict: the row is flagged for mandatory
    doctor review either way, so the chosen value is a placeholder pending
    confirmation, not a claimed answer. If review is ever skipped anyway,
    over-flagging (a value that reads slightly more severe than reality)
    costs a clinician a second look; under-flagging risks missing a real
    DSA. Erring high puts the residual risk on the recoverable side.

    `num_tiles` is accepted for symmetry with the report shape and
    possible future use (e.g. an expected-coverage check); today's gap
    detection works off the observed bead-ID range directly and doesn't
    need it.
    """
    groups: dict[tuple, list[BeadObservation]] = {}
    for obs in observations:
        key = ("bead", obs.bead) if obs.bead is not None else ("fallback", obs.antigen.lower(), obs.mfi)
        groups.setdefault(key, []).append(obs)

    rows: list[ReconciledRow] = []
    conflicts: list[BeadConflict] = []
    unreadable_mfi: list[str] = []
    no_bead_id = 0

    for group in groups.values():
        bead = group[0].bead
        antigen = group[0].antigen
        mfis = [o.mfi for o in group]

        # Cluster the group's MFI readings into agreement classes --
        # more than one class means a genuine disagreement, not just
        # tile-overlap re-reading the same value.
        distinct: list[float | None] = []
        for mfi in mfis:
            if not any(_agree(mfi, d, band_edges) for d in distinct):
                distinct.append(mfi)

        report_key = bead if bead is not None else antigen
        if len(distinct) <= 1:
            chosen = mfis[0]
            conflict = None
        else:
            candidates_with_value = [m for m in mfis if m is not None]
            chosen = max(candidates_with_value) if candidates_with_value else None
            conflict = tuple(mfis)
            conflicts.append(BeadConflict(key=report_key, candidates=tuple(mfis)))

        rows.append(
            ReconciledRow(
                bead=bead, antigen=antigen, mfi=chosen, observations=len(group), conflict=conflict
            )
        )

        if bead is None:
            no_bead_id += 1
        if chosen is None:
            unreadable_mfi.append(report_key)

    observed_ints = sorted({int(o.bead) for o in observations if o.bead is not None})
    gaps: list[str] = []
    if len(observed_ints) >= 2:
        full_range = set(range(observed_ints[0], observed_ints[-1] + 1))
        gaps = [f"{missing:03d}" for missing in sorted(full_range - set(observed_ints))]

    report = BeadReconciliationReport(
        observed_beads=len(observed_ints),
        gaps=gaps,
        conflicts=conflicts,
        unreadable_mfi=unreadable_mfi,
        no_bead_id=no_bead_id,
    )
    return rows, report


def detect_degenerate_tiles(tile_rows: list[list[dict] | None]) -> list[int]:
    """Flags a tile as likely-degenerate — the repeated-row hallucination
    tiling.py's overlap exists to catch the effects of, not eliminate the
    cause of (see llm_extract.py's CONCURRENT_TILE_LIMIT comment for a
    real observed instance) — when either holds:
      - 5+ of its own rows share an identical MFI (to the cent), or
      - it returned more than 3x the median row count of the other tiles.

    Runs on each tile's RAW rows, before reconciliation — reconciliation
    only ever sees the merged result, so a degenerate tile that collapsed
    to "one clean row" post-merge would otherwise be indistinguishable
    from a tile that legitimately only saw one row. That indistinguishability
    is exactly what made a real hallucination invisible under the old
    dedupe (see this module's own docstring, third bullet)."""
    degenerate: list[int] = []
    valid_indices = [i for i, rows in enumerate(tile_rows) if rows]
    counts = {i: len(tile_rows[i]) for i in valid_indices}

    for i in valid_indices:
        rows = tile_rows[i]
        mfi_values = [
            coerce_mfi(row.get("mfi")) for row in rows if isinstance(row, dict)
        ]
        mfi_tally = Counter(v for v in mfi_values if v is not None)
        if mfi_tally and max(mfi_tally.values()) >= _DEGENERATE_MIN_REPEATED_MFI:
            degenerate.append(i)
            continue

        other_counts = [counts[j] for j in valid_indices if j != i]
        if other_counts:
            median_other = statistics.median(other_counts)
            if median_other > 0 and counts[i] > _DEGENERATE_ROW_COUNT_RATIO * median_other:
                degenerate.append(i)

    return degenerate
