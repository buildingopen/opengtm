"""Live three-seller research with a loopback TraceRoot receiver; no cloud export."""

from __future__ import annotations

import argparse
import gzip
import json
import os
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.protobuf.json_format import MessageToDict
from opengtm import telemetry
from opengtm.public import PublicFetcher, run, save
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path(__file__).with_name("three-companies.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    batches = []

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if self.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            batches.append(ExportTraceServiceRequest.FromString(body))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    os.environ["OPENGTM_TRACEROOT_ENABLED"] = "true"
    os.environ["TRACEROOT_ENABLED"] = "true"
    os.environ["TRACEROOT_API_KEY"] = "synthetic-local-receiver-only"
    os.environ["TRACEROOT_HOST_URL"] = f"http://127.0.0.1:{receiver.server_port}"
    start = time.perf_counter()
    try:
        report = run(json.loads(args.input.read_text()), PublicFetcher())
        elapsed = time.perf_counter() - start
        telemetry.flush()
        spans = [
            s
            for batch in batches
            for resource in batch.resource_spans
            for scope in resource.scope_spans
            for s in scope.spans
        ]
        assert spans, "No spans received; tracing did not initialize"
        decoded = [MessageToDict(batch) for batch in batches]
        serialized = json.dumps(decoded)
        forbidden = ["synthetic-local-receiver-only"] + [
            r.get("domain", "") for r in report["results"] if r.get("domain")
        ]
        assert all(value not in serialized for value in forbidden), (
            "Prospect or credential leaked into traces"
        )
        statuses = Counter(r["status"] for r in report["results"])
        report.update(
            elapsed_seconds=round(elapsed, 3),
            trace_destination="loopback receiver; no cloud export",
            trace_spans=len(spans),
            traces=len({s.trace_id for s in spans}),
            statuses=dict(statuses),
            config_sha256=__import__("hashlib")
            .sha256(args.input.read_bytes())
            .hexdigest(),
        )
        save(report, args.output)
        (args.output / "traces.json").write_text(json.dumps(decoded, indent=2) + "\n")
        (args.output / "run-summary.json").write_text(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k not in ("results", "seller_checks")
                },
                indent=2,
            )
            + "\n"
        )
        print(json.dumps(report["statuses"], indent=2))
        print(
            f"Actual live run: {elapsed:.2f}s; {len(spans)} SDK spans; local export privacy check passed"
        )
    finally:
        telemetry.shutdown()
        receiver.shutdown()
        receiver.server_close()
        thread.join()


if __name__ == "__main__":
    main()
