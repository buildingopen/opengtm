# GTM prioritization and research efficiency

The pipeline separates four questions: does the account fit the seller's offer,
is there a sourced reason to investigate now, is the evidence valid, and is an
approved recipient available? An account-level match cannot answer all four.

`opengtm.gtm.prioritize` assigns up to 50 points for explicit offer-fit signal
groups and up to 25 for a dated event present in the same source and no older than
90 days. A generic pricing page, contact form, hiring link or assumed budget adds
no timing points. Potential existing capability lowers research priority; it is
not automatically a reason to discard a company. All scores are configurable
heuristics, not calibrated conversion probabilities or independently validated
sales judgments. Buying intent stays unknown.

The three example profiles use finance/risk discovery for Selfin, an authorized
one-episode production pilot for Overlap, and one instrumented agent failure with
before/after evaluation for TraceRoot. The Overlap profile flags an existing clip
operation as a possible reason to investigate a gap before pitching. These are
seller-specific discovery offers, not promised outcomes.

## Efficiency controls

- Canonical-domain duplicates and known customers are removed before research.
- Bounded workers research independent accounts in parallel; results keep input
  order. Worker context is copied so TraceRoot children stay under their pipeline.
- Each thread owns its requests session. Robots policy access and shared metrics
  are synchronized.
- An optional bounded in-memory LRU cache reuses page observations until its TTL
  expires. Copies prevent downstream mutations from changing cached evidence.
  Failed fetches are not cached. Original observation timestamps and hashes stay
  intact. The default CLI cache TTL is 300 seconds, with three workers.
- The cache is process-local and ephemeral; it does not eliminate work across
  separate CLI invocations or make cached observations into fresh web audits.

```sh
python -m opengtm.public --input examples/three-companies.json --output /tmp/leads --workers 3 --cache-ttl 300
# Disable reuse when a fresh read is required:
python -m opengtm.public --input examples/three-companies.json --output /tmp/leads-fresh --workers 1 --cache-ttl 0
```

`research-priority.csv` contains the account queue, buyer role hypotheses, discovery
questions and pilot offers. `outreach-ready.csv` remains gated by validation and
trusted recipient/account clearance. Published sales forms are not direct buyers.

## TraceRoot profiling and measured comparison

The released SDK exports actual spans for HTTP work, page fetches, validation,
prioritization, prospect research and pipeline execution. Metadata contains only
counts, scores and closed-set validation categories. Company domains, source
text, contacts and exception messages remain outside telemetry.

```sh
python examples/benchmark_public.py --output /tmp/gtm-benchmark
```

The runner uses a local receiver, makes real public HTTP calls and compares the
same curated targets and policies over two runs per execution policy. It checks
that every run remains one trace despite worker threads, then decodes the export
and checks for domain/credential leakage. It emits stage mean durations and
validation reason counts. Span durations include children and overlapping work;
they cannot be summed as pipeline wall time.

Observed November 26, 2026: two serial/no-cache runs made 50 HTTP requests. The
parallel/cached pair made 25. Both policies produced eight research passes per
run and zero outreach-ready recipients. The second cached run took 0.0586 seconds
using 12 cache hits and zero HTTP requests. The first parallel run took 3.6586
seconds; serial runs took 4.3114 and 4.4018 seconds. This small sequentially ordered
experiment is not enough to establish a general cold-run speed improvement.

The actionable trace finding was eight `recipient_missing` results and one
`research_not_qualified`. Further broad account research would not resolve the
missing contact clearance. Identify and verify the appropriate buyer before
spending more on outreach generation. Model calls were zero; no inference-cost
savings, sales conversions, cloud ingestion or hosted detectors are claimed.
