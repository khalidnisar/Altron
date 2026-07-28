"""Clone Potential Score must match blueprint section 2.4 exactly."""

from __future__ import annotations

from appforge.services.scoring import (
    calculate_clone_potential,
    estimate_complexity,
    trend_score,
)


def _app(**over):
    base = {
        "last_month_revenue": 0,
        "last_month_downloads": 100_000,
        "this_month_downloads": 100_000,
        "total_reviews": 10_000,
        "one_to_three_star_reviews": 500,
        "key_features": ["Notes"],
    }
    base.update(over)
    return base


class TestRevenuePotential:
    def test_top_tier_awards_25(self):
        r = calculate_clone_potential(_app(last_month_revenue=2_000_000))
        assert r["breakdown"]["revenue_potential"] == 25

    def test_tiers_are_monotonic(self):
        tiers = [(2_000_000, 25), (600_000, 20), (200_000, 15),
                 (60_000, 10), (20_000, 5), (5_000, 0)]
        for revenue, expected in tiers:
            r = calculate_clone_potential(_app(last_month_revenue=revenue))
            assert r["breakdown"]["revenue_potential"] == expected, revenue


class TestGrowthVelocity:
    def test_hypergrowth_awards_20(self):
        r = calculate_clone_potential(_app(last_month_downloads=100_000,
                                           this_month_downloads=200_000))
        assert r["breakdown"]["growth_velocity"] == 20

    def test_decline_awards_zero(self):
        r = calculate_clone_potential(_app(last_month_downloads=100_000,
                                           this_month_downloads=80_000))
        assert r["breakdown"]["growth_velocity"] == 0

    def test_zero_baseline_does_not_divide_by_zero(self):
        r = calculate_clone_potential(_app(last_month_downloads=0, this_month_downloads=5_000))
        assert r["breakdown"]["growth_velocity"] == 0


class TestImprovementOpportunity:
    def test_many_unhappy_users_is_max_opportunity(self):
        r = calculate_clone_potential(_app(total_reviews=1000, one_to_three_star_reviews=400))
        assert r["breakdown"]["improvement_opportunity"] == 25

    def test_happy_userbase_scores_zero(self):
        r = calculate_clone_potential(_app(total_reviews=1000, one_to_three_star_reviews=50))
        assert r["breakdown"]["improvement_opportunity"] == 0


class TestMarketCompetition:
    def test_low_saturation_awards_15(self):
        r = calculate_clone_potential(_app(), niche_saturation=0.2)
        assert r["breakdown"]["market_competition"] == 15

    def test_saturated_market_awards_zero(self):
        r = calculate_clone_potential(_app(), niche_saturation=0.9)
        assert r["breakdown"]["market_competition"] == 0


class TestTechnicalFeasibility:
    def test_simple_app_is_most_feasible(self):
        r = calculate_clone_potential(_app(key_features=["Notes", "Reminders"]))
        assert r["breakdown"]["technical_feasibility"] == 15

    def test_ar_streaming_is_disqualifying(self):
        r = calculate_clone_potential(_app(key_features=["Real-time streaming"]))
        assert r["breakdown"]["technical_feasibility"] == 0
        assert r["complexity"] == "very_high"


def test_score_is_bounded_and_sums_components():
    r = calculate_clone_potential(
        _app(last_month_revenue=2_000_000, last_month_downloads=100_000,
             this_month_downloads=300_000, total_reviews=1000,
             one_to_three_star_reviews=400),
        niche_saturation=0.1,
    )
    assert r["score"] == sum(r["breakdown"].values())
    assert 0 <= r["score"] <= 100
    assert r["score"] == 100  # perfect candidate


def test_estimate_complexity_ordering():
    assert estimate_complexity(["Notes"]) == "low"
    assert estimate_complexity(["Cloud sync"]) == "medium"
    assert estimate_complexity(["AI editing"]) == "high"
    assert estimate_complexity(["Video call"]) == "very_high"


def test_trend_score_is_bounded():
    for mentions in (0, 5_000, 100_000):
        s = trend_score(_app(social_mentions_7d=mentions,
                             last_month_downloads=1000, this_month_downloads=2000))
        assert 0 <= s <= 100
