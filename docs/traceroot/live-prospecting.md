# Live public-source prospecting for three sellers

This extension works without Gemini or TraceRoot cloud credentials. It validates
curated account seeds against live public website text, using a separate targeting
policy per seller. It is a read-only prospect-research tool; no email or outreach
is sent. Seller policies and business hypotheses are analyst supplied.

```sh
# Base dependencies are enough for public research.
python -m pip install -e .
python -m opengtm.public --input examples/three-companies.json --output /tmp/live-leads

# To repeat the observed run with actual TraceRoot SDK export to a local receiver:
python -m pip install -e '.[traceroot]'
python examples/run_public_demo.py --output /tmp/live-leads-traced
```

The example uses Selfin, Overlap and TraceRoot as sellers. It checks the current
seller website before applying the targeting policy, then excludes configured
existing customers and duplicate domains before fetching prospect pages. Matched
signal groups, short source quotations, fetch time, response hash, public contact
links, role hypotheses and reviewable outreach drafts are retained locally.
Raw website text and company domains do not enter telemetry. The demo decodes
real OTLP protobuf exports and checks for domain or credential leakage.

Unlike the original Gemini research path, this mode performs no LLM inference or
search API calls. Candidate discovery is manual web research; live HTTP checks
validate the seeded shortlist. Keyword presence is a coarse research gate, not
proof of context, unmet need, willingness to buy, or financial-product eligibility.
Drafts use observed terms and questions, never analyst-supplied growth claims.

Fetcher constraints: public HTTPS URLs, IP-address check before requests, manual
redirect handling, robots policy checks on every destination, timeouts and a 2 MB
response limit. This local tool is not a hardened multi-tenant crawl service;
proxy routing and DNS rebinding are outside the current protection boundary.

Published contact routes can be sales or sponsorship forms; they do not establish
a decision maker's identity or confirm a suitable outbound recipient. Emails are
not guessed. A missing contact route remains missing.

The supplied real-company example remains separate from the synthetic validator
dataset. Generated reports are local outputs and are not committed. The recorded zero
provider spend applies only to this deterministic path, not to production model
or infrastructure cost. The local receiver is an exporter test, not TraceRoot
cloud ingestion or a hosted detector run.
