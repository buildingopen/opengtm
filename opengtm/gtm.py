"""Evidence-limited account prioritization, independent of recipient clearance."""

from __future__ import annotations

from datetime import datetime, timezone

from .validate import contains, matched_groups, timestamp


def prioritize(policy: dict, page: dict, research: str) -> dict:
    """A score orders research work. It never claims purchase probability."""
    body = page.get("content_text", page.get("text", ""))
    groups = policy["signal_groups"]
    fit = matched_groups(body, groups)
    fit_score = round(50 * sum(bool(g) for g in fit) / len(groups)) if groups else 0
    profile = policy.get("gtm_profile", {})
    triggers, risks = [], []
    trigger_score = 0
    for rule in profile.get("timing_rules", []):
        # A dated event must be visible in the same independent source. A
        # generic pricing page or hiring link alone is not buying intent.
        try:
            event_date = datetime.strptime(rule["date_text"], "%B %d, %Y").replace(
                tzinfo=timezone.utc
            )
        except (KeyError, TypeError, ValueError):
            continue
        fetched_at = timestamp(page.get("fetched_at"))
        recent = fetched_at is not None and 0 <= (fetched_at - event_date).days <= 90
        if (
            recent
            and contains(body, rule["date_text"])
            and all(matched_groups(body, rule["groups"]))
        ):
            triggers.append(
                {
                    "code": rule["code"],
                    "source_url": page["url"],
                    "interpretation": "Published signal; recency and buying intent need review",
                }
            )
            trigger_score = max(trigger_score, min(25, max(0, rule["weight"])))
    for rule in profile.get("risk_rules", []):
        if all(matched_groups(body, rule["groups"])):
            risks.append(
                {
                    "code": rule["code"],
                    "source_url": page["url"],
                    "interpretation": "Potential existing capability; not a disqualification by itself",
                }
            )
    # No points for a contact form, guessed budget, fabricated intent or industry size.
    score = max(0, fit_score + trigger_score - min(25, len(risks) * 10))
    blocked = research == "reject" or not all(fit)
    action = (
        "repair_evidence"
        if blocked
        else "investigate_now"
        if trigger_score
        else "validate_need"
    )
    return {
        "score": score,
        "score_max": 75,
        "priority": "hold" if blocked else "A" if trigger_score else "B",
        "action": action,
        "fit_score": fit_score,
        "timing_score": trigger_score,
        "timing_signals": triggers,
        "capability_risks": risks,
        "buying_intent": "unknown",
        "buyer_role_hypothesis": policy["buyer_role"],
        "discovery_question": policy["validation_question"],
        "offer": profile.get("pilot_offer", policy["conversation"]),
        "score_basis": "Heuristic research priority, not conversion probability; no independent labels yet",
    }
