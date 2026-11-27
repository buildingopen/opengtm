"""Fail-closed validation of source-backed prospect records (standard library only).

This validates evidence provenance and a constrained outreach template, not the
truth of arbitrary prose or buying intent. Fresh pages and clearances must come
from trusted callers, never model-produced verification flags in lead records.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypeGuard
from urllib.parse import urlsplit

VERSION = "1.0"


@dataclass(frozen=True)
class Finding:
    code: str
    stage: str
    severity: str


@dataclass(frozen=True)
class Clearance:
    """Trusted adapter/human receipt; not an email-verification service itself."""

    recipient: str
    issued_at: datetime
    deliverable: bool
    account_reviewed: bool


@dataclass(frozen=True)
class Validation:
    research: str
    outreach: str
    findings: tuple[Finding, ...]
    version: str = VERSION

    @property
    def ready_for_outreach(self) -> bool:
        return self.research == self.outreach == "pass"

    def to_dict(self) -> dict:
        return {**asdict(self), "ready_for_outreach": self.ready_for_outreach}


def host(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value if "://" in value else "https://" + value)
        hostname = (parsed.hostname or "").lower().rstrip(".").removeprefix("www.")
        if (
            parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or "." not in hostname
        ):
            return ""
        try:
            ipaddress.ip_address(hostname)
            return ""
        except ValueError:
            pass
        hostname = hostname.encode("idna").decode("ascii")
        return (
            hostname
            if len(hostname) <= 253
            and all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in hostname.split(".")
            )
            else ""
        )
    except (ValueError, UnicodeError):
        return ""


def normalized(text: str) -> str:
    return " ".join(text.split())


def contains(text: str, term: str) -> bool:
    """Whole terms: API must not match 'capital'; phrases tolerate whitespace."""
    return bool(
        re.search(
            r"(?<!\w)" + re.escape(normalized(term)) + r"(?!\w)",
            normalized(text),
            re.IGNORECASE,
        )
    )


def groups_valid(groups: Any) -> TypeGuard[list[list[str]]]:
    return (
        isinstance(groups, list)
        and bool(groups)
        and all(
            isinstance(group, list)
            and bool(group)
            and all(
                isinstance(term, str) and bool(term.strip()) and len(term) <= 100
                for term in group
            )
            for group in groups
        )
    )


def matched_groups(text: str, groups: list[list[str]]) -> list[list[str]]:
    return [[term for term in group if contains(text, term)] for group in groups]


def draft_for(signals: list[list[str]], policy: dict) -> str:
    return (
        f"Your public site mentions {' and '.join(group[0] for group in signals if group)}. "
        f"Would it be useful to explore {policy['conversation']}? "
        f"I would first want to understand {policy['validation_question']}."
    )


def timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def validate_lead(
    lead: Any,
    policy: Any,
    page: dict | None = None,
    *,
    now: datetime | None = None,
    seen_domains: set[str] | None = None,
    clearance: Clearance | None = None,
    max_age_days: int = 30,
) -> Validation:
    """Pure validator. No network, SDK initialization, telemetry, or sending.

    `page` is an independently obtained fetch result, never a field pulled out of
    `lead`. `clearance` is injected by a trusted application boundary. Callers
    remain responsible for authenticating adapters and storing original sources.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or max_age_days < 0:
        raise ValueError("Validation clock must be timezone-aware and age nonnegative")
    findings: list[Finding] = []

    def add(code: str, stage: str = "research", severity: str = "reject"):
        findings.append(Finding(code, stage, severity))

    def finish() -> Validation:
        def verdict(stage: str) -> str:
            severities = {f.severity for f in findings if f.stage == stage}
            return (
                "reject"
                if "reject" in severities
                else "review"
                if "review" in severities
                else "pass"
            )

        research = verdict("research")
        outreach = verdict("outreach")
        if research == "reject":
            outreach = "reject"
        elif research == "review" and outreach == "pass":
            outreach = "review"
        return Validation(research, outreach, tuple(findings))

    if not isinstance(lead, dict) or not isinstance(policy, dict):
        add("invalid_record")
        return finish()
    groups = policy.get("signal_groups")
    if not groups_valid(groups) or not all(
        isinstance(policy.get(k), str) and policy[k].strip()
        for k in ("conversation", "validation_question")
    ):
        add("invalid_policy")
        return finish()
    early_reasons = {
        "excluded_existing_customer": "existing_customer",
        "excluded_duplicate": "duplicate_account",
        "research_failed": "research_failed",
    }
    if isinstance(lead.get("status"), str) and lead["status"] in early_reasons:
        add(early_reasons[lead["status"]])
        return finish()
    domain = host(lead.get("domain"))
    if not domain or host(lead.get("source_url")) != domain:
        add("invalid_company_domain")
    exclusions = policy.get("existing_customers", [])
    if not isinstance(exclusions, list):
        add("invalid_policy")
        return finish()
    excluded = {host(d) for d in exclusions}
    if lead.get("status") == "excluded_existing_customer" or (
        domain and domain in excluded
    ):
        add("existing_customer")
    if lead.get("status") == "excluded_duplicate" or (
        domain and domain in (seen_domains or set())
    ):
        add("duplicate_account")
    if not isinstance(lead.get("status"), str) or lead.get("status") not in {
        "research_qualified",
        "excluded_existing_customer",
        "excluded_duplicate",
        "research_failed",
        "insufficient_evidence",
    }:
        add("invalid_research_status")
    if lead.get("status") == "insufficient_evidence":
        add("research_not_qualified")
    if lead.get("status") == "research_failed":
        add("research_failed")
    proof = lead.get("evidence")
    if not isinstance(proof, dict):
        add("evidence_missing")
        return finish()
    if host(proof.get("url")) != domain:
        add("source_domain_mismatch")
    recorded_at = timestamp(proof.get("fetched_at"))
    if recorded_at is None:
        add("invalid_evidence_timestamp")
    elif recorded_at > now + timedelta(minutes=5):
        add("future_evidence")
    elif now - recorded_at > timedelta(days=max_age_days):
        add("stale_evidence", severity="review")
    digest = proof.get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        add("invalid_source_digest")
    quotes = proof.get("excerpts")
    if (
        not isinstance(quotes, list)
        or not quotes
        or any(not isinstance(q, str) or not q.strip() for q in quotes)
    ):
        add("invalid_source_quotes")
        quotes = []
    if page is None:
        add("independent_source_required", severity="review")
    elif not isinstance(page, dict) or not isinstance(page.get("text"), str):
        add("invalid_independent_source")
    else:
        fresh_at = timestamp(page.get("fetched_at"))
        if fresh_at is None or fresh_at > now + timedelta(minutes=5):
            add("invalid_fresh_source_timestamp")
        elif now - fresh_at > timedelta(days=max_age_days):
            add("fresh_source_too_old", severity="review")
        if host(page.get("url")) != domain:
            add("fresh_source_domain_mismatch")
        elif page.get("url") != proof.get("url"):
            add("source_location_changed", severity="review")
        if not isinstance(page.get("sha256"), str) or not re.fullmatch(
            r"[a-f0-9]{64}", page["sha256"]
        ):
            add("invalid_fresh_source_digest")
        elif page["sha256"] != digest:
            add("source_snapshot_changed", severity="review")
        text = normalized(page["text"])
        if any(normalized(q) not in text for q in quotes):
            add("quote_not_in_source")
        body = page.get("content_text", page["text"])
        if not isinstance(body, str):
            add("invalid_content_text")
            body = ""
        if not all(matched_groups(body, groups)):
            add("insufficient_body_signals")
        signals = lead.get("signals")
        if (
            not isinstance(signals, list)
            or len(signals) != len(groups)
            or any(
                not isinstance(g, list)
                or not g
                or any(
                    not isinstance(term, str)
                    or term not in allowed
                    or not contains(body, term)
                    for term in g
                )
                for g, allowed in zip(signals, groups)
            )
        ):
            add("unsupported_signal_claim")

    signals = lead.get("signals")
    if not groups_valid(signals) or len(signals) != len(groups):
        add("invalid_draft_signals", "outreach")
    elif lead.get("draft_outreach") != draft_for(signals, policy):
        add("unsupported_draft_content", "outreach")
    # Model-supplied status flags and public forms never verify a recipient.
    email = lead.get("contact_email")
    if not email:
        add("recipient_missing", "outreach", "review")
    elif not isinstance(email, str) or not re.fullmatch(
        r"[^\s@]+@[^\s@]+\.[^\s@]+", email
    ):
        add("invalid_recipient", "outreach")
    if clearance is None:
        add("trusted_clearance_required", "outreach", "review")
    elif not isinstance(clearance, Clearance):
        add("invalid_clearance", "outreach")
    else:
        if (
            not isinstance(clearance.issued_at, datetime)
            or clearance.issued_at.tzinfo is None
            or not timedelta(0) <= now - clearance.issued_at <= timedelta(days=7)
        ):
            add("clearance_expired", "outreach", "review")
        if not email or clearance.recipient != email:
            add("clearance_recipient_mismatch", "outreach")
        if clearance.deliverable is not True:
            add("recipient_not_deliverable", "outreach")
        if clearance.account_reviewed is not True:
            add("account_review_required", "outreach", "review")
    return finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 unless every record is ready for outreach",
    )
    args = parser.parse_args()
    report = json.loads(args.input.read_text())
    policies = {p["name"]: p for p in json.loads(args.policy.read_text())["sellers"]}
    seen: dict[str, set[str]] = {}
    results = []
    for index, lead in enumerate(report["results"]):
        seller = lead.get("seller", "") if isinstance(lead, dict) else ""
        result = validate_lead(
            lead, policies.get(seller), seen_domains=seen.setdefault(seller, set())
        )
        if isinstance(lead, dict) and host(lead.get("domain")):
            seen[seller].add(host(lead["domain"]))
        results.append({"index": index, **result.to_dict()})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"version": VERSION, "results": results}, indent=2) + "\n"
    )
    if args.strict and any(not r["ready_for_outreach"] for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
