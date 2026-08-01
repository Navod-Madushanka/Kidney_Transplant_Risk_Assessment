# Phase 1 spike — OCR → local vision-LLM

Throwaway/scratch code per `claude/ocr-to-local-llm-migration-plan.md`
(Phase 1). Does not touch `ocr-service` — this is purely "does the approach
work at all" before we commit to rewriting anything real.

## What's here

- `fixtures/` — hand-verified ground truth for the HLA typing report and
  crossmatch report (high confidence), plus a **partial anchor set** for
  the bead specificity chart (low-medium confidence, spot-check only —
  read the `_confidence` note inside that file before trusting it).
- `prompts.py` — one prompt + expected JSON shape per document type,
  matching `ocr-service`'s current field names exactly.
- `run_eval.py` — calls a local Ollama model against the real sample
  images and scores its output against the fixtures.

## Setup (PowerShell)

1. **Install Ollama** if you don't have it: https://ollama.com/download —
   Windows installer, no extra config needed.
2. **Pull the model:**
   ```powershell
   ollama pull qwen3-vl:2b
   ```
   (Requires Ollama ≥0.12.7 — the installer should already be current, but
   run `ollama --version` if the pull fails oddly.)
3. **Confirm Ollama is serving** (it usually starts automatically after
   install — check with):
   ```powershell
   ollama list
   ```
   If that fails to connect, start it with `ollama serve` in its own
   terminal window and leave it running.
4. **Put the four sample images in one folder** — reuse
   `Project_Resouces\photos\` (or wherever they already live):
   `sample.jpg`, `sample_simple.jpg`, `sample_mfi_page1.jpg`,
   `sample_mfi_page2.jpg`.
5. **Build a non-thinking model variant — REQUIRED, not optional.**
   `qwen3-vl` has a confirmed, currently-open Ollama bug
   ([#13353](https://github.com/ollama/ollama/issues/13353),
   [#14798](https://github.com/ollama/ollama/issues/14798)): the per-request
   `"think": false` option and the `/no_think` prompt convention are both
   silently ignored, so the model always reasons in a hidden `thinking`
   channel and leaves the real answer (`message.content`) empty. Running
   against plain `qwen3-vl:2b` will still "work" (the script has a fallback
   that salvages JSON out of the `thinking` text) but that fallback is
   provably unreliable — identical temperature-0 runs against the same
   image were observed swinging between 15/15 and 8/15 on the crossmatch
   document, because `thinking` text isn't guaranteed to contain the
   *complete* answer. Fix it once, at the model level:
   ```powershell
   ollama show qwen3-vl:2b --modelfile > qwen3-vl-2b.modelfile
   ```
   Open `qwen3-vl-2b.modelfile` in a text editor and add these two lines
   (don't change anything else — the existing `TEMPLATE` is what handles
   image encoding correctly, so leave it alone):
   ```
   RENDERER qwen3-vl-instruct
   PARSER qwen3-vl-instruct
   ```
   Then build the fixed variant:
   ```powershell
   ollama create qwen3-vl:2b-nothink -f qwen3-vl-2b.modelfile
   ```
   Use `qwen3-vl:2b-nothink` (not `qwen3-vl:2b`) for every `--model` flag
   below. If you later try `qwen3-vl:4b`, repeat this same process for that
   model too — the bug affects the whole `qwen3-vl` family, not just `2b`.

## Run it

```powershell
cd llm-migration-spike
python run_eval.py --model qwen3-vl:2b-nothink --images "C:\Users\navod\Documents\Hospital_Project_Documants\Project_Resouces\photos"
```

This prints a field-by-field score for the HLA and crossmatch documents
(should be easy to get to 100% — these are the "PaddleOCR already worked
fine" documents, so they're the baseline sanity check that the LLM approach
isn't a regression), and an anchor spot-check for the bead specificity
chart (the actual hard case this migration exists for). Full raw model
output for every document lands in `results/*.json` — open those and
compare the bead specificity ones against the real chart yourself, since
the anchor set only covers a fraction of the ~150-200 total rows.

## What to do with the results

Per the migration plan's Phase 1 exit criteria: don't move on to Phase 2
(real `ocr-service` rewrite) until one model clears a concrete bar you're
happy with — HLA/crossmatch should be at or near 100%, and the bead
specificity chart should hit a hit-rate you'd actually trust (defined
before you look at the numbers, not after). If `qwen3-vl:2b` falls short,
try `qwen3-vl:4b` (`ollama pull qwen3-vl:4b`, same command with
`--model qwen3-vl:4b`) before concluding the approach needs more prompt
work or a different model entirely (PaddleOCR-VL is the next thing worth
trying — see the migration plan for how to get it into Ollama via GGUF).

Come back with the numbers (or just the `results/` folder) and we'll decide
whether to proceed to Phase 2.
