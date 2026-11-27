"""Revalidate an earlier lead report against freshly fetched public sources."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import requests
from opengtm.public import PublicFetcher
from opengtm.validate import host, validate_lead


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    report = json.loads(args.input.read_text())
    policies = {p["name"]: p for p in json.loads(args.policy.read_text())["sellers"]}
    fetcher, seen, results = PublicFetcher(), {}, []
    for lead in report["results"]:
        seller = lead.get("seller", "")
        page, fetch_error = None, None
        if lead.get("status") == "research_qualified":
            try:
                page = fetcher.fetch(lead["evidence"]["url"])
            except (requests.RequestException, ValueError, OSError) as exc:
                fetch_error = type(exc).__name__
        result = validate_lead(
            lead,
            policies.get(seller),
            page,
            seen_domains=seen.setdefault(seller, set()),
        )
        seen[seller].add(host(lead.get("domain")))
        results.append(
            {
                "seller": seller,
                "company": lead.get("company"),
                "validation": result.to_dict(),
                "fresh_source_fetch_error": fetch_error,
                "fresh_source_hash": page.get("sha256") if page else None,
            }
        )
    summary = {
        "research": dict(Counter(r["validation"]["research"] for r in results)),
        "outreach": dict(Counter(r["validation"]["outreach"] for r in results)),
        "ready": sum(r["validation"]["ready_for_outreach"] for r in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "mode": "live independent source revalidation; no trusted contact clearances supplied",
                "summary": summary,
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(summary, indent=2))
    if args.strict and not all(r["validation"]["ready_for_outreach"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
