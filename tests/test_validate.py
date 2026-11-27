from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from opengtm.validate import Clearance, validate_lead

CASES = json.loads(
    (Path(__file__).parents[1] / "evals/validator-cases.json").read_text()
)


def execute(case):
    values = dict(case)
    values["now"] = datetime.fromisoformat(values["now"])
    receipt = values.pop("clearance", None)
    if receipt:
        receipt = Clearance(
            **{**receipt, "issued_at": datetime.fromisoformat(receipt["issued_at"])}
        )
    return validate_lead(**values, clearance=receipt)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_labeled_cases(case):
    result = execute(case["input"])
    assert (result.research, result.outreach) == (
        case["expected"]["research"],
        case["expected"]["outreach"],
    )
    if case["expected"]["code"]:
        assert case["expected"]["code"] in {f.code for f in result.findings}
    assert result.ready_for_outreach == (result.research == result.outreach == "pass")


def test_reasons_do_not_contain_sensitive_input():
    source = dict(CASES[0]["input"])
    source["lead"] = {**source["lead"], "contact_email": "private-secret@example.test"}
    result = execute(source)
    assert "private-secret" not in json.dumps(result.to_dict())


def test_validator_import_does_not_initialize_tracing():
    import subprocess
    import sys

    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import opengtm.validate; assert 'traceroot' not in sys.modules; assert 'requests' not in sys.modules",
        ],
        check=True,
    )


@pytest.mark.parametrize("status", [{}, [], False, None])
def test_malformed_status_is_rejected_without_crash(status):
    source = dict(CASES[0]["input"])
    source["lead"] = {**source["lead"], "status": status}
    result = execute(source)
    assert result.research == result.outreach == "reject"
    assert "invalid_research_status" in {f.code for f in result.findings}


def test_string_true_cannot_approve_recipient():
    source = dict(CASES[0]["input"])
    source["clearance"] = {**source["clearance"], "deliverable": "true"}
    assert execute(source).outreach == "reject"


def test_bad_clearance_timestamp_is_not_accepted():
    source = dict(CASES[0]["input"])
    source["now"] = datetime.fromisoformat(source["now"])
    receipt = Clearance(
        recipient="buyer@example.test",
        issued_at="yesterday",
        deliverable=True,
        account_reviewed=True,
    )
    source.pop("clearance")
    result = validate_lead(**source, clearance=receipt)
    assert result.outreach == "review"


def test_strict_cli_writes_safe_report_and_fails_review(tmp_path):
    import subprocess
    import sys

    data = CASES[0]["input"]
    lead = {**data["lead"], "seller": "Synthetic seller"}
    source = tmp_path / "input.json"
    policy = tmp_path / "policy.json"
    output = tmp_path / "validation.json"
    source.write_text(json.dumps({"results": [lead]}))
    policy.write_text(json.dumps({"sellers": [data["policy"]]}))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "opengtm.validate",
            "--input",
            str(source),
            "--policy",
            str(policy),
            "--output",
            str(output),
            "--strict",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    saved = json.loads(output.read_text())
    assert saved["results"][0]["outreach"] == "review"
    assert not saved["results"][0]["ready_for_outreach"]
    assert (
        "buyer@example.test" not in output.read_text() + result.stdout + result.stderr
    )
