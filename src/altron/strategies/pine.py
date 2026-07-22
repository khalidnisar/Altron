from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


class PineTranslationError(ValueError):
    pass


@dataclass(slots=True)
class PineTranslation:
    schema: dict[str, Any]
    warnings: list[str]

    def to_python(self, class_name: str = "TranslatedPineStrategy") -> str:
        """Emit an auditable Python plugin that delegates to the safe rule engine."""
        payload = json.dumps(self.schema, indent=4)
        return f'''from altron.strategies.rules import RuleStrategy\n\n\nclass {class_name}(RuleStrategy):\n    """Generated from the supported Pine subset; review before trading."""\n\n    def __init__(self):\n        super().__init__({payload})\n'''


class PineTranspiler:
    """Translate a deliberately small, auditable Pine v5 strategy subset.

    Supported declarations are ta.sma, ta.ema, and ta.rsi. Conditions may use
    ta.crossover/ta.crossunder or simple numeric comparisons. Arbitrary Pine code,
    broker-emulator semantics, arrays, repainting calls, and request.security are
    rejected rather than guessed.
    """

    indicator_pattern = re.compile(
        r"(?m)^\s*(?P<name>[A-Za-z_]\w*)\s*=\s*ta\.(?P<kind>sma|ema|rsi)"
        r"\(\s*(?P<source>open|high|low|close|volume)\s*,\s*(?P<period>\d+)\s*\)\s*$"
    )
    condition_pattern = re.compile(
        r"(?m)^\s*(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<expr>"
        r"ta\.(?:crossover|crossunder)\([^\n]+\)|[A-Za-z_]\w*\s*(?:>=|<=|>|<)\s*(?:[A-Za-z_]\w*|\d+(?:\.\d+)?))\s*$"
    )

    def _condition(self, expression: str) -> dict[str, Any]:
        cross = re.fullmatch(
            r"ta\.(crossover|crossunder)\(\s*([A-Za-z_]\w*)\s*,\s*([A-Za-z_]\w*)\s*\)",
            expression.strip(),
        )
        if cross:
            return {
                "left": cross.group(2),
                "operator": "crosses_above" if cross.group(1) == "crossover" else "crosses_below",
                "right": cross.group(3),
            }
        comparison = re.fullmatch(
            r"([A-Za-z_]\w*)\s*(>=|<=|>|<)\s*([A-Za-z_]\w*|\d+(?:\.\d+)?)",
            expression.strip(),
        )
        if not comparison:
            raise PineTranslationError(f"Unsupported Pine condition: {expression}")
        right: str | float = comparison.group(3)
        try:
            right = float(right)
        except ValueError:
            pass
        return {"left": comparison.group(1), "operator": comparison.group(2), "right": right}

    def transpile(self, source: str, *, name: str = "pine_translated") -> PineTranslation:
        forbidden = [token for token in ("request.security", "strategy.order", "array.", "matrix.") if token in source]
        if forbidden:
            raise PineTranslationError(f"Unsupported/repainting-sensitive Pine features: {', '.join(forbidden)}")
        indicators = [
            {
                "name": match.group("name"),
                "indicator": match.group("kind"),
                "source": match.group("source"),
                "period": int(match.group("period")),
            }
            for match in self.indicator_pattern.finditer(source)
        ]
        if not indicators:
            raise PineTranslationError("No supported ta.sma/ta.ema/ta.rsi declarations found")
        aliases = {
            match.group("name"): self._condition(match.group("expr"))
            for match in self.condition_pattern.finditer(source)
        }

        actions: dict[str, dict[str, Any]] = {}
        lines = source.splitlines()
        pending_condition: str | None = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("if "):
                pending_condition = stripped[3:].strip()
                continue
            entry = re.search(r"strategy\.entry\([^,]+,\s*strategy\.(long|short)(?:,\s*when\s*=\s*([^\)]+))?", stripped)
            close = re.search(r"strategy\.close\([^\)]*?(?:when\s*=\s*([^\)]+))?\)", stripped)
            if entry:
                expression = entry.group(2) or pending_condition
                if expression:
                    actions[f"{entry.group(1)}_entry"] = aliases.get(expression.strip()) or self._condition(expression)
            elif close:
                expression = close.group(1) or pending_condition
                if expression:
                    # A close without side information is used as both exits.
                    condition = aliases.get(expression.strip()) or self._condition(expression)
                    actions["long_exit"] = condition
                    actions["short_exit"] = condition
            if stripped and not stripped.startswith("//") and not stripped.startswith("if "):
                pending_condition = None

        long_entry = actions.get("long_entry")
        short_entry = actions.get("short_entry")
        if not long_entry and not short_entry:
            raise PineTranslationError("No supported strategy.entry action was found")
        if long_entry and not actions.get("long_exit"):
            if short_entry:
                actions["long_exit"] = short_entry
            else:
                raise PineTranslationError("A long entry needs strategy.close or an opposite short entry")
        if short_entry and not actions.get("short_exit"):
            actions["short_exit"] = long_entry or actions["long_exit"]
        schema: dict[str, Any] = {
            "name": name,
            "indicators": indicators,
            "long_entry": long_entry or {"left": "close", "operator": "<", "right": 0},
            "long_exit": actions["long_exit"],
        }
        if short_entry:
            schema["short_entry"] = short_entry
            schema["short_exit"] = actions["short_exit"]
        warnings = [
            "Translation covers signal logic only; TradingView order-fill and bar-state semantics are not reproduced.",
            "Signals execute on the next bar in Altron backtests to avoid look-ahead bias.",
        ]
        return PineTranslation(schema=schema, warnings=warnings)
