from __future__ import annotations

import time
from contextvars import ContextVar
from threading import Lock
from unittest.mock import Mock

import pytest
from opengtm.gtm import prioritize
from opengtm.public import PublicFetcher, run


def test_cache_reuses_fetch_but_not_mutable_output(monkeypatch):
    fetcher = PublicFetcher(cache_ttl=300)
    load = Mock(return_value={"url": "https://example.test/", "text": "original"})
    monkeypatch.setattr(fetcher, "_fetch_page", load)
    first = fetcher.fetch("https://example.test/")
    first["text"] = "mutated"
    second = fetcher.fetch("https://example.test/")
    assert second["text"] == "original"
    assert load.call_count == 1
    assert fetcher.stats()["cache_hits"] == 1


def test_expired_cache_requires_a_new_fetch(monkeypatch):
    fetcher = PublicFetcher(cache_ttl=1)
    clock = Mock(side_effect=[0, 2, 2])
    monkeypatch.setattr("opengtm.public.time.monotonic", clock)
    load = Mock(return_value={"text": "source"})
    monkeypatch.setattr(fetcher, "_fetch_page", load)
    fetcher.fetch("https://example.test/")
    fetcher.fetch("https://example.test/")
    assert load.call_count == 2


def test_failed_fetch_is_not_cached(monkeypatch):
    fetcher = PublicFetcher(cache_ttl=300)
    load = Mock(side_effect=[ValueError("failed"), {"text": "source"}])
    monkeypatch.setattr(fetcher, "_fetch_page", load)
    with pytest.raises(ValueError):
        fetcher.fetch("https://example.test/")
    assert fetcher.fetch("https://example.test/")["text"] == "source"
    assert load.call_count == 2


def test_lru_cache_is_bounded(monkeypatch):
    fetcher = PublicFetcher(cache_ttl=300, cache_size=1)
    load = Mock(return_value={"text": "source"})
    monkeypatch.setattr(fetcher, "_fetch_page", load)
    for url in ["https://a.test/", "https://b.test/", "https://a.test/"]:
        fetcher.fetch(url)
    assert load.call_count == 3


def test_parallel_research_is_bounded_ordered_and_preserves_context(monkeypatch):
    value = ContextVar("test_context", default=None)
    value.set("parent")
    state = {"active": 0, "peak": 0}
    lock = Lock()

    def prospect(policy, candidate, fetcher):
        assert value.get() == "parent"
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.01)
        with lock:
            state["active"] -= 1
        return {
            "seller": "Seller",
            "company": candidate["company"],
            "status": "research_qualified",
            "validation": {"research": "pass"},
            "ready_for_outreach": False,
        }

    monkeypatch.setattr("opengtm.public.prospect", prospect)
    fetcher = Mock()
    fetcher.fetch.return_value = {
        "text": "clipping",
        "url": "https://seller.test/",
        "sha256": "a" * 64,
        "fetched_at": "test",
    }
    seller = {
        "name": "Seller",
        "url": "https://seller.test/",
        "positioning_groups": [["clipping"]],
        "candidates": [
            {"company": str(i), "url": f"https://company{i}.test/"} for i in range(6)
        ],
    }
    result = run({"sellers": [seller]}, fetcher, max_workers=2)
    assert [r["company"] for r in result["results"]] == [str(i) for i in range(6)]
    assert state["peak"] == 2


def policy():
    return {
        "signal_groups": [["GPU"], ["pricing"]],
        "buyer_role": "Finance",
        "conversation": "risk discovery",
        "validation_question": "who owns the exposure",
        "gtm_profile": {
            "timing_rules": [
                {
                    "code": "pricing_update",
                    "groups": [["Updated"], ["pricing"]],
                    "date_text": "November 12, 2026",
                    "weight": 20,
                }
            ]
        },
    }


def test_match_and_public_contact_do_not_invent_timing_or_intent():
    result = prioritize(
        policy(),
        {
            "content_text": "GPU pricing. Contact sales.",
            "url": "https://example.test/",
            "fetched_at": "2026-11-26T12:00:00+00:00",
        },
        "pass",
    )
    assert result["fit_score"] == 50
    assert result["timing_score"] == 0
    assert result["buying_intent"] == "unknown"
    assert result["priority"] == "B"


def test_timing_requires_a_recent_date_in_the_same_source():
    page = {
        "content_text": "GPU pricing Updated November 12, 2026",
        "url": "https://example.test/",
        "fetched_at": "2026-11-26T12:00:00+00:00",
    }
    assert prioritize(policy(), page, "pass")["timing_score"] == 20
    assert (
        prioritize(
            policy(), {**page, "fetched_at": "2027-11-26T12:00:00+00:00"}, "pass"
        )["timing_score"]
        == 0
    )
    assert (
        prioritize(policy(), {**page, "content_text": "GPU pricing Updated"}, "pass")[
            "timing_score"
        ]
        == 0
    )


def test_invalid_research_stays_on_hold_even_with_a_trigger():
    page = {
        "content_text": "GPU pricing Updated November 12, 2026",
        "url": "https://example.test/",
        "fetched_at": "2026-11-26T12:00:00+00:00",
    }
    assert prioritize(policy(), page, "reject")["priority"] == "hold"


@pytest.mark.parametrize("workers", [0, 9, True, -1])
def test_worker_limits(workers):
    with pytest.raises(ValueError):
        run({"sellers": []}, Mock(), max_workers=workers)
