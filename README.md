# PolicyDrift

PolicyDrift is a standalone GenLayer Intelligent Contract that reaches consensus on **what changed between two committed versions of a privacy policy, and whether the change weakens or strengthens user protection**.

A proposer commits two document URLs and the SHA-256 of the exact bytes of each. Every validator independently fetches both documents, verifies the commitments, and computes the paragraph-level difference with plain deterministic code. Only the *changed* paragraphs are shown to a model, which answers one bounded question per change. The verdict, its precedence rules and every bound are code. Other contracts read one typed answer: `is_weakened(id)`.

It is intentionally not a frontend, not a generic AI oracle and not an escrow. It records a small, auditable fact that other contracts can gate on.

> **Scope.** PolicyDrift compares the text of two documents. It does not say whether a policy is lawful, whether a company follows its own policy, or who is right in a dispute. It is not legal advice. All fixtures in this repository describe a fictional company.

## Release status

| Field | Value |
|---|---|
| Network | GenLayer Studio (studio.genlayer.com), mode "Normal (Full Consensus)" |
| Contract | `0x5eC4529a74234035e366c95143e50ffa283A5D56` |
| Live result | 6 of 6 labelled scenarios returned the expected verdict (one run each) |

The step-by-step deployment and live-run guide, and the full live record, are in [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## The problem

Privacy policies change quietly. A retention period grows, a sharing clause widens, a protection disappears inside a rewritten paragraph. Anything that depends on a provider's promises (a wallet choosing a custody service, a DAO choosing infrastructure, an insurer pricing a risk) needs a neutral, reproducible answer to one question:

> Between version A and version B of this policy, did user protection get weaker, stronger, or stay the same?

Today that answer comes from whoever reads the documents, and it cannot be re-checked on chain.

## Why GenLayer

| Instead of consensus | What goes wrong |
|---|---|
| A deterministic contract | It cannot fetch a web page, and "does this sentence weaken protection" is a judgement about meaning, not a property of a byte string. |
| One reviewer or one LLM behind an API | The authority moves to whoever runs the endpoint and writes the prompt. The same capture, a different owner. |
| An ordinary oracle | An oracle reports values. This question is about meaning, before any value exists. |

### Delete GenLayer: what breaks?

The two facts the verdict rests on are exactly the two a deterministic contract cannot produce: *what do these two documents say* and *what does this change mean for the user*. The first is made checkable by the committed SHA-256: every validator fetches the bytes itself, and a server that serves anything else is caught as `HASH_MISMATCH`. The second needs independent readers. With consensus, each validator runs its own model on the same changed paragraphs and no single party chooses the answer.

### Why this is not a rejected pattern

- **Not a thin LLM wrapper.** The model answers one bounded question per changed paragraph: `WEAKENS`, `STRENGTHENS`, `NEUTRAL` or `UNCLEAR`. It never sees unchanged text, never proposes a verdict, and never sees a threshold. The diff, the verdict, the precedence between findings and every bound are code.
- **Not a format-only validator.** A validator re-fetches both documents, re-checks both hashes, recomputes the diff and re-asks its own model, then compares the stable decision fields. It rejects a leader that is well-formed and substantively false.
- **Not caller-authored evidence.** The proposer supplies addresses and hashes, never the bytes. Validators fetch the bytes.
- **Not toy storage.** Comparisons carry a lifecycle with bounded retries and a per-proposer cap on work in flight that always releases.
- **Not a full application.** One contract, no frontend, no backend, no custody.
- **Not a generic "AI decides X".** The model's answer is grounded: every claim must quote the changed text, and the contract checks that the quote is really in it. An ungrounded `WEAKENS` is downgraded to `UNCLEAR`, and `UNCLEAR` can never become an accusation.

## Boundary: who owns what

| Step | Owner |
|---|---|
| Choosing which two versions to compare, hosting the files, UI, notifications | Frontend or integrator |
| Committing URLs and hashes; rules, bounds, lifecycle, slot accounting | Contract (deterministic) |
| Fetching the bytes | Validators, each on its own, against the committed hash |
| Paragraph diff and its bounds | Contract (deterministic) |
| Judging each changed paragraph | Validators' models (non-deterministic) |
| Verdict and `is_weakened` | Contract (deterministic) |
| Acting on the verdict (blocking, repricing, alerting) | Consuming contract or app |

Flow: `propose_comparison` → `assess` → leader fetches, hashes, diffs, asks the model → validators repeat the whole round and compare → state is written after consensus → consumers read `is_weakened`.

## Verdicts

| Verdict | Meaning |
|---|---|
| `NO_CHANGE` | Different bytes, but no paragraph changed (for example, only reordered). The model is not called. |
| `COSMETIC_ONLY` | Every change is `NEUTRAL`. |
| `STRENGTHENED` | At least one `STRENGTHENS`, no `WEAKENS`. |
| `WEAKENED` | At least one `WEAKENS`, no `STRENGTHENS`. |
| `MIXED` | Both `WEAKENS` and `STRENGTHENS` are present. |
| `UNDETERMINED` | Any `UNCLEAR`, or the round hit a bound (too many changes, paragraph too long, document too large, unreadable encoding). |

`is_weakened(id)` is `True` only for an assessed `WEAKENED` or `MIXED`. Nothing that fails or is uncertain produces an accusation: wrongly saying "unclear" costs a re-read, wrongly saying "weakened" would harm a provider.

## Lifecycle

```
propose_comparison ─► OPEN ──────────────── withdraw ──► WITHDRAWN
                       │
                    assess
                       │
        ┌──────────────┼───────────────┐
   hash mismatch   consensus ruled   error (reverts, nothing stored)
        │              │
   RETRYABLE        ASSESSED
        │
   after 3 rounds
        ▼
    EXHAUSTED
```

`ASSESSED`, `EXHAUSTED` and `WITHDRAWN` release the proposer's slot (at most 5 comparisons in flight per proposer, so the allowance can never be used up permanently).

## Contract surface

Writes: `propose_comparison(label, old_url, old_sha256, new_url, new_sha256)`, `assess(id)` (anyone may call it), `withdraw(id)`.

Views: `is_weakened`, `get_verdict`, `get_comparison`, `get_items`, `open_slots`, `get_stats`, `bounds`.

Bounds: documents up to 60,000 bytes, paragraphs up to 600 characters, up to 12 changed paragraphs, quotes up to 160 characters, 3 rounds, 5 comparisons in flight per proposer.

## Consensus

There is exactly one non-deterministic round per `assess`, run by the leader and again by every validator. [`docs/CONSENSUS.md`](docs/CONSENSUS.md) states the rule in full; in short:

| Validators must agree on | Validators may differ on |
|---|---|
| The round outcome and reason | Which topic label or which excerpt is chosen (each must still be in the vocabulary and a real excerpt of the changed text) |
| The deterministic list of changed paragraphs | Anything the contract does not store as a decision |
| The `effect` of every change | |

Failure paths follow the GenLayer error classes:

| Class | When | Agreement |
|---|---|---|
| `[EXPECTED]` | A business rule was violated (bad URL, bad hash, cap reached) | Exact match |
| `[EXTERNAL]` | A source answered 4xx or a redirect | Exact match |
| `[TRANSIENT]` | Network failure or 5xx | Agree if both are transient |
| `[LLM_ERROR]` | The model failed or returned malformed output | Validators always disagree, which forces a new leader. Nothing is stored. |

A fetched document that does not match its committed hash is not an error: it is recorded as a bounded `RETRY` and ends as `EXHAUSTED` after three rounds.

## Reading the verdict from another contract

```python
policy = gl.get_contract_at(Address(policy_drift_address))
if policy.view().is_weakened(comparison_id):
    ...  # for example: refuse a new deposit, raise a fee, flag for review
```

PolicyDrift does not execute anything on its own and holds no funds.

## Verification

Everything below was run against the source in this repository.

| Gate | Result | How to reproduce |
|---|---|---|
| Direct Mode suite | 222 passed | `python -m pytest -q` |
| GenVM lint | passed (3 checks) | `genvm-lint check contracts/policy_drift.py` |
| GenVM check | 10 methods (7 view, 3 write) | same command |
| Mutation sweep | 23 of 25 mutants killed, 2 equivalent by construction, 0 survived | `python scripts/mutate.py` |

A green suite shows the contract passes its tests, not that the tests would notice a deleted guard. The mutation sweep removes or reverses one rule at a time (the validator's comparison, the hash check, the quote grounding, the slot release, the error-class handling and others) and reruns the whole suite. It found real gaps: a leader forging only the round outcome, and (while writing `docs/CONSENSUS.md`) stored fields such as quotes that validators did not check, which every validator now verifies. Both have their own tests. Each equivalent mutant carries a written argument in `scripts/mutate.py`.

What Direct Mode does **not** cover, and what the live run is for: real multi-validator consensus with different models, real model answers, and closure serialisation under `run_nondet_unsafe`. The six live scenarios above ran on Studio without error; they show the contract works end to end, but they are one run each and do not measure how stable the models' answers are across many runs.

## Limitations

- **The model can be wrong.** `effect` is a judgement. The contract limits the damage (grounded quotes, `UNCLEAR` fails closed, validators compare effects) but cannot make a judgement correct.
- **Paragraph granularity.** A one-word edit inside a long paragraph is a whole `MODIFIED` change. A reordering is not a change. Renaming a heading is.
- **Plain text only.** Bytes are decoded as UTF-8 and split on blank lines. HTML or PDF would be compared as markup or fail to decode. Publish a plain-text or Markdown copy of each version.
- **Commitments, not truth.** The hash proves that two documents are the ones the proposer named. It does not prove they were ever the live policy of anyone.
- **URL admission is not complete SSRF prevention.** The contract rejects non-HTTPS, credentials, IP literals, local and internal names and odd ports. It cannot see DNS resolution or redirects from contract code.
- **Size limits are enforced after the response arrives**, because the runtime does not expose a trusted pre-fetch byte limit.
- **English-language policies only** were exercised.
- **Not legal advice**, and no real company is evaluated by this repository.

## Repository layout

```
contracts/policy_drift.py     the one deployable contract
tests/direct/                 Direct Mode suite (pure logic, contract flow, validator)
fixtures/                     fictional policies and manifest.json (hashes, expected answers)
scripts/mutate.py             mutation sweep
scripts/make_manifest.py      builds fixtures/manifest.json (and manifest.live.json with --base-url)
scripts/print_live_commands.py prints the CLI commands for the six live scenarios
docs/                         consensus rule, security notes, deployment and live-run guide
```

## Reviewer fast path

1. [`docs/CONSENSUS.md`](docs/CONSENSUS.md): what must agree and why.
2. [`contracts/policy_drift.py`](contracts/policy_drift.py): start at `verdict_from`, then `parse_model_output` (the grounding gate), then `_analyze` and `assess`.
3. [`tests/direct/test_validator.py`](tests/direct/test_validator.py): whether the contract has a validator or only a shape check.
4. [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): the live evidence (contract address, scenarios, observed results).

## Development

```
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest -q
genvm-lint check contracts/policy_drift.py
python scripts/mutate.py
```
