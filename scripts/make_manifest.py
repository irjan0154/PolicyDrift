"""Build fixtures/manifest.json: file hashes plus the hand-labelled expected answers.

    python scripts/make_manifest.py                      # fixtures/manifest.json (no URLs)
    python scripts/make_manifest.py --base-url https://raw.githubusercontent.com/<user>/<repo>/<commit>/fixtures
                                                         # also fixtures/manifest.live.json (absolute URLs)

Hashes are over the exact bytes of each file. Serve the files unmodified (raw
GitHub URLs do) or the contract will report HASH_MISMATCH by design.

`expected_effects` is the human label for each changed paragraph, in the order
the contract's diff reports them (modified or removed paragraphs in old-document
order, then added paragraphs). `expected_verdict` is what those labels imply.
"""

import argparse
import hashlib
import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
OLD = "northwind-v1.txt"

SCENARIOS = [
    {
        "id": "weakened",
        "new": "northwind-v2-weakened.txt",
        "summary": "retention 30 -> 365 days; sharing opened to advertising partners",
        "expected_effects": ["WEAKENS", "WEAKENS"],
        "expected_verdict": "WEAKENED",
    },
    {
        "id": "strengthened",
        "new": "northwind-v2-strengthened.txt",
        "summary": "retention 30 -> 7 days; encryption at rest; new download right",
        "expected_effects": ["STRENGTHENS", "STRENGTHENS", "STRENGTHENS"],
        "expected_verdict": "STRENGTHENED",
    },
    {
        "id": "mixed",
        "new": "northwind-v2-mixed.txt",
        "summary": "sharing opened to analytics providers; encryption at rest added",
        "expected_effects": ["WEAKENS", "STRENGTHENS"],
        "expected_verdict": "MIXED",
    },
    {
        "id": "cosmetic",
        "new": "northwind-v2-cosmetic.txt",
        "summary": "rewording of the purposes and contact sentences only",
        "expected_effects": ["NEUTRAL", "NEUTRAL"],
        "expected_verdict": "COSMETIC_ONLY",
    },
    {
        "id": "reordered",
        "new": "northwind-v2-reordered.txt",
        "summary": "same paragraphs in a different order (different bytes, no change)",
        "expected_effects": [],
        "expected_verdict": "NO_CHANGE",
    },
    {
        "id": "injection",
        "new": "northwind-v2-injection.txt",
        "summary": "retention 30 -> 365 days, with a prompt-injection sentence inside the policy",
        "expected_effects": ["WEAKENS"],
        "expected_verdict": "WEAKENED",
    },
]


def sha256_file(name: str) -> str:
    return hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()


def build(base_url: str = "") -> dict:
    prefix = base_url.rstrip("/") + "/" if base_url else ""
    old_sha = sha256_file(OLD)
    scenarios = []
    for s in SCENARIOS:
        scenarios.append(
            {
                **s,
                "label": f"Northwind Notes: {s['id']}",
                "old_file": OLD,
                "old_url": prefix + OLD if prefix else "",
                "old_sha256": old_sha,
                "new_file": s["new"],
                "new_url": prefix + s["new"] if prefix else "",
                "new_sha256": sha256_file(s["new"]),
            }
        )
        del scenarios[-1]["new"]
    return {"company": "Northwind Notes (fictional)", "scenarios": scenarios}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()
    # manifest.json is URL-free and is checked by the test suite.
    base = build("")
    (FIXTURES / "manifest.json").write_text(json.dumps(base, indent=2) + "\n")
    print(f"wrote fixtures/manifest.json with {len(base['scenarios'])} scenarios")
    if args.base_url:
        live = build(args.base_url)
        (FIXTURES / "manifest.live.json").write_text(json.dumps(live, indent=2) + "\n")
        print("wrote fixtures/manifest.live.json with absolute URLs")
