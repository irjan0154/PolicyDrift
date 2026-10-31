# Deployment and live run

This file is both the guide and the record. The guide comes first. The **Live record** at the bottom stays empty until a real run fills it in, and nothing else in the repository claims live results.

## Prerequisites

- Node.js and the GenLayer CLI: `npm install -g genlayer`
- Python 3.12 or newer for the checks: `pip install -r requirements.txt`
- A public GitHub repository containing this project

StudioNet is gasless, so a zero GEN balance is normal and no faucet is needed. StudioNet is rate limited per IP (about 60 requests a minute), so run the scenarios one after another and wait for each receipt.

## 1. Check the source locally

```
python -m pytest -q
genvm-lint check contracts/policy_drift.py
sha256sum contracts/policy_drift.py          # record this value below
```

Expected: all tests pass; lint passes; 10 methods (7 view, 3 write).

## 2. Publish the fixtures at stable raw URLs

The contract fetches each document and checks its SHA-256, so the files must be served **byte for byte** as committed. `.gitattributes` pins line endings to LF.

1. Commit and push everything. Note the full commit hash `<commit>` that contains `fixtures/`.
2. Check that the raw files match the manifest (this is the check that prevents `HASH_MISMATCH`):

   ```
   curl -s https://raw.githubusercontent.com/<user>/<repo>/<commit>/fixtures/northwind-v1.txt | sha256sum
   ```

   Compare with `old_sha256` in `fixtures/manifest.json`. Repeat for each `northwind-v2-*.txt`.
3. Build the manifest with absolute URLs, pinned to that commit:

   ```
   python scripts/make_manifest.py --base-url https://raw.githubusercontent.com/<user>/<repo>/<commit>/fixtures
   ```

   This writes `fixtures/manifest.live.json`. Commit it afterwards. The URLs stay valid because they point at the earlier commit.

## 3. Deploy

```
genlayer network set studionet
genlayer account create --name policydrift      # first time only
genlayer deploy --contract contracts/policy_drift.py
```

The constructor takes no arguments. Note the **transaction hash** and the **contract address**.

Lifecycle status is not execution success: a failed deploy can still reach `ACCEPTED` or `FINALIZED` with no contract created. Always read the receipt:

```
genlayer receipt <deployTxHash> --stdout --stderr
```

Then confirm the deployment is what you intend:

```
genlayer schema <address>        # expect the 10 methods
genlayer code <address>          # compare with contracts/policy_drift.py
```

Open `https://explorer-studio.genlayer.com/address/<address>` and check the transaction shows a finalized, successful result.

## 4. Run the six scenarios

```
python scripts/print_live_commands.py <address>
```

This prints, for each scenario, the four commands to run in order: `propose_comparison`, `assess`, `get_comparison`, `get_items`. Run the blocks in the order printed, on a fresh deployment, so comparison ids are 1 to 6. Each block assesses its comparison before the next is proposed (a proposer may have at most 5 in flight).

| # | Scenario | Expected verdict | Why it is in the set |
|---|---|---|---|
| 1 | `weakened` | `WEAKENED` | two weakening edits |
| 2 | `strengthened` | `STRENGTHENED` | three strengthening edits |
| 3 | `mixed` | `MIXED` | one of each |
| 4 | `cosmetic` | `COSMETIC_ONLY` | wording only |
| 5 | `reordered` | `NO_CHANGE` | different bytes, no paragraph change; the model is not called |
| 6 | `injection` | `WEAKENED` | a prompt-injection sentence inside the policy must not change the verdict |

The expected effects per changed paragraph are in `fixtures/manifest.json` (`expected_effects`).

## 5. Record what happened

For every scenario record the transaction hash, the validators' votes shown in the explorer, `status`, `verdict`, `rounds`, and each item's `effect`. **Record disagreements and failures as they happened.** A reverted `assess` (`[LLM_ERROR]`, `[TRANSIENT]`, `[EXTERNAL]`) is a normal outcome of the design: nothing is stored and the call can be repeated. A verdict that differs from the label is a finding about the model, not a reason to edit the label afterwards.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `status` is `RETRYABLE` with reason `HASH_MISMATCH` | The served bytes differ from the manifest. Re-run the `curl | sha256sum` check; look for line-ending or trailing-newline changes. |
| `assess` reverts with `[EXTERNAL] HTTP 404` | Wrong URL, or the commit is not pushed yet. |
| `assess` reverts with `[LLM_ERROR]` | The model failed or answered badly. Nothing was stored; call `assess` again. |
| `assess` reverts with `[TRANSIENT]` | Network or server error on the source. Call `assess` again. |
| HTTP 429 or `-32429` from the CLI | StudioNet rate limit. Wait a minute and continue. |
| Deploy receipt shows an execution error | Fix the error first. Missing code or schema is expected after a failed deploy. |
| `propose_comparison` reverts with `[EXPECTED] BAD_URL` | The URL is not plain HTTPS on port 443, or contains credentials, an IP address or an internal name. |

## Live record

_Empty until a real run fills it in._

### Deployment

| Field | Value |
|---|---|
| Network | |
| Chain ID | |
| Contract address | |
| Deployment transaction | |
| Deployment result | |
| Deployed source SHA-256 | |
| Source parity (`genlayer code` equals the file) | |
| Fixtures commit | |

### Scenarios

| # | Scenario | Expected | Observed status / verdict | Observed effects | Validator votes | Transactions |
|---|---|---|---|---|---|---|
| 1 | weakened | `WEAKENED` | | | | |
| 2 | strengthened | `STRENGTHENED` | | | | |
| 3 | mixed | `MIXED` | | | | |
| 4 | cosmetic | `COSMETIC_ONLY` | | | | |
| 5 | reordered | `NO_CHANGE` | | | | |
| 6 | injection | `WEAKENED` | | | | |

### Notes

_Anything that went wrong, was retried, or disagreed with the label._
