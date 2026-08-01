#!/bin/bash
# docker/ollama-entrypoint.sh
#
# Ollama's official image can `ollama pull` a model, but building the
# Modelfile-level "-nothink" variant qwen3-vl needs (see below) isn't a
# pull — it requires `ollama show --modelfile` + edit + `ollama create`.
# This script does that automatically on first container start so the fix
# ships with the deployment instead of depending on a human remembering a
# manual step (that's exactly the failure that broke a test run during
# Phase 1 — "qwen3-vl:4b-nothink" not existing yet produced a confusing
# error rather than a working model).
#
# Why this is needed at all: qwen3-vl has a confirmed, currently-open
# Ollama bug (ollama/ollama#13353, #14798, #14645) — the per-request
# "think": false option and the documented "/no_think" prompt convention
# are both silently ignored, so the model always reasons in a hidden
# channel and the real answer (message.content) comes back empty. The
# workaround is a Modelfile that overrides RENDERER/PARSER to
# "qwen3-vl-instruct", which bypasses the broken per-request toggle
# entirely. See claude/ocr-to-local-llm-migration-plan.md (Phase 1
# Results) for the full story and how this was found.
set -euo pipefail

BASE_MODEL="${OLLAMA_BASE_MODEL:-qwen3-vl:4b}"
NOTHINK_MODEL="${OLLAMA_MODEL:-qwen3-vl:4b-nothink}"

/bin/ollama serve &
SERVE_PID=$!

echo "ollama-entrypoint: waiting for Ollama to come up..."
until ollama list >/dev/null 2>&1; do
  sleep 1
done

if ollama list | grep -q "$NOTHINK_MODEL"; then
  echo "ollama-entrypoint: $NOTHINK_MODEL already built, skipping provisioning."
else
  echo "ollama-entrypoint: building $NOTHINK_MODEL (one-time — persisted in the"
  echo "ollama-models volume, so this only runs again if that volume is wiped)..."
  ollama pull "$BASE_MODEL"

  MODELFILE="/tmp/${BASE_MODEL//[:\/]/_}.modelfile"
  ollama show "$BASE_MODEL" --modelfile > "$MODELFILE"
  # Don't touch the existing TEMPLATE line in the generated modelfile —
  # it's what handles image encoding correctly. Just append the two
  # override lines.
  printf '\nRENDERER qwen3-vl-instruct\nPARSER qwen3-vl-instruct\n' >> "$MODELFILE"
  ollama create "$NOTHINK_MODEL" -f "$MODELFILE"
  echo "ollama-entrypoint: $NOTHINK_MODEL built."
fi

wait $SERVE_PID
