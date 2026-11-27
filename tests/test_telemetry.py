from __future__ import annotations

# Optional SDK tests are skipped by the base Python 3.10 installation.
import pytest

pytest.importorskip("traceroot")
# ruff: noqa: E402

import asyncio
import gzip
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opengtm import telemetry
from opengtm.reliability import canonical_domain, normalize_research, source_quote
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def captured(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource({"service.name": "opengtm"}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setenv("OPENGTM_TRACEROOT_ENABLED", "true")
    monkeypatch.setenv("TRACEROOT_ENABLED", "true")
    monkeypatch.setattr(telemetry, "_provider", provider)
    monkeypatch.setattr(telemetry, "_attempted", True)
    yield exporter
    provider.shutdown()


def attrs(span):
    return json.loads(span.attributes["traceroot.span.metadata"])


def test_disabled_never_imports_sdk():
    code = """
import os, sys
os.environ['OPENGTM_TRACEROOT_ENABLED'] = 'false'
from opengtm.qualify import qualify
assert qualify({})['tier'] == 'cold'
assert 'traceroot' not in sys.modules
assert 'opentelemetry.sdk.trace' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_missing_sdk_and_missing_key_fail_open(monkeypatch):
    monkeypatch.setenv("OPENGTM_TRACEROOT_ENABLED", "true")
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setattr(telemetry, "_attempted", False)
    monkeypatch.delenv("TRACEROOT_API_KEY", raising=False)
    with pytest.warns(RuntimeWarning, match="unavailable"):
        with telemetry.span("opengtm.test"):
            pass
    assert telemetry._provider is None
    monkeypatch.setattr(telemetry, "_attempted", False)
    monkeypatch.setitem(sys.modules, "traceroot.transport.span_processor", None)
    with pytest.warns(RuntimeWarning, match="unavailable"):
        with telemetry.span("opengtm.test"):
            pass


def test_error_payload_is_not_recorded(captured):
    secret = "secret-alex@example.test-password"
    with pytest.raises(RuntimeError, match=secret):
        with telemetry.span("opengtm.test"):
            telemetry.update(email=secret, score=secret, outcome=secret)
            raise RuntimeError(secret)
    spans = captured.get_finished_spans()
    assert secret not in str(spans[0].to_json())
    assert not spans[0].events
    assert attrs(spans[0])["error_category"] == "provider"
    assert spans[0].status.is_ok is False


def test_parent_child_and_concurrent_context(captured):
    @telemetry.observed("opengtm.async", "agent")
    async def run(value):
        await asyncio.sleep(0)
        with telemetry.span("opengtm.tool"):
            telemetry.update(score=value)

    async def both():
        await asyncio.gather(run(10), run(20))

    asyncio.run(both())
    spans = captured.get_finished_spans()
    roots = [s for s in spans if s.parent is None]
    assert len(roots) == 2
    assert roots[0].context.trace_id != roots[1].context.trace_id
    assert all(
        sum(
            s.parent is not None and s.parent.span_id == r.context.span_id
            for s in spans
        )
        == 1
        for r in roots
    )


def test_cost_and_usage_are_reported_not_guessed(captured, monkeypatch):
    for key, value in {
        "INPUT_USD_PER_MILLION": "2",
        "OUTPUT_USD_PER_MILLION": "4",
        "TOOL_USD_PER_CALL": "0",
    }.items():
        monkeypatch.setenv("OPENGTM_" + key, value)
    with telemetry.span("opengtm.pipeline", "agent"):
        with telemetry.span("opengtm.llm", "llm"):
            telemetry.usage(
                {"usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50}}
            )
        telemetry.qualified(True)
    root = captured.get_finished_spans()[-1]
    assert attrs(root)["cost_per_qualified_prospect_usd"] == pytest.approx(0.0004)
    assert attrs(root)["llm_calls"] == 1
    assert captured.get_finished_spans()[0].attributes["llm.token_count.prompt"] == 100


def test_failed_retry_makes_total_cost_unknown(captured, monkeypatch):
    for key in ("INPUT_USD_PER_MILLION", "OUTPUT_USD_PER_MILLION", "TOOL_USD_PER_CALL"):
        monkeypatch.setenv("OPENGTM_" + key, "1")
    with telemetry.span("opengtm.pipeline", "agent"):
        with pytest.raises(TimeoutError):
            with telemetry.span("opengtm.llm", "llm"):
                raise TimeoutError("private data")
        with telemetry.span("opengtm.llm", "llm"):
            telemetry.usage(
                {"usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50}}
            )
        telemetry.qualified(True)
    root = attrs(captured.get_finished_spans()[-1])
    assert root["llm_calls"] == 2
    assert root["cost_known"] is False
    assert "cost_per_qualified_prospect_usd" not in root


@pytest.mark.parametrize(
    "metadata", [{}, {"promptTokenCount": -1}, {"promptTokenCount": "100"}]
)
def test_missing_or_invalid_usage_is_unknown(captured, metadata):
    with telemetry.span("opengtm.llm", "llm"):
        telemetry.usage({"usageMetadata": metadata})
    result = attrs(captured.get_finished_spans()[-1])
    assert not result["cost_known"]
    assert "input_tokens" not in result


def test_model_provenance_is_never_trusted():
    result = normalize_research(
        {
            "contact": {"email": "alex@example.test", "email_status": "verified"},
            "findings": [{"verification": "source_quote", "source_text": "invented"}],
        }
    )
    assert result["contact"]["email_status"] == "unverified"
    assert result["findings"][0] == {"verification": "unverified"}


@pytest.mark.parametrize(
    "source", ["https://evil.test/", "", "https://example.test.evil.test/"]
)
def test_unrelated_evidence_is_rejected(source):
    assert not source_quote(
        dict(
            verification="source_quote",
            source_url=source,
            source_text="Home",
            evidence="Home",
        ),
        "example.test",
    )




def test_exported_otlp_payload_is_private(monkeypatch, tmp_path):
    """Exercise the released TraceRoot SDK's real gzip/protobuf HTTP exporter."""
    requests = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            requests.append((self.path, body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(telemetry, "_provider", None)
    monkeypatch.setattr(telemetry, "_attempted", False)
    monkeypatch.setenv("OPENGTM_TRACEROOT_ENABLED", "true")
    monkeypatch.setenv("TRACEROOT_ENABLED", "true")
    monkeypatch.setenv("TRACEROOT_API_KEY", "synthetic-auth-only")
    monkeypatch.setenv("TRACEROOT_HOST_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "private.email=alex@example.test")
    try:
        with telemetry.span("opengtm.pipeline", "agent"):
            with telemetry.span("opengtm.research", "tool"):
                telemetry.update(
                    finding_count=1, email="alex@example.test", input_chars=23
                )
            with pytest.raises(RuntimeError):
                with telemetry.span("opengtm.failure", "tool"):
                    raise RuntimeError("secret-password alex@example.test")
        telemetry.flush()
        assert requests and all(path == "/api/v1/public/traces" for path, _ in requests)
        payloads = [ExportTraceServiceRequest.FromString(body) for _, body in requests]
        text = "\n".join(str(p) for p in payloads)
        for secret in (
            "alex@example.test",
            "secret-password",
            "synthetic-auth-only",
            "private.email",
        ):
            assert secret not in text
        spans = [
            s
            for p in payloads
            for rs in p.resource_spans
            for ss in rs.scope_spans
            for s in ss.spans
        ]
        assert len(spans) == 3
        assert len({s.trace_id for s in spans}) == 1
        assert sum(bool(s.parent_span_id) for s in spans) == 2
    finally:
        telemetry.shutdown()
        server.shutdown()
        server.server_close()
        thread.join()




@pytest.mark.parametrize(
    "raw", ["https://www.EXAMPLE.test/about", "www.example.test", "example.test."]
)
def test_canonical_domain(raw):
    assert canonical_domain(raw) == "example.test"


def test_broken_exporter_cannot_change_business_result(monkeypatch):
    class BrokenProvider:
        def get_tracer(self, *args):
            raise RuntimeError("private exporter failure")

    monkeypatch.setattr(telemetry, "_get_provider", lambda: BrokenProvider())

    @telemetry.observed("opengtm.test")
    def business():
        return 42

    assert business() == 42


def test_redactor_drops_nested_private_fields():
    assert telemetry.redact(
        {
            "traceroot.span.metadata": json.dumps(
                {"score": 80, "email": "alex@example.test", "input": {"key": "secret"}}
            ),
            "input.value": "private",
        }
    ) == {"traceroot.span.metadata": '{"score": 80}'}
