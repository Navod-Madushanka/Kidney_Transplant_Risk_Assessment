# app/tests/conftest.py
#
# Phase 4 of claude/ocr-to-local-llm-migration-plan.md: ocr-service had no
# test suite at all before this. Fixtures here are shared by both
# app/tests/unit/ (fast, network-mocked, run on every CI push) and
# app/tests/integration/ (real calls to a live Ollama, excluded by default
# — see [tool.pytest.ini_options] in pyproject.toml).
import json
import os
from pathlib import Path

import pytest

# Must happen before any `app.*` import anywhere in the test session —
# app/core/config.py's Settings() reads this eagerly at import time with no
# default (real deployments always set it via docker-compose.yml's
# OCR_SERVICE_API_KEY). No test here calls the authenticated /extract HTTP
# route directly — they call the extraction functions in-process — so this
# value is never actually checked against anything, it just has to exist
# so Settings() doesn't raise on import.
os.environ.setdefault("OCR_SERVICE_API_KEY", "test-key-not-used")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
TEST_IMAGES_DIR = Path(__file__).parent.parent / "test_images"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _image_bytes(filename: str) -> bytes:
    path = TEST_IMAGES_DIR / filename
    if not path.exists():
        pytest.skip(f"{filename} not present in app/test_images/ (gitignored test fixture)")
    return path.read_bytes()


# --- Ground truth / anchor fixtures ---
# Ported from llm-migration-spike/fixtures/ (Phase 1). See each JSON file's
# own "_confidence" field for how trustworthy it is — hla_typing and
# crossmatch are hand-verified "high confidence"; bead_specificity is
# explicitly a partial, best-effort anchor set, not full ground truth.

@pytest.fixture
def hla_ground_truth() -> dict:
    return _load_fixture("hla_typing_ground_truth.json")


@pytest.fixture
def crossmatch_ground_truth() -> dict:
    return _load_fixture("crossmatch_ground_truth.json")


@pytest.fixture
def bead_specificity_anchors() -> dict:
    return _load_fixture("bead_specificity_anchor.json")


# --- Sample document images (integration tests only) ---
# Not committed to git (app/test_images/ predates this and is already
# gitignored — see .gitignore) — these fixtures skip gracefully rather than
# erroring if the images aren't present on the machine running pytest.

@pytest.fixture
def hla_image_bytes() -> bytes:
    return _image_bytes("sample_report.jpg")


@pytest.fixture
def crossmatch_image_bytes() -> bytes:
    return _image_bytes("sample_simple.jpg")


@pytest.fixture
def bead_specificity_page1_bytes() -> bytes:
    return _image_bytes("sample_mfi_page1.jpg")


@pytest.fixture
def bead_specificity_page2_bytes() -> bytes:
    return _image_bytes("sample_mfi_page2.jpg")
