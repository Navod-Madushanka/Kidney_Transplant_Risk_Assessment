#!/usr/bin/env python3
"""CI guard against the frontend's hand-copied clinical constants drifting
out of sync with their backend source of truth (B4.4, FINALIZATION-PLAN.md
Phase 4.4).

kidney-frontend/src/constants/sensitizationWeights.js and clinicalEnums.js
are deliberately hand-copied rather than generated or imported (a
Python-to-JS build step was judged more machinery than the problem
warrants) -- each file's own header says "if the backend changes, update
both places". Nothing enforced that promise before this script: a doctor-
approved change to, say, SENSITIZATION_EVENT_WEIGHTS in the backend could
land with the frontend's copy silently stale, showing a doctor a live
points preview that no longer matches what the backend will actually
compute.

This parses both sides as plain text (ast on the Python side, regex on the
JS side) rather than importing app.* -- keeps this script dependency-free,
consistent with scripts/check_no_real_nics.py, and runnable in a lightweight
CI job with no backend venv install.

What this can and can't prove:
- CAN catch: a value, weight, or enum member added/removed/changed on one
  side and not the other, for the specific constants named below.
- CANNOT catch: a *label* drifting from clinical reality (e.g. T15's
  "Prior pregnancy" wording) -- that's a doctor sign-off question, not a
  sync question. Also can't catch a new constant file that should have
  been added to CHECKS below but wasn't; extend that list when adding a
  new hand-copied constant.
"""
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "kidney-backend" / "app"
FRONTEND = REPO_ROOT / "kidney-frontend" / "src" / "constants"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _py_dict_literal(source: str, name: str) -> dict:
    """Extracts `NAME: ... = {...}` or `NAME = {...}` at module level via ast,
    then literal_eval's just that one assignment's value -- no need to
    execute or import the module."""
    tree = ast.parse(source)
    for node in tree.body:
        targets = None
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        if not targets:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                return ast.literal_eval(node.value)
    raise ValueError(f"Could not find module-level assignment {name!r}")


def _py_enum_values(source: str, class_name: str) -> set:
    """Extracts the string values of a `class NAME(str, enum.Enum): MEMBER = "value"`
    block via ast -- member names/order don't matter, only the value set."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            values = set()
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            values.add(ast.literal_eval(item.value))
            return values
    raise ValueError(f"Could not find class {class_name!r}")


def _js_object_literal(source: str, name: str) -> dict:
    """Extracts `export const NAME = { key: value, ... }` -- values may be
    bare numbers (int/float), which is all these files ever hold."""
    match = re.search(rf"export const {re.escape(name)}\s*=\s*\{{(.*?)\}}", source, re.S)
    if not match:
        raise ValueError(f"Could not find `export const {name} = {{...}}`")
    body = match.group(1)
    entries = {}
    for line in body.splitlines():
        line = line.split("//", 1)[0].strip().rstrip(",")
        if not line:
            continue
        key, _, value = line.partition(":")
        entries[key.strip()] = float(value.strip())
    return entries


def _js_option_values(source: str, name: str) -> set:
    """Extracts the `value: "..."` fields out of `export const NAME = [ {value: "...", label: "..."}, ... ]`."""
    match = re.search(rf"export const {re.escape(name)}\s*=\s*\[(.*?)\n\]", source, re.S)
    if not match:
        raise ValueError(f"Could not find `export const {name} = [...]`")
    body = match.group(1)
    return set(re.findall(r'value:\s*"([^"]*)"', body))


def check_sensitization_weights() -> list[str]:
    backend_source = _read(BACKEND / "reference_data" / "sensitization_weights.py")
    frontend_source = _read(FRONTEND / "sensitizationWeights.js")

    backend_weights = _py_dict_literal(backend_source, "SENSITIZATION_EVENT_WEIGHTS")
    frontend_weights = _js_object_literal(frontend_source, "SENSITIZATION_EVENT_WEIGHTS")

    if backend_weights != frontend_weights:
        return [
            "SENSITIZATION_EVENT_WEIGHTS drifted: backend has "
            f"{backend_weights!r}, frontend (sensitizationWeights.js) has {frontend_weights!r}"
        ]
    return []


# (backend enum class name, frontend constants.js export name)
ENUM_CHECKS = [
    ("BloodType", "BLOOD_TYPE_OPTIONS"),
    ("RhFactor", "RH_FACTOR_OPTIONS"),
    ("HLALocusEnum", "HLA_LOCUS_OPTIONS"),
    ("SensitizationEventTypeEnum", "SENSITIZATION_EVENT_OPTIONS"),
    ("Sex", "SEX_OPTIONS"),
    ("Race", "RACE_OPTIONS"),
    ("SmokingStatus", "SMOKING_STATUS_OPTIONS"),
]


def check_clinical_enums() -> list[str]:
    backend_source = _read(BACKEND / "models" / "enums.py")
    frontend_source = _read(FRONTEND / "clinicalEnums.js")

    violations = []
    for class_name, option_name in ENUM_CHECKS:
        backend_values = _py_enum_values(backend_source, class_name)
        frontend_values = _js_option_values(frontend_source, option_name)
        if backend_values != frontend_values:
            violations.append(
                f"{class_name}/{option_name} drifted: backend has {backend_values!r}, "
                f"frontend (clinicalEnums.js) has {frontend_values!r}"
            )
    return violations


def main() -> int:
    violations = check_sensitization_weights() + check_clinical_enums()

    if violations:
        print("Frontend clinical constants have drifted from their backend source of truth:\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nUpdate kidney-frontend/src/constants/sensitizationWeights.js and/or "
            "clinicalEnums.js to match, in the same PR as the backend change. See "
            "docs/changing-clinical-constants.md."
        )
        return 1

    print("Frontend clinical constants match their backend source of truth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
