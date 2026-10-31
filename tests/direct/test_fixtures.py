"""The synthetic fixtures behave as labelled, and the manifest matches the files."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))
import make_manifest  # noqa: E402

MANIFEST = json.loads((FIX / "manifest.json").read_text())
SCENARIOS = MANIFEST["scenarios"]
IDS = [s["id"] for s in SCENARIOS]


def test_manifest_is_current():
    assert MANIFEST == make_manifest.build("")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_manifest_hashes_match_the_exact_bytes(scenario):
    for side in ("old", "new"):
        data = (FIX / scenario[f"{side}_file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == scenario[f"{side}_sha256"]


@pytest.mark.parametrize("name", sorted(p.name for p in FIX.glob("*.txt")))
def test_fixture_files_are_plain_lf_utf8(name):
    data = (FIX / name).read_bytes()
    assert b"\r" not in data and not data.startswith(b"\xef\xbb\xbf")
    assert data.endswith(b"\n") and not data.endswith(b"\n\n")
    data.decode("utf-8")
    assert len(data) < 60_000


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_every_scenario_is_within_the_contract_bounds(fns, scenario):
    old = (FIX / scenario["old_file"]).read_text()
    new = (FIX / scenario["new_file"]).read_text()
    assert fns.sha256_hex(old.encode()) != fns.sha256_hex(new.encode())
    status, changes = fns.diff_paragraphs(old, new)
    assert status == "OK"
    assert len(changes) == len(scenario["expected_effects"])
    assert all(len(c["old"]) <= 600 and len(c["new"]) <= 600 for c in changes)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_labels_imply_the_expected_verdict(fns, scenario):
    items = [{"effect": e} for e in scenario["expected_effects"]]
    assert fns.verdict_from("OK", items) == scenario["expected_verdict"]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_contract_reaches_the_labelled_verdict_with_a_faithful_model(env, scenario):
    """End to end in direct mode: documents and model are mocked, the rest is the contract."""
    old = (FIX / scenario["old_file"]).read_text()
    new = (FIX / scenario["new_file"]).read_text()
    env.serve(old, new)
    if scenario["expected_effects"]:
        env.model(old, new, scenario["expected_effects"])
    cid = env.propose(old, new)
    env.c.assess(cid)
    assert env.info(cid)["verdict"] == scenario["expected_verdict"]


def test_the_injection_fixture_really_contains_an_injection():
    text = (FIX / "northwind-v2-injection.txt").read_text()
    assert "ignore all previous instructions" in text.lower()
    assert "ignore" not in (FIX / "northwind-v1.txt").read_text().lower()


def test_fixtures_describe_only_a_fictional_company():
    for path in FIX.glob("*.txt"):
        text = path.read_text()
        assert "Northwind Notes" in text
        assert "@northwind-notes.example" in text  # reserved .example domain, never a real mailbox
