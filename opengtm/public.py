"""Public-source prospect research without model credentials.

Seeds are explicit inputs, not autonomous search results. Every fit signal is
linked to a fetched source; fit means worth investigating, not buying intent.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import ipaddress
import json
import socket
import threading
import time
from collections import Counter, OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from .gtm import prioritize
from .reliability import canonical_domain
from .telemetry import category, observed, qualified, span, update
from .validate import draft_for, matched_groups, validate_lead

AGENT = "OpenGTM-PublicResearch/0.1"
MAX_BYTES = 2_000_000


def public_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("Only public HTTPS sources are supported")
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(
        not ipaddress.ip_address(a[4][0]).is_global for a in addresses
    ):
        raise ValueError("Non-public source")
    return url


class PublicFetcher:
    def __init__(self, cache_ttl=0, cache_size=128):
        if cache_ttl < 0 or cache_size < 1:
            raise ValueError("Invalid cache limits")
        self.cache_ttl, self.cache_size = cache_ttl, cache_size
        self._local = threading.local()
        self._cache, self._lock = OrderedDict(), threading.RLock()
        self._robots_lock = threading.RLock()
        self.robots = {}
        self._stats: Counter[str] = Counter()

    @property
    def session(self):
        # requests.Session is not shared across worker threads.
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
            self._local.session.headers["User-Agent"] = AGENT
        return self._local.session

    def stats(self):
        with self._lock:
            return dict(self._stats)

    def _count(self, key, value=1):
        with self._lock:
            self._stats[key] += value

    @observed("opengtm.public.http", "tool")
    def _get(self, url, check_robots=False):
        requests_made = 0
        for _ in range(5):
            public_url(url)
            if check_robots:
                self._allowed(url)
            self._count("http_requests")
            requests_made += 1
            update(http_requests=requests_made)
            response = self.session.get(
                url, timeout=(8, 20), allow_redirects=False, stream=True
            )
            if response.is_redirect:
                target = urljoin(url, response.headers["Location"])
                response.close()
                url = target
                continue
            try:
                response.raise_for_status()
                content = bytearray()
                for block in response.iter_content(16384):
                    content.extend(block)
                    self._count("response_bytes", len(block))
                    if len(content) > MAX_BYTES:
                        raise ValueError("Source exceeds size limit")
                return url, response.headers.get("Content-Type", ""), bytes(content)
            finally:
                response.close()
        raise ValueError("Too many redirects")

    def _allowed(self, url):
        with self._robots_lock:
            return self._allowed_locked(url)

    def _allowed_locked(self, url):
        origin = f"https://{urlsplit(url).netloc}"
        if origin not in self.robots:
            try:
                _, _, body = self._get(origin + "/robots.txt")
                rules = RobotFileParser()
                rules.parse(body.decode("utf-8", errors="replace").splitlines())
                self.robots[origin] = rules
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    self.robots[origin] = None
                else:
                    raise ValueError("Could not verify robots policy") from None
        rules = self.robots[origin]
        if rules is not None and not rules.can_fetch(AGENT, url):
            raise ValueError("Source disallows automated research")

    @observed("opengtm.public.fetch", "tool")
    def fetch(self, url):
        with self._lock:
            cached = self._cache.get(url)
            if cached and time.monotonic() - cached[0] < self.cache_ttl:
                self._cache.move_to_end(url)
                self._stats["cache_hits"] += 1
                update(cache_hits=1)
                return copy.deepcopy(cached[1])
            self._stats["cache_misses"] += 1
            self._cache.pop(url, None)
        update(cache_misses=1)
        page = self._fetch_page(url)
        if self.cache_ttl:
            with self._lock:
                self._cache[url] = (time.monotonic(), copy.deepcopy(page))
                while len(self._cache) > self.cache_size:
                    self._cache.popitem(last=False)
        return page

    def _fetch_page(self, url):
        final, content_type, body = self._get(url, check_robots=True)
        if "html" not in content_type:
            raise ValueError("Expected HTML source")
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = " ".join(soup.stripped_strings)
        routes: list[dict] = []
        for link in soup.find_all("a", href=True):
            label = " ".join(link.stripped_strings)
            if any(
                word in label.lower()
                for word in (
                    "contact",
                    "sales",
                    "advertis",
                    "sponsor",
                    "partnership",
                    "talk to",
                    "book a demo",
                )
            ):
                href = urljoin(final, link["href"])
                if (
                    href.startswith("https://")
                    and not urlsplit(href).query
                    and href != final
                    and not any(r["url"] == href for r in routes)
                ):
                    routes.append({"label": label[:80], "url": href})
        content = BeautifulSoup(str(soup), "html.parser")
        for element in content(["header", "footer", "nav", "aside", "title", "form"]):
            element.decompose()
        main = content.find("main") or content.body or content
        return {
            "content_text": " ".join(main.stripped_strings),
            "url": final,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "sha256": hashlib.sha256(body).hexdigest(),
            "text": text,
            "routes": routes[:5],
        }


def match_groups(text, groups):
    return matched_groups(text, groups)


def excerpt(text, groups):
    # One short quotation per URL; do not export entire website text.
    terms = [term for group in groups for term in group]
    words = text.split()
    for index, word in enumerate(words):
        if any(term.lower() in word.lower() for term in terms):
            return " ".join(words[max(0, index - 3) : index + 7])
    return " ".join(words[:10])


@observed("opengtm.public.prospect", "agent")
def prospect(seller, candidate, fetcher, seen_domains=None):
    start = time.perf_counter()
    base = {
        "seller": seller["name"],
        "company": candidate["company"],
        "domain": canonical_domain(candidate["url"]),
        "source_url": candidate["url"],
        "buyer_role_hypothesis": seller["buyer_role"],
        "buying_intent": "unknown",
        "existing_customer_status": "not_established",
        "email_status": "not_verified",
        "contact_route_status": "published_link_only; recipient_not_verified",
    }
    if base["domain"] in seller.get("existing_customers", []):
        update(outcome="empty")
        return {**base, "status": "excluded_existing_customer"}
    try:
        page = fetcher.fetch(candidate["url"])
        matched = match_groups(
            page.get("content_text", page["text"]), seller["signal_groups"]
        )
        accepted = all(matched)
        update(outcome="completed", score=sum(bool(m) for m in matched))
        qualified(accepted)
        proof = {k: v for k, v in page.items() if k not in {"text", "content_text"}}
        proof["excerpts"] = [
            excerpt(page["text"], [group]) for group in seller["signal_groups"]
        ]
        draft = draft_for(matched, seller)
        result = {
            **base,
            "status": "research_qualified" if accepted else "insufficient_evidence",
            "fit_hypothesis": candidate["hypothesis"],
            "observed_business": candidate["observation"],
            "signals": matched,
            "evidence": proof,
            "next_step": seller["validation_question"],
            "draft_outreach": draft if accepted else None,
            "draft_basis": "Observed keyword presence; review source context before sending",
            "latency_seconds": round(time.perf_counter() - start, 3),
        }
        with span("opengtm.public.validate", "tool"):
            with_validation = validate_lead(
                result, seller, page, seen_domains=seen_domains
            )
            update(**{f"validation_{with_validation.outreach}_count": 1})
            first_reason = next((f.code for f in with_validation.findings), "none")
            update(
                validation_reason=first_reason
                if first_reason
                in {
                    "recipient_missing",
                    "trusted_clearance_required",
                    "insufficient_body_signals",
                    "unsupported_signal_claim",
                    "source_snapshot_changed",
                    "quote_not_in_source",
                    "stale_evidence",
                    "research_not_qualified",
                }
                else "other"
            )
        with span("opengtm.public.prioritize", "tool"):
            result["qualification"] = prioritize(seller, page, with_validation.research)
            update(
                fit_score=result["qualification"]["fit_score"],
                timing_score=result["qualification"]["timing_score"],
            )
        result["validation"] = with_validation.to_dict()
        result["ready_for_outreach"] = with_validation.ready_for_outreach
        return result
    except (requests.RequestException, ValueError, OSError) as exc:
        update(outcome="failed", error_category=category(exc))
        return {
            **base,
            "status": "research_failed",
            "error_category": type(exc).__name__,
            "latency_seconds": round(time.perf_counter() - start, 3),
        }


@observed("opengtm.public.pipeline", "agent")
def run(config, fetcher, max_workers=1):
    if type(max_workers) is not int or not 1 <= max_workers <= 8:
        raise ValueError("Workers must be between 1 and 8")
    started = time.perf_counter()
    initial_stats = fetcher.stats() if isinstance(fetcher, PublicFetcher) else {}
    results: list[dict] = []
    sellers: list[dict] = []
    for seller in config["sellers"]:
        # Verify seller positioning before applying its curated targeting policy.
        try:
            page = fetcher.fetch(seller["url"])
            if not all(match_groups(page["text"], seller["positioning_groups"])):
                sellers.append(
                    {"name": seller["name"], "status": "positioning_changed"}
                )
                continue
            sellers.append(
                {
                    "name": seller["name"],
                    "status": "positioning_checked",
                    "url": page["url"],
                    "sha256": page["sha256"],
                    "fetched_at": page["fetched_at"],
                }
            )
        except (requests.RequestException, ValueError, OSError) as exc:
            sellers.append(
                {
                    "name": seller["name"],
                    "status": "seller_fetch_failed",
                    "error_category": type(exc).__name__,
                }
            )
            continue
        seen: set[str] = set()
        pending: list[dict] = []
        ordered: list[dict | None] = []
        excluded = {canonical_domain(d) for d in seller.get("existing_customers", [])}
        for candidate in seller["candidates"]:
            domain = canonical_domain(candidate["url"])
            if domain in seen:
                ordered.append(
                    {
                        "seller": seller["name"],
                        "company": candidate["company"],
                        "domain": domain,
                        "status": "excluded_duplicate",
                    }
                )
                continue
            seen.add(domain)
            if domain in excluded:
                ordered.append(
                    {
                        "seller": seller["name"],
                        "company": candidate["company"],
                        "domain": domain,
                        "status": "excluded_existing_customer",
                    }
                )
                continue
            pending.append(candidate)
            ordered.append(None)
        if max_workers == 1:
            computed = [prospect(seller, c, fetcher) for c in pending]
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                # Propagate only the existing OpenGTM context; preserve result order.
                jobs = [
                    pool.submit(copy_context().run, prospect, seller, c, fetcher)
                    for c in pending
                ]
                computed = [job.result() for job in jobs]
        iterator = iter(computed)
        results.extend(next(iterator) if entry is None else entry for entry in ordered)
    update(
        result_count=len(results),
        qualified_count=sum(r["status"] == "research_qualified" for r in results),
    )
    for result in results:
        if "validation" not in result:
            policy = next(s for s in config["sellers"] if s["name"] == result["seller"])
            result["validation"] = validate_lead(result, policy).to_dict()
            result["ready_for_outreach"] = False
    stats = fetcher.stats() if isinstance(fetcher, PublicFetcher) else {}
    metrics = {
        k: stats.get(k, 0) - initial_stats.get(k, 0)
        for k in ("http_requests", "response_bytes", "cache_hits", "cache_misses")
    }
    metrics.update(
        elapsed_seconds=round(time.perf_counter() - started, 4),
        workers=max_workers,
        research_pass=sum(
            r.get("validation", {}).get("research") == "pass" for r in results
        ),
        outreach_ready=sum(r.get("ready_for_outreach", False) for r in results),
    )
    update(
        **{
            k: v
            for k, v in metrics.items()
            if k in ("http_requests", "cache_hits", "cache_misses")
        }
    )
    return {
        "efficiency": metrics,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "mode": "live public HTTP; curated seeds; deterministic fit rules",
        "seller_checks": sellers,
        "results": results,
        "model_calls": 0,
        "provider_cost_usd": 0,
        "trace_destination": "caller_configured",
        "outreach_sent": False,
        "limitations": "No buying intent, budget, deliverability, existing vendor relationship or financial-product eligibility is established.",
    }


def save(report, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    fields = [
        "seller",
        "company",
        "domain",
        "status",
        "buyer_role_hypothesis",
        "observed_business",
        "fit_hypothesis",
        "source_url",
        "next_step",
        "draft_outreach",
        "email_status",
        "validation_research",
        "validation_outreach",
        "validation_reasons",
        "ready_for_outreach",
    ]
    with (destination / "leads.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            {
                **r,
                "validation_research": r.get("validation", {}).get(
                    "research", "review"
                ),
                "validation_outreach": r.get("validation", {}).get(
                    "outreach", "review"
                ),
                "validation_reasons": ";".join(
                    f["code"] for f in r.get("validation", {}).get("findings", [])
                ),
            }
            for r in report["results"]
        )
    ranked = sorted(
        (r for r in report["results"] if r.get("qualification")),
        key=lambda r: (
            r["qualification"]["priority"] == "hold",
            -r["qualification"]["score"],
        ),
    )
    with (destination / "research-priority.csv").open("w", newline="") as handle:
        priority_fields = [
            "seller",
            "company",
            "priority",
            "score",
            "action",
            "buyer_role_hypothesis",
            "discovery_question",
            "offer",
            "buying_intent",
        ]
        writer = csv.DictWriter(
            handle, fieldnames=priority_fields, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows({**r, **r["qualification"]} for r in ranked)
    # A separate queue makes the gate enforceable without sending anything.
    with (destination / "outreach-ready.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(
            r
            for r in report["results"]
            if r.get("ready_for_outreach") is True
            and r.get("validation", {}).get("ready_for_outreach") is True
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--cache-ttl", type=float, default=300)
    args = parser.parse_args()
    report = run(
        json.loads(args.input.read_text()),
        PublicFetcher(cache_ttl=args.cache_ttl),
        max_workers=args.workers,
    )
    save(report, args.output)
    print(
        json.dumps(
            {
                "sellers": report["seller_checks"],
                "statuses": [
                    {k: r[k] for k in ("seller", "company", "status")}
                    for r in report["results"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
