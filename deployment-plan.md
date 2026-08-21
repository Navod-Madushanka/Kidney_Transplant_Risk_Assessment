# Deployment plan — Kidney Transplant Compatibility System

**Recommendation: one GPU box on hospital premises, exposed over HTTPS through a Cloudflare Tunnel. Recurring cost ≈ electricity.**

Two facts about your system decide this, and neither is negotiable by choosing a different provider.

---

## The two facts that decide it

### 1. You need a GPU. This is not a performance preference.

Your own measurements:

| Measurement | Source |
|---|---|
| Bead page at **6 tiles on an RTX 2060: 402 s** | recorded in the codebase |
| Production uses **8 tiles**, not 6 | `DEFAULT_NUM_TILES = 8` |
| CPU model load alone: **~88 s** | `llm/client.py:31` |
| First CPU request **timed out at 120 s** | `docker-compose.override.yml` |
| Per-document ceiling: **600 s** | `ocr_service_timeout_seconds` |

Extrapolating the GPU figure, 8 tiles ≈ 536 s — already inside 90% of the timeout *on a GPU*. CPU inference for a 4B vision model runs several times slower again. **On a CPU-only box, every bead-specificity page fails**, not slowly but by timeout. The base `docker-compose.yml` is CPU-only by design; the GPU appears only in the dev override.

So the real choice is: put a GPU somewhere, or accept that bead charts are typed by hand. There is no cloud plan that makes CPU inference work.

Note that HLA typing and crossmatch reports are **single-shot** calls, not tiled. Those are plausibly tolerable on CPU at 1–3 minutes each. It is specifically the two bead pages — 8 tiles each — that are impossible.

### 2. The application is architecturally a single box.

Parts G, H and K all established this, and it is by design:

- In-process `asyncio.Semaphore` bounds extraction concurrency — meaningless across processes.
- Upload spooling is to **local disk**; a second worker cannot read the first's spool directory.
- Startup reconciliation marks every `RUNNING` job `FAILED` — correct with one process, destructive with two.
- Background jobs run as `asyncio.create_task` in the API process.
- No `--workers` in the Dockerfile, deliberately.

**Cloud hosting therefore buys you no scalability here.** You are paying for one box either way. That removes the usual argument for cloud and leaves cost, uptime and governance — where on-prem wins for this specific system.

---

## Options, costed

| # | Shape | Setup | Recurring | Bead OCR |
|---|---|---|---|---|
| **A** | **On-prem GPU box + Cloudflare Tunnel** | Hardware (you may already have it) + UPS | **Electricity only** | ✅ |
| **B** | Lanka Government Cloud for app + DB, on-prem GPU for OCR | Application to ICTA | Likely free/subsidised | ✅ via tunnel |
| **C** | Hetzner CX43 for app + DB, on-prem GPU for OCR | — | **€15.99/mo** | ✅ via tunnel |
| **D** | Hetzner CX43 only, no GPU anywhere | — | €15.99/mo | ❌ manual entry |
| **E** | Everything in the cloud, GPU rented **always-on** | — | **~$150–280/mo** | ✅ |
| **F** | **VPS for app + DB, scale-to-zero serverless GPU for OCR** | Container + endpoint work | **~$20–27/mo** | ✅ |

Hetzner CX43 is 8 vCPU / 16 GB / 160 GB at €15.99. The cheaper CX33 (4 vCPU / 8 GB, €8.49) is tight once Postgres and the backend share it. Option E's low end is Vast.ai's RTX 4090 marketplace rate from $0.20/hr — which is a **spot marketplace**, so it is simultaneously the most expensive option and the least reliable one. That combination is why it is listed last.

**Option A is the recommendation if you can host a box.** Option B is worth a phone call before you spend anything. **Option F is the right answer if you cannot** — see the section below; it is roughly ten times cheaper than always-on cloud GPU and the arithmetic is not close.

### Worth investigating first: Lanka Government Cloud

ICTA runs [LGC 2.0](https://lgc.gov.lk/) — OpenStack VMs, 200+ government organisations, 170+ managed VMs, eligibility covering "government agencies and statutory bodies whose applications are deemed critical, important, or beneficial for enhancing government service delivery." A National Hospital transplant system plausibly qualifies. No GPU offering is advertised, so the OCR service would still sit on-prem, but LGC would give you in-country hosting with real uptime for the stateful half at little or no cost. **Email ICTA before buying anything.**

---

## Option F — split architecture with a scale-to-zero GPU

This workload is unusually well suited to serverless GPU, for a reason that is worth stating: **the jobs are long.** The usual objection to serverless GPU is that cold start dominates a two-second inference. Here a patient's batch is ~7 minutes of GPU work, so a ~60 s cold start is around 10% overhead rather than 3000%.

### The arithmetic

A full patient batch is **18 model calls** — one HLA typing, one crossmatch, and eight tiles for each of the two bead pages. Scaling the measured 67 s/call on an RTX 2060 to an L4 (roughly 3× the throughput) gives ~22 s/call:

```
18 calls × ~22 s        ≈ 400 s  of GPU work
+ one cold start        ≈  60 s  (once per batch, if idle timeout spans it)
                        ≈ 460 s  ≈ 0.13 GPU-hours per patient
```

At an L4 serverless rate around $0.69/hr that is **≈ $0.09 per patient**:

| Throughput | GPU cost/month |
|---|---|
| 20 patients | ~$1.80 |
| 50 patients | ~$4.50 |
| 100 patients | ~$9.00 |

Add a €15.99 VPS and the whole system lands at **roughly $20–27/month**. Even if the speed estimate is wrong by a factor of two, it stays under $40. The conclusion does not depend on the exact rate — at any plausible per-hour price, seven minutes of GPU per patient is cents.

### Two implementations, one of which bites

| | Platform manages lifecycle | You manage lifecycle |
|---|---|---|
| **How** | A request wakes the container; idle timeout scales it to zero | You call an API to start a pod, poll for health, run, call stop |
| **Cost/hr** | Higher (~$0.69 L4) | Lower (~$0.49 L4) |
| **Failure mode** | Worst case, an instance idles for its timeout | **A failed stop call bills a GPU 24/7 until someone notices** — about $350/month |

The second is closer to "turn it on, extract, turn it off," and it is the one to avoid. Owning the state machine means owning every way it can fail mid-flight. **Choose the platform-managed option: you cannot forget to turn it off.** If you do go the DIY route, put a hard watchdog and a billing alert on it before the first real job.

### Cloud Run GPU is the low-friction fit

Your `ocr-service` is already a containerised FastAPI app. Google Cloud Run with an **L4 (24 GB)** runs that container essentially unchanged, scales to zero, bills per second, and reports GPU instance start in about 5 seconds. Critically, it is available in **asia-south1 (Mumbai)** and **asia-southeast1 (Singapore)** — far better than Europe on both latency and the residency conversation.

RunPod Serverless is cheaper per hour but wants a **handler function**, not an HTTP server. Porting `extract_report` and `extract_bead_specificity_stream` into their SDK and re-plumbing the NDJSON progress stream through their streaming API is a day or more of work, and it changes the contract the backend depends on. Cloud Run does not.

### What has to change either way

1. **Verify the request timeout.** `call_ocr_service_stream` holds a *single* HTTP request open for the whole bead page, reading NDJSON progress events. That long-lived streaming request has to survive the platform's request cap — check it before committing.
2. **Cold start now sits inside `ocr_service_timeout_seconds`** (600 s). A faster GPU shrinks the work, so this gets easier, not harder — but re-measure.
3. **Bake the model into the image** or mount it from object storage. Do not pull 3 GB on every cold start.
4. **Set the idle timeout to ~120 s** so one patient's four documents share a single warm worker instead of paying four cold starts.
5. **`X-Internal-API-Key` becomes internet-facing.** TLS only, strong secret, rotate it. It is now the only thing between the public internet and your GPU bill.
6. **Set a spend cap and a billing alert.** Your `asyncio.Semaphore(1)` already caps concurrency at one in-flight job, which is a useful natural guard.

### The governance consequence — and a mitigation

With on-prem, sending clinical images abroad was optional. With Option F it is structural: every scan crosses a border on every job.

But look at what is actually in each image. On a bead-specificity chart the patient name and ID sit in a **header band at the top**; the eight tiles are row bands of a table of antigen names and MFI numbers, which are not identifying on their own. Crop the header before tiling and those tiles are de-identified.

The HLA typing and crossmatch reports are the opposite case — extracting the patient's name, NIC and date of birth *is* their purpose. They cannot be de-identified.

That suggests a cleaner line than "cloud or not":

- **Bead tiles → cloud GPU, de-identified.** 16 of the 18 calls, and the only ones that genuinely need a GPU.
- **HLA typing and crossmatch → local CPU.** Two single-shot calls, not tiled, 1–3 minutes each. Tolerable, and every identifier stays in the country.

One caveat: `make_row_band_tiles` currently cuts the whole page, so **tile 0 carries the header today**. This needs a crop-before-tiling step, not just a configuration change — and Part J's projection-profile idea (§J8) would help locate where the table actually starts.

---

## Why Cloudflare Tunnel

The tunnel is what makes an on-prem box viable as a real service:

- **Public HTTPS with no inbound ports opened.** The hospital firewall stays shut; the daemon dials out.
- **No static IP needed** — which matters, because hospital connections rarely have one.
- **Free tier** covers this use comfortably.
- Solves your missing-HTTPS problem without a certificate workflow.
- Gives the cross-hospital exchange feature a stable public hostname, which it needs — a paired exchange is explicitly designed to match across participating hospitals.

The alternative if you prefer not to depend on Cloudflare is a WireGuard link between the hospital box and a €4/mo VPS acting as the public entrypoint. More moving parts, same effect.

---

## On data residency — the legal answer and the practical one

**Legally:** Sri Lanka's Personal Data Protection Act No. 9 of 2022 has been in force since **18 March 2025**, and it contains **no data-localisation requirement**. Cross-border transfer is permitted either under an instrument specified by the Authority (standard contractual clauses, binding corporate rules) paired with a transfer impact assessment, or under derogations including explicit informed consent. Hosting in Germany is not unlawful.

**Practically:** health data is special-category, this is a national hospital, and your ethics committee will have its own view that is likely stricter than the statute. "The data never left the building" is a far easier sentence in a review than explaining standard contractual clauses and a transfer impact assessment to a transplant board.

That is a governance argument for on-prem, not a legal one — but it is the argument that will actually decide it, so treat it as the operative constraint. If you do go off-shore, budget time for a transfer impact assessment; it is a real document, not a checkbox.

---

## Blockers — you cannot deploy today

These are prerequisites, not improvements.

1. **`POST /auth/register` is unauthenticated and open.** Anyone who reaches the API self-provisions a doctor account and auto-creates a hospital via `get_or_create_hospital`. **Hard blocker for anything internet-reachable.** Close it, or gate it behind an admin invite.
2. **CORS is hardcoded to `http://localhost:5173`** with `allow_credentials=True`. Nothing works from a real hostname. Make it an env-driven list.
3. **There is no deployment artifact.** `kidney-backend` appears in no compose file. `.env.example` does not exist despite the README telling you to copy it. The root README says `uv main.py`, which is not a command. `ocr-service/README.md` is 0 bytes. Nobody — including you in six months — can stand this up from the repo as it is.
4. **No backup story**, for either Postgres or `uploads/report_files/`. That directory holds permanent clinical attachments on local disk. Losing it loses source documents.
5. **No structured logging anywhere** in the backend. When something fails at 2 a.m. you will have nothing. The hash-chained audit log covers *who did what*, not *why the service fell over*.
6. **JWT expires at 60 minutes with no refresh.** A clinician's session will die mid-clinic.

Items 1–3 block deployment outright. Items 4–6 block *reliable* deployment.

---

## Build the deployable artifact

One `docker-compose.prod.yml` covering all five services:

| Service | Notes |
|---|---|
| `postgres:16` | Named volume, `restart: unless-stopped`, healthcheck |
| `backend` | Depends on Postgres healthy; runs `alembic upgrade head` on start; **no `--workers`** |
| `frontend` | Static Vite build served by Caddy or nginx |
| `ocr-service` | Already has `mem_limit: 1g`; **no `--reload`** in the prod image |
| `ollama` | Pinned to `0.12.7`; GPU device reservation; **add a `mem_limit`** — it has none and the model is the memory consumer |
| `cloudflared` | The tunnel daemon |

Plus a `.env.example` with every variable named and no values, and a README that has actually been followed on a clean machine.

**Do not set `--workers` on uvicorn.** Fact 2 above.

---

## Sizing the box

| Component | Recommendation |
|---|---|
| GPU | 8 GB VRAM minimum. Your RTX 2060 (6 GB) works but is why a bead page takes 402 s. An RTX 3060 12 GB is inexpensive and would roughly halve that. |
| System RAM | **16 GB workable, 32 GB comfortable.** Ollama holds the model resident permanently (`OLLAMA_KEEP_ALIVE=-1`) alongside Postgres, the backend and ocr-service. |
| Disk | 256 GB+ SSD. `uploads/report_files/` grows with every scan and never shrinks. |
| Power | **UPS is mandatory**, not optional — see below. |

---

## Reliability checklist

Ranked by what actually protects you.

1. **Nightly `pg_dump`, encrypted, copied off the box.** Cloudflare R2's free tier (10 GB) or Backblaze B2 covers this for roughly nothing. **Then restore it onto a scratch machine and confirm the system boots against it.** An untested backup is not a backup.
2. **Back up `uploads/report_files/` too.** A database restore without the source documents is half a recovery.
3. **UPS.** An unclean shutdown mid-inference is likely given `OLLAMA_KEEP_ALIVE=-1`. Part G's startup reconciliation now marks orphaned jobs `FAILED` rather than stranding them at `RUNNING`, so a power cut is survivable — but only because that fix landed.
4. **`restart: unless-stopped` on every service.** Two of five have it today.
5. **Add structured logging** and ship it somewhere off-box. Even a file with rotation beats nothing.
6. **An uptime check** hitting `/health` — free tiers abound. Note that `/health/db` will hang if the connection pool is exhausted, so monitor both: one tells you the process is alive, the other that it can serve.
7. **Raise or verify `ocr_service_timeout_seconds`.** At 8 tiles on your current GPU you are within ~10% of the ceiling. One slow run and a legitimate extraction fails.

The honest ranking: **a €0 on-prem box with tested restores is more reliable than a $300/month cloud setup without them.** Reliability here is a backup-and-recovery problem far more than a hosting problem, because the architecture is single-box regardless of where the box lives.

---

## Suggested sequence

1. Email ICTA about LGC eligibility — it costs a day and may change the answer.
2. Fix the three hard blockers: open registration, CORS, and the missing compose/`.env.example`/README.
3. Stand the full stack up on the GPU box from that compose file alone, on a clean OS install. If it does not come up from the repo, the artifact is not finished.
4. Add the tunnel, get a hostname, confirm HTTPS end to end.
5. Backups and a restore drill. Do not skip the drill.
6. Logging and an uptime check.
7. Then the P0/P1 items from `stakeholder-review-readiness.md` — the missing `.catch()` handlers and the real-patient identifiers in tracked files matter more once the system is reachable from outside the building.
