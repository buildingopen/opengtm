"""Opt-in, content-free TraceRoot spans on an isolated OpenTelemetry provider.

Never auto-instrument: raw arguments, return values, exception messages, URLs,
user/session IDs and environment-derived resources must not enter telemetry.
"""

from __future__ import annotations

import atexit
import inspect
import json
import math
import os
import threading
import warnings
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any
from urllib.parse import urlsplit

_provider: Any = None
_attempted = False
_lock = threading.Lock()
_active: ContextVar[Any] = ContextVar("opengtm_span", default=None)
_ledger: ContextVar[Any] = ContextVar("opengtm_cost", default=None)
_ENUMS = {
    "validation_reason": {
        "recipient_missing",
        "trusted_clearance_required",
        "insufficient_body_signals",
        "unsupported_signal_claim",
        "source_snapshot_changed",
        "quote_not_in_source",
        "stale_evidence",
        "research_not_qualified",
        "none",
        "other",
    },
    "outcome": {"completed", "failed", "retry", "empty"},
    "error_category": {
        "timeout",
        "invalid_response",
        "configuration",
        "provider",
        "other",
    },
    "tier": {"hot", "warm", "cold"},
    "email_status": {"missing", "invalid", "unverified"},
}
_NUMBERS = {
    "http_requests",
    "cache_hits",
    "cache_misses",
    "fit_score",
    "timing_score",
    "validation_pass_count",
    "validation_review_count",
    "validation_reject_count",
    "attempt",
    "retry_count",
    "input_chars",
    "output_chars",
    "input_tokens",
    "output_tokens",
    "score",
    "finding_count",
    "unverified_findings",
    "duplicate_count",
    "result_count",
    "verification_failed",
    "qualified_count",
    "llm_calls",
    "cost_known",
    "cost_usd",
    "cost_per_qualified_prospect_usd",
    "research_failed",
    "email_missing",
    "email_invalid",
}


def safe_metadata(values: dict) -> dict:
    safe = {}
    for key, value in values.items():
        if (
            key in _ENUMS
            and isinstance(value, str)
            and value in _ENUMS[key]
            or (
                key in _NUMBERS
                and type(value) in (int, float, bool)
                and math.isfinite(value)
                and value >= 0
            )
        ):
            safe[key] = value
    return safe


def redact(attributes: dict) -> dict:
    """Defence in depth; only our prevalidated JSON metadata survives."""
    try:
        metadata = json.loads(attributes.get("traceroot.span.metadata", "{}"))
        return {"traceroot.span.metadata": json.dumps(safe_metadata(metadata))}
    except (TypeError, ValueError, AttributeError):
        return {}


def _enabled() -> bool:
    return os.getenv("OPENGTM_TRACEROOT_ENABLED", "").lower() == "true" and os.getenv(
        "TRACEROOT_ENABLED", "true"
    ).lower() not in {"false", "0", "no", "off"}


def _get_provider():
    global _provider, _attempted
    if not _enabled():
        return None
    with _lock:
        if _attempted:
            return _provider
        _attempted = True
        try:
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from traceroot.transport.span_processor import TracerootSpanProcessor

            key = os.getenv("TRACEROOT_API_KEY", "")
            if not key:
                raise ValueError("missing configuration")
            host = os.getenv("TRACEROOT_HOST_URL", "https://app.traceroot.ai")
            parsed = urlsplit(host)
            if (
                parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
                or not parsed.hostname
                or (
                    parsed.scheme != "https"
                    and not (
                        parsed.scheme == "http"
                        and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                    )
                )
            ):
                raise ValueError("invalid host")
            # Resource() avoids Resource.create() environment and host detectors.
            provider = TracerProvider(resource=Resource({"service.name": "opengtm"}))
            processor = TracerootSpanProcessor(
                api_key=key,
                host_url=host,
                flush_interval=1.0,
                timeout=2.0,
                git_repo="buildingopen/opengtm",
                git_ref=None,
                redact=redact,
            )
            provider.add_span_processor(processor)
            _provider = provider
            atexit.register(shutdown)
        except Exception:
            # Never interpolate exceptions: providers can put credentials in them.
            warnings.warn(
                "OpenGTM telemetry unavailable; continuing without tracing.",
                RuntimeWarning,
                stacklevel=2,
            )
        return _provider


def update(**values):
    state = _active.get()
    if state:
        state[1].update(safe_metadata(values))


def category(error: BaseException) -> str:
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, (json.JSONDecodeError, TypeError)):
        return "invalid_response"
    if isinstance(error, ValueError):
        return "configuration"
    if isinstance(error, RuntimeError):
        return "provider"
    return "other"


@contextmanager
def span(name: str, kind: str = "tool"):
    provider = _get_provider()
    if provider is None:
        yield
        return
    from opentelemetry.context import Context
    from opentelemetry.trace import Status, StatusCode, set_span_in_context

    parent = _active.get()
    # Only our own spans can become parents. Do not inherit foreign baggage.
    context = set_span_in_context(parent[0], Context()) if parent else Context()
    try:
        current = provider.get_tracer("opengtm").start_span(name, context=context)
        current.set_attribute("traceroot.span.type", kind)
    except Exception:
        yield
        return
    values: dict[str, Any] = {"outcome": "completed"}
    if kind == "llm":
        values["cost_known"] = False
    token = _active.set((current, values))
    cost_token = None
    if _ledger.get() is None:
        cost_token = _ledger.set(
            {"calls": 0, "known": True, "cost": 0.0, "qualified": 0}
        )
    try:
        yield
    except BaseException as exc:
        update(outcome="failed", error_category=category(exc))
        # No record_exception(): stack traces and error messages can contain PII.
        raise
    finally:
        ledger = _ledger.get()
        if kind == "llm":
            ledger["calls"] += 1
            ledger["known"] = ledger["known"] and values.get("cost_known", False)
            ledger["cost"] += values.get("cost_usd", 0.0)
        if cost_token is not None:
            update(
                llm_calls=ledger["calls"],
                qualified_count=ledger["qualified"],
                cost_known=bool(ledger["calls"] and ledger["known"]),
            )
            if ledger["calls"] and ledger["known"]:
                update(cost_usd=ledger["cost"])
                if ledger["qualified"]:
                    update(
                        cost_per_qualified_prospect_usd=ledger["cost"]
                        / ledger["qualified"]
                    )
            _ledger.reset(cost_token)
        _active.reset(token)
        try:
            if values.get("outcome") == "failed":
                current.set_status(Status(StatusCode.ERROR))
            current.set_attribute("traceroot.span.metadata", json.dumps(values))
            current.end()
        except Exception:
            pass


def observed(name: str, kind: str = "tool"):
    """Names are code constants, never prospect input. Supports sync and async."""

    def decorate(fn):
        if inspect.iscoroutinefunction(fn):

            @wraps(fn)
            async def async_wrapped(*args, **kwargs):
                with span(name, kind):
                    return await fn(*args, **kwargs)

            return async_wrapped

        @wraps(fn)
        def wrapped(*args, **kwargs):
            with span(name, kind):
                return fn(*args, **kwargs)

        return wrapped

    return decorate


def qualified(is_qualified: bool):
    ledger = _ledger.get()
    if ledger is not None:
        ledger["qualified"] += int(is_qualified)


def usage(response: Any):
    """Capture provider-reported tokens only. Unknown cost stays unknown."""
    metadata = (
        response.get("usageMetadata", {})
        if isinstance(response, dict)
        else getattr(response, "usage_metadata", None)
    )

    def get(camel, snake):
        value = (
            metadata.get(camel)
            if isinstance(metadata, dict)
            else getattr(metadata, snake, None)
        )
        return value if type(value) is int and value >= 0 else None

    inputs = get("promptTokenCount", "prompt_token_count")
    outputs = get("candidatesTokenCount", "candidates_token_count")
    thoughts = get("thoughtsTokenCount", "thoughts_token_count") or 0
    cost = None
    if inputs is not None and outputs is not None:
        update(input_tokens=inputs, output_tokens=outputs + thoughts)
        state = _active.get()
        if state:
            state[0].set_attribute("llm.token_count.prompt", inputs)
            state[0].set_attribute("llm.token_count.completion", outputs + thoughts)
        try:
            # Prices must be supplied for the configured model, including tool/grounding fees.
            input_rate = float(os.environ["OPENGTM_INPUT_USD_PER_MILLION"])
            output_rate = float(os.environ["OPENGTM_OUTPUT_USD_PER_MILLION"])
            tool_cost = float(os.environ["OPENGTM_TOOL_USD_PER_CALL"])
            if all(
                math.isfinite(x) and x >= 0
                for x in (input_rate, output_rate, tool_cost)
            ):
                cost = (
                    inputs * input_rate + (outputs + thoughts) * output_rate
                ) / 1_000_000 + tool_cost
        except (KeyError, ValueError):
            pass
    update(cost_known=cost is not None)
    if cost is not None:
        update(cost_usd=cost)
        state = _active.get()
        if state:
            state[0].set_attribute("llm.cost.total", cost)


def flush():
    if _provider is not None:
        try:
            _provider.force_flush(timeout_millis=3000)
        except Exception:
            pass


def shutdown():
    if _provider is not None:
        try:
            _provider.shutdown()
        except Exception:
            pass


@observed("opengtm.gemini", "llm")
def call_llm(fn, *args, **kwargs):
    """Wrap existing SDK calls without changing their provider or retry behavior."""
    prompt = kwargs.get("contents", args[0] if args else None)
    if isinstance(prompt, str):
        update(input_chars=len(prompt))
    response = fn(*args, **kwargs)
    try:
        usage(response)
        text = getattr(response, "text", None)
        if isinstance(text, str):
            update(output_chars=len(text))
    except Exception:
        pass
    return response
