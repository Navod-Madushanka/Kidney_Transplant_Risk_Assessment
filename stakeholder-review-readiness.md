# Stakeholder review — readiness assessment

**Verdict: not ready today, but close. The engineering underneath is solid; what is not ready is the demo surface.** Nothing found is deep or architectural. The blockers are a hardcoded CORS origin, a live OCR path that will time out on CPU, four missing `.catch()` blocks, an unreachable admin feature, and real patient identifiers in tracked files.

Estimate: **one focused day** for everything in P0 and P1.

---

## What is genuinely solid — lean on this

These were verified by execution, not by reading.

| Check | Result |
|---|---|
| Backend tests | **504 passed, 0 failed, 0 skipped** in 217 s (264 unit + 240 integration), against a real Postgres 16 |
| Frontend tests | **249 passed, 0 failed** across 34 files |
| ocr-service tests | **78 passed, 0 failed** (4 live-Ollama tests correctly deselected by the project's own marker) |
| **Total** | **831 automated tests, all green** |
| Migrations | 35 files, **single head**, unbroken chain, no hand-edit artifacts |
| Routes | 20 routes, **zero stubs, zero placeholders** — every one renders a real page |
| Code hygiene | **Zero** `TODO`/`FIXME`/`coming soon`, zero `console.log`, zero empty click handlers, zero commented-out JSX |
| Secrets | No `.env` ever committed; `secret_key` has **no default** so the app refuses to boot unset |
| Audit trail | Hash-chained with an advisory lock and `seq`-ordered verification — a strong answer if IT asks |
| Parts G & H | Fully landed, and H went further than specified (see below) |

Two things worth saying out loud in the room: **831 passing tests** and the **hash-chained audit log**. Both are unusual at this stage and both answer questions a hospital IT reviewer will ask.

One implementation detail deserves credit: Part H's session fix was taken further than the plan. The route now uses `asyncio.create_task` via `schedule_extraction_job` rather than `BackgroundTasks`, because FastAPI closes the `Depends(get_db)` exit stack only *after* background tasks run — so the request's own session stayed checked out regardless of the per-write scoping. That was correctly diagnosed beyond what Part H specified, and the tests were updated to match (`test_ocr_job_db_sessions.py` asserts `checked_out_during_call == [0]` under 40 concurrent jobs).

---

## P0 — will visibly break the demo

**1. CORS is hardcoded to `http://localhost:5173`.**
`app/main.py:86`, not configurable, with `allow_credentials=True`. Demo from a LAN IP so clinicians can open it on their own phones, or from `vite preview` (port 4173), or from `127.0.0.1` instead of `localhost`, and **every request fails, including login**. The app looks completely broken.
→ Make origins an env-driven list, or commit to presenting only from the presenter's own browser at exactly `localhost:5173`.

**2. Live OCR on CPU will time out mid-demo.**
`ocr_service_timeout_seconds = 600` is a **per-document** ceiling. On the dev RTX 2060 a bead page already took 402 s at *six* tiles; production is 8 tiles and CPU-only. `llm/client.py:31` records ~88 s just to load the model on CPU, and `docker-compose.override.yml` records a first CPU request timing out at 120 s. A four-document job is 18 serial model calls.
→ **Pre-bake the extraction.** Run it beforehand on the GPU box and demo the stored job, or show the tile-by-tile progress stream from a pre-warmed run. Do not click Extract live on CPU.

**3. The Audit Log is unreachable.**
`Doctor.is_admin` defaults `false` and there is **no endpoint, script, or UI to promote anyone**. The nav item never appears. One of the strongest features is invisible.
→ `UPDATE doctors SET is_admin = true WHERE email = '<demo account>';` before the review. Add a management script afterwards.

**4. "Register patient & donor" is permanently disabled with no explanation.**
`NewPairPage.jsx:208-212` — `canSubmit` requires `patientPayload && donorPayload`, which are only set by clicking each sub-form's own "Save patient details" / "Save donor details" button. Fill both forms, press the main button, nothing happens. The explanatory hint at 419-424 only renders when OCR ran.
→ Either enable on valid form state, or always show the hint. This is the pair-registration flow — it is central to the demo.

**5. Four missing `.catch()` blocks — failures are silent.**
- `NewPatientPage.jsx:12-20` and `NewDonorPage.jsx:12-20` — a duplicate NIC becomes an unhandled rejection; the button un-spins and nothing else happens.
- `ExchangeProposalDetailPage.jsx:67-89` and `ExchangeProposalsInboxPage.jsx:42-60` — Accept / Decline / Cancel use `try/finally` with no catch. **This is the newest feature and the one you most want to show.**

**6. Two wizard dead ends.**
- `DetailsStep.jsx:133` — a blood-group conflict makes Continue silently do nothing. No message, no path forward except leaving the wizard.
- `SubjectStep.jsx:296-298` "Fix" links and `WizardLayout.jsx:29` "Exit check" navigate outside `/checks/new`, unmounting `WizardProvider` and **destroying every uploaded photo and OCR result with no confirmation**. On a demo where extraction took minutes, this is unrecoverable.

**7. No duration hint on extraction.**
`ExtractionProgressList.jsx` shows good per-document progress bars ("3/8 sections — 38%"), but nothing tells the viewer that 2–3 minutes per page is normal. The only place that knowledge exists is a code comment at `api/ocr.js:39`. A clinician watching a bar sit at 1/8 assumes it crashed.
→ One line of copy: "This usually takes 2–3 minutes per page."

---

## P1 — clinical credibility and privacy

These will not break the demo. They are worse than that: they are the things a transplant clinician might actually notice.

**8. Real patient identifiers are in tracked files.**
`app/tests/integration/test_ocr_jobs.py:31` contains `"Rev.A.Premarathna Thero"` and NIC `198001610076`. `implementation-prompt-part-f.md:390` lists four real NICs. There are also 20 real lab-report JPEGs in `kidney-backend/uploads/report_files/` on the laptop (gitignored, but served by the app).
→ **Replace with fictional identities before the review.** Showing real patient names and NIC numbers to a room of stakeholders without a data-use basis is a governance problem, not a polish problem — and it is the single finding most likely to cause you an actual issue.

**9. The UI tells the doctor the opposite of what the code does.**
Part F §F12 ("do not extract the bead chart during registration") was not implemented — `NewPairPage.jsx` still renders both bead slots and still calls `startExtractionJob(..., result.patientId)` after registration. But the UI text at lines 21-22, 44 and 49 still reads *"The bead specificity pages are storage-only here… not needed to create a record"* and *"Stored for the compatibility check — not read now."* They are read, seconds later.
→ Pick one and make the code and copy agree. In a clinical room, being caught telling the user one thing while doing another undermines everything else you show.

**10. The cPRA dedup shipped with no disclosure.**
Part I §I9 landed correctly (`dict.fromkeys` in `cpra_service.py:37`), but I9/I12 asked for the change to be disclosed and versioned. There is no audit note, no `HLA_FREQUENCY_TABLE_VERSION` bump, nothing in the clinical-basis doc. **Every historical `MatchReport.cpra_percentage` is now silently non-comparable to a new one.** If a clinician opens an old report next to a new one, the number moved and nothing explains why.

**11. Live correctness bug: the two cPRA call sites key differently.**
`cpra_fraction` (exchange) uses the **raw** `antibody.antigen`, while `match_pipeline` uses `normalize_antibody_antigen(...)`. So the exchange path misses the frequency table entirely for names like `"B45,Bw6"` — which is the normal format on the bead charts. This affects the `equity_weighted` policy's output today, and there is no test covering the dedup's effect on exchange weights (`test_exchange_matching_service.py` has only `test_equity_weighted_runs_end_to_end_without_antibody_data`).

**12. The sidebar shows an email address where the clinician's name should be.**
`AuthProvider.jsx:52` stores only `{access_token, email}` on login, and `:23-32` builds camelCase `fullName`/`hospitalName` while `Sidebar.jsx:52-53` reads snake_case `full_name`/`hospital_name`. Both are always null. The sidebar renders the raw email and the literal word **"doctor"**; `DashboardPage.jsx:77` renders "Hi" with no name. This is the first thing on screen for the whole demo.

**13. CI is currently red on lint.** `ruff check .` → **70 errors** in kidney-backend (63 × E501 line-too-long, 5 × I001 unsorted imports, 2 × F401 unused import). `npx eslint .` → **16 errors** (11 × `react-hooks/set-state-in-effect`, 1 × `react-hooks/refs` at `useExtractionJobPolling.js:70`, 4 × unused vars). Tests are green but the lint steps in both workflows fail. 7 of the ruff findings are auto-fixable; the E501s are mechanical.

---

## P2 — have an answer ready

You will probably be asked these. You do not need to fix them first.

- **`POST /auth/register` is unauthenticated and open.** Anyone reaching the API can self-provision a doctor account and auto-create a hospital via `get_or_create_hospital`. Hospital IT will ask about this.
- **No HTTPS, JWT in `sessionStorage`, 60-minute expiry with no refresh.** Expected at this stage — but note a session will die mid-demo after an hour with no silent renewal.
- **No structured logging.** `kidney-backend` configures none at all. Counter with the hash-chained audit log, which is the stronger answer anyway.
- **Cold start is undocumented and the README is wrong.** The root `README.md` is mangled UTF-8 and says `uv main.py`, which is not a command; `ocr-service/README.md` is 0 bytes; `.env.example` does not exist despite the backend README telling you to copy it; no compose file covers backend + Postgres + frontend. If anyone asks you to set it up on a fresh machine, it will not work.
- **`ollama` has no `mem_limit`** even though `ocr-service` now does — and the 4B model is the actual memory consumer.
- **PuLP deprecation:** all 416 test warnings are `LpVariable` and `PULP_CBC_CMD` deprecations. Both break on PuLP 4.0 and `pulp>=3.3.2` is unpinned upward. The exchange solver will stop working on an unlucky `uv sync`.

---

## P3 — after the review

- Part I §I6: structured warnings die at the backend boundary (`ocr_batch_service.py:148-149` keeps only `detail`; `code` and `bead_ids` never reach the frontend).
- Part I §I11: the live scoring harness still uses 15% fuzzy MFI tolerance with no bead-ID anchors — so Part J §J10's A/B prerequisite for constrained decoding is still unmet.
- `antibody_profile_verified` still flips True→False automatically for fresh patients (asserted in `test_ocr_jobs.py:296`). Defensible for a new patient, but it is the transition J13 forbids and it ejects them from the exchange pool.
- Dead code: `run_batch_extraction` / `BatchExtractionResult` have no production caller since `POST /ocr/extract-batch` was deleted. `POST /ocr/lab-report` has no frontend caller.
- `_DEGENERATE_MIN_REPEATED_MFI = 5` on exact-cent equality may false-positive on a tile covering a panel's low-MFI block. Review against a real page.
- Polish: raw ISO dates on four screens; `AuditLogPage.jsx:171` renders `JSON.stringify(details)` and `:152` raw snake_case actions; empty states are purely negative with no next action; `ExchangeCycleGraph` renders an empty SVG box above the empty state on desktop; no confirmation on exchange Accept/Decline (irreversible, one click).
- Projector legibility: `--color-clear` (#16A34A ≈ 3.0:1) and `--color-moderate` (#D97706 ≈ 3.1:1) on white are below AA 4.5:1 and are used for 12-13 px status text. Much of the UI is 11-13 px and will be unreadable past the third row.

---

## Suggested demo path

Routes around everything in P0 you do not have time to fix.

**Before the room:**
1. `UPDATE doctors SET is_admin = true WHERE email = '<demo account>';`
2. Seed the database — there is no seed script, so populate by hand and **verify it holds** (a demo starting empty shows only negative empty states).
3. Pre-run one full extraction on the GPU box so a completed job exists to open.
4. Rename patient identifiers in anything that will be on screen.
5. Confirm the URL bar reads exactly `http://localhost:5173`.
6. Close the editor, or at least `_to_delete/` (tracked in git, contains dead PaddleOCR code), `git status` (~50 modified files), and the six `implementation-prompt-part-*.md` files — they contain candid failure narratives ("0/13 anchors matched", "hallucinated repetition") that read badly out of context.
7. Delete `_to_delete/_stakeholder_check_src.tgz` (3.5 MB) — created during this audit; the sandbox could not remove it.

**In the room:**
1. Log in → dashboard.
2. Patient and donor records, then a **pre-registered** pair (avoid the disabled-button trap unless fixed).
3. Compatibility check from existing records — the full wizard, with **pre-extracted** OCR results already hydrated.
4. Match report: ABO, HLA mismatch, DSA bands, LKDPI, cPRA.
5. Paired exchange: the graph, the four policies, a proposal and its accept flow. Strongest feature — show it last and do not touch Decline unless the catch block is in.
6. Audit log, to close on provenance.

**Have ready but do not lead with:** the 831 passing tests, the CI workflow, and the `hla_antigen_frequencies.py` provenance docstring — Grifoni et al. 2018, 714 Colombo blood donors, computed from AFND raw genotypes rather than transcribed. A clinician who asks "where did these frequencies come from?" will be more impressed by that answer than by anything else in the system.
