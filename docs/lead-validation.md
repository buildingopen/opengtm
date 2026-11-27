# Evidence and outreach validation

A prospect with matching keywords is not necessarily a valid sales lead. This
validator checks a structured evidence contract and separates **research** from
**outreach** decisions. Each stage returns `pass`, `review`, or `reject`, with
stable reason codes. Missing evidence never silently passes.

The core `opengtm.validate` module uses Python 3.10+ and only the standard library.
It does not call a model, fetch pages, initialize telemetry, or send outreach.
TraceRoot remains optional; OpenGTM's public-source adapter exports decision
counts, while keeping the actual lead data in local reports.

## Evidence contract

A record needs a company domain, HTTPS source URL, completed research status,
source timestamp, SHA-256 response digest, source excerpts, declared signal groups
and a constrained outreach draft. The validator receives an independently fetched
page separately from the lead. It never trusts a model's `verified` or
`ready_for_outreach` flags.

- Source and company hosts must match, with `www` normalization and IDNA handling.
  Credentials, non-HTTPS sources, IP addresses and lookalike suffixes are rejected.
- Evidence must carry a timezone-aware timestamp and valid digest. Evidence older
  than 30 days requires review; future-dated evidence is rejected.
- Quotes must occur in the independently supplied source after whitespace
  normalization. Changed snapshots or locations require review, even when quotes
  still occur. Dynamic pages can therefore create conservative review decisions.
- Signal phrases use word boundaries, so `API` does not match `capital`. The
  public-source adapter removes navigation, header, footer, forms and title from
  the text used for qualification; a menu mention alone is insufficient.
- Known customers, duplicates and research failures are rejected. Exclusions are
  caller-maintained policy; the validator does not autonomously know customers.
- Outreach must match the supported template built from verified source terms
  and the trusted seller policy. Arbitrary extra assertions, including invented
  metrics, are rejected. Freely edited outreach needs a separate review path;
  this validator does not claim to understand every natural-language statement.

## Contact clearance

Public sales forms, email syntax and HTTP reachability cannot establish a buyer's
identity or email deliverability. A lead's embedded `email_status=verified` is
ignored. Releasing a record requires a separate `Clearance` from a trusted adapter
or a human-reviewed process: the exact recipient, a recent timestamp, explicit
boolean deliverability approval, and explicit account review. Receipts expire
after seven days and cannot be transferred to a different address.

The receipt is a caller trust boundary, not a cryptographic credential or an
email-verification provider. An application must authenticate its adapters and
keep an audit record. No actual email verification service is integrated here.
Consent, campaign eligibility and product suitability remain application concerns.

## Library API

```python
from opengtm.validate import validate_lead

result = validate_lead(lead, seller_policy, page=fresh_page)
print(result.research, result.outreach)
print([finding.code for finding in result.findings])
# No recipient clearance means review, even with valid research.
assert not result.ready_for_outreach
```

`fresh_page` is a trusted fetch result, including `url`, `text`, `content_text`,
`fetched_at` and `sha256`. It must not come from the lead's own unverified metadata.
`content_text` omits navigation and other boilerplate. The pure validator falls
back to `text` for trusted legacy adapters; boilerplate removal is the adapter's
responsibility. A valid digest is a provenance marker; the core cannot prove its
authenticity without trusting the fetcher. Old snapshots should be preserved by
the consuming application if historical byte-for-byte replay is required.

## CLI and live use

Conservative offline validation (no independent source or contact clearances):

```sh
python -m opengtm.validate --input leads.json --policy examples/three-companies.json --output validation.json --strict
```

`--strict` exits 1 if any row needs review or is rejected. Offline records cannot
be promoted merely by claiming verification in the input file.

Fresh-source revalidation of an earlier report:

```sh
python examples/validate_public_leads.py --input leads.json --policy examples/three-companies.json --output validation.json
```

New public-source runs attach validation to every record. They export a separate
`outreach-ready.csv`; it remains empty without a trusted clearance. Research
briefs and draft material remain in `leads.csv` for review. This is a queue gate;
there is no sending implementation. Existing legacy CRM/outreach commands are
not silently changed by this module and do not automatically enforce this gate.

## Verification

`evals/validator-cases.json` contains 39 synthetic labeled scenarios covering
clean records, missing clearances, forged evidence, stale/future timestamps,
changed sources, wrong companies, substring and navigation matches, invalid
policies, duplicates, known customers and unsupported outreach. Positive fixtures
include explicit synthetic clearances; those are not real verified contacts.

```sh
python -m pytest tests/test_validate.py -q
# Optional TraceRoot SDK evaluation, entirely local:
python evals/validator.py --output /tmp/validator-eval.json
```

The TraceRoot runner scores research verdicts, outreach verdicts and reason codes.
The standalone tests also cover malformed input, sensitive-value exclusion and
importing the validator without SDK or network initialization.
