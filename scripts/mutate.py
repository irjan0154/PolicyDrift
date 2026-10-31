"""Mutation sweep: break one rule at a time and check the direct suite notices.

A green suite proves the contract passes its tests, not that the tests would
notice a deleted guard. Each mutation below removes or reverses one rule in a
scratch copy of the contract; the whole suite then runs against that copy.
A mutation is KILLED when the suite fails and SURVIVED when it still passes.

    python scripts/mutate.py
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "contracts" / "policy_drift.py").read_text()

MUTATIONS = [
    ("validator accepts every leader",
     "return rounds_agree(leaders_res.calldata, mine)", "return True"),
    ("equivalence ignores per-change effects",
     'if a.get("id") != b.get("id") or a.get("effect") != b.get("effect"):',
     'if a.get("id") != b.get("id"):'),
    ("equivalence ignores the change list",
     'if leader["changes"] != mine["changes"]:\n        return False\n', ""),
    ("equivalence ignores the outcome",
     'if leader["outcome"] != mine["outcome"] or leader["reason"] != mine["reason"]:',
     'if leader["reason"] != mine["reason"]:'),
    ("UNCLEAR no longer fails closed",
     'if "UNCLEAR" in effects:\n        return VERDICT_UNDETERMINED', 'if False:\n        return VERDICT_UNDETERMINED'),
    ("ungrounded quotes still count",
     'effect = entry["effect"] if quote_ok else "UNCLEAR"', 'effect = entry["effect"]'),
    ("committed hash is not checked",
     "if sha256_hex(body) != expected_sha:", "if False:"),
    ("model errors are agreed on",
     'if validator_message.startswith(ERROR_TRANSIENT) and leader_message.startswith(ERROR_TRANSIENT):\n        return True\n    return False',
     'if validator_message.startswith(ERROR_TRANSIENT) and leader_message.startswith(ERROR_TRANSIENT):\n        return True\n    return True'),
    ("a leader error is accepted when the validator succeeds",
     "return False  # leader errored, I succeeded: disagree", "return True"),
    ("open-comparison cap is off by one",
     "if open_now >= MAX_OPEN_PER_PROPOSER:", "if open_now > MAX_OPEN_PER_PROPOSER:"),
    ("assessing never releases the proposer slot",
     "        self.assessed_total = u256(self.assessed_total + 1)\n        self._release(c.proposer)",
     "        self.assessed_total = u256(self.assessed_total + 1)"),
    ("IPv4 literals are admitted",
     "if all(c.isdigit() or c == \".\" for c in host):  # IPv4 literal", "if False:"),
    ("diff becomes case sensitive",
     "return paragraph.casefold()", "return paragraph"),
    ("anyone can withdraw",
     "if gl.message.sender_address != c.proposer:", "if False:"),
    ("retries never exhaust",
     "if c.rounds >= MAX_ROUNDS:", "if c.rounds > 1000:"),
    ("MIXED no longer counts as weakened",
     "c.verdict in (VERDICT_WEAKENED, VERDICT_MIXED)", "c.verdict == VERDICT_WEAKENED"),
    ("is_weakened ignores the status",
     'return c.status == STATUS_ASSESSED and c.verdict in', 'return c.verdict in'),
    ("redirects count as success",
     "if response.status != 200:", "if response.status >= 400:"),
    ("WEAKENS and STRENGTHENS collapse to WEAKENED",
     "    if weak and strong:\n        return VERDICT_MIXED\n", ""),
    ("proposing the same version is allowed",
     "if old_sha256 == new_sha256:", "if False:"),
    ("unchanged text is also sent to the model",
     "if len(changes) == 0:\n        return {\"outcome\": OUT_OK", "if False:\n        return {\"outcome\": OUT_OK"),
    ("too many changes is not enforced",
     "if len(removed) + len(added) > 2 * MAX_CHANGES:\n        return OUT_TOO_MANY, []", "if False:\n        return OUT_TOO_MANY, []"),
    ("validators skip the stored-field checks",
     "    if not leader_result_valid(leader):\n        return False\n", ""),
    ("any quote counts as grounded",
     "    return any(_key(quote) in h for h in haystacks)", "    return True"),
    ("model JSON may carry extra keys",
     'if not isinstance(entry, dict) or set(entry.keys()) != {"id", "topic", "effect", "quote"}:',
     "if not isinstance(entry, dict):"),
]


# Mutants that cannot change observable behaviour, each with the argument why.
EQUIVALENT = {
    "is_weakened ignores the status":
        "a verdict is only ever written together with status ASSESSED and an assessed "
        "comparison can never be withdrawn or reopened, so the status test is defensive only",
    "too many changes is not enforced":
        "the early check bounds the work done by the pairing loop; any input it rejects "
        "(more than 2 * MAX_CHANGES unmatched paragraphs) yields more than MAX_CHANGES "
        "changes, which the later check rejects with the same result",
}


def main() -> int:
    killed, survived, equivalent = [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        for name, old, new in MUTATIONS:
            if SOURCE.count(old) != 1:
                print(f"SKIP   {name}: pattern found {SOURCE.count(old)} times")
                survived.append(name + " (pattern not unique)")
                continue
            target = Path(tmp) / "policy_drift.py"
            target.write_text(SOURCE.replace(old, new))
            env = dict(os.environ, POLICYDRIFT_CONTRACT=str(target))
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "tests/direct"],
                cwd=ROOT, env=env, capture_output=True, text=True,
            )
            if proc.returncode != 0:
                killed.append(name)
                print(f"KILLED   {name}")
            elif name in EQUIVALENT:
                equivalent.append(name)
                print(f"EQUIVALENT {name}: {EQUIVALENT[name]}")
            else:
                survived.append(name)
                print(f"SURVIVED {name}")
    print(
        f"\n{len(killed)} killed, {len(equivalent)} equivalent by construction, "
        f"{len(survived)} survived, {len(MUTATIONS)} total"
    )
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
