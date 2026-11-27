<!-- keywords: claude code gtm automation, ai lead generation python, answer engine optimization tool, aeo checker open source, cold outreach automation, icp scoring, lead qualification python, open source sales tools, ai content pipeline, outreach automation python -->

# opengtm

**Open source AI GTM toolkit.** Find leads, score ICP fit, generate outreach, audit AEO health, and research keywords — all from your terminal.

No Clay. No Apollo. No Semrush. Just a Gemini API key.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![GitHub stars](https://img.shields.io/github/stars/buildingopen/opengtm?style=social)

> **Demo:** `opengtm analytics --url your-site.com` -> instant AEO health report with grade A+ to F
> Full pipeline demo GIF coming soon — [watch the repo](https://github.com/buildingopen/opengtm) for updates.

One toolkit for the full GTM loop. Discover B2B leads, research decision-makers, score ICP fit, generate personalized outreach, run multi-touch sequences, and track your AI visibility — all from the terminal.

## Table of Contents

- [The Problem](#the-problem)
- [Pipeline Overview](#pipeline-overview)
- [Quickstart](#quickstart)
- [Modules](#modules)
- [ICP Scoring](#icp-scoring)
- [AEO Health Check](#aeo-health-check)
- [Message Frameworks](#message-frameworks)
- [Comparison](#comparison)
- [Use Case Personas](#use-case-personas)
- [Python API](#python-api)
- [Configuration](#configuration)
- [FAQ](#faq)
- [Related Projects](#related-projects)
- [Contributing](#contributing)
- [License](#license)

## The Problem

The GTM stack is broken for indie teams and small agencies.

- **Clay costs $800/month.** For a solo founder or 3-person team, that's a serious burn before you have revenue.
- **Apollo has 50M contacts but zero personalization.** Spray-and-pray doesn't work anymore. Buyers tune it out.
- **Writing outreach manually doesn't scale.** You can't research 50 companies per week and write tailored messages for each one by hand.
- **AEO (Answer Engine Optimization) is the new SEO and nobody has tools for it.** ChatGPT and Perplexity are replacing Google for discovery queries. Your prospects research vendors in AI search engines before replying to your outreach. If you're invisible there, you lose.

opengtm is the open-source alternative. MIT licensed, runs locally, uses Gemini + Google Search grounding for real data (no hallucinations), and integrates natively with Claude Code.

## Pipeline Overview

```
Lead Generation                         Content & AEO
──────────────────────────────────       ──────────────────────────────
Discover → Research → Qualify           Context → Keywords → Blog
    |           |        |                  |                    |
    v           v        v                  v                    v
Message → Outreach → Sync             Analytics ──────→ AEO Mentions
    |
  CRM (Google Sheets)
```

**Outbound pipeline:** Find companies, extract decision-maker contacts, score ICP fit, generate personalized outreach by pattern (A/B/C/D/E), manage a 4-touch sequence, sync to CRM.

**Content pipeline:** Extract company context, run keyword research (7 stages), generate SEO blog articles (5 stages), run AEO health check (29 checks), measure AI visibility with real queries.

## Quickstart

Three commands to your first qualified lead:

```bash
pip install opengtm
export GEMINI_API_KEY=your_key_here
opengtm pipeline --industry "B2B SaaS" --region "Berlin" --limit 10
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com).

## Modules

| Module | What it does | CLI command |
|--------|-------------|-------------|
| `discover.py` | Find companies by industry + region via Gemini + Google Search grounding | `opengtm discover` |
| `research.py` | Extract decision-maker contact + run 7-point website audit | `opengtm research` |
| `qualify.py` | Score ICP fit 0-100 across 6 dimensions, return hot/warm/cold | `opengtm qualify` |
| `message.py` | Generate personalized outreach by pattern (A/B/C/D/E), EN + DE | `opengtm message` |
| `outreach.py` | Manage 4-touch sequences, daily limits, due-today queue | `opengtm outreach` |
| `sync.py` | Push leads to Google Sheet CRM via Apps Script webhook | `opengtm sync` |
| `context.py` | Extract company context: industry, products, pain points, tone | `opengtm context` |
| `analytics.py` | AEO health check (29 checks, tiered scoring) + AI visibility | `opengtm analytics` |
| `blog.py` | Generate SEO blog articles (5-stage pipeline, internal linking) | `opengtm blog` |
| `keywords.py` | AI keyword research pipeline (7 stages, semantic clustering) | `opengtm keywords` |
| `sitemap.py` | Crawl and classify sitemap URLs by type | `opengtm sitemap` |

### Discover companies

```bash
opengtm discover --industry "IT Services" --region "Hamburg" --limit 20
# -> /tmp/opengtm-discovered.json
```

### Research a domain

```bash
opengtm research --domain example.com --company "Acme GmbH" --industry "B2B SaaS"
# -> /tmp/opengtm-researched.json

# Batch research from discover output:
opengtm research --input /tmp/opengtm-discovered.json
```

### Score ICP fit

```bash
opengtm qualify --input /tmp/opengtm-researched.json --icp-profile saas
# -> /tmp/opengtm-qualified.json (sorted by score, hot leads first)
```

Available ICP profiles: `default`, `saas`, `agency`, `professional_services`

### Generate outreach messages

```bash
opengtm message --input /tmp/opengtm-qualified.json --language en
# -> /tmp/opengtm-messages.json (Pattern A/B/C/D/E per lead)
```

### Manage outreach sequences

```bash
opengtm outreach load --input /tmp/opengtm-messages.json --state-file seq.json
opengtm outreach queue --state-file seq.json
opengtm outreach status --state-file seq.json
```

### Sync to CRM

```bash
opengtm sync --input /tmp/opengtm-messages.json
opengtm sync --input /tmp/opengtm-messages.json --dry-run
```

### Extract company context

```bash
opengtm context --url https://example.com
opengtm context --url https://example.com --country DE --language de
```

### AEO health check

```bash
# Health check (29 checks, tiered scoring, grade A+ to F)
opengtm analytics --url https://example.com --health-only

# AI visibility check
opengtm analytics --company "Example Corp" --industry "SaaS" --mentions-only

# Full analysis
opengtm analytics --url https://example.com --company "Example Corp"
```

### Keyword research

```bash
opengtm keywords --domain example.com --limit 50
opengtm keywords --domain example.com --language de --region DE --clusters 8
opengtm keywords --domain example.com --no-briefs
```

### Generate blog articles

```bash
opengtm blog --domain example.com --keyword "best practices for SaaS onboarding"
opengtm blog --domain example.com --keyword "was ist AEO" --language de --country Germany
opengtm blog --domain example.com --keyword "keyword" --context /tmp/opengtm-context.json
```

### Crawl sitemap

```bash
opengtm sitemap --url https://example.com
opengtm sitemap --url https://example.com --validate
```

## ICP Scoring

Leads are scored 0-100 across 6 dimensions inferred from website signals. No manual input required — the score is derived automatically from the website audit.

| Dimension | Max pts | What it measures |
|-----------|---------|-----------------|
| Company size | 20 | Blog, social links, site complexity as headcount proxy |
| Industry fit | 25 | Tiered by typical LTV and digital spend |
| Digital maturity | 15 | Blog investment, social presence, schema markup, language consistency |
| Pain signals | 20 | Severity-weighted website audit findings |
| Revenue signals | 10 | Content investment, multiple high-severity issues (budget proxy) |
| Contact quality | 10 | Name + LinkedIn + email found |

Score interpretation:

| Score | Tier | Recommended action |
|-------|------|--------------------|
| 70-100 | **Hot** | Prioritize: connect on LinkedIn this week |
| 45-69 | **Warm** | Standard outreach sequence |
| 0-44 | **Cold** | Long-term nurture pool |

You can override the ICP profile entirely with a custom dict for niche verticals.

## AEO Health Check

**What is AEO?** Answer Engine Optimization is the practice of making your website visible in AI search engines like ChatGPT, Perplexity, and Claude. These tools answer user queries by citing sources — if your site isn't structured for AI crawlers and doesn't have the right schema, you don't appear. AEO is the 2025+ equivalent of SEO.

The health check runs 29 checks across 4 categories and returns a tiered score with grade A+ to F.

| Category | Checks | What it covers |
|----------|--------|---------------|
| AI Crawler Access | 4 | GPTBot (OpenAI), Claude-Web (Anthropic), PerplexityBot, CCBot |
| Structured Data | 6 | Organization schema completeness, FAQ, sameAs links, content freshness |
| Technical SEO | 16 | Title, meta description, H1, heading structure, image alt, viewport, HTTPS, canonical, robots, word count, internal links, language tag, sitemap, response time, hreflang |
| Authority Signals | 3 | About page, contact info, social proof links |

Tiered scoring caps:

| Tier | Condition | Score Cap |
|------|-----------|-----------|
| 0 | Blocks all AI crawlers | 10 |
| 0 | Blocks 3+ AI crawlers | 25 |
| 0 | noindex directive on page | 5 |
| 1 | Missing Organization schema | 45 |
| 1 | Missing title or HTTPS | 55 |
| 2 | Incomplete schema or thin content | 75-95 |

| Grade | Score | Visibility band |
|-------|-------|----------------|
| A+ | 90+ | Excellent |
| A | 80-89 | Strong |
| B | 65-79 | Good |
| C | 45-64 | Moderate |
| D | 25-44 | Weak |
| F | <25 | Critical |

The logic: first, can AI crawlers even access your site? If not, nothing else matters. Second, can AI understand who you are (Organization schema)? Third, is your content structured and readable?

## Message Frameworks

5 pattern categories, selected automatically based on the best audit finding:

| Pattern | Trigger | Example hook |
|---------|---------|--------------|
| **A** | Specific finding (meta, title, broken elements, schema) | "I noticed example.com has no meta description. Google shows random text snippets instead. Quick win, 5 minutes of work." |
| **B** | Competitor visible in AI search, you're not | "[Competitor] shows up in ChatGPT for B2B SaaS companies, example.com doesn't yet. I looked at why." |
| **C** | Blog exists but content not indexed | "Your blog isn't being picked up by search engines. The content is there, but it's not surfacing in searches. Usually 1-2 technical fixes." |
| **D** | No strong finding / free tool angle | "Do you know your AI visibility? You can check how example.com ranks in ChatGPT and Perplexity in 60 seconds." |
| **E** | Clean site / no strong finding / fallback | "I tested whether example.com shows up in ChatGPT and Perplexity. Most B2B SaaS companies in Berlin don't yet." |

Every output includes: `connection_note` (LinkedIn request, 280 chars), `first_dm`, `followup`, `followup_2`, `followup_3`, and `alternatives` (other pattern options).

Supports English and German. German output uses DACH-calibrated formal address (Herr/Frau + last name) for Finance, Legal, and Medical verticals.

## Comparison

| Feature | opengtm | Clay.run | Apollo.io | Instantly.ai | Semrush | Clearbit | AEO SaaS tools |
|---------|---------|----------|-----------|-------------|---------|----------|---------------|
| Lead discovery | AI-powered | Yes | Yes | No | No | Yes | No |
| ICP scoring | Customizable 6-dimension | Basic | Yes | No | No | Yes | No |
| AEO health check | 29 checks, tiered | No | No | No | Partial | No | Yes |
| Content pipeline | Blog + Keywords + Context | No | No | No | Yes | No | No |
| Outreach sequences | 4-touch with daily limits | Yes | Yes | Yes | No | No | No |
| Open source | MIT | No | No | No | No | No | No |
| Claude Code integration | Native | No | No | No | No | No | No |
| German language support | Full (DACH-calibrated) | No | No | No | No | No | No |
| Runs locally | Yes | No | No | No | No | No | No |
| **Monthly cost** | **Free*** | **$400/mo** | **$99/mo** | **$30/mo** | **$130/mo** | **$99/mo** | **$49/mo** |

**Total if you replaced opengtm with all of the above: ~$807/month → $0 + Gemini API key**

\* Gemini free tier: 1,500 requests/day. Sufficient for most small teams.

## Use Case Personas

**1. Startup founder** — You're doing 0-to-1 outbound and can't afford Clay. Use opengtm to find 20 qualified B2B leads per week, research decision-makers, write personalized LinkedIn messages, and track your AEO visibility so prospects find you before you reach out.

**2. Growth agency** — Run discovery + research for clients at scale. Automate the research leg, generate message templates per lead, sync to client Google Sheets via webhook. Use the content pipeline to generate SEO content for multiple client domains.

**3. SEO consultant** — Run AEO health checks for client sites, identify schema gaps, check AI crawler access, run keyword research (7 stages), generate content briefs. The 29-check audit gives you a structured deliverable you can hand to a client.

**4. Claude Code power user** — Integrate the full GTM pipeline into your Claude Code workflow. Import any module directly, use the Python API, extend with custom ICP profiles or CRM integrations. Everything is standard Python, no black boxes.

**5. Content marketer** — Use the 5-stage blog pipeline: company context extraction, Gemini + Google Search grounding, content similarity check, URL verification, structured output with HTML + sources. AEO optimization is built into every article.

## Python API

```python
from opengtm.discover import discover
from opengtm.research import research
from opengtm.qualify import qualify_batch
from opengtm.message import generate_messages
from opengtm.context import extract_context
from opengtm.analytics import run_health_check, run_mentions
from opengtm.blog import generate_article
from opengtm.keywords import research_keywords
from opengtm.sitemap import crawl_sitemap

# --- AEO Health Check ---
health = run_health_check("https://example.com")
print(f"Score: {health['score']} | Grade: {health['grade']} | Band: {health['band']}")
# Score: 62.0 | Grade: C | Band: Moderate

for issue in health['issues'][:3]:
    print(f"  [{issue['severity'].upper()}] {issue['check']}: {issue['message']}")

# --- AI Visibility ---
visibility = run_mentions(
    domain="example.com",
    company_name="Example Corp",
    industry="B2B SaaS",
    queries=20,
)
print(f"Visibility: {visibility['visibility']}% | Mentions: {visibility['mentions']}/20")

# --- Full Outbound Pipeline ---
leads = discover(industry="B2B SaaS", region="Berlin", limit=10)
for lead in leads:
    lead["audit"] = research(domain=lead["domain"], company=lead["company"])

qualified = qualify_batch(leads, icp_profile="saas")
for lead in qualified:
    lead["messages"] = generate_messages(
        domain=lead["domain"],
        company=lead["company"],
        contact_name=lead["audit"].get("contact", {}).get("name", ""),
        industry=lead["industry"],
        audit=lead["audit"],
        region=lead["region"],
    )
    print(f"[{lead['qualification']['tier'].upper()}] {lead['company']}: {lead['messages']['pattern']} pattern")
    print(f"  Connection: {lead['messages']['connection_note'][:80]}...")

# --- Keyword Research ---
keywords = research_keywords("example.com", limit=30)
for kw in keywords[:5]:
    print(f"[{kw['score']}] {kw['keyword']} — cluster: {kw.get('cluster', 'N/A')}")

# --- Blog Article ---
context = extract_context("https://example.com")
article = generate_article(
    domain="example.com",
    keyword="best practices for SaaS onboarding",
    context=context,
)
print(f"Title: {article['title']}")
print(f"Words: {article['word_count']} | Sources: {len(article.get('sources', []))}")
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
# Required
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: override default Gemini model (default: gemini-2.0-flash)
# GEMINI_MODEL=gemini-2.0-flash

# Optional: CRM sync via Google Apps Script
# CRM_WEBHOOK_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec
# CRM_WEBHOOK_TOKEN=your_optional_auth_token

# Optional: outreach defaults
# DEFAULT_LANGUAGE=en          # en or de
# DEFAULT_DAILY_LIMIT=20       # max LinkedIn connection requests per day
```

Get a Gemini API key at [aistudio.google.com](https://aistudio.google.com). The free tier is sufficient for development and small-scale use. For production runs (100+ leads/day), a paid tier is recommended.

## FAQ

**How is this different from Clay.run?**
Clay is a closed SaaS that costs $800/month. opengtm is MIT licensed, runs locally, and you pay only for API usage (Gemini free tier covers development). Clay has more integrations; opengtm has AEO health checks, content pipelines, and Claude Code integration that Clay doesn't have.

**Does it work without a Gemini API key?**
The `qualify.py`, `message.py`, `outreach.py`, and `sync.py` modules work without an API key. Discovery, research, context, analytics (AI visibility), blog, and keywords all require Gemini. The AEO health check (29 technical checks) also works without a key — it fetches and parses the HTML locally.

**Can I use it for non-German markets?**
Yes. Language defaults to English. The German-specific logic in `message.py` (formal address, DACH-calibrated copy) is opt-in via `--language de`. Discovery and research work for any city or region worldwide.

**How much does the Gemini API cost for a full pipeline run?**
A typical pipeline run (10 leads: discover + research + message) uses roughly 30-50 API calls with ~2K tokens each. At Gemini 2.0 Flash pricing (~$0.075/1M input tokens), that's under $0.01. Full analytics + content pipeline adds more, but total cost per lead is typically $0.001-$0.01.

**Can I add custom ICP profiles?**
Yes. Pass `custom_profile={"top_industries": [...], "ideal_size_range": (5, 100), "pain_weight": 1.2}` to `qualify()` or `qualify_batch()`. See `qualify.py` for the full profile schema.

**What is AEO / Answer Engine Optimization?**
AEO is the practice of optimizing your website to appear as a cited source in AI search engines (ChatGPT, Perplexity, Claude, Gemini). Unlike traditional SEO where you target keyword rankings, AEO targets entity recognition: does AI know who you are, what you do, and can it verify your authority? The key signals are Organization schema, sameAs links, AI crawler access (robots.txt), and content structure.

**How does the blog pipeline avoid duplicate content?**
Stage 3 uses character shingle similarity (Jaccard coefficient, shingle size 5) to compare the generated article against existing content from your sitemap. If similarity exceeds 0.65, the article is flagged for review. This catches near-duplicate content before publication.

**Can I connect my own CRM instead of Google Sheets?**
`sync.py` posts to any HTTP endpoint that accepts a JSON array. The Google Apps Script webhook is the default integration, but you can pass any `webhook_url` to `sync_leads()`. Adding Airtable, HubSpot, or Pipedrive adapters is a straightforward contribution — see `sync.py` for the payload format.

**Is there a rate limit on the discovery?**
The `discover()` function makes one Gemini API call per batch (with up to 3 retries). It then validates domains with HEAD requests, which are rate-limited to sequential calls. For large batches (100+ companies), run multiple smaller batches with `existing_domains` deduplication.

**How do I contribute?**
Fork the repo, create a branch, make your changes, and open a PR. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions. The most useful contributions: new ICP profiles, new CRM integrations, additional language support in `message.py`, SERP volume integration in `keywords.py`.

## Related Projects

- [buildingopen/claude-setup](https://github.com/buildingopen/claude-setup) — Claude Code setup scripts and configuration
- [buildingopen/session-recall](https://github.com/buildingopen/session-recall) — Claude Code session transcript recovery
- [federicodeponte/openblog](https://github.com/federicodeponte/openblog) — Standalone blog generation pipeline
- [federicodeponte/openanalytics](https://github.com/federicodeponte/openanalytics) — Standalone AEO analytics
- [federicodeponte/openkeyword](https://github.com/federicodeponte/openkeyword) — Standalone keyword research

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for full instructions. Pull requests are welcome.

Most useful contributions:
1. New ICP profiles in `qualify.py`
2. New message frameworks in `message.py`
3. CRM integrations in `sync.py` (HubSpot, Pipedrive, Airtable)
4. Additional language support in `message.py`
5. SERP volume integration in `keywords.py` (Serper, DataForSEO)

Open an issue first for significant changes.

## License

MIT License. Copyright 2026 Federico De Ponte.

## Evidence-backed public prospect research

Research curated account seeds without a model key, validate their source evidence,
prioritize seller-specific discovery work, and keep recipient clearance separate
from account fit. Existing discovery, research, messaging and CRM commands keep
their current behavior.

```sh
python -m opengtm.public --input examples/three-companies.json --output /tmp/leads --workers 3 --cache-ttl 300
python -m pytest tests -q
```

See [lead validation](docs/lead-validation.md), [live public research](docs/traceroot/live-prospecting.md),
and [measured efficiency and limitations](docs/traceroot/gtm-efficiency.md).
TraceRoot is optional on Python 3.11+: install `.[traceroot]` to run the local SDK
export demo or benchmark. Base research and validation support Python 3.10+.
