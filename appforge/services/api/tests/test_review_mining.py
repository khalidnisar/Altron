"""Review mining behaviour (blueprint 3.2.2)."""

from __future__ import annotations

from appforge.services.review_mining import analyze_reviews, classify_sentiment


def test_low_rating_is_negative():
    assert classify_sentiment({"text": "fine", "rating": 1}) == "negative"


def test_high_rating_without_complaints_is_positive():
    assert classify_sentiment({"text": "love this app", "rating": 5}) == "positive"


def test_lexical_override_catches_complaint_in_mid_rating():
    assert classify_sentiment({"text": "it crashes constantly", "rating": 3}) == "negative"


def _issue_reviews(n: int, issue="Excessive battery drain"):
    return [
        {"text": "Drains battery fast", "rating": 1, "kind": "negative",
         "issue": issue, "issue_type": "performance", "severity": "high",
         "root_cause": "Unoptimized pipeline", "fix": "Add battery saver"}
        for _ in range(n)
    ]


def test_issue_requires_ten_corroborating_reviews():
    """Blueprint quality standard: verify issues are REAL via 10+ reviews."""
    weak = analyze_reviews(_issue_reviews(9), 10_000)
    assert weak["identified_issues"] == []

    strong = analyze_reviews(_issue_reviews(10), 10_000)
    assert len(strong["identified_issues"]) == 1
    assert strong["identified_issues"][0]["frequency"] == 10


def test_issues_ranked_by_frequency_times_severity():
    reviews = _issue_reviews(30, "Minor annoyance")
    for r in reviews:
        r["severity"] = "low"
    critical = _issue_reviews(15, "Data loss after update")
    for r in critical:
        r["severity"] = "critical"

    result = analyze_reviews(reviews + critical, 10_000)
    # 15 * 4 (critical) = 60 beats 30 * 1 (low) = 30
    assert result["identified_issues"][0]["issue"] == "Data loss after update"


def test_sentiment_breakdown_totals_match_input():
    reviews = _issue_reviews(12) + [
        {"text": "love it", "rating": 5, "theme": "Easy to use", "kind": "positive"}
        for _ in range(8)
    ]
    result = analyze_reviews(reviews, 10_000)
    counts = result["sentiment_breakdown"]
    assert counts["positive"] + counts["neutral"] + counts["negative"] == len(reviews)
    assert result["total_reviews_analyzed"] == len(reviews)


def test_feature_requests_are_ranked():
    reviews = (
        [{"text": "add offline", "rating": 3, "request": "Offline mode",
          "request_desc": "Work without internet"} for _ in range(5)]
        + [{"text": "add widgets", "rating": 3, "request": "Widgets",
            "request_desc": "Home screen widgets"} for _ in range(2)]
    )
    result = analyze_reviews(reviews, 10_000)
    assert result["feature_requests"][0]["feature"] == "Offline mode"
    assert result["feature_requests"][0]["frequency"] == 5
