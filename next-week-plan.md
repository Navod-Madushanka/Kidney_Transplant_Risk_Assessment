# Next week — status and plan

**Verified against the working tree on 19 August. HEAD is `2bb5d1b` "Bug fixing in exchange pair".**

---

## The one-paragraph version

The build is in better shape than the to-do list suggests: **Part K landed completely**, Parts G–J are in, and there are no TODO markers anywhere in the source. What's left is not really engineering — it's **clinical input you don't have yet, and a deployment artifact that doesn't exist.** Almost every remaining code decision (DSA thresholds, the cPRA >60% band, the proposal expiry window) is blocked on the doctors' meeting, so the highest-leverage thing you can do next week is get that meeting to happen and spend the rest of the week on the work that *isn't* waiting on an answer.

Two things need doing in the first hour, before any other work.

---

## Fix these before you write a line of code

**1. There's a stale `.git/index.lock` on the laptop.** Git reported it could not unlink it. Local git writes may be silently failing. Delete it and confirm `git status` runs clean.

**2. Your diff is 94% line-ending noise.** 163 files show as changed; only **10 have real content changes**. The other 153 are CRLF↔LF flips. If you commit now, every one of those files looks fully rewritten and `git blame` is destroyed for the whole project.

Do this, in this order:

```
git rm --cached -r .            # after adding .gitattributes
echo "* text=auto eol=lf" > .gitattributes
git add --renormalize .
git commit -m "Normalise line endings"   # ONE isolated commit, nothing else in it
```

**3. Then commit the four real fixes that are sitting unsaved and unbacked-up.** These are genuine work you'd lose to a disk failure:

- the CORS env-driven fix (`config.py` + `main.py`)
- the `errors` passthrough in `ocrNormalize.js`
- OCR-failure surfacing in `NewPairPage.jsx`
- **the bead-verification bug fix in `compatibilityWizard.js`** — its own comment says it shipped and was blocking real submissions

---

## What's done

| Area | Status |
|---|---|
| Parts G, H, I, J | Landed. Upload spooling, DB session scoping, bead reconciliation, the guarded auto-save |
| **Part K — all stages** | Proposal workflow, explanations, cross-policy compare, `dialysis_start_date` + deterministic tie-break, mobile cycle cards. Nothing half-finished |
| Compatibility pipeline | All 7 steps, decision table, 4 verdicts, LKDPI, donor risk projection |
| Paired exchange | Pool, graph, optimiser, 4 policies, proposals, inbox, hard-to-match |
| Audit | Hash-chained, advisory-locked, sequence-ordered |
| Tests | ~831 across three suites, no deletions detected |
| Ollama pinned, `--reload` out of prod image | Done |
| CORS env-driven, NewPairPage submit hint | Done — **but uncommitted** |
| Documentation | Two reference PDFs, deployment plan, presentation script, capture sheet |

## What's left

| # | Item | Blocked on doctors? |
|---|---|---|
| 1 | `POST /auth/register` open and unauthenticated | No |
| 2 | No admin-promotion path (only direct SQL) | No |
| 3 | No prod compose, no `.env.example`, root README broken, ocr-service README empty | No |
| 4 | 4 missing `.catch()` — new patient, new donor, accept/decline, cancel | No |
| 5 | No confirmation on an irreversible exchange accept/decline | No |
| 6 | No "2–3 minutes per page" copy on extraction | No |
| 7 | Real patient identifiers in **9 files** (wider than previously found) | No |
| 8 | F12 not implemented; UI copy still contradicts the code | Partly |
| 9 | Sidebar shows raw email — deeper than a rename, see below | No |
| 10 | `ollama` service still has no `mem_limit` | No |
| 11 | Lint red — 69 over-length lines, 11 `set-state-in-effect` | No |
| 12 | Structured OCR warnings still dropped at the backend boundary (I6) | No |
| 13 | `cpra_fraction` raw-vs-normalised antigen bug, still untested | No |
| 14 | cPRA dedup never disclosed, no version bump | **Yes** |
| 15 | DSA floor and bands, cPRA >60% points, mismatch loci, LKDPI bands | **Yes** |
| 16 | Proposal expiry window (7 days vs 2–4 week approvals) | **Yes** |
| 17 | Donor age / eligibility rules | **Yes** |

**Item 9 is worse than reported.** `AuthProvider.jsx:52` only stores `{access_token, email}` — the doctor's name and hospital are not in the session at all. Renaming the camelCase keys won't fix it; you need a `/auth/me` call on login or extra JWT claims.

---

## The week

### Monday — hygiene, then the two security blockers

**Morning.** The three items above: index.lock, `.gitattributes` renormalise commit, then commit the four real fixes separately so they're reviewable.

**Afternoon.** Close `POST /auth/register`. Add an admin-promotion path — a small management script is enough (`uv run python -m app.scripts.promote_admin <email>`), audited like everything else. These two are the reason the system cannot be exposed to anything, and they're a few hours together.

### Tuesday — the deployment artifact

`docker-compose.prod.yml` covering all five services, `.env.example` with every variable named and no values, a root README that has actually been followed, and something in `ocr-service/README.md`. Add the `ollama` `mem_limit` while you're in the compose file.

**The test is not "it runs on my machine."** Clone to a clean directory, follow only the README, and see if it comes up. If it doesn't, it isn't finished. This also gives you a reproducible way to run the demo instead of a dev laptop.

### Wednesday — the things a clinician would notice

- The four `.catch()` blocks. An accept/decline that fails silently on the newest feature is the worst possible demo moment.
- Confirmation dialog on accept/decline — it's an irreversible commitment behind one click.
- The "2–3 minutes per page" line on extraction.
- `DetailsStep` Continue: the red banner is there, but the button still bare-returns with no feedback. Disable it, or explain why it can't proceed.
- **Replace the real patient identifiers.** It's in 9 files, including ocr-service fixtures and `llm-migration-spike`, not just the two we found before. This is mechanical, it takes an hour, and it's the item with actual governance consequences.
- **Resolve the F12 contradiction.** Cheapest correct action: fix the copy to match what the code does, and take the question to the doctors rather than deciding it yourself.

### Thursday — green the gates

- `ruff check --fix`, then the ~69 long lines by hand.
- The 11 `set-state-in-effect` eslint errors. These are real React problems, not style noise — fix them rather than suppressing.
- `/auth/me` on login so the sidebar shows a name and a hospital instead of an email address and the word "doctor".
- Re-run all three suites. Confirm 504 / 249 / 78 still green after a week of changes.

### Friday — meeting preparation, and nothing else

Print the capture sheet. Seed the database. Pre-run every extraction. Promote your demo account to admin. Rehearse the script end to end with a timer — the Step 5 block will run long, and it should.

**Write no new features on Friday.** A rehearsed demo of what exists beats an unrehearsed demo of slightly more.

### All week, in the background

- **Chase the doctors' meeting.** Send the capture sheet ahead of it so they arrive having thought about the numbers.
- **Email the Grifoni corresponding author** for Supplementary Table III. One email, best-case outcome is the haplotype data nobody else has.
- **Email ICTA** about Lanka Government Cloud eligibility.

---

## What not to do next week

This list matters as much as the other one.

- **Don't touch any clinical constant.** DSA floor and bands, cPRA >60% points, mismatch loci, LKDPI bands, donor age rules — all of it is on the capture sheet. Changing them now means changing them twice, and the second change invalidates whatever tests you write for the first.
- **Don't bump `HLA_FREQUENCY_TABLE_VERSION` yet.** Do it once, when the doctors have signed off on the cPRA change together with any threshold changes, so there's one clean version boundary in the record rather than three.
- **Don't start haplotype-aware cPRA.** It's a research project and it depends on data you don't have yet.
- **Don't build the split-GPU deployment.** Get the single-box artifact working first; the split is a later optimisation and it needs the compose file to exist either way.
- **Don't fix the live scoring harness (I11).** You already made a considered decision there — bead-ID anchors were explicitly rejected in favour of a structural invariant. That's fine. Revisit only if you actually pursue constrained decoding.
- **Don't rewrite git history** for the 3.5 MB tarball that got committed in `2bb5d1b` — that was an artifact of my audit and I should have told you to delete it before you committed. It's not worth a history rewrite. Just delete the file going forward.

---

## Two open questions I couldn't answer from the code

1. **When is the doctors' meeting?** If it's inside next week, move Friday's preparation earlier and let Thursday's lint work slip — the meeting is worth more than a green CI badge.
2. **`kidney-backend/uploads/report_files/` now holds 2 files where 20 real lab scans were before.** Worth confirming those were moved deliberately and are backed up somewhere, rather than lost.

Also worth resolving: the ocr-service LLM timeout was raised from 180 s to 300 s (uncommitted), while the deployment plan records 120 s as the CPU failure point. Two different numbers are in play — pick one and make the plan match the code.
