"""Print the exact GenLayer CLI commands for the live run, one block per scenario.

    python scripts/print_live_commands.py <contract-address>

Reads fixtures/manifest.live.json (see scripts/make_manifest.py). Nothing is
executed: copy each block into a terminal. Run the scenarios in order on a
fresh deployment so comparison ids are 1, 2, 3 ... in the order printed.
A proposer may have at most 5 comparisons in flight, so each block assesses
its comparison before the next one is proposed.
"""

import json
import shlex
import sys
from pathlib import Path

LIVE = Path(__file__).resolve().parent.parent / "fixtures" / "manifest.live.json"


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("0x"):
        print(__doc__)
        return 2
    address = sys.argv[1]
    if not LIVE.exists():
        print("fixtures/manifest.live.json is missing: run make_manifest.py with --base-url first")
        return 1
    scenarios = json.loads(LIVE.read_text())["scenarios"]
    for index, s in enumerate(scenarios, start=1):
        if not s["old_url"] or not s["new_url"]:
            print(f"scenario {s['id']} has no URL in the live manifest")
            return 1
        propose = " ".join(
            shlex.quote(str(a))
            for a in (s["label"], s["old_url"], s["old_sha256"], s["new_url"], s["new_sha256"])
        )
        print(f"# --- {index}. {s['id']}: {s['summary']}")
        print(f"# expected verdict: {s['expected_verdict']}")
        print(f"genlayer write {address} propose_comparison --args {propose}")
        print(f"genlayer write {address} assess --args {index}")
        print(f"genlayer call {address} get_comparison --args {index}")
        print(f"genlayer call {address} get_items --args {index}")
        print()
    print(f"genlayer call {address} get_stats")
    return 0


if __name__ == "__main__":
    sys.exit(main())
