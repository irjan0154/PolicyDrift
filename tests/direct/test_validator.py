"""Consensus behaviour: what a validator accepts and what it rejects.

`run_validator()` replays the validator function captured from the last
`assess` call. Mocks apply at replay time, so swapping them simulates a
validator that sees different documents or a different model answer.
"""

import copy
import json

import pytest

from conftest import (
    OLD_URL,
    NEW_URL,
    doc,
    P_RETENTION_OLD,
    P_RETENTION_NEW,
    P_SHARING_OLD,
    P_SHARING_NEW,
    P_RIGHTS,
    P_CONTACT_OLD,
)

OLD = doc(P_RETENTION_OLD, P_SHARING_OLD, P_RIGHTS, P_CONTACT_OLD)
NEW = doc(P_RETENTION_NEW, P_SHARING_NEW, P_RIGHTS, P_CONTACT_OLD)  # two weakening edits


@pytest.fixture
def assessed(env):
    """A finished, honest round: leaves one captured validator behind."""
    env.run(OLD, NEW, ["WEAKENS", "WEAKENS"], topic="SHARING")
    assert len(env.vm._captured_validators) == 1
    return env


def test_exactly_one_nondeterministic_round_per_assess(assessed):
    assessed.vm.clear_validators()
    cid = assessed.propose(OLD, NEW)
    assessed.c.assess(cid)
    assert len(assessed.vm._captured_validators) == 1


# ------------------------------------------------ honest leader, honest view


def test_validator_agrees_with_an_honest_leader(assessed):
    assert assessed.vm.run_validator() is True


def test_validator_may_differ_on_topics_and_quotes(assessed):
    assessed.reset()
    assessed.serve(OLD, NEW)
    items = assessed.items_for(OLD, NEW, ["WEAKENS", "WEAKENS"], topic="PURPOSE")
    for it in items:
        it["quote"] = it["quote"][:20]
    assessed.model_raw(json.dumps({"items": items}))
    assert assessed.vm.run_validator() is True


# ------------------------------------------- validator sees something else


def test_validator_disagrees_when_its_model_judges_differently(assessed):
    assessed.reset()
    assessed.serve(OLD, NEW)
    assessed.model(OLD, NEW, ["WEAKENS", "STRENGTHENS"])
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_its_model_is_unsure(assessed):
    assessed.reset()
    assessed.serve(OLD, NEW)
    assessed.model(OLD, NEW, ["WEAKENS", "UNCLEAR"])
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_the_document_it_fetches_does_not_match_the_commitment(assessed):
    assessed.reset()
    assessed.serve(OLD, NEW + "\nA paragraph the proposer never committed to.\n")
    assessed.model(OLD, NEW, ["WEAKENS", "WEAKENS"])
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_its_model_answers_garbage(assessed):
    assessed.reset()
    assessed.serve(OLD, NEW)
    assessed.model_raw("I am sorry, I cannot do that.")
    assert assessed.vm.run_validator() is False


def test_validator_disagrees_when_its_source_is_down(assessed):
    assessed.reset()
    assessed.serve_status(OLD_URL, 503)
    assessed.serve_status(NEW_URL, 503)
    assessed.model(OLD, NEW, ["WEAKENS", "WEAKENS"])
    assert assessed.vm.run_validator() is False


# ------------------------------------------------------------ forged leader


def forged(env, mutate):
    result = copy.deepcopy(env.captured())
    mutate(result)
    return result


def test_validator_rejects_a_leader_that_hides_the_changes(assessed):
    def hide(r):
        r["changes"], r["items"] = [], []

    assert assessed.vm.run_validator(leader_result=forged(assessed, hide)) is False


def test_validator_rejects_a_leader_that_flips_an_effect(assessed):
    def flip(r):
        r["items"][0]["effect"] = "STRENGTHENS"

    assert assessed.vm.run_validator(leader_result=forged(assessed, flip)) is False


def test_validator_rejects_a_leader_that_invents_a_change(assessed):
    def invent(r):
        r["changes"].append({"id": 2, "kind": "ADDED", "old": "", "new": "We sell your data."})
        r["items"].append({"id": 2, "kind": "ADDED", "topic": "SHARING", "effect": "WEAKENS", "quote": "We sell"})

    assert assessed.vm.run_validator(leader_result=forged(assessed, invent)) is False


def test_validator_rejects_a_leader_that_edits_the_quoted_text(assessed):
    def edit(r):
        r["changes"][0]["new"] = r["changes"][0]["new"].replace("365", "3")

    assert assessed.vm.run_validator(leader_result=forged(assessed, edit)) is False


def test_validator_rejects_a_leader_that_claims_a_different_outcome(assessed):
    def claim(r):
        r["outcome"], r["reason"] = "TOO_LARGE", "DOC_SIZE"

    assert assessed.vm.run_validator(leader_result=forged(assessed, claim)) is False


def test_validator_rejects_a_leader_that_changes_only_the_outcome(assessed):
    def claim(r):
        r["outcome"] = "TOO_LARGE"  # reason, changes and items left as they were

    assert assessed.vm.run_validator(leader_result=forged(assessed, claim)) is False


@pytest.mark.parametrize(
    "field, value",
    [
        ("quote", "They sell everything to everyone."),
        ("quote", "x" * 400),
        ("topic", "MONEY"),
        ("kind", "REMOVED"),
    ],
)
def test_validator_rejects_a_leader_that_stores_forged_diagnostics(assessed, field, value):
    # the effects are exactly what an honest validator computes; only a stored field is forged
    def forge(r):
        r["items"][0][field] = value

    assert assessed.vm.run_validator(leader_result=forged(assessed, forge)) is False


def test_validator_rejects_a_leader_that_stores_an_extra_field(assessed):
    def forge(r):
        r["items"][0]["note"] = "smuggled"

    assert assessed.vm.run_validator(leader_result=forged(assessed, forge)) is False


@pytest.mark.parametrize("bad", [None, "WEAKENED", 7, [], {}, {"outcome": "OK"}])
def test_validator_rejects_malformed_leader_results(assessed, bad):
    assert assessed.vm.run_validator(leader_result=bad) is False


# ---------------------------------------- recorded failure (hash mismatch)


def test_validators_agree_on_a_hash_mismatch_only_if_they_see_it_too(env):
    env.serve(OLD, NEW + "\nDrift.\n")
    cid = env.propose(OLD, NEW)
    env.c.assess(cid)
    assert env.info(cid)["status"] == "RETRYABLE"
    assert env.vm.run_validator() is True  # same bytes, same mismatch
    env.reset()
    env.serve(OLD, NEW)
    env.model(OLD, NEW, ["WEAKENS", "WEAKENS"])
    assert env.vm.run_validator() is False  # this validator saw the committed bytes


# ----------------------------------------------------- leader raised an error


def test_leader_llm_error_never_gets_agreement(assessed):
    # the validator's own model works, so the leader is the odd one out
    assert assessed.vm.run_validator(leader_error=Exception("[LLM_ERROR] model call failed")) is False


def test_leader_llm_error_never_gets_agreement_even_if_the_validator_fails_too(assessed):
    assessed.reset()
    assessed.serve(OLD, NEW)
    assessed.model_raw("garbage")
    assert assessed.vm.run_validator(leader_error=Exception("[LLM_ERROR] model call failed")) is False


def test_external_errors_must_match_exactly(assessed):
    assessed.reset()
    assessed.serve_status(OLD_URL, 404)
    assessed.serve_status(NEW_URL, 404)
    assert assessed.vm.run_validator(leader_error=Exception("[EXTERNAL] HTTP 404")) is True
    assert assessed.vm.run_validator(leader_error=Exception("[EXTERNAL] HTTP 403")) is False


def test_external_leader_error_is_rejected_when_the_validator_reads_the_page(assessed):
    assert assessed.vm.run_validator(leader_error=Exception("[EXTERNAL] HTTP 404")) is False


def test_transient_errors_agree_when_both_sides_are_transient(assessed):
    assessed.reset()
    assessed.serve_status(OLD_URL, 502)
    assessed.serve_status(NEW_URL, 502)
    assert assessed.vm.run_validator(leader_error=Exception("[TRANSIENT] fetch failed")) is True


def test_transient_leader_error_is_rejected_when_the_validator_succeeds(assessed):
    assert assessed.vm.run_validator(leader_error=Exception("[TRANSIENT] fetch failed")) is False


def test_transient_leader_vs_external_validator_do_not_agree(assessed):
    assessed.reset()
    assessed.serve_status(OLD_URL, 404)
    assessed.serve_status(NEW_URL, 404)
    assert assessed.vm.run_validator(leader_error=Exception("[TRANSIENT] fetch failed")) is False


def test_unclassified_leader_errors_are_never_agreed(assessed):
    assert assessed.vm.run_validator(leader_error=Exception("boom")) is False
    assessed.reset()
    assessed.serve_status(OLD_URL, 404)
    assessed.serve_status(NEW_URL, 404)
    assert assessed.vm.run_validator(leader_error=Exception("boom")) is False


def test_validator_rejects_a_leader_that_forges_the_outcome_of_a_round_without_changes(env):
    # a reordered document has no changes, so there are no items or quotes to give the forgery away
    reordered = doc(P_CONTACT_OLD, P_RIGHTS, P_SHARING_OLD, P_RETENTION_OLD)
    env.serve(OLD, reordered)
    cid = env.propose(OLD, reordered)
    env.c.assess(cid)
    assert env.info(cid)["verdict"] == "NO_CHANGE"
    assert env.vm.run_validator() is True

    def forge(r):
        r["outcome"] = "TOO_LARGE"  # same reason (empty), same empty change list

    assert env.vm.run_validator(leader_result=forged(env, forge)) is False
