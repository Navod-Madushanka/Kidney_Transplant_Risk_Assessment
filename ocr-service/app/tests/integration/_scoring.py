# app/tests/integration/_scoring.py
#
# Shared anchor-scoring helper for the bead specificity integration test.
# Matches the ad-hoc scoring approach used throughout this session's real
# manual debugging (see claude/ocr-to-local-llm-migration-plan.md, Phase
# 3's Post-Deployment Debugging section) -- match by antigen name (case/
# whitespace/punctuation-insensitive), pick the nearest MFI among
# same-named candidates, count as a match if within 15% (per
# bead_specificity_anchor.json's own "_scoring_guidance" field). Not a
# test file itself (no test_ prefix) -- imported by test_bead_specificity_live.py.


def _norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def score_anchors(rows: list[dict], anchors: list[dict]) -> tuple[int, int]:
    """Returns (matched, total) -- how many of `anchors` have a same-named
    row in `rows` within 15% MFI tolerance. Each row can only be consumed
    by one anchor (no double-counting one lucky row against several
    same-named anchors, e.g. bead_specificity_anchor.json's two separate
    "A24" rows)."""
    used = set()
    matched = 0
    for anchor in anchors:
        target = _norm(anchor["antigen"])
        best_index, best_diff = None, None
        for i, row in enumerate(rows):
            if i in used or row.get("mfi") is None:
                continue
            if _norm(str(row.get("antigen", ""))) != target:
                continue
            diff = abs(row["mfi"] - anchor["mfi"])
            if best_diff is None or diff < best_diff:
                best_index, best_diff = i, diff
        if best_index is not None and best_diff <= 0.15 * anchor["mfi"]:
            used.add(best_index)
            matched += 1
    return matched, len(anchors)
