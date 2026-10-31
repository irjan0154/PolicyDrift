# Consensus rule

This document states exactly what PolicyDrift's validators must agree on, what they may differ on, and why. The code is `rounds_agree`, `leader_result_valid`, `errors_agree` and `_handle_leader_error` in [`contracts/policy_drift.py`](../contracts/policy_drift.py); the behaviour is pinned by [`tests/direct/test_validator.py`](../tests/direct/test_validator.py).

## The round

`assess(id)` runs exactly one non-deterministic block with `gl.vm.run_nondet_unsafe(leader_fn, validator_fn)`. `leader_fn` is `_analyze`:

1. Fetch the old document. Check size, then SHA-256 against the commitment, then UTF-8.
2. Do the same for the new document. (If step 1 already produced a recorded failure, the new document is not fetched. Every node follows the same order, so this is deterministic.)
3. Split both into paragraphs and compute the deterministic diff. Apply the bounds.
4. If nothing changed, stop. The model is not called.
5. Otherwise ask the model one bounded question per changed paragraph, then parse the answer strictly and ground every quote.

All state changes happen after consensus, outside the block. The block never touches storage.

## What a round produces

A round returns `{outcome, reason, changes, items}`.

| outcome | reason | When | Stored as |
|---|---|---|---|
| `OK` | _(empty)_ | Diff computed. `items` has one entry per change. | `ASSESSED`, verdict from the effects |
| `RETRY` | `HASH_MISMATCH` | Fetched bytes differ from the committed SHA-256 | `RETRYABLE`; `EXHAUSTED` on the third round |
| `TOO_LARGE` | `DOC_SIZE` | Empty body, or over 60,000 bytes | `ASSESSED`, `UNDETERMINED` |
| `TOO_LARGE` | `PARAGRAPH_TOO_LONG` | A changed paragraph over 600 characters | `ASSESSED`, `UNDETERMINED` |
| `TOO_MANY_CHANGES` | `TOO_MANY_CHANGES` | More than 12 changed paragraphs | `ASSESSED`, `UNDETERMINED` |
| `UNREADABLE` | `BAD_ENCODING` | Bytes are not valid UTF-8 | `ASSESSED`, `UNDETERMINED` |

Each `items` entry is `{id, kind, topic, effect, quote}`.

## What a validator does

When the leader returned a value:

1. Re-run the whole round (`_analyze`) with its own fetches and its own model.
2. If that raises a classified error, **disagree**. The leader produced something this validator could not reproduce.
3. Otherwise accept only if `rounds_agree(leader, mine)` holds.

When the leader raised an error, `_handle_leader_error` re-runs the round: if it succeeds, **disagree** (the leader is the odd one out); if it raises a classified error, apply `errors_agree`; any unclassified exception means **disagree**.

## `rounds_agree`: must agree

| Field | Rule |
|---|---|
| `outcome` and `reason` | Equal |
| `changes` (id, kind, old text, new text, for every changed paragraph) | Equal |
| Number of `items` | Equal |
| `id` and `effect` of every item | Equal |

`changes` is a pure function of the two committed byte strings, so honest nodes always produce the identical list. Comparing it in full means a leader cannot hide a change, invent one, or edit the text that the model is later said to have read.

## `rounds_agree`: may differ, but must be valid

`topic` and `quote` are not compared with the validator's own answer, because two honest models can name the same concern differently or quote different parts of the same paragraph. They are still **stored**, so they are held to deterministic rules by `leader_result_valid`, which every validator applies to the leader's result:

- items line up one to one with `changes` (same `id`, same `kind`), with exactly the keys `id, kind, topic, effect, quote`;
- `topic` is in the topic vocabulary and `effect` in the effect vocabulary;
- `quote` is a string of at most 160 characters;
- a non-empty `quote` is a real excerpt of the changed text (case and spacing insensitive); an empty `quote` is allowed only with `UNCLEAR`;
- a round that did not end `OK` carries no changes and no items.

Without this a leader could agree with the validators on every effect and still store an invented quote. `test_validator_rejects_a_leader_that_stores_forged_diagnostics` pins it.

## What is not compared, and why

| Not compared | Reason |
|---|---|
| Model wording beyond the fixed fields | The model has no free-text field. The prompt asks for fixed keys, and anything else fails the strict parse. |
| Latency, byte counts, raw model output | Never used to decide anything. |
| The leader's verdict | The leader never sends one. The verdict is computed after consensus by `verdict_from` from the agreed effects. |

## Failure paths

| Class | Raised as | Agreement |
|---|---|---|
| `[EXPECTED]` | `[EXPECTED] BAD_URL`, `NOT_ASSESSABLE`, and so on | Exact message match |
| `[EXTERNAL]` | `[EXTERNAL] HTTP <status>` for any non-200, non-5xx answer (404, 403, redirects) | Exact message match |
| `[TRANSIENT]` | `[TRANSIENT] fetch failed`, `[TRANSIENT] source unavailable` (5xx) | Agree if both sides are transient |
| `[LLM_ERROR]` | `[LLM_ERROR] model call failed`, `[LLM_ERROR] malformed model output` | Never agree. This forces a new leader; nothing is stored. |

A hash mismatch is deliberately **not** an error. It is an agreed, recorded fact ("the bytes served do not match the commitment"), bounded to three rounds. Validators agree on it only if they see it too; a validator that fetched the committed bytes disagrees.

## Worked examples

**Honest leader.** The leader and every validator fetch the same bytes (the hash guarantees it), derive the same changes, and ask their own models. Wording of `topic` and `quote` differs; effects match; the result is accepted.

**Leader forges the diff.** It reports no changes for a weakened policy. Validators recompute the diff, see a different `changes` list, and disagree.

**Leader forges a verdict-shaping effect.** It flips `WEAKENS` to `STRENGTHENS`. Validators' own models say `WEAKENS`; the effects differ; disagree.

**Leader stores an invented quote.** Effects match, but `leader_result_valid` fails because the quote is not in the changed text; disagree.

**Leader's model hallucinates.** It raises `[LLM_ERROR]`. Validators never agree on that, a new leader is chosen, and the comparison stays `OPEN` with nothing stored.

**The server serves different bytes to different nodes.** A node that is served bytes other than the committed ones records `HASH_MISMATCH`. It can agree only with nodes that saw the same mismatch; a node that saw the committed bytes disagrees.

## Assumptions and limits

- **Diverse models.** The scheme relies on validators running different models, so that one model's blind spot is not shared by a majority. If most validators ran the same model, agreement would be cheap and less informative.
- **The model can be wrong consistently.** Agreement shows that independent readers reached the same effect, not that the effect is right.
- **Direct Mode does not run real multi-validator consensus.** It replays one validator function against mocked data (`run_validator`), which pins the comparison logic. Real consensus with real models is exercised only by the live run recorded in [`DEPLOYMENT.md`](DEPLOYMENT.md).
- **Appeals and leader rotation** are GenLayer protocol behaviour and are not reimplemented here.
