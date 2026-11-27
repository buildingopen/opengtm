from __future__ import annotations

from unittest.mock import Mock

import pytest
from opengtm.public import PublicFetcher, public_url, run


def seller(**changes):
    return dict(
        name="Seller",
        url="https://seller.example/",
        positioning_groups=[["clipping"]],
        signal_groups=[["podcast"], ["video"]],
        buyer_role="Producer",
        conversation="a clipping pilot",
        validation_question="whether editing is already covered",
        candidates=changes.pop("candidates", []),
        **changes,
    )


def page(text):
    return dict(
        url="https://source.example/",
        text=text,
        routes=[],
        sha256="test",
        fetched_at="test",
    )


def test_existing_customer_and_duplicate_are_not_refetched():
    fetcher = Mock()
    fetcher.fetch.side_effect = [page("clipping"), page("podcast video")]
    spec = seller(
        existing_customers=["customer.example"],
        candidates=[
            dict(company="Existing", url="https://customer.example/"),
            dict(
                company="Prospect",
                url="https://source.example/",
                observation="a video podcast",
                hypothesis="test",
            ),
            dict(company="Duplicate", url="https://www.source.example/about"),
        ],
    )
    report = run({"sellers": [spec]}, fetcher)
    assert [r["status"] for r in report["results"]] == [
        "excluded_existing_customer",
        "research_qualified",
        "excluded_duplicate",
    ]
    assert fetcher.fetch.call_count == 2


def test_changed_seller_positioning_stops_prospecting():
    fetcher = Mock()
    fetcher.fetch.return_value = page("a completely different product")
    report = run(
        {
            "sellers": [
                seller(
                    candidates=[
                        {"company": "Never fetched", "url": "https://source.example/"}
                    ]
                )
            ]
        },
        fetcher,
    )
    assert report["seller_checks"][0]["status"] == "positioning_changed"
    assert report["results"] == []
    assert fetcher.fetch.call_count == 1


def test_missing_signal_is_not_qualified_and_has_no_draft():
    fetcher = Mock()
    fetcher.fetch.side_effect = [page("clipping"), page("podcast only")]
    spec = seller(
        candidates=[
            dict(
                company="Prospect",
                url="https://source.example/",
                observation="a podcast",
                hypothesis="test",
            )
        ]
    )
    report = run({"sellers": [spec]}, fetcher)
    assert report["results"][0]["status"] == "insufficient_evidence"
    assert report["results"][0]["draft_outreach"] is None
    assert "text" not in report["results"][0]["evidence"]


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:password@example.com",
        "https://example.com:8443",
    ],
)
def test_invalid_sources_are_rejected_before_network(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_private_dns_is_blocked(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(ValueError, match="Non-public"):
        public_url("https://example.com")


def test_robot_denial_stops_page_request(monkeypatch):
    fetcher = PublicFetcher()
    monkeypatch.setattr(
        fetcher,
        "_get",
        lambda *a, **k: (
            "https://example.com/robots.txt",
            "text/plain",
            b"User-agent: *\nDisallow: /",
        ),
    )
    with pytest.raises(ValueError, match="disallows"):
        fetcher._allowed("https://example.com/")


def test_outreach_does_not_repeat_unverified_seed_claim():
    fetcher = Mock()
    fetcher.fetch.side_effect = [page("clipping"), page("podcast video")]
    spec = seller(
        candidates=[
            dict(
                company="Prospect",
                url="https://source.example/",
                observation="a business with 500% growth",
                hypothesis="test",
            )
        ]
    )
    result = run({"sellers": [spec]}, fetcher)["results"][0]
    assert "500%" not in result["draft_outreach"]
    assert result["draft_basis"].startswith("Observed keyword presence")


def test_research_match_cannot_enter_outreach_queue_without_clearance(tmp_path):
    import csv
    from datetime import datetime, timezone

    from opengtm.public import save

    verified_page = {
        **page("podcast video"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "sha256": "a" * 64,
        "content_text": "podcast video",
    }
    fetcher = Mock()
    fetcher.fetch.side_effect = [page("clipping"), verified_page]
    report = run(
        {
            "sellers": [
                seller(
                    candidates=[
                        dict(
                            company="Prospect",
                            url="https://source.example/",
                            observation="video podcast",
                            hypothesis="test",
                        )
                    ]
                )
            ]
        },
        fetcher,
    )
    result = report["results"][0]
    assert result["validation"]["research"] == "pass"
    assert result["validation"]["outreach"] == "review"
    # Even a stale/forged top-level flag cannot override the validation verdict.
    result["ready_for_outreach"] = True
    save(report, tmp_path)
    with (tmp_path / "outreach-ready.csv").open() as handle:
        assert list(csv.DictReader(handle)) == []
