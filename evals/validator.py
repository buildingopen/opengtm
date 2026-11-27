"""39 labeled validation scenarios, scored by TraceRoot locally (never uploaded)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from opengtm.validate import Clearance, validate_lead
from traceroot import EvalCase, evaluate


def task(case):
    values = dict(case)
    values["now"] = datetime.fromisoformat(values["now"])
    receipt = values.pop("clearance", None)
    if receipt:
        receipt = Clearance(
            **{**receipt, "issued_at": datetime.fromisoformat(receipt["issued_at"])}
        )
    return validate_lead(**values, clearance=receipt).to_dict()


def verdicts(input, output, expected=None):
    codes = {f["code"] for f in output["findings"]}
    return {
        "research_decision": output["research"] == expected["research"],
        "outreach_decision": output["outreach"] == expected["outreach"],
        "reason_code": expected["code"] is None or expected["code"] in codes,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("validator-cases.json").read_text())
    result = evaluate(
        name="GTM evidence and outreach validator",
        evaluation_key="gtm-validator-v1",
        dataset=[EvalCase(**c) for c in cases],
        task=task,
        scorers=[verdicts],
        local=True,
        progress=False,
        max_concurrency=1,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(str(args.output))
    failed = [
        r.id
        for r in result.item_results
        if r.error or r.scorer_errors or any(s.value is not True for s in r.scores)
    ]
    print(json.dumps({"cases": result.case_count, "failed": failed, "local": True}))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
