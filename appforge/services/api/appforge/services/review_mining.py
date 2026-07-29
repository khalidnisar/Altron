"""Review mining: sentiment, topic clustering, issue extraction (blueprint 3.2.2).

Uses a lexicon + frequency clustering approach so it runs with no ML service
dependency. When an LLM key is configured the summaries are upgraded, but the
structure of the output is identical either way.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

POSITIVE_WORDS = {
    "love", "great", "excellent", "amazing", "intuitive", "clean", "fast", "useful",
    "helpful", "best", "perfect", "easy", "snappy", "saves", "responsive", "cleanest",
}
NEGATIVE_WORDS = {
    "crash", "crashes", "drains", "slow", "useless", "expensive", "spyware", "ads",
    "unusable", "lost", "broken", "bug", "bugs", "terrible", "worst", "hate",
    "confusing", "overpriced", "fails", "laggy", "freezes",
}

SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


#: Words that invert the polarity of a complaint term that follows them.
NEGATORS = {"never", "no", "not", "without", "zero", "doesn't", "does",
            "don't", "hasn't", "haven't", "isn't", "wasn't", "rarely"}

#: How far after a negator the inversion still applies.
_NEGATION_WINDOW = 3

# A negator must never also be a polarity word, or it would negate itself.
assert not (NEGATORS & NEGATIVE_WORDS), NEGATORS & NEGATIVE_WORDS
assert not (NEGATORS & POSITIVE_WORDS), NEGATORS & POSITIVE_WORDS


def _count_polarity(tokens: list[str], vocabulary: set[str]) -> int:
    """Count vocabulary hits, skipping any that sit inside a negation window.

    "never crashes" and "no bugs" are praise, not complaints; counting the
    complaint token naively flipped 5-star reviews to negative and inflated
    the issue counts that drive the whole improvement thesis.
    """
    hits = 0
    for i, token in enumerate(tokens):
        if token not in vocabulary:
            continue
        window = tokens[max(0, i - _NEGATION_WINDOW):i]
        if any(w in NEGATORS for w in window):
            continue  # negated -> does not count toward this polarity
        hits += 1
    return hits


def classify_sentiment(review: dict[str, Any]) -> str:
    """Rating-anchored sentiment with negation-aware lexical override."""
    text = (review.get("text") or "").lower()
    rating = review.get("rating")
    tokens = re.findall(r"[a-z']+", text)

    pos = _count_polarity(tokens, POSITIVE_WORDS)
    neg = _count_polarity(tokens, NEGATIVE_WORDS)

    # The star rating is the strongest available signal; trust it first.
    if rating is not None:
        if rating >= 4:
            # Only override a high rating on an un-negated complaint.
            return "negative" if neg > pos else "positive"
        if rating <= 2:
            return "negative"

    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def analyze_reviews(reviews: list[dict[str, Any]], target_scope: int) -> dict[str, Any]:
    """Produce the full review_analysis block from blueprint 3.2.2."""
    for r in reviews:
        r["sentiment"] = classify_sentiment(r)

    counts = Counter(r["sentiment"] for r in reviews)

    # --- what users love: cluster positive reviews by theme -------------
    love_clusters: dict[str, list[dict]] = defaultdict(list)
    for r in reviews:
        if r["sentiment"] == "positive":
            love_clusters[r.get("theme") or "General satisfaction"].append(r)

    what_users_love = [
        {
            "theme": theme,
            "frequency": len(items),
            "example": items[0].get("text", ""),
        }
        for theme, items in sorted(love_clusters.items(), key=lambda kv: -len(kv[1]))
    ][:5]

    # --- identified issues: cluster negatives by topic ------------------
    issue_clusters: dict[str, list[dict]] = defaultdict(list)
    for r in reviews:
        if r["sentiment"] == "negative" and r.get("issue"):
            issue_clusters[r["issue"]].append(r)

    identified_issues = []
    for issue, items in issue_clusters.items():
        # Blueprint quality standard: only trust issues with 10+ corroborating reviews.
        if len(items) < 10:
            continue
        first = items[0]
        severity = first.get("severity", "medium")
        identified_issues.append(
            {
                "issue": issue,
                "type": first.get("issue_type", "ux"),
                "severity": severity,
                "frequency": len(items),
                "user_quotes": [i.get("text", "") for i in items[:3]],
                "root_cause_hypothesis": first.get("root_cause", "Unknown"),
                "suggested_fix": first.get("fix", "Investigate and remediate"),
                "impact_rank": len(items) * SEVERITY_WEIGHT.get(severity, 2),
            }
        )
    identified_issues.sort(key=lambda i: -i["impact_rank"])

    # --- feature requests ------------------------------------------------
    request_clusters: dict[str, list[dict]] = defaultdict(list)
    for r in reviews:
        if r.get("request"):
            request_clusters[r["request"]].append(r)

    feature_requests = [
        {
            "feature": feat,
            "frequency": len(items),
            "description": items[0].get("request_desc", ""),
        }
        for feat, items in sorted(request_clusters.items(), key=lambda kv: -len(kv[1]))
    ][:6]

    return {
        "total_reviews_analyzed": len(reviews),
        "review_scope_target": target_scope,
        "sentiment_breakdown": {
            "positive": counts.get("positive", 0),
            "neutral": counts.get("neutral", 0),
            "negative": counts.get("negative", 0),
        },
        "what_users_love": what_users_love,
        "identified_issues": identified_issues,
        "feature_requests": feature_requests,
    }
