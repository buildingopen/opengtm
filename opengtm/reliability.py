"""Deterministic validation; these checks are not independent factual research."""

from __future__ import annotations

import re
from copy import deepcopy
from urllib.parse import urlsplit


def canonical_domain(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parsed = urlsplit(
            value.strip() if "://" in value else "https://" + value.strip()
        )
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return ""
        host = (parsed.hostname or "").lower().rstrip(".")
        host = host.removeprefix("www.")
        host = host.encode("idna").decode("ascii")
        if (
            len(host) > 253
            or "." not in host
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            )
        ):
            return ""
        return host
    except (ValueError, UnicodeError):
        return ""


def linkedin_profile(value: str) -> str:
    if not isinstance(value, str):
        return ""
    try:
        url = value if "://" in value else "https://" + value
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"linkedin.com", "www.linkedin.com"}
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not re.fullmatch(r"/in/[A-Za-z0-9_%\-]+/?", parsed.path)
        ):
            return ""
        return "https://www.linkedin.com" + parsed.path.rstrip("/")
    except ValueError:
        return ""


def normalize_research(raw: dict) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("contact", {}), dict):
        raise TypeError("Invalid research object")
    findings = raw.get("findings", [])
    if not isinstance(findings, list) or any(not isinstance(f, dict) for f in findings):
        raise TypeError("Invalid findings")
    data = deepcopy(raw)
    contact = data.setdefault("contact", {})
    email = contact.get("email")
    valid = isinstance(email, str) and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
    contact["email_status"] = (
        "missing" if not email else "unverified" if valid else "invalid"
    )
    if email and not valid:
        contact["email"] = None
    contact["linkedin_status"] = (
        "unverified" if contact.get("linkedin_url") else "missing"
    )
    # Model-supplied provenance is not trusted. A model may invent quotes and URLs.
    for finding in data.setdefault("findings", []):
        finding["verification"] = "unverified"
        finding.pop("source_text", None)
    data["status"] = "completed"
    data["research_accuracy"] = "unverified"
    return data


def source_quote(finding: dict, domain: str) -> str:
    """Validate a caller-supplied source snapshot, not an LLM's verification claim.

    The caller must obtain source_text independently. Matching a quotation proves
    only that text occurs in that snapshot, never the finding's interpretation.
    """
    quote = finding.get("evidence")
    source = finding.get("source_text")
    if (
        finding.get("verification") == "source_quote"
        and isinstance(quote, str)
        and 1 <= len(quote.strip()) <= 160
        and isinstance(source, str)
        and quote.strip() in source
        and canonical_domain(domain)
        and canonical_domain(finding.get("source_url", "")) == canonical_domain(domain)
    ):
        return " ".join(quote.split())
    return ""
