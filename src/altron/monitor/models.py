"""Pydantic models for monitors, windows, and alerts.

Validation lives here so the YAML loader, the scheduler, the runner, and
the CLI all share one source of truth. The schema is intentionally
narrow: name, URL, optional interval, an active window, what to look for,
and where to send alerts. Anything more complex belongs in the runner.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class Weekday(str, Enum):
    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"

    @classmethod
    def from_pyweekday(cls, weekday: int) -> "Weekday":
        return [cls.MON, cls.TUE, cls.WED, cls.THU, cls.FRI, cls.SAT, cls.SUN][weekday]


class DiffConfig(BaseModel):
    full_page_hash: bool = True
    ignore_selectors: list[str] = Field(default_factory=list)
    min_change_chars: int = 20


class QuietHours(BaseModel):
    start: time
    end: time

    @field_validator("start", "end", mode="before")
    @classmethod
    def _parse(cls, value: Any) -> time:
        if isinstance(value, time):
            return value
        if isinstance(value, str):
            return time.fromisoformat(value)
        raise ValueError("quiet hours must be HH:MM strings or time objects")


class NotifyConfig(BaseModel):
    channels: list[str] = Field(default_factory=lambda: ["log"])
    quiet_hours: QuietHours | None = None
    cooldown_seconds: int = 30 * 60
    digest_on_quiet: bool = True
    urgent_keywords: list[str] = Field(default_factory=list)
    urgent_regex: list[str] = Field(default_factory=list)

    @field_validator("channels", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> list[str]:
        if value is None:
            return ["log"]
        if isinstance(value, str):
            return [c.strip() for c in value.split(",") if c.strip()]
        if isinstance(value, list):
            return [str(c).strip() for c in value if str(c).strip()]
        raise ValueError("channels must be a list or comma-separated string")

    @field_validator("urgent_keywords", "urgent_regex", mode="before")
    @classmethod
    def _listify(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return [str(v) for v in value]


class Monitor(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1)
    method: str = "GET"
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 20.0
    interval: str = "15m"

    active_from: date | None = None
    active_until: date | None = None
    days_of_week: list[Weekday] | None = None
    hours_of_day: tuple[time, time] | None = None
    timezone: str = "UTC"

    selectors: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    regex: str | None = None

    diff: DiffConfig = Field(default_factory=DiffConfig)
    notify: NotifyConfig = Field(default_factory=lambda: NotifyConfig(channels=["log"]))

    # --- validators ----------------------------------------------------

    @field_validator("name")
    @classmethod
    def _name_slug(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._\-]+", value):
            raise ValueError("name must be a slug (letters, digits, dot, dash, underscore)")
        return value

    @field_validator("method")
    @classmethod
    def _method(cls, value: str) -> str:
        value = value.upper()
        if value not in {"GET", "POST"}:
            raise ValueError("method must be GET or POST")
        return value

    @field_validator("url")
    @classmethod
    def _url(cls, value: str) -> str:
        if not (value.startswith("http://") or value.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return value

    @field_validator("days_of_week", mode="before")
    @classmethod
    def _days(cls, value: Any) -> list[Weekday] | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        return [Weekday(str(v).lower()) for v in value]

    @field_validator("hours_of_day", mode="before")
    @classmethod
    def _hours(cls, value: Any) -> tuple[time, time] | None:
        if value is None or value == "":
            return None
        if isinstance(value, str):
            if "-" in value and "," not in value:
                start_str, end_str = value.split("-", 1)
                value = [start_str.strip(), end_str.strip()]
            else:
                value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("hours_of_day must be 'HH:MM-HH:MM' or [start, end]")
        start = time.fromisoformat(str(value[0]))
        end = time.fromisoformat(str(value[1]))
        if start == end:
            raise ValueError("hours_of_day start and end must differ")
        return (start, end)

    @field_validator("interval")
    @classmethod
    def _interval(cls, value: str) -> str:
        if not re.fullmatch(r"\d+[smhd]", value):
            raise ValueError("interval must be like 30s, 15m, 1h, 1d")
        return value

    @field_validator("keywords", "selectors", mode="before")
    @classmethod
    def _lists(cls, value: Any) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return [str(v) for v in value]

    @field_validator("regex")
    @classmethod
    def _regex(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regex: {exc}") from exc
        return value

    @field_validator("active_from", "active_until", mode="before")
    @classmethod
    def _date(cls, value: Any) -> date | None:
        if value is None or value == "":
            return None
        return date.fromisoformat(str(value))

    @model_validator(mode="after")
    def _window_sanity(self) -> "Monitor":
        if (
            self.active_from is not None
            and self.active_until is not None
            and self.active_from > self.active_until
        ):
            raise ValueError("active_from must be <= active_until")
        for pattern in self.notify.urgent_regex:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid urgent regex: {exc}") from exc
        return self

    # --- public helpers ------------------------------------------------

    def is_active(self, moment: datetime | None = None) -> bool:
        """Return True if ``moment`` falls inside the active window."""
        moment = moment or datetime.now(UTC)
        local = _to_local(moment, self.timezone)
        if self.active_from and local.date() < self.active_from:
            return False
        if self.active_until and local.date() > self.active_until:
            return False
        if self.days_of_week and Weekday.from_pyweekday(local.weekday()) not in self.days_of_week:
            return False
        if self.hours_of_day is not None:
            start, end = self.hours_of_day
            if not _time_in_window(local.time(), start, end):
                return False
        return True


def _to_local(moment: datetime, tz_name: str) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    try:
        from zoneinfo import ZoneInfo

        return moment.astimezone(ZoneInfo(tz_name))
    except Exception:
        return moment.astimezone(UTC)


def _time_in_window(now: time, start: time, end: time) -> bool:
    if start < end:
        return start <= now < end
    return now >= start or now < end


class Alert(BaseModel):
    monitor: str
    url: str
    kind: str  # page_change | selector_change | keyword_match | regex_match
    summary: str
    details: dict[str, Any] = Field(default_factory=dict)
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    urgent: bool = False
