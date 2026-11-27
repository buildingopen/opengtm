"""Compare serial/no-cache and parallel/cached policies with real local SDK export."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import statistics
import threading
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opengtm import telemetry
from opengtm.public import PublicFetcher, run, save
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


def profile(spans):
    stages = defaultdict(list)
    reasons = Counter()
    for s in spans:
        stages[s.name].append((s.end_time_unix_nano - s.start_time_unix_nano) / 1e6)
        if s.name == "opengtm.public.validate":
            for attr in s.attributes:
                if attr.key == "traceroot.span.metadata":
                    values = json.loads(attr.value.string_value)
                    reasons[values.get("validation_reason", "unknown")] += 1
    return {
        "stages": {
            name: {"count": len(v), "mean_ms": round(statistics.mean(v), 3)}
            for name, v in stages.items()
        },
        "validation_reasons": dict(reasons),
        "note": "Span durations include children and concurrent waits; do not sum them as wall time.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path(__file__).with_name("three-companies.json")
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    config = json.loads(args.input.read_text())
    batches = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            data = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            batches.append(ExportTraceServiceRequest.FromString(data))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    os.environ.update(
        OPENGTM_TRACEROOT_ENABLED="true",
        TRACEROOT_ENABLED="true",
        TRACEROOT_API_KEY="synthetic-benchmark-receiver",
        TRACEROOT_HOST_URL=f"http://127.0.0.1:{server.server_port}",
    )
    runs = []
    cached = PublicFetcher(cache_ttl=300)
    try:
        for mode in ("serial_no_cache", "parallel_cached"):
            for iteration in (1, 2):
                before = len(batches)
                report = run(
                    config,
                    PublicFetcher() if mode == "serial_no_cache" else cached,
                    max_workers=1 if mode == "serial_no_cache" else 3,
                )
                telemetry.flush()
                spans = [
                    s
                    for b in batches[before:]
                    for r in b.resource_spans
                    for scope in r.scope_spans
                    for s in scope.spans
                ]
                assert spans and len({s.trace_id for s in spans}) == 1, (
                    "Disconnected or missing trace"
                )
                assert sum(not s.parent_span_id for s in spans) == 1, (
                    "Lost worker trace context"
                )
                report["profiling"] = profile(spans)
                report["trace_spans"] = len(spans)
                report["trace_destination"] = "loopback receiver; no cloud export"
                save(report, args.output / f"{mode}-{iteration}")
                runs.append(
                    {
                        "mode": mode,
                        "iteration": iteration,
                        **report["efficiency"],
                        "statuses": dict(
                            Counter(r["status"] for r in report["results"])
                        ),
                        "profiling": report["profiling"],
                    }
                )
        encoded = [MessageToDict(b) for b in batches]
        text = json.dumps(encoded)
        forbidden = ["synthetic-benchmark-receiver"] + [
            r["domain"] for r in report["results"] if r.get("domain")
        ]
        assert all(s not in text for s in forbidden), "Sensitive data in spans"
        summary = {
            "runs": runs,
            "request_reduction": 1
            - sum(r["http_requests"] for r in runs if r["mode"] == "parallel_cached")
            / sum(r["http_requests"] for r in runs if r["mode"] == "serial_no_cache"),
            "privacy_check_passed": True,
            "model_calls": 0,
            "cloud_verified": False,
            "comparison": "Same curated accounts and policies. Cache is local, in memory, 300s TTL. Second cached run reuses observations; it is not a fresh web audit. Network timing is noisy and run order was not randomized.",
        }
        (args.output / "benchmark.json").write_text(
            json.dumps(summary, indent=2) + "\n"
        )
        (args.output / "traces.json").write_text(json.dumps(encoded, indent=2) + "\n")
        print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2))
        for row in runs:
            print(
                row["mode"],
                row["iteration"],
                row["elapsed_seconds"],
                row["http_requests"],
                row["cache_hits"],
                row["research_pass"],
            )
    finally:
        telemetry.shutdown()
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
