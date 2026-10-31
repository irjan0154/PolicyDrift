"""Shared fixtures for the PolicyDrift direct-mode suite.

`env` wires a deployed contract to mocked documents and a mocked model so every
test reads as: serve two policy versions, propose, assess, assert.
"""

import json
import os
import re
import hashlib
import types

import pytest

CONTRACT = os.environ.get("POLICYDRIFT_CONTRACT", "contracts/policy_drift.py")
OLD_URL = "https://policies.example.com/privacy-v1.txt"
NEW_URL = "https://policies.example.com/privacy-v2.txt"

# Synthetic, fictional policy paragraphs. No real company is described.
P_RETENTION_OLD = "We keep your data for 30 days after you close your account."
P_RETENTION_NEW = "We keep your data for 365 days after you close your account."
P_SHARING_OLD = "We do not share your personal data with third parties."
P_SHARING_NEW = "We may share your personal data with advertising partners."
P_RIGHTS = "You can ask us to delete your data at any time."
P_CONTACT_OLD = "Write to privacy@example.com for any privacy question."
P_CONTACT_NEW = "Write to privacy@example.com for any privacy questions."
P_SECURITY_NEW = "All personal data is encrypted at rest and in transit."


def doc(*paragraphs: str) -> str:
    return "\n\n".join(paragraphs) + "\n"


def sha(text) -> str:
    data = text if isinstance(text, bytes) else text.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class Env:
    def __init__(self, vm, contract, fns, alice, bob):
        self.vm = vm
        self.c = contract
        self.fns = fns
        self.alice = alice
        self.bob = bob
        self.vm.sender = alice

    # -- documents -------------------------------------------------------
    def serve(self, old, new, old_url=OLD_URL, new_url=NEW_URL):
        for url, body in ((old_url, old), (new_url, new)):
            self.vm.mock_web(re.escape(url) + "$", {"status": 200, "body": body})

    def serve_status(self, url, status):
        self.vm.mock_web(re.escape(url) + "$", {"status": status, "body": "x"})

    def serve_bytes(self, url, data: bytes):
        self.vm.mock_web(
            re.escape(url) + "$",
            {"response": {"status": 200, "headers": {}, "body": data}, "method": "GET"},
        )

    def reset(self):
        self.vm.clear_mocks()

    # -- model -----------------------------------------------------------
    def items_for(self, old, new, effects, topic="OTHER"):
        status, changes = self.fns.diff_paragraphs(old, new)
        assert status == "OK", status
        assert len(changes) == len(effects), (len(changes), effects)
        return [
            {
                "id": ch["id"],
                "topic": topic,
                "effect": effects[i],
                "quote": (ch["new"] or ch["old"])[:60],
            }
            for i, ch in enumerate(changes)
        ]

    def model(self, old, new, effects, topic="OTHER"):
        payload = {"items": self.items_for(old, new, effects, topic)}
        self.vm.mock_llm(r".*", json.dumps(payload))

    def model_raw(self, raw: str):
        self.vm.mock_llm(r".*", raw)

    # -- contract --------------------------------------------------------
    def propose(self, old, new, label="Acme Notes v1 to v2", sender=None):
        if sender is not None:
            self.vm.sender = sender
        return self.c.propose_comparison(label, OLD_URL, sha(old), NEW_URL, sha(new))

    def run(self, old, new, effects, topic="OTHER"):
        """Serve, mock the model, propose and assess. Returns the comparison id."""
        self.serve(old, new)
        self.model(old, new, effects, topic)
        cid = self.propose(old, new)
        self.c.assess(cid)
        return cid

    def info(self, cid):
        return self.c.get_comparison(cid)

    def slots(self, who):
        """open_slots takes an Address; the direct_* fixtures are raw bytes."""
        return self.c.open_slots(self.fns.Address(who) if isinstance(who, (bytes, bytearray)) else who)

    def captured(self):
        return self.vm._captured_validators[-1][0]


@pytest.fixture
def env(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    cls = type(contract._instance)
    fns = types.SimpleNamespace(**cls.__init__.__globals__)
    return Env(direct_vm, contract, fns, direct_alice, direct_bob)


@pytest.fixture
def fns(env):
    return env.fns
