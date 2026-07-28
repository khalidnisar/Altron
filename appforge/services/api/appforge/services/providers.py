"""External provider adapters.

Each provider has a live implementation (used when credentials are configured)
and a deterministic offline implementation. Offline providers are seeded from a
hash of their input so repeated runs produce identical output -- this keeps the
pipeline, the tests, and the dashboard demo reproducible without paid API keys.
"""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from appforge.config import Settings, get_settings

NICHE_CATEGORIES = [
    "social_media",
    "productivity",
    "health_fitness",
    "finance",
    "education",
    "entertainment",
    "shopping",
    "travel",
    "food_drink",
    "communication",
    "photography",
    "music_audio",
    "utilities",
    "gaming",
    "lifestyle",
    "business",
    "news_magazines",
    "weather",
    "parenting",
    "dating",
]

# Blueprint 2.6: exclude apps from major tech companies.
EXCLUDED_DEVELOPERS = {
    "google llc",
    "google",
    "meta platforms, inc.",
    "meta",
    "facebook",
    "microsoft corporation",
    "microsoft",
    "amazon mobile llc",
    "amazon",
    "apple",
    "samsung electronics co., ltd.",
    "bytedance",
    "tencent",
    "alibaba",
    "netflix, inc.",
    "x corp.",
}


def _seed_from(*parts: Any) -> random.Random:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    text: str
    model: str
    offline: bool


class LLMProvider:
    """Text generation. Falls back to structured templates when offline."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def offline(self) -> bool:
        return self.settings.offline_mode

    def generate(self, prompt: str, *, purpose: str = "generic", **ctx: Any) -> LLMResponse:
        if self.offline:
            return LLMResponse(
                text=self._offline_text(prompt, purpose, ctx),
                model="offline-deterministic",
                offline=True,
            )
        return LLMResponse(text=self._live_text(prompt), model=self.settings.llm_model, offline=False)

    def generate_json(self, prompt: str, *, purpose: str, **ctx: Any) -> Any:
        raw = self.generate(prompt, purpose=purpose, **ctx).text
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}

    def _live_text(self, prompt: str) -> str:
        import httpx

        if self.settings.openai_api_key:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                json={
                    "model": self.settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]

        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.settings.llm_model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]

    def _offline_text(self, prompt: str, purpose: str, ctx: dict) -> str:
        rng = _seed_from(prompt, purpose)
        if purpose == "app_names":
            return json.dumps(self._offline_names(ctx, rng))
        if purpose == "store_listing":
            return json.dumps(self._offline_listing(ctx))
        return json.dumps({"summary": f"[offline:{purpose}] deterministic response"})

    @staticmethod
    def _offline_names(ctx: dict, rng: random.Random) -> list[dict]:
        base = (ctx.get("niche") or "app").split("_")[0].capitalize()
        prefixes = ["Quick", "Snap", "Bright", "Nova", "Lumen", "Swift", "Clear", "Aero"]
        suffixes = ["Forge", "Flow", "Kit", "Lab", "Hub", "Craft", "Wave", "Mind"]
        rng.shuffle(prefixes)
        rng.shuffle(suffixes)
        out = []
        for i in range(5):
            name = f"{prefixes[i]}{suffixes[i]}"
            out.append(
                {
                    "name": name,
                    "tagline": f"{base} made effortless every day",
                    "rationale": f"'{prefixes[i]}' signals speed; '{suffixes[i]}' signals craft.",
                    "memorability": 70 + rng.randint(0, 25),
                }
            )
        return out

    @staticmethod
    def _offline_listing(ctx: dict) -> dict:
        name = ctx.get("name", "App")
        value = ctx.get("value_prop", "Get more done, faster.")
        keywords = ctx.get("keywords") or ["fast", "simple", "private"]
        title = f"{name}: {keywords[0].title()} {ctx.get('niche_label', 'Tools')}"[:30]
        short = f"{value}"[:80]
        bullets = "\n".join(f"* {k.title()} by design" for k in keywords[:6])
        full = (
            f"{value}\n\n{name} is built around what users actually asked for.\n\n"
            f"WHY {name.upper()}\n{bullets}\n\n"
            "PRIVACY FIRST\nMinimal permissions. No hidden data collection. "
            "Full export and deletion controls.\n\n"
            "Download today and see the difference."
        )[:4000]
        return {
            "title": title,
            "short_description": short,
            "full_description": full,
            "keywords": keywords,
        }


# ---------------------------------------------------------------------------
# Image / design generation
# ---------------------------------------------------------------------------

ICON_SIZES = [48, 72, 96, 144, 192, 512]


class ImageProvider:
    """Generates brand assets. Offline mode emits deterministic SVG placeholders."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def offline(self) -> bool:
        return not self.settings.openai_api_key

    def generate_logo_set(self, project_id: int, name: str, palette: dict) -> dict:
        root = Path(self.settings.storage_root) / f"projects/{project_id}/brand"
        root.mkdir(parents=True, exist_ok=True)
        initial = (name or "A")[0].upper()
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
            f'<rect width="512" height="512" rx="112" fill="{palette["primary"]}"/>'
            f'<text x="50%" y="50%" dy="0.36em" text-anchor="middle" '
            f'font-family="Inter,Arial,sans-serif" font-size="280" font-weight="700" '
            f'fill="#FFFFFF">{initial}</text></svg>'
        )
        (root / "logo.svg").write_text(svg, encoding="utf-8")
        base = self.settings.storage_public_base
        assets = {"svg": f"{base}/projects/{project_id}/brand/logo.svg"}
        for size in ICON_SIZES:
            sized = svg.replace('viewBox="0 0 512 512"', f'width="{size}" height="{size}" viewBox="0 0 512 512"')
            (root / f"logo-{size}.svg").write_text(sized, encoding="utf-8")
            assets[f"icon_{size}"] = f"{base}/projects/{project_id}/brand/logo-{size}.svg"
        return assets

    def generate_screenshots(self, project_id: int, screens: list[dict], palette: dict) -> list[str]:
        root = Path(self.settings.storage_root) / f"projects/{project_id}/play-store/screenshots"
        root.mkdir(parents=True, exist_ok=True)
        urls = []
        for screen in screens[:8]:
            sid = screen["id"]
            svg = (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920">'
                f'<rect width="1080" height="1920" fill="{palette["background_dark"]}"/>'
                f'<rect x="60" y="120" width="960" height="160" rx="24" fill="{palette["primary"]}"/>'
                f'<text x="540" y="225" text-anchor="middle" font-family="Inter,Arial" '
                f'font-size="64" font-weight="700" fill="#FFF">{screen["name"]}</text>'
                f'<text x="540" y="1000" text-anchor="middle" font-family="Inter,Arial" '
                f'font-size="44" fill="{palette["text_secondary"]}">Preview</text></svg>'
            )
            (root / f"{sid}.svg").write_text(svg, encoding="utf-8")
            urls.append(f"{self.settings.storage_public_base}/projects/{project_id}/play-store/screenshots/{sid}.svg")
        return urls

    def generate_feature_graphic(self, project_id: int, name: str, tagline: str, palette: dict) -> str:
        root = Path(self.settings.storage_root) / f"projects/{project_id}/play-store"
        root.mkdir(parents=True, exist_ok=True)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="500">'
            f'<rect width="1024" height="500" fill="{palette["primary_dark"]}"/>'
            f'<text x="512" y="230" text-anchor="middle" font-family="Inter,Arial" '
            f'font-size="88" font-weight="700" fill="#FFF">{name}</text>'
            f'<text x="512" y="310" text-anchor="middle" font-family="Inter,Arial" '
            f'font-size="36" fill="#E5E7EB">{tagline}</text></svg>'
        )
        (root / "feature-graphic.svg").write_text(svg, encoding="utf-8")
        return f"{self.settings.storage_public_base}/projects/{project_id}/play-store/feature-graphic.svg"


# ---------------------------------------------------------------------------
# Play Store data
# ---------------------------------------------------------------------------

_APP_THEMES = {
    "photography": ("Photo & video editing with one-tap effects", ["Filters", "Templates", "4K export", "Batch edit"]),
    "productivity": ("Task and note capture that syncs everywhere", ["Tasks", "Notes", "Reminders", "Offline sync"]),
    "health_fitness": ("Workout and habit tracking with coaching", ["Workouts", "Streaks", "Coaching", "Wearables"]),
    "finance": ("Budgeting and spend tracking with insights", ["Budgets", "Sync", "Reports", "Alerts"]),
    "education": ("Bite-size lessons with spaced repetition", ["Lessons", "Quizzes", "Streaks", "Offline"]),
    "entertainment": ("Personalized streaming and discovery", ["Watchlist", "Downloads", "Profiles", "Cast"]),
    "shopping": ("Deal discovery and price tracking", ["Price alerts", "Coupons", "Wishlist", "Compare"]),
    "travel": ("Trip planning and itinerary management", ["Itineraries", "Offline maps", "Bookings", "Budget"]),
    "food_drink": ("Recipes and meal planning", ["Recipes", "Meal plans", "Grocery list", "Nutrition"]),
    "communication": ("Fast private messaging", ["Chat", "Calls", "Encryption", "Backup"]),
    "music_audio": ("Music and podcast listening", ["Playlists", "Offline", "Equalizer", "Sleep timer"]),
    "utilities": ("Device cleanup and file management", ["Cleaner", "Files", "Battery", "Security"]),
    "gaming": ("Casual puzzle gameplay", ["Levels", "Daily challenge", "Leaderboard", "Offline"]),
    "lifestyle": ("Daily habits and personal organization", ["Habits", "Journal", "Reminders", "Insights"]),
    "business": ("Invoicing and client management", ["Invoices", "Clients", "Expenses", "Reports"]),
    "news_magazines": ("Personalized news aggregation", ["Feeds", "Topics", "Offline", "Digest"]),
    "weather": ("Hyperlocal forecasts and alerts", ["Radar", "Alerts", "Widgets", "Hourly"]),
    "parenting": ("Baby tracking and milestones", ["Feeding", "Sleep", "Growth", "Milestones"]),
    "dating": ("Matching and conversation", ["Matches", "Chat", "Filters", "Safety"]),
    "social_media": ("Short-form video sharing", ["Feed", "Camera", "Effects", "Sharing"]),
}

_ISSUE_LIBRARY = [
    ("Excessive battery drain", "performance", "high", "Drains 30% battery in 20 minutes", "Unoptimized processing pipeline and wake locks", "Add battery saver mode, batch background work, adaptive quality"),
    ("Too many permissions required", "privacy", "high", "Why does it need my contacts?", "Over-collection for ad targeting", "Minimal permission model; make social features opt-in"),
    ("Intrusive and frequent ads", "ux", "high", "An ad every 20 seconds, unusable", "Aggressive interstitial cadence", "Frequency capping, no ads in first sessions, cheap ad-removal IAP"),
    ("App crashes on older devices", "performance", "critical", "Crashes every time I open it on Android 10", "Memory pressure and unguarded APIs", "Lower memory ceiling, guard API levels, add crash telemetry"),
    ("Slow startup time", "performance", "medium", "Takes 10 seconds just to open", "Synchronous work on main thread at boot", "Deferred init, lazy modules, splash prefetch"),
    ("No offline mode", "ux", "medium", "Useless without internet", "Server-only data path", "Local-first cache with background sync"),
    ("Subscription is overpriced", "monetization", "medium", "Way too expensive for what it does", "Single high-priced tier", "Introduce mid tier and regional pricing"),
    ("Confusing navigation", "ux", "medium", "I can never find settings", "Deep nesting and unlabeled icons", "Flatten IA, label icons, add search"),
    ("Poor accessibility support", "accessibility", "medium", "Unusable with TalkBack", "Missing semantic labels and low contrast", "Full semantics, WCAG AA contrast, dynamic type"),
    ("Data loss after update", "reliability", "critical", "Lost all my data after updating", "Unsafe migrations without backup", "Versioned migrations, pre-migration backup, restore path"),
]

_LOVE_LIBRARY = [
    ("Easy to use", "Super intuitive, figured it out in two minutes"),
    ("Great design", "Cleanest interface I have used in this category"),
    ("Genuinely useful", "Actually saves me time every single day"),
    ("Fast performance", "Snappy and responsive, no lag at all"),
    ("Good free tier", "You can do a lot without paying anything"),
]

_REQUEST_LIBRARY = [
    ("Offline mode", "Use core features without an internet connection"),
    ("Dark theme", "A true black theme for OLED screens"),
    ("Widgets", "Home screen widgets for quick access"),
    ("Cloud backup", "Automatic backup and cross-device restore"),
    ("Tablet layout", "A proper two-pane layout on tablets"),
    ("Export data", "Export to CSV or PDF"),
]


class PlayStoreProvider:
    """Google Play data source.

    Live mode expects ``google-play-scraper``; offline mode synthesizes a stable,
    realistic catalog so discovery/analysis can be exercised end to end.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def offline(self) -> bool:
        try:
            import google_play_scraper  # noqa: F401

            return False
        except Exception:
            return True

    def top_apps(self, niche: str, limit: int = 100) -> list[dict]:
        if not self.offline:
            try:
                return self._live_top_apps(niche, limit)
            except Exception:
                pass
        return self._offline_top_apps(niche, limit)

    def _live_top_apps(self, niche: str, limit: int) -> list[dict]:
        from google_play_scraper import collection  # type: ignore
        from google_play_scraper import list as gp_list

        results = gp_list(
            collection=collection.Collection.TOP_FREE,
            category=niche.upper(),
            count=limit,
        )
        return [self._normalize_live(r, niche) for r in results]

    @staticmethod
    def _normalize_live(raw: dict, niche: str) -> dict:
        return {
            "package_name": raw.get("appId"),
            "name": raw.get("title"),
            "developer": raw.get("developer"),
            "icon": raw.get("icon"),
            "rating": raw.get("score"),
            "total_downloads": raw.get("minInstalls"),
            "description": raw.get("description"),
            "niche": niche,
        }

    def _offline_top_apps(self, niche: str, limit: int) -> list[dict]:
        purpose, features = _APP_THEMES.get(niche, ("General utility app", ["Feature A", "Feature B"]))
        apps = []
        count = min(limit, 12)
        for i in range(count):
            rng = _seed_from(niche, i)
            name_word = ["Nimbus", "Volt", "Echo", "Pulse", "Atlas", "Zenith", "Orbit", "Vertex",
                         "Halo", "Prism", "Fable", "Tempo"][i % 12]
            total = rng.randint(500_000, 90_000_000)
            last_month = int(total * rng.uniform(0.02, 0.09))
            growth = rng.uniform(-0.15, 0.85)
            this_month = max(1000, int(last_month * (1 + growth)))
            reviews = max(1200, int(total * rng.uniform(0.01, 0.04)))
            neg_ratio = rng.uniform(0.06, 0.38)
            one_to_three = int(reviews * neg_ratio)
            rating = round(max(2.6, min(4.9, 5 - neg_ratio * 5.2)), 1)
            arpu = rng.uniform(0.02, 0.55)
            revenue = int(last_month * arpu * rng.uniform(0.6, 2.4))
            apps.append(
                {
                    "package_name": f"com.{niche.replace('_', '')}.{name_word.lower()}",
                    "name": f"{name_word} {niche.split('_')[0].capitalize()}",
                    "developer": f"{name_word} Labs",
                    "icon": None,
                    "rating": rating,
                    "total_downloads": total,
                    "last_month_downloads": last_month,
                    "this_month_downloads": this_month,
                    "last_month_revenue": revenue,
                    "total_reviews": reviews,
                    "one_to_three_star_reviews": one_to_three,
                    "rating_distribution": {
                        "5_star": reviews - one_to_three - int(reviews * 0.15),
                        "4_star": int(reviews * 0.15),
                        "3_star": int(one_to_three * 0.45),
                        "2_star": int(one_to_three * 0.25),
                        "1_star": one_to_three - int(one_to_three * 0.45) - int(one_to_three * 0.25),
                    },
                    "description": purpose,
                    "problem_solved": purpose,
                    "key_features": features,
                    "monetization_model": rng.choice(["free_with_ads", "freemium", "subscription"]),
                    "price": 0.0,
                    "rank": i + 1,
                    "niche": niche,
                    "social_mentions_7d": rng.randint(200, 40_000),
                }
            )
        return apps

    def fetch_reviews(self, package_name: str, target: int = 10_000) -> list[dict]:
        """Return review records. Offline mode synthesizes a realistic mix."""
        if not self.offline:
            try:
                return self._live_reviews(package_name, target)
            except Exception:
                pass
        return self._offline_reviews(package_name, target)

    def _live_reviews(self, package_name: str, target: int) -> list[dict]:
        from google_play_scraper import Sort, reviews  # type: ignore

        collected: list[dict] = []
        token = None
        while len(collected) < target:
            batch, token = reviews(
                package_name, count=min(200, target - len(collected)),
                sort=Sort.NEWEST, continuation_token=token,
            )
            if not batch:
                break
            collected.extend({"text": b["content"], "rating": b["score"], "user": b["userName"]} for b in batch)
            if token is None:
                break
        return collected

    def _offline_reviews(self, package_name: str, target: int) -> list[dict]:
        rng = _seed_from(package_name, "reviews")
        # Keep synthetic volume bounded for runtime while reporting the target scope.
        n = min(target, 1200)
        out = []
        issue_pool = rng.sample(_ISSUE_LIBRARY, k=rng.randint(4, 7))
        for i in range(n):
            if rng.random() < 0.68:
                theme, quote = rng.choice(_LOVE_LIBRARY)
                out.append({"text": quote, "rating": rng.choice([4, 5, 5]), "user": f"user{i}",
                            "theme": theme, "kind": "positive"})
            elif rng.random() < 0.55:
                issue = rng.choice(issue_pool)
                out.append({"text": issue[3], "rating": rng.choice([1, 2, 2, 3]), "user": f"user{i}",
                            "issue": issue[0], "issue_type": issue[1], "severity": issue[2],
                            "root_cause": issue[4], "fix": issue[5], "kind": "negative"})
            else:
                feat, desc = rng.choice(_REQUEST_LIBRARY)
                out.append({"text": f"Please add {feat.lower()}. {desc}", "rating": 3,
                            "user": f"user{i}", "request": feat, "request_desc": desc,
                            "kind": "request"})
        return out


# ---------------------------------------------------------------------------
# Device farm / simulator / Play Console
# ---------------------------------------------------------------------------


class DeviceFarmProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def offline(self) -> bool:
        return not (self.settings.browserstack_user and self.settings.browserstack_key)

    def simulator_session(self, project_id: int, app_name: str) -> str:
        if self.offline:
            return f"/simulator/local/{project_id}"
        return f"https://app-automate.browserstack.com/dashboard/v2/live/{project_id}"


class PlayConsoleProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def offline(self) -> bool:
        return not self.settings.play_console_service_account_json

    def submit(self, package_name: str, track: str, listing: dict, release_notes: str) -> dict:
        if self.offline:
            return {
                "success": True,
                "offline": True,
                "track": track,
                "version_code": 1,
                "play_store_url": f"https://play.google.com/store/apps/details?id={package_name}",
                "note": "Offline mode: submission simulated, no Play Console call was made.",
            }
        return self._live_submit(package_name, track, listing, release_notes)

    def _live_submit(self, package_name: str, track: str, listing: dict, release_notes: str) -> dict:
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build as build_service  # type: ignore

        creds = service_account.Credentials.from_service_account_file(
            self.settings.play_console_service_account_json,
            scopes=["https://www.googleapis.com/auth/androidpublisher"],
        )
        service = build_service("androidpublisher", "v3", credentials=creds)
        edit = service.edits().insert(packageName=package_name).execute()
        edit_id = edit["id"]
        try:
            service.edits().listings().update(
                packageName=package_name, editId=edit_id, language="en-US",
                body={
                    "title": listing["title"],
                    "shortDescription": listing["short_description"],
                    "fullDescription": listing["full_description"],
                },
            ).execute()
            service.edits().commit(packageName=package_name, editId=edit_id).execute()
            return {"success": True, "offline": False, "track": track,
                    "play_store_url": f"https://play.google.com/store/apps/details?id={package_name}"}
        except Exception:
            service.edits().delete(packageName=package_name, editId=edit_id).execute()
            raise
