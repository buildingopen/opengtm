"""
research.py - Lead research and website enrichment.

Combines:
- Decision-maker contact extraction (name, title, email, LinkedIn)
- 7-point technical website audit
- Structured output for downstream qualify/message steps

Free-tier adaptation:
- Uses Gemini URL Context instead of Google Search grounding.
- The supplied company website is explicitly included in the prompt.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request

from . import DEFAULT_MODEL

MODEL = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


RESEARCH_PROMPT = """Analyze the company "{company}" at this website:

https://{domain}

Industry: {industry}

Use the URL Context tool to inspect the supplied website and only report
information that can be verified from the retrieved website content.

Task 1 - Find the decision-maker / main contact:
- Check the About, Team, Contact, Impressum, Leadership, or similar pages
  available from the supplied website.
- Find their full name and title/position.
- Find a company email address if it is explicitly shown.
- Find their LinkedIn profile URL only if the URL is explicitly present
  on the website.
- The LinkedIn URL must be linkedin.com/in/ format, NOT
  linkedin.com/company/.
- Do NOT guess, construct, or infer LinkedIn URLs.

Task 2 - Technical website audit (7 dimensions):

1. Title tag:
   - Is it generic ("Home", "Welcome")?
   - Is it too long (>60 chars)?
   - Is it too short?
   - Is it missing?

2. Meta description:
   - Is it missing?
   - Is it too short (<120 chars)?
   - Is it too long (>160 chars)?

3. Content indexing:
   - Is a blog/news section visibly accessible?
   - Is relevant content behind a login?
   - Report noindex only if the retrieved page explicitly exposes it.

4. Broken elements:
   - Report only clearly visible broken links, placeholder text,
     dead hrefs, or broken-looking plugin/output elements.

5. Social media links:
   - Check whether visible links to LinkedIn, X/Twitter, Instagram,
     YouTube, etc. are present.

6. Language consistency:
   - Check whether the website content and metadata appear to use
     inconsistent languages.

7. Schema markup:
   - Report structured data only if it is visible in the retrieved
     website content.

IMPORTANT:
- Only report findings you can VERIFY from the supplied website.
- Do not invent contact details.
- Do not claim Google Search results or external sources were checked.
- Return ONLY valid JSON.

Return this exact structure:

{{
  "contact": {{
    "name": "Full Name or empty string if not found",
    "title": "Their title/position or empty string",
    "email": "company email or null",
    "linkedin_url": "linkedin.com/in/name URL or null"
  }},
  "findings": [
    {{
      "type": "title_tag|meta_description|content_indexing|broken_element|social_links|language_mismatch|schema|other",
      "severity": "high|medium|low",
      "detail": "Exact specific finding",
      "evidence": "The exact text/element from the website"
    }}
  ],
  "title_tag_text": "exact title tag text or empty string",
  "meta_description_text": "exact meta description or MISSING",
  "site_language": "en|de|mixed|other",
  "has_blog_or_news": true,
  "has_social_links": true,
  "overall_assessment": "One sentence summary of the most important finding"
}}
"""


def _gemini_call(prompt: str, timeout: int = 90) -> str:
    """Call Gemini GenerateContent using URL Context."""

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY environment variable is not set")

    api_url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    payload = json.dumps({
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "tools": [
            {
                "url_context": {}
            }
        ],
        "generationConfig": {
            "temperature": 0.1
        },
    })

    result = subprocess.run(
        [
            "curl",
            "-s",
            "--max-time",
            str(timeout),
            "-H",
            "Content-Type: application/json",
            "-d",
            payload,
            api_url,
        ],
        capture_output=True,
        text=True,
        timeout=timeout + 10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"curl exit {result.returncode}")

    if not result.stdout.strip():
        raise RuntimeError("Empty response from Gemini")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"Invalid JSON response from Gemini: {result.stdout[:500]}"
        )

    if "error" in data:
        error = data["error"]
        code = error.get("code", "")
        status = error.get("status", "")
        message = error.get("message", "")

        raise RuntimeError(
            f"API error [{code} {status}]: {message[:500]}"
        )

    candidates = data.get("candidates", [])

    if not candidates:
        raise RuntimeError("No candidates in Gemini response")

    parts = candidates[0].get("content", {}).get("parts", [])

    text_parts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and "text" in part
    ]

    if not text_parts:
        raise RuntimeError("Gemini returned no text content")

    return "\n".join(text_parts)


def _verify_linkedin(url: str) -> bool:
    """Verify that a LinkedIn profile URL responds."""

    if not url:
        return False

    if "linkedin.com/in/" not in url:
        return False

    if "linkedin.com/company/" in url:
        return False

    full_url = url if url.startswith("http") else f"https://{url}"

    try:
        req = urllib.request.Request(
            full_url,
            method="HEAD",
        )

        req.add_header(
            "User-Agent",
            "Mozilla/5.0 (compatible; opengtm/0.1)",
        )

        resp = urllib.request.urlopen(req, timeout=8)

        return resp.status in (200, 301, 302)

    except Exception:
        return False


def research(
    domain: str,
    company: str = "",
    industry: str = "",
    verify_linkedin: bool = True,
    verbose: bool = True,
) -> dict:
    """
    Research a company using Gemini + URL Context.

    Args:
        domain:
            Company website domain, e.g. example.com

        company:
            Company name.

        industry:
            Industry vertical.

        verify_linkedin:
            Whether to perform an HTTP check on extracted LinkedIn URLs.

        verbose:
            Print progress.

    Returns:
        Structured research dictionary.
    """

    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY environment variable is not set"
        )

    # Normalize domain
    domain = domain.strip()

    if domain.startswith("https://"):
        domain = domain[8:]

    elif domain.startswith("http://"):
        domain = domain[7:]

    if domain.startswith("www."):
        domain = domain[4:]

    # Remove trailing slash
    domain = domain.rstrip("/")

    comp = company.strip() or domain

    prompt = RESEARCH_PROMPT.format(
        domain=domain,
        company=comp,
        industry=industry.strip() or "general",
    )

    if verbose:
        print(
            f"[research] Analyzing https://{domain}...",
            flush=True,
        )

    for attempt in range(3):
        try:
            text = _gemini_call(prompt, timeout=90)

            text = text.strip()

            # Remove markdown JSON fences if Gemini returns them
            if text.startswith("```"):
                lines = text.splitlines()

                if len(lines) >= 3:
                    text = "\n".join(lines[1:-1]).strip()

            data = json.loads(text)

            if not isinstance(data, dict):
                raise ValueError(
                    "Gemini returned JSON, but it is not an object"
                )

            # Ensure expected fields exist
            data.setdefault("contact", {})
            data.setdefault("findings", [])
            data.setdefault("title_tag_text", "")
            data.setdefault("meta_description_text", "MISSING")
            data.setdefault("site_language", "unknown")
            data.setdefault("has_blog_or_news", False)
            data.setdefault("has_social_links", False)
            data.setdefault(
                "overall_assessment",
                "",
            )

            contact = data["contact"]

            contact.setdefault("name", "")
            contact.setdefault("title", "")
            contact.setdefault("email", None)
            contact.setdefault("linkedin_url", None)

            # Validate LinkedIn URL
            linkedin = contact.get("linkedin_url")

            if linkedin:
                if verify_linkedin:
                    if not _verify_linkedin(linkedin):
                        if verbose:
                            print(
                                f"  LinkedIn URL unverified, dropping: "
                                f"{linkedin}",
                                flush=True,
                            )

                        contact["linkedin_url"] = None

                else:
                    if (
                        "linkedin.com/in/" not in linkedin
                        or "linkedin.com/company/" in linkedin
                    ):
                        contact["linkedin_url"] = None

            if verbose:
                finding_count = len(
                    data.get("findings", [])
                )

                name = contact.get(
                    "name",
                    "not found",
                ) or "not found"

                assessment = data.get(
                    "overall_assessment",
                    "",
                )

                print(
                    f"  Contact: {name} | "
                    f"{finding_count} findings | "
                    f"{assessment[:100]}",
                    flush=True,
                )

            return data

        except json.JSONDecodeError as e:
            if verbose:
                print(
                    f"  Attempt {attempt + 1}/3 "
                    f"JSON parse error: {e}",
                    flush=True,
                )

            if attempt < 2:
                time.sleep(2 * (attempt + 1))

        except Exception as e:
            error_text = str(e)

            if verbose:
                print(
                    f"  Attempt {attempt + 1}/3 error: "
                    f"{error_text}",
                    flush=True,
                )

            # Don't repeatedly retry quota/auth/model errors.
            fatal_markers = (
                "429",
                "403",
                "401",
                "quota",
                "TooManyRequests",
                "PERMISSION_DENIED",
                "UNAUTHENTICATED",
                "not available to new users",
                "is no longer available",
            )

            if any(
                marker in error_text
                for marker in fatal_markers
            ):
                if verbose:
                    print(
                        "  Stopping retries because this "
                        "appears to be a quota/auth/model "
                        "configuration error.",
                        flush=True,
                    )

                break

            if attempt < 2:
                time.sleep(3 * (attempt + 1))

    # Return empty-but-valid structure on total failure
    return {
        "contact": {
            "name": "",
            "title": "",
            "email": None,
            "linkedin_url": None,
        },
        "findings": [],
        "title_tag_text": "",
        "meta_description_text": "MISSING",
        "site_language": "unknown",
        "has_blog_or_news": False,
        "has_social_links": False,
        "overall_assessment": "Research failed after available attempts",
    }
