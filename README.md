# openDev: a local autonomous company operator

openDev turns a short company request such as "process the invoices in the inbox" into finished, checked work. It runs on a local model (Qwen 3.5 through Ollama or any OpenAI compatible server), drives a real browser, reads company files and procedures, and refuses to act outside its permissions. It does not trust its own answer: an independent verifier compares what it claims with the system of record before the run is accepted.

The prototype is deliberately narrow. It automates one real back office workflow, supplier invoice processing for accounts payable, end to end, and shows the pieces that make autonomy trustworthy rather than simulated.

## What happens in a run

1. The request is matched to company context. Procedures (`company/sops/*.md`) are chunked and ranked with BM25 and the best ones are put in front of the model. Lessons saved by earlier runs come back from memory.
2. The model plans, then acts one step at a time. Each step is a JSON tool call: read a file, search a procedure, open an ERP page, fill a form, click a numbered element, ask a human, or finish.
3. Every action passes through a deterministic policy engine (`company/policy.yaml`) that the model cannot talk its way around: allowed hosts, forbidden paths such as `/api/` and `/admin`, readable and writable folders, forbidden fields such as bank details, and click guards such as "Approve invoice is refused when the page amount is above 2,500.00".
4. A blocked action comes back to the model as an observation with the reason, so it can take the permitted route (submit for manager approval) or escalate.
5. Write actions capture screenshots as evidence. Every step is appended to a hash chained audit log, so tampering is detectable.
6. When the model calls `finish`, the verifier reads the ERP state and re derives what the SOP requires for each inbox document. It checks the reported disposition, the ERP record (status, amount, PO), the hold comment, that no records were created for escalated items, and global invariants (nothing above the limit self approved, vendor master untouched, no duplicate invoices). If anything fails, the failures are fed back once so the operator can repair the real state or correct its report.
7. `runs/<timestamp>/report.md` lists outcomes, verification results, escalations and evidence.

## The demo workload

`tasks/inbox` holds six invoices and the mock ERP (`erp/app.py`, a small Flask app with vendors, purchase orders and invoices) holds the system of record. They cover the cases that make people slow: a clean match to auto approve, an over limit invoice that must go to a manager, an amount mismatch that must be held with a stated difference, a duplicate that must not be entered twice, an unknown vendor, and a blocked vendor with no PO. Each needs a different action, and two need no ERP action at all.


## See it work

The recordings below come from a real browser session against the mock ERP, with the full agent loop, policy engine, audit log and verifier running. The decisions were played back by a scripted stand in for the model (`scripts/record_replay.py`), not by Qwen, so they show the machinery and the guardrails, not model quality. Run `opendev run` with your own model for that.

![openDev processing the invoice batch](docs/media/replay.gif)

Full video: [docs/media/replay.mp4](docs/media/replay.mp4)

| Auto approved (1,200.00 under the limit) | Over limit, routed to a manager (4,800.00) | Amount mismatch, held with the difference |
|---|---|---|
| ![approved](docs/media/approved.png) | ![manager](docs/media/manager.png) | ![hold](docs/media/hold.png) |

Run report from the good run, 19 of 19 independent checks passed:

![report](docs/media/report_replay.png)

Adversarial run. The script tries `/api/state`, an outside website, `../../etc/passwd` and approving an over limit invoice. All four are blocked by policy, and its false "approved" claim is caught by the verifier (3 of 10 checks pass because it left the real work undone):

![guardrails](docs/media/report_guardrails.png)

## Run it on your machine

```
pip install -e .[dev]
playwright install chromium
ollama pull qwen3.5            # or use the tag you already have
opendev --model <your tag> doctor
opendev --model <your tag> run
```

`doctor` lists the models your server exposes and sends a test message. Use `--base-url` for llama.cpp, LM Studio or vLLM, for example `http://localhost:8080/v1`. Add `--headed` to watch the browser and `--interactive` to answer escalations live. Environment variables `OPENDEV_MODEL` and `OPENDEV_BASE_URL` work too.

`opendev run` starts its own ERP on a free port, resets it to the seed data, runs the task and writes the report. Exit code 0 means the run finished and every independent check passed.

## Layout

```
company/policy.yaml     permissions and guardrails enforced outside the model
company/sops/           procedures the operator retrieves and follows
erp/                    mock internal system with a seed dataset
src/opendev/agent.py   plan, act, observe loop with loop guard, context trimming, verify and repair
src/opendev/tools/     browser (Playwright, numbered elements, policy routed), files
src/opendev/policy.py  deterministic permission checks
src/opendev/verify.py  check type shared by verifiers
src/opendev/packs/     workflow packs: document parsing, expected outcome rules, verifier
src/opendev/audit.py   hash chained audit log
tests/                  unit tests and end to end tests through a real browser
```

## Tests and what they prove

```
pytest
```

The end to end tests drive the real agent loop, browser, policy engine, ERP and verifier. The model is replaced by a scripted stand in, because a language model cannot run inside CI. One script behaves correctly and must finish with all checks green. The other tries to read `/api/state`, visit an outside site, read `../../etc/passwd` and approve an over limit invoice, and must be blocked four times, and its false report must be caught by the verifier. These tests prove the guardrails and verification work. They do not measure how well Qwen plans, which you can see by running the demo against your model.

## Adding another workflow

Write SOPs for it under `company/sops`, add permissions to `policy.yaml`, and add a pack in `src/opendev/packs` with a document parser and a verifier that reads the target system's state. The agent, tools, policy engine, audit log and reporting are shared.

## Known limits

The browser tool targets web apps. Desktop application control is not included in this prototype. The model is small and local, so it can mis-plan; the policy engine and verifier exist so that mistakes are blocked or caught instead of becoming silent wrong work. The mock ERP has no login. Memory is a simple keyword store.
