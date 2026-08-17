# Implementation prompt — Part K: Completing paired exchange — commitment workflow, decision support, and a mobile-first view

**Insert as Part K of `implementation-prompt.md`, after Part J. Everything below the line goes to your coding agent.**

---

## K0. What is missing

Paired exchange today is a calculator, not a workflow. `GET /exchange/match` loads the pool, builds a directed graph, enumerates every 2- and 3-cycle, solves a binary ILP with CBC, and renders the answer. Then it forgets. Both service docstrings say so: *"read-only, advisory… nothing here writes to the database or transitions donor/patient status. Acting on a discovered cycle is a separate, not-yet-built step."*

Three consequences:

1. **No commitment.** A coordinator who finds a viable 3-way swap has no way to record it. The only cross-hospital channel is the `donor_doctor_email` string in the response, for a human to act on by phone.
2. **No overlap protection.** Overlap is prevented *within* one solve. Two coordinators looking at two runs can both act on cycles sharing a pair, and nothing notices.
3. **Nothing explains itself.** A pair that never appears in a selected cycle is indistinguishable from one that was never eligible. The most common coordinator question — *why wasn't my patient matched?* — has no answer in the UI.

And it is effectively desktop-only. The shell is responsive (`Topbar`/`TabBar` below `md`, `Sidebar` at `md`+, Exchange already in the mobile tab bar), but `ExchangePoolPage.jsx` uses **zero** responsive utilities, opens with an unconditional `grid-cols-3`, and its centrepiece is a 560-unit circular SVG with a hard `min-w-[420px]` inside a horizontally-scrolling div. On a 375 px phone the graph overflows and its 11 px labels render at about 7 px.

---

## K1. Decisions taken

| Decision | Choice |
|---|---|
| Who approves a cycle | **Each pair's own doctor.** A cycle locks only when every pair has been accepted by the doctor who owns it. No one commits another hospital's patient. |
| Mobile scope | **Mobile-first redesign of the exchange view only.** Cycle cards become the primary representation; the SVG graph is demoted to a desktop affordance. |
| Decision support | **Three additions:** per-pair "why not matched", cross-policy agreement, and hard-to-match/waiting surfacing. What-if simulation is explicitly out of scope. |

---

## K2. Data model

Two tables. **JSONB for the immutable clinical snapshot, relational rows for the mutable workflow state** — do not blur them.

**`exchange_proposals`** — mirrors `MatchReport`'s conventions: a computed clinical result is snapshotted, not re-derived on read.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | `UUIDPrimaryKeyMixin` |
| `created_by_doctor_id` | FK doctors | |
| `policy` | String(50) | Policy in force when proposed |
| `weight` | Float | The policy weight, for display |
| `status` | enum `ExchangeProposalStatus` | `proposed` / `accepted` / `declined` / `expired` / `cancelled` / `completed` |
| `cycle_snapshot` | JSONB | Nodes, directed edges, and every `mismatch_result` / `dsa_result` / `lkdpi_result` **as computed at proposal time**, plus `HLA_FREQUENCY_TABLE_VERSION` and the DSA band constants in force |
| `expires_at` | timestamptz | |
| `created_at` / `updated_at` | | `TimestampMixin` |

The snapshot is the point. `MatchReport` already documents why: *"a later change to the decision table doesn't silently reinterpret an old report."* A proposal accepted on Thursday must show the clinical picture it was accepted on, not a re-run against a pool that has since changed.

**`exchange_proposal_pairs`** — one row per pair in the cycle.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `proposal_id` | FK, indexed | |
| `donor_id`, `patient_id` | FK | |
| `owning_doctor_id` | FK doctors, indexed | Denormalised from `Donor.doctor_id` at creation so "proposals awaiting my decision" is one indexed query |
| `decision` | enum | `pending` / `accepted` / `declined` |
| `decided_at`, `decided_by_doctor_id` | | |
| `decline_reason` | String, nullable | |
| `is_open` | Boolean, indexed | See K3 |

Add an `ExchangeProposalStatus` state machine in the shape of `donor_service._ALLOWED_TRANSITIONS`, with an `IllegalExchangeProposalTransition` exception. Match that file's style exactly — it is the house pattern and its comment already names the exchange pool as the thing it protects.

```
proposed  -> {accepted, declined, expired, cancelled}
accepted  -> {completed, cancelled}
declined  -> {}
expired   -> {}
cancelled -> {}
completed -> {}
```

---

## K3. The overlap invariant, enforced by Postgres

A pair may be in **at most one open proposal**. Do not enforce this in application code alone — it is exactly the class of invariant that survives one careful implementation and then quietly breaks.

- `is_open` on `exchange_proposal_pairs` is `True` while the parent is `proposed` or `accepted`, `False` otherwise.
- Partial unique index: `CREATE UNIQUE INDEX ... ON exchange_proposal_pairs (donor_id) WHERE is_open`.
- **Exactly one service function may write proposal status**, and it updates the parent status and every child `is_open` in the same transaction. Every other caller goes through it. Write that constraint in the module docstring.

Proposal creation refuses with **409** and names the conflicting proposal when any pair is already committed. First-come-first-served is the right policy at this pool size; a coordinator who wants a different cycle cancels the blocking proposal, which is an audited act.

Take `pg_advisory_xact_lock` around creation, as `audit_service` already does for the hash chain, so two simultaneous creations serialise rather than racing to the unique index and surfacing an IntegrityError to a user.

---

## K4. Donor status, and keeping the pool honest

`load_exchange_pool` requires `Donor.status == AVAILABLE`, so donor status and pool membership are the same switch. Three rules follow:

1. **Do not reserve on proposal.** Only on full acceptance does the transition `AVAILABLE → RESERVED` fire for every donor in the cycle — already legal in `_ALLOWED_TRANSITIONS`, already audited by `updated_donor_status`. Reserving at proposal time would pull pairs out of the pool while a decision sits pending, starving the matcher on the strength of a maybe.
2. **Release on decline, cancel, or expiry.** `RESERVED → AVAILABLE` is legal. Fire it for any donor already reserved by a proposal that ends without a transplant.
3. **Pairs with an open proposal stay visible but stop being selectable.** They remain nodes in the response with an `open_proposal_id`, so the graph tells the truth about the pool — but `enumerate_cycles` skips them. Otherwise the optimizer keeps proposing cycles that creation will refuse with a 409.

Reserving a donor is a cross-hospital act performed by the system on acceptance, not by a doctor calling `PUT /donors/{id}/status`. Route it through `update_donor_status(..., commit=False)` so the state machine and the audit row both still apply, folded into the acceptance transaction.

---

## K5. Endpoints and authorisation

| Endpoint | Auth | Behaviour |
|---|---|---|
| `POST /exchange/proposals` | any doctor | Body: `{policy, pair_ids}`. Re-runs the match server-side and verifies the submitted cycle is actually in the current selected set — **never trust a client-supplied cycle**. Snapshots it, creates child rows with `decision=pending`, audits `proposed_exchange_cycle`. |
| `GET /exchange/proposals` | any doctor | `?mine=true` filters to `owning_doctor_id == me AND decision == pending` — the pending-decisions inbox. Unfiltered lists all open proposals, since exchange is cross-hospital by nature. |
| `GET /exchange/proposals/{id}` | any doctor | Full snapshot plus every pair's decision state. |
| `POST /exchange/proposals/{id}/pairs/{pair_id}/decision` | **owning doctor only** | Body `{decision, decline_reason?}`. 403 if the caller does not own that pair. On the last acceptance: parent → `accepted`, reserve all donors, audit. On any decline: parent → `declined`, release, audit. |
| `POST /exchange/proposals/{id}/cancel` | proposer or admin | Releases everything. Audits `cancelled_exchange_cycle`. |

New audit actions, matching the existing `verb_noun` past-tense convention: `proposed_exchange_cycle`, `accepted_exchange_pair`, `declined_exchange_pair`, `locked_exchange_cycle`, `cancelled_exchange_cycle`, `expired_exchange_cycle`. Every one uses `commit=False` folded into the same transaction as the state change, exactly as `update_donor_status_endpoint` does.

**Which doctor owns a pair.** The schema permits `Donor.doctor_id` to differ from the patient's `PatientDoctor.id`. **The donor's doctor decides**, because it is the donor's organ being committed and the donor status transition is the one they are already authorised for. The patient's doctor gets read visibility and appears on the proposal. Flag this to the clinical team before shipping — if in practice the recipient's centre must also consent, it becomes a second required decision per pair, which the child-row model already accommodates.

Do **not** reuse `get_donor_by_id_for_doctor` for reading a proposal. It 404s for non-owners, which is right for donor records and wrong here — every participant must be able to see the whole cycle they are part of.

---

## K6. Expiry, and the notification channel that does not exist

**There is no notification infrastructure in this codebase.** No SMTP, no mail library, no notifications table, no websockets, no push. Confirmed by grep. Multi-party acceptance needs *some* way for the other hospital's doctor to learn they have a decision pending, so:

- **In-app inbox, polled.** A pending count on the `Exchange` nav item in both `Sidebar.jsx` and `TabBar.jsx`, fed by `GET /exchange/proposals?mine=true`. Reuse the polling shape from `BackgroundJobsProvider` — this is the pattern the codebase already trusts for out-of-band state.
- **Keep the emails visible.** `donor_doctor_email` / `patient_doctor_email` are already in the response. Surface them on the proposal as tap-to-mail links so a coordinator can chase a decision the way they do today.
- **Email is a follow-up with a written trigger:** adopt it when proposals routinely sit pending longer than a working day. Do not add SMTP as part of this change.

**Expiry** defaults to 7 days. There is no scheduler, so handle it the way Part G handles spool cleanup: lazily on read (a `proposed` row past `expires_at` is reported as expired and its pairs released on next access) **and** in a sweep on the lifespan startup hook Part G introduced. Belt and braces, no new infrastructure.

---

## K7. Decision support 1 — "why wasn't this pair matched?"

The single most valuable addition, and cheap, because the answer is already being computed and thrown away. `build_exchange_graph` evaluates all n² ordered pairs and keeps only the compatible ones; the rejections vanish.

Keep **aggregate counts**, never the n² detail — at a 300-pair pool that is 90,000 results. Per pool pair, both directions:

```python
@dataclass(frozen=True)
class PairMatchExplanation:
    pair_id: uuid.UUID
    outbound_blocked: dict[str, int]   # {"abo": 11, "dsa_strong": 2, "mismatch": 1}
    inbound_blocked: dict[str, int]
    outbound_edges: int
    inbound_edges: int
    candidate_cycles: int              # cycles containing this pair
    verdict: str                       # see below
```

Four verdicts, in priority order:

| Verdict | Meaning | What the coordinator does |
|---|---|---|
| `no_donor_out` | This pair's donor is incompatible with every recipient | Structural — pool needs different donors |
| `no_donor_in` | No donor in the pool can give to this patient | **The sensitisation signal.** Desensitisation or national referral |
| `no_reciprocal_path` | Has edges, but sits in no 2- or 3-cycle | Pool composition; a 4-cycle might help, which the cap forbids |
| `lost_to_overlap` | Sits in *n* candidate cycles, none selected | The optimizer preferred an overlapping cycle |

`lost_to_overlap` is the one that matters most, because it is where the arbitrariness in K9 becomes visible. When a pair loses to an equally-weighted alternative, say so.

---

## K8. Decision support 2 — cross-policy agreement

Add `GET /exchange/match/compare`. Return the union of selected cycles with a `selected_by: list[str]` on each. A cycle chosen by all four policies is robust; one chosen by a single policy is a policy artefact.

**Enumerate once, solve four times.** Pool load, graph build and cycle enumeration are the expensive part — the ~5.6 s measured at 300 pairs is dominated by them, not by CBC. Only the weight vector differs per policy, so four policies should cost roughly 1.3× one, not 4×. Build `GraphIndex` once (its `_cpra_fraction_cache` memoisation then serves all four) and loop the solve. Keep the whole thing inside the existing `run_in_threadpool` offload.

This is also the honest fix for the dropdown nobody understands: instead of asking a coordinator to pick an optimisation policy, show them what all four agree on.

Expose `max_lkdpi_quality` in `src/constants/exchangePolicies.js` while you are here — it is implemented backend-side and unreachable from the UI.

---

## K9. Decision support 3 — waiting, hard-to-match, and deterministic tie-breaking

**Add a real waiting-time field.** `exchange_weight_policies.py` already admits the gap: *"this codebase has no dedicated 'on dialysis since' or 'waiting list since' field, only `Patient.created_at`… a real deployment would need a real waiting-time field."* Add `Patient.dialysis_start_date` (Date, nullable) — time on dialysis, not time in this database, is what allocation systems credit. Migration, `PatientCreate`/`PatientUpdate` schemas, and the patient form. `_wait_fraction` prefers it and falls back to `created_at` with the fallback disclosed in the response, so old records keep working and nobody mistakes a proxy for a fact.

**Hard-to-match view.** A ranked list of pool pairs never appearing in a selected cycle under *any* policy (reuse K8's comparison), sorted by waiting time, with cPRA and the K7 verdict alongside. This is the desensitisation and national-referral worklist.

**Deterministic tie-breaking — do this as part of "complete".** Today cycle weight under `max_transplants` is just `len(cycle)`, so a large fraction of candidate packings score identically and CBC returns whichever it reaches first. Which patients get transplanted among equal-scoring solutions is currently arbitrary. That is not acceptable in an allocation tool, even an advisory one.

Use **integer weights with a lexicographic tie-break**:

```python
PRIMARY_SCALE = 1_000_000
# tie-break: total waiting fraction across the cycle, 0..300 for a 3-cycle
scaled = int(round(policy_weight(cycle) * PRIMARY_SCALE)) + int(round(wait_total(cycle) * 100))
```

The tie-break can never exceed 300, so it only decides between cycles whose primary weights differ by less than 0.0003 — numerically meaningless differences. Integer coefficients also keep CBC exact. **Return the unscaled `policy_weight` in the API response** so the UI keeps showing a number a human recognises.

The rule this encodes — *among equally good solutions, prefer the one serving the longest-waiting patients* — is defensible and explainable. Arbitrary is not.

---

## K10. Mobile-first redesign

The shell needs nothing: `Topbar` and `TabBar` are already `md:hidden`, `Sidebar` is already `hidden md:flex`, `DashboardLayout` already handles `pb-24 md:pb-6` and safe-area insets, and Exchange is already in the mobile tab bar. **All the work is inside the exchange pages.**

**Cycle cards replace the table, at every breakpoint.** Do not build two representations. Each selected cycle is a `Card`: a vertical chain of pairs, each showing patient blood type ← donor blood type, hospital, and the per-hop mismatch and DSA badges, closing back to the first. Weight and cycle size in the header. Proposal state and the accept/decline action in the footer when it is yours. This reads better than the four-column table on a desktop too — delete `Table` from this page.

**The graph becomes a desktop affordance.** `ExchangeCycleGraph` keeps its `viewBox` and its `min-w-[420px]`, wrapped in `hidden md:block`. Below `md`, offer a "View graph" control that opens it full-screen in a sheet. **Do not build pan/zoom.** A 40-node circular layout is not a phone interface, and the cards carry every fact the graph does. Spending the effort on pinch-zoom would be building the wrong thing well.

Specifics:

- **Stat tiles.** `grid-cols-3` is the first thing that breaks. Keep three columns — they are three short numbers — but drop the label to `text-xs` with `leading-tight` and the value to `text-xl` at base, restoring larger sizes at `sm:`. Verify at 320 px, not just 375 px.
- **Policy selector.** Keep `Select`; the native mobile picker is better than a four-option `SegmentedControl` crammed into 375 px. If K8 lands, the compare view largely replaces the dropdown anyway.
- **Sheet primitive.** Add `variant="sheet"` to the existing `Modal` rather than a new component — bottom-anchored and full-width below `md`, centred `max-w-md` above. Modal already owns the portal, Escape handling, backdrop click and body-scroll lock; reuse all of it.
- **Sticky action bar** on the proposal detail view for accept/decline, offset above the `TabBar` with `env(safe-area-inset-bottom)`.
- **Touch targets are already fine** — `Button` floors every size at `min-h-11`. Any new tappable row must meet the same bar.
- Add the two genuinely missing primitives: `Spinner` (currently inlined ad hoc in `ExchangePoolPage` and `Button`) and `EmptyState` (every page hand-rolls a bordered div).

**One hard constraint, from your own `@theme` comment:** *"Clinical state: clear / moderate / high-moderate / high-risk — reserved ONLY for clinical status… a color meaning something different in two places is a safety bug in this app."* Proposal workflow states are **not** clinical. Do **not** render "accepted" in `--color-clear` green or "declined" in `--color-high-risk` red — on a page that also shows DSA and mismatch severity in those exact colours, that collision is precisely the bug the comment warns about. Use neutral and accent tokens for workflow state, and keep the clinical palette for the clinical badges.

---

## K11. Incidental fixes while in here

- **`Topbar` shows "Dashboard" on every page.** `DashboardLayout` passes a hardcoded `title="Dashboard"` even though routes declare `handle={{ title }}`. Read it via `useMatches()`. Mobile users see this header on every screen, so it matters more than it looks.
- **`NAV_ITEMS` is duplicated** between `Sidebar.jsx` (7 items + admin-gated Audit Log) and `TabBar.jsx` (5 items). Extract one shared list with a `mobile: boolean` flag. K6 adds a pending-count badge to Exchange in both — do not add it twice.
- **Width mismatch.** `ExchangePoolPage` wraps in `max-w-4xl` inside `DashboardLayout`'s `max-w-6xl`. Pick one.
- **`src/App.css`** is leftover Vite template CSS imported nowhere. Delete it.

---

## K12. Sequencing

Four independently shippable stages. Do not merge them.

1. **K7 — explanations.** Pure read-only addition to an existing endpoint. No schema change, immediate value, zero risk.
2. **K10 — mobile view.** Frontend only, builds on stage 1's data. Ships the visible win early.
3. **K9 — waiting field and tie-break.** One migration plus a weight change. Land the tie-break and re-run `research/exchange_policy_comparison.md`; its numbers already predate Part I's cPRA dedup and will move again here.
4. **K2–K6 — the proposal workflow.** The largest and riskiest, and it depends on nothing above. Do it last so the first three are not blocked behind it.

K8 (cross-policy) can slot in after 1 or 3 — it is independent, but the hard-to-match list in K9 consumes it, so land it before that part of stage 3.

---

## K13. Tests

**Backend**

- Proposal state machine: every legal transition succeeds, every illegal one raises `IllegalExchangeProposalTransition` — same shape as the donor status transition tests.
- **The overlap invariant, at the database level.** Two open proposals sharing a donor must fail on the partial unique index, not just on the application check. Test with the application check bypassed.
- Concurrent creation: two simultaneous `POST /exchange/proposals` for overlapping cycles → one 201, one 409, never two 201s and never an unhandled IntegrityError.
- Acceptance: donors go `AVAILABLE → RESERVED` **only** on the last acceptance, never before; decline and cancel release them; a proposal whose donors were released leaves those pairs back in the pool on the next match.
- Authorisation: a doctor who does not own a pair gets 403 on its decision endpoint but 200 on `GET /exchange/proposals/{id}`.
- `POST /exchange/proposals` rejects a client-supplied cycle that is not in the current selected set.
- Expiry: a `proposed` row past `expires_at` reports as expired and releases its pairs, on both the lazy read path and the startup sweep.
- Snapshot immutability: change `HLA_FREQUENCY_TABLE_VERSION` after proposing and confirm the stored snapshot still reports the old version.
- K7 verdicts: a fixture pool producing one pair of each of the four verdicts.
- K8: a cycle selected by all four policies reports all four in `selected_by`; enumeration runs once (assert via a spy on `enumerate_cycles`).
- K9: identical-weight cycles resolve to the one with the longer-waiting patients, **deterministically across 100 runs**. And a `dialysis_start_date` of `None` falls back to `created_at` with the fallback flagged.

**Frontend**

- Extend `ExchangePoolPage.test.jsx`: cycle cards render the full chain; a pair the current doctor owns shows accept/decline; one they do not own does not.
- Pending-count badge appears in nav when `?mine=true` returns rows.
- Workflow state badges use accent/neutral tokens — **assert the clinical colour classes are absent.** This is the K10 safety rule, and a class assertion is the only way to keep it from eroding.
- Note the limits honestly: `test.globals` is off, `matchMedia` is not stubbed in `src/test/setup.js`, and jsdom has no layout engine, so **responsive behaviour cannot be verified by rendering at a width.** Keep the responsive layer purely CSS with no JS breakpoints, so there is nothing behavioural to test; assert class presence for the critical switches (`hidden md:block` on the graph). If real viewport coverage is wanted later, that is a Playwright job, not a Vitest one.

---

## K14. Do not

- **Do not trust a client-supplied cycle.** `POST /exchange/proposals` re-runs the match and verifies the cycle server-side. A crafted body must not be able to reserve arbitrary donors.
- **Do not enforce the overlap invariant in application code alone.** The partial unique index is the guarantee; the application check is the friendly error message.
- **Do not reserve donors at proposal time.** Pending proposals would starve the pool on the strength of a maybe.
- **Do not let one doctor accept on another's behalf** — not even an admin. Admin can cancel; only the owning doctor can accept.
- **Do not use the clinical colour tokens for workflow state.** Green-for-accepted next to green-for-clinically-clear is the exact collision `index.css` warns is a safety bug.
- **Do not build two representations of a cycle.** Cards at every breakpoint; the graph is supplementary.
- **Do not build pan/zoom for the mobile graph.** Cards carry the same facts.
- **Do not add SMTP or a queue for notifications** in this change. Polled in-app count, plus the mailto links that already exist.
- **Do not raise the cycle cap above 3 while adding this.** `enumerate_cycles` has no 4-cycle path — it is the algorithm, not a constant — and simultaneous-nephrectomy logistics are the reason for the cap in the first place.
- **Do not skip re-running `research/exchange_policy_comparison.md`.** Its equity figures predate both Part I's cPRA dedup and K9's tie-break, and stale published numbers on an allocation tool are worse than none.
