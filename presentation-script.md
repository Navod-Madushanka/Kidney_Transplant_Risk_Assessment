# Presentation script — Kidney Transplant Compatibility System

**For:** transplant physicians, histocompatibility lab staff, and academic supervisors
**Duration:** ~40 minutes presenting, 30+ minutes structured questions
**Primary goal:** not to impress. To leave with **real numbers replacing every value we guessed.**

---

## Part 0 — How to run this meeting

### Frame it correctly from the first minute

The instinct in a room like this is to present a finished thing and defend it. Do the opposite. The system contains roughly **forty clinical values that were chosen without a clinical source** — MFI cutoffs, mismatch thresholds, risk bands, allocation weights. Every one of them is a decision that belongs to the people in that room, not to the developer.

Say that out loud at the start. It changes the room from *evaluating* to *contributing*, and it is also simply true.

### Who needs to be there

| Role | Answers questions about |
|---|---|
| Transplant nephrologist / surgeon | Thresholds, what halts, risk vocabulary, eligibility |
| Histocompatibility / immunology lab | MFI cutoffs, DSA bands, loci, serological vs allele level, the frequency table |
| Transplant coordinator | Workflow, who uses it, approvals, timelines |
| Academic supervisor | Validation methodology, publication, ethics approval |

If the lab is not represented, roughly a third of the questions cannot be answered — reschedule rather than guess again.

### Prepare before the room

1. **Pre-run every extraction.** Live OCR on CPU will time out; even on GPU a bead page is ~7 minutes of dead air. Open a completed job.
2. **Replace the real patient identifiers** in anything on screen. Test fixtures currently contain a real name and NIC.
3. Promote your demo account to admin so the audit log is visible: `UPDATE doctors SET is_admin = true WHERE email = '…';`
4. Seed enough data that no screen shows an empty state.
5. Print **Appendix A** — one copy per clinician. Ask them to write on it.
6. Nominate a **scribe** who is not you. You cannot present and capture decisions simultaneously.

### A rule for the discussion

When a clinician gives you a number, ask two follow-ups every time:

> *"Is that your centre's practice, or is it from a guideline we can cite?"*
> *"Is that a hard stop, or a flag for review?"*

The second question matters more than the first. Most of what the system currently treats as an automatic halt may be intended as a prompt for a human.

---

## Part 1 — Opening (3 min)

> Good morning, and thank you for the time.
>
> I'm going to show you a system that supports two decisions: whether a specific living donor is compatible with a specific recipient, and — when they aren't — whether a swap with another incompatible pair could work.
>
> I want to be direct about why I asked for this meeting. The software is built and tested. What it does not have is clinical authority. There are around forty numbers inside it — antibody cutoffs, mismatch thresholds, risk bands — and I chose most of them myself from reading, not from practice. Some of them I'm confident about. Several I'm fairly sure are wrong.
>
> So this is not a demonstration asking for approval. It's a walkthrough asking you to replace my assumptions with your practice. I have a list of every place I guessed, and I'd like to leave today with as many of those filled in as possible.
>
> I'll show you the system in the order a doctor would actually use it, and I'll stop at each point where there's a number I need from you.

**[SLIDE: one line — "Forty numbers. I guessed most of them. Please correct me."]**

---

## Part 2 — The problem and the current workflow (4 min)

> Every living donor transplant needs a compatibility assessment: blood group, tissue typing, antibody screening, crossmatch. Today at this unit that assessment is assembled by hand from several lab reports, and the reasoning behind a decision lives in a clinician's head and their notes.
>
> Two things follow from that. First, it takes time. Second, when someone revisits a decision six months later, the reasoning is hard to reconstruct.
>
> This system does three things. It reads the lab reports. It runs the same checks in a fixed order and records every intermediate value. And when a pair is incompatible, it looks for a swap.

**[ASK — Q1–Q6, workflow. See Appendix A.]** Do not skip these. Everything downstream depends on the answers, and if the workflow assumption is wrong the thresholds barely matter.

> Before I go further — can I check how this actually works here today? How long does a full compatibility assessment take, who assembles it, and at what point in the workup does it happen?

---

## Part 3 — Registration and data entry (3 min)

**[DEMO]** Register a patient, then a donor, then link them as a pair.

> Patients and donors are separate records, linked by an intended recipient. Everything is scoped to the doctor who created it, except paired exchange, which I'll come to.
>
> Each record carries three verification flags — demographics, HLA typing, and for patients the antibody profile. **Nothing can be used in a compatibility check until a human has confirmed it.** That's the boundary between machine-read data and clinical data, and it's enforced: the check refuses outright, and no report is created.

**[ASK — Q7–Q9, eligibility.]**

> One gap I want to flag rather than hide. Published Sri Lankan guidance says a male living donor must be at least 25 and a female donor at least 30. **The system does not check that anywhere.** It also doesn't enforce any minimum eGFR or maximum BMI for donation. Should it block those, warn about them, or stay out of it?

---

## Part 4 — Reading the lab reports (5 min)

**[DEMO]** Open a **pre-completed** extraction job. Walk through the four document slots and the extracted values.

> The system reads four documents: the HLA typing report, the crossmatch report, and the two pages of the bead specificity chart. A local vision model runs on our own hardware — no patient image is sent to any external service.
>
> The bead chart is the hard one. It's a dense table of around a hundred rows, and asking the model to read it in one pass makes it hallucinate — we saw it report six different antigens all with the same MFI. So the page is cut into eight overlapping horizontal strips and read strip by strip. That's why it takes two to three minutes a page.
>
> Overlapping strips means some rows get read twice, so there's a reconciliation step: readings are matched by the bead's own ID number, and if two reads of the same bead disagree, the row is flagged rather than silently resolved. Disagreements that cross a clinically decisive threshold are always flagged, however small — a 990 against a 1010 is only 2% apart, but it straddles the DSA floor.
>
> I want to be honest about accuracy. HLA typing and crossmatch extraction match the source reliably. **Bead specificity does not** — in our own testing it matched far fewer rows than we'd accept. That's why every bead extraction carries a mandatory verify-against-source warning, and why the doctor must confirm the whole chart before it can be used.

**[ASK — Q10–Q14, extraction.]**

> Given that accuracy, two questions. Is machine reading of the bead chart worth having at all, or would you rather type those rows and have us drop the feature? And is the single confirm-the-whole-chart toggle acceptable for a hundred rows, or does each row need its own sign-off?

---

## Part 5 — The compatibility check, step by step (12 min)

This is the core of the meeting. **Budget the most time here and expect to be interrupted — that is the point.**

> The check runs seven steps in a fixed order. Four can stop it; two are informational; the last classifies what survived. Every step's result is recorded, so you can always see where a decision came from.

### Step 1 — Blood group

**[DEMO]** Show the ABO gate.

> Standard OPTN compatibility. Rhesus is displayed but not used, on the basis that RhD doesn't drive rejection in kidney transplantation the way ABO does.

**[ASK — Q15.]** *Is excluding Rh correct? And do you ever do ABO-incompatible transplants with desensitisation here — because right now ABO incompatibility is an absolute stop.*

### Step 2 — Sensitisation history

> Prior transfusions, pregnancies and transplants each carry a weight — 0.5, 1.0 and 2.0 — and produce a score. **That score currently does nothing.** It's displayed and gates nothing, because nobody has told me what rule it should trigger.

**[ASK — Q16–Q17.]** *Should sensitisation history change anything automatically? If so, what rule? And are those relative weights right?*

### Step 3 — HLA mismatch

**[DEMO]** Show the per-locus breakdown.

> Mismatches are counted across three loci — A, B and DRB1 — as the number of donor alleles the recipient doesn't carry. Zero to six. **At six the check stops.**

**[ASK — Q18–Q21.]** *Three questions here, and I suspect I have at least one wrong.*

> *One: should DQB1 count? I've only got A, B and DRB1.*
> *Two: is a full six-out-of-six mismatch really an absolute contraindication in a living donor with modern immunosuppression — or should that be a flag, not a stop?*
> *Three: when a locus is untyped I score it as the worst case, two mismatches. Is that the right default, or should the check simply refuse to run?*

### Step 4 — cPRA

> This estimates what percentage of the general donor population the patient would react against. Antibodies above 2,000 MFI count as sensitisations, and their antigen frequencies are combined as a union.
>
> The frequencies come from a study of 714 blood-bank donors in Colombo — Grifoni and colleagues, 2018 — counted from the raw genotype data rather than transcribed from the paper.
>
> Two things to flag. The calculation assumes antigens occur independently. They don't — HLA is inherited in haplotypes — so **this overstates cPRA**, and I couldn't get the haplotype table to correct it. And bands are under 30, 30 to 60, and over 60 percent.

**[ASK — Q22–Q26.]** *Is 714 Colombo donors the right reference population, or does the NBTS have something better? Is the independence approximation acceptable to you, or does it make the number unusable? And critically — **there is no risk score assigned to a cPRA above 60%**, because nobody gave me one. The system currently refuses to produce a risk level at all in that case. What should it be?*

### Step 5 — Donor-specific antibodies

**[DEMO]** Show a DSA match with its band, then a halted report.

> The virtual crossmatch. Any antibody at or above 1,000 MFI against an antigen the donor carries is a DSA. Three bands: weak from 1,000, moderate from 2,000, strong from 5,000. **Only strong halts the check.** Weak and moderate leave the pairing viable and flag it for desensitisation review.
>
> Note there are two different MFI numbers in this system: 1,000 for what counts as a DSA, and 2,000 for what counts as a sensitisation in the cPRA calculation. That split was deliberate, but it was my decision.

**[ASK — Q27–Q32.]** *This is the block I'm least confident about. What is your actual DSA floor? Where are your band boundaries? Should moderate DSA halt as well? Should anything halt automatically at all, or should the system only ever flag and let the clinician decide? And is having two different cutoffs right, or should they be one number?*

> One more, for the lab: we match antibodies at the serological level — the Sero column on the bead chart, not the allele column. Is that sufficient, or do you need allele-level matching? And related: **antibodies against DRB3/4/5, DQA1 and DPA1 are currently invisible** to this check. Is that a gap that matters clinically?

### Step 6 — Physical crossmatch

> Unlike everything else, this isn't computed or read from a file. The doctor enters their own reading of the lab crossmatch on every check. We deliberately never store it as a stored yes/no, so a stale result can't quietly drive a new decision. A positive result stops the check; no result at all gives you an "awaiting crossmatch" report rather than a verdict.

**[ASK — Q33–Q34.]** *Is re-entering it every time the right behaviour, or does it become friction? And do T-cell and B-cell results need to be treated differently — right now they're recorded separately but only the overall reading drives the decision.*

### Step 7 — Risk level

**[DEMO]** Show the final risk level and the verdict.

> The only arithmetic in the whole verdict: the mismatch band contributes zero, one or two points, the cPRA band zero or one, and the total maps to one of four labels — Low, Low-Average, High-Average, High Risk.
>
> I should show you something awkward. There are **two different risk vocabularies** in the system right now. An older scoring method over all nine loci produces labels like "High-Moderate Risk" on a different scale, and it's still computed alongside the new one.

**[SLIDE: the two scales side by side.]**

**[ASK — Q35–Q38.]** *Which vocabulary do you want? Should I delete the old one? Are those four labels meaningful to you — would you act differently on Low-Average versus High-Average? And are the point weights right: should a mismatch band really count double a cPRA band?*

### The verdict

> Everything resolves to one of four verdicts: Compatible, Proceed with Caution, Cannot Assess, or Not Compatible.
>
> There is deliberately **no compatibility percentage**. A single 0-to-100 number across blood group, mismatch, antibodies and crossmatch would imply relative weights I have no basis for. I'd rather show you four categories and the evidence than one number that looks more precise than it is.

**[ASK — Q39.]** *Is that the right call, or would a single score actually be more useful to you in practice?*

---

## Part 6 — Donor quality and donor safety (4 min)

**[DEMO]** The LKDPI card with its contribution chart, then the donor risk projection.

> Two separate things here, both about the donor rather than the pairing.
>
> **LKDPI** predicts graft longevity from thirteen donor characteristics. It's from a 2016 US study of 36,000 transplants. It never affects the verdict — it's shown alongside. I want to be blunt about its limits: its discrimination is modest, around 0.59 in the original cohort and 0.55 in European and Canadian validation, a Japanese cohort found no association at all, and **it has never been validated in any South Asian population.** Its only ethnicity term is African-American versus not, so every Sri Lankan donor scores zero on it.
>
> **Donor ESRD risk** uses the Grams model from the New England Journal, projecting the donor's own long-term kidney failure risk. There's also a contraindication screen — low eGFR, high albuminuria, uncontrolled blood pressure — but **it currently blocks nothing.** It's advisory only.

**[ASK — Q40–Q44.]** *Given the validation problem, should LKDPI be shown at all — or does displaying a number that looks authoritative do more harm than good? If we keep it, where should the band boundaries sit? And should the donor contraindication screen actually block a match, or stay advisory? Three of the screen's criteria we can't assess at all because we don't collect the data — insulin-dependent diabetes, four or more antihypertensives, and established cardiovascular disease. Should we be collecting those?*

---

## Part 7 — Paired exchange (8 min)

**[DEMO]** The pool, the cycle graph, cycle cards, the comparison view, the hard-to-match list, then a proposal and its acceptance flow.

> When a pair is incompatible, their donor may still be able to give to someone else's recipient. The system builds a graph of every viable donation across all participating hospitals and finds closed loops — two-way swaps and three-way cycles.
>
> It then solves for the best set of non-overlapping cycles. "Best" is a policy question, so there are four: most transplants, best tissue match, an equity weighting that favours highly sensitised and long-waiting patients, and best donor quality. You can compare all four side by side — cycles that every policy agrees on are the robust ones.
>
> On our test pool, all four policies transplant the same number of people but not the same people. The policies that reach the most sensitised patients are most-transplants and equity. Optimising for the best tissue match inverts that — **it quietly leaves the hardest-to-match patients in the pool.** That trade-off is yours to make, not mine.
>
> Every pair that isn't matched gets an explanation: no donor can give to them, their donor can't give to anyone, they're in no closed loop, or they lost to an overlapping cycle.
>
> Committing to a swap requires each pair's own doctor to accept. Only when all of them have accepted are the donors reserved.

**[ASK — Q45–Q53. This block matters most.]**

> Now the questions I most need answered, and the first one may make the rest moot.
>
> **Has a paired kidney exchange ever been done in Sri Lanka?** Published guidance I found says it hasn't been tried here. Is it permitted under the Transplantation of Human Tissues Act and the DGHS approval process? Would an ethics review committee approve a swap between two unrelated pairs?
>
> If it is possible — I've read that DGHS approval takes two to four weeks per pair. **My system expires a proposal after seven days.** That's almost certainly wrong. What should the window be, given approvals have to run in parallel for two or three pairs?
>
> Is a three-way simultaneous nephrectomy logistically feasible here, or should we cap at two-way?
>
> Which policy should be the default? Right now it's most-transplants, which was my choice, not a clinical one.
>
> And who should have to accept a cycle — the donor's doctor, the recipient's doctor, or both? I made it the donor's doctor because it's their donor's organ being committed.

---

## Part 8 — Safety, audit and provenance (3 min)

**[DEMO]** The audit log.

> Three things worth showing.
>
> Nothing enters a clinical calculation until a human has verified it — five separate confirmations across the patient and donor records.
>
> Every consequential action is written to a **hash-chained** audit log: each entry includes a hash of the one before, so altering or deleting a historic record breaks the chain detectably. Entries are ordered by a database sequence rather than a timestamp, so a clock change can't reorder them. It's tamper-evident, not tamper-proof — I'd rather describe it accurately.
>
> And every report **snapshots the reference data in force when it was generated** — the antibody thresholds, the frequency table version, the whole verdict. If we change a threshold next year, a report from today still means what it meant today.

**[ASK — Q54–Q55.]** *How long must these records be retained? And who should be allowed to create accounts — right now that's not properly controlled and it needs to be before this touches real patients.*

---

## Part 9 — Where it runs, and what leaves the building (2 min)

> Everything runs on hardware we control. The vision model that reads the lab images runs locally — no patient image goes to any external service, and no clinical data leaves the country.
>
> Sri Lanka's data protection act has been in force since March 2025. It doesn't require data to stay in the country, but keeping it here is much simpler to defend than the alternative.

**[ASK — Q56.]** *Does the hospital have a position on where this data may be hosted, and is there an ethics or IT approval we need before a pilot?*

---

## Part 10 — Closing and the ask (2 min)

> To summarise what this does: it reads the lab reports, runs the compatibility assessment in a fixed order with every step recorded, tells you where a decision came from, and finds swaps when a direct transplant isn't possible.
>
> What it does not have is your numbers. The sheet in front of you lists every value I guessed. Some of them — the antibody cutoffs, the mismatch threshold, the missing cPRA band — change what the system tells a doctor. I'd rather have three of them right than forty of them plausible.
>
> Anything you can fill in today I'll implement. Anything you want to think about, I'll come back for.
>
> One last thing I'd ask the academic side: what would convince you this is safe enough to use on a real patient? My instinct is a retrospective run against decisions you've already made, where we compare the system's verdict to yours. If that's the right shape, I'd like to design it with you.

---

# Appendix A — Decision capture sheet

**Hand one copy to each clinician. Ask them to write on it.** Anything left blank is still a guess.

## Workflow and users

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q1 | How is a compatibility assessment done today, and by whom? | — | |
| Q2 | How long does it take end to end? | — | |
| Q3 | At what point in the workup does it happen? | — | |
| Q4 | Who would use this system — nephrologist, coordinator, lab? | Doctor | |
| Q5 | How many living donor transplants per year here? | Unknown | |
| Q6 | Does the report go into the patient notes? In what form? | Not addressed | |

## Eligibility

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q7 | Minimum donor age — enforce, warn, or ignore? | **Not checked at all** | |
| Q8 | Minimum donor eGFR / maximum BMI for donation? | Not enforced | |
| Q9 | Any other hard eligibility rules to enforce? | None | |

## Document extraction

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q10 | Are these the right four documents? | HLA typing, crossmatch, 2 bead pages | |
| Q11 | Is machine-reading the bead chart worth keeping, given accuracy? | Keep, with mandatory verification | |
| Q12 | One verification toggle for ~100 rows — acceptable? | Yes | |
| Q13 | Serological level (Sero column) sufficient, or allele level needed? | Serological only | |
| Q14 | Is stripping the Bw4/Bw6 suffix correct? | Yes | |

## Step 1 — Blood group

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q15 | Exclude Rh? Ever do ABO-incompatible with desensitisation? | Rh excluded; ABO is a hard stop | |

## Step 2 — Sensitisation history

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q16 | Should sensitisation history gate anything? What rule? | **Gates nothing** | |
| Q17 | Are the weights right — transfusion 0.5, pregnancy 1.0, prior transplant 2.0? | Project slides | |

## Step 3 — HLA mismatch

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q18 | Which loci should count? | A, B, DRB1 only | |
| Q19 | Should DQB1 be included? | No | |
| Q20 | Is 6/6 mismatch an absolute stop, or a flag? | **Absolute stop** | |
| Q21 | Untyped locus — worst-case score, or refuse to run? | Worst case (2) | |

## Step 4 — cPRA

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q22 | MFI cutoff for a "sensitised" antigen? | **2,000** | |
| Q23 | Are the bands right? | <30% / 30–60% / >60% | |
| Q24 | **What risk points for cPRA >60%?** | **None — system refuses to classify** | |
| Q25 | Is 714 Colombo donors the right reference population? | Grifoni 2018 | |
| Q26 | Is the independence approximation acceptable? | Disclosed, overstates cPRA | |

## Step 5 — Donor-specific antibodies

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q27 | MFI floor for a DSA? | **1,000** | |
| Q28 | Band boundaries? | 1,000 / 2,000 / 5,000 | |
| Q29 | Which band should halt? | Strong only (≥5,000) | |
| Q30 | Should *anything* halt automatically, or only flag? | Strong DSA halts | |
| Q31 | Two different cutoffs (1,000 DSA / 2,000 cPRA) — correct? | Deliberate split | |
| Q32 | Do DRB3/4/5, DQA1, DPA1 antibodies matter? | **Currently invisible** | |

## Step 6 — Crossmatch

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q33 | Re-enter every check, or store it? | Re-enter, never stored | |
| Q34 | Should T-cell and B-cell be treated differently? | Only overall reading used | |

## Step 7 — Risk level and verdict

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q35 | Which risk vocabulary — old or new? | Both exist | |
| Q36 | Are the four labels meaningful and actionable? | Low / Low-Avg / High-Avg / High | |
| Q37 | Are the point weights right (mismatch 0-2, cPRA 0-1)? | Project slides | |
| Q38 | Should the legacy 9-locus score be deleted? | Still computed | |
| Q39 | Is "no composite score" the right call? | No 0–100 number | |

## Donor quality and donor safety

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q40 | Show LKDPI at all, given no South Asian validation? | Shown, advisory | |
| Q41 | LKDPI band boundaries? | 0 / 20 / 40 (invented) | |
| Q42 | Should the donor contraindication screen block a match? | **Advisory only** | |
| Q43 | Collect the three unassessed criteria? | Not collected | |
| Q44 | Should donor ESRD projection gate anything? | Advisory only | |

## Paired exchange

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q45 | **Has paired exchange ever been done in Sri Lanka?** | Reportedly not | |
| Q46 | Is it permitted under the Act and DGHS approval? | **Unknown** | |
| Q47 | Would an ethics committee approve an unrelated-pair swap? | Unknown | |
| Q48 | **Proposal expiry window, given 2–4 week approvals?** | **7 days — likely wrong** | |
| Q49 | Is a 3-way simultaneous nephrectomy feasible here? | Assumed yes | |
| Q50 | Which allocation policy should be default? | Most transplants | |
| Q51 | How should cPRA and waiting time be weighted against each other? | Equal (1.0 / 1.0) | |
| Q52 | Waiting time from dialysis start, or listing date? | Dialysis start, falls back to registration | |
| Q53 | Who accepts a cycle — donor's doctor, recipient's, or both? | Donor's doctor | |

## Governance

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q54 | Record retention period? | **No policy** | |
| Q55 | Who may create accounts? | **Currently uncontrolled** | |
| Q56 | Hospital position on hosting; ethics/IT approval needed? | On-premises assumed | |

## For the academic supervisors

| # | Question | Current assumption | Their answer |
|---|---|---|---|
| Q57 | What evidence would justify clinical use? | Retrospective comparison proposed | |
| Q58 | Is a retrospective run against historical decisions the right validation? | Proposed | |
| Q59 | Ethics approval needed to use real patient records? | Not obtained | |
| Q60 | Is the Grifoni frequency table defensible for publication? | Assumed yes | |

---

# Appendix B — After the meeting

**Same day, while it's fresh:**

1. Transcribe the capture sheets into one table. Mark each answer **confirmed**, **changed**, or **still open**.
2. For every changed value, note *who* said it and whether it's centre practice or a citable guideline. That attribution goes in the code comment beside the constant — the codebase already does this for its sourced values, and it is what makes them defensible later.
3. Anything still open after the meeting is a follow-up with a named owner and a date, not a guess to re-make.

**Then, in order:**

4. Implement the confirmed numbers. Most are single-constant changes in `app/reference_data/`; the tests that assert boundary values will need updating alongside them.
5. **Bump the frequency table and threshold version strings.** Old reports snapshot the values in force when they were generated, so historical reports stay interpretable — but only if the version changes when the values do.
6. Q24 (cPRA >60% points) and Q48 (proposal expiry) are the two that unblock the most: one removes a whole class of unclassifiable report, the other decides whether the exchange workflow is usable at all.
7. Q45–Q47 come before any further exchange work. If paired exchange isn't permissible here yet, that reframes the feature as a research contribution rather than a clinical tool — which is still valuable, but it's a different conversation with the supervisors.
