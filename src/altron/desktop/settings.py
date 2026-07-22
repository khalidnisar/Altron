from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DesktopSettings:
    """Non-secret JSON settings plus OS credential-vault secrets."""

    SERVICE = "AltronQuant"

    def __init__(self) -> None:
        try:
            from platformdirs import user_config_path, user_data_path
        except ImportError as exc:
            raise RuntimeError("Install the desktop with: pip install '.[desktop]'") from exc
        self.config_dir = Path(user_config_path("AltronQuant", "Altron"))
        self.data_dir = Path(user_data_path("AltronQuant", "Altron"))
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.config_dir / "settings.json"
        self.values: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def set(self, name: str, value: Any) -> None:
        self.values[name] = value
        self.save()

    def set_secret(self, name: str, value: str) -> None:
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError("Install the desktop credential backend with '.[desktop]'") from exc
        if value:
            keyring.set_password(self.SERVICE, name, value)
        else:
            try:
                keyring.delete_password(self.SERVICE, name)
            except keyring.errors.PasswordDeleteError:
                pass

    def get_secret(self, name: str) -> str | None:
        try:
            import keyring
        except ImportError:
            return None
        return keyring.get_password(self.SERVICE, name)
