"""Lovelace dashboard operations."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
import uuid

from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import BACKUP_DIR, JOURNAL_FILE, STATE_DIR_NAME


def _sha(config: dict[str, Any]) -> str:
    raw = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _decode_pointer(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise HomeAssistantError("JSON pointer must start with /")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def _parent_and_key(document: Any, pointer: str) -> tuple[Any, str]:
    parts = _decode_pointer(pointer)
    if not parts:
        raise HomeAssistantError("Patching the whole document root is not supported; use SaveDashboard")
    current = document
    for part in parts[:-1]:
        if isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError) as err:
                raise HomeAssistantError(f"Invalid list path segment: {part}") from err
        elif isinstance(current, dict):
            if part not in current:
                raise HomeAssistantError(f"Path does not exist: {part}")
            current = current[part]
        else:
            raise HomeAssistantError("JSON pointer traverses a scalar value")
    return current, parts[-1]


def apply_patch(document: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a safe RFC6902 subset: add, replace and remove."""
    result = deepcopy(document)
    for operation in operations:
        op = operation.get("op")
        pointer = operation.get("path")
        if op not in {"add", "replace", "remove"} or not isinstance(pointer, str):
            raise HomeAssistantError("Each patch operation needs op=add|replace|remove and a path")
        parent, key = _parent_and_key(result, pointer)
        if isinstance(parent, list):
            if key == "-" and op == "add":
                parent.append(deepcopy(operation.get("value")))
                continue
            try:
                index = int(key)
            except ValueError as err:
                raise HomeAssistantError(f"Invalid list index: {key}") from err
            if op == "add":
                if index < 0 or index > len(parent):
                    raise HomeAssistantError(f"List index out of range: {index}")
                parent.insert(index, deepcopy(operation.get("value")))
            elif op == "replace":
                if index < 0 or index >= len(parent):
                    raise HomeAssistantError(f"List index out of range: {index}")
                parent[index] = deepcopy(operation.get("value"))
            else:
                if index < 0 or index >= len(parent):
                    raise HomeAssistantError(f"List index out of range: {index}")
                parent.pop(index)
        elif isinstance(parent, dict):
            if op == "add":
                parent[key] = deepcopy(operation.get("value"))
            elif op == "replace":
                if key not in parent:
                    raise HomeAssistantError(f"Replace target does not exist: {pointer}")
                parent[key] = deepcopy(operation.get("value"))
            else:
                if key not in parent:
                    raise HomeAssistantError(f"Remove target does not exist: {pointer}")
                del parent[key]
        else:
            raise HomeAssistantError("Patch parent is not a list or object")
    return result


class DashboardManager:
    """Read and safely modify Lovelace dashboards."""

    def __init__(self, hass: HomeAssistant, settings: dict[str, Any]) -> None:
        self.hass = hass
        self.settings = settings
        self.root = Path(hass.config.config_dir).resolve()
        self.state_dir = self.root / STATE_DIR_NAME
        self.backup_dir = self.state_dir / BACKUP_DIR / "dashboards"
        self.journal_path = self.state_dir / JOURNAL_FILE
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _dashboards(self):
        data = self.hass.data.get(LOVELACE_DATA)
        if data is None:
            raise HomeAssistantError("Lovelace is not loaded")
        return data.dashboards

    @staticmethod
    def _normalise_path(url_path: str | None) -> str | None:
        return url_path or None

    def _get(self, url_path: str | None):
        key = self._normalise_path(url_path)
        dashboards = self._dashboards()
        if key not in dashboards:
            known = ["default" if item is None else str(item) for item in dashboards]
            raise HomeAssistantError(f"Dashboard not found. Available: {known}")
        return dashboards[key]

    async def list_dashboards(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for key, dashboard in self._dashboards().items():
            try:
                config = await dashboard.async_load(False)
                hash_value = _sha(config)
                views = len(config.get("views", [])) if isinstance(config, dict) else None
            except Exception as err:
                hash_value = None
                views = None
                error = str(err)
            else:
                error = None
            info = {
                "url_path": "" if key is None else str(key),
                "display_path": "default" if key is None else str(key),
                "mode": dashboard.mode,
                "views": views,
                "sha256": hash_value,
                "error": error,
            }
            if hasattr(dashboard, "path"):
                try:
                    info["source_path"] = str(Path(dashboard.path).relative_to(self.root))
                except Exception:
                    info["source_path"] = str(dashboard.path)
            result.append(info)
        return result

    async def get_dashboard(self, url_path: str | None) -> dict[str, Any]:
        dashboard = self._get(url_path)
        config = await dashboard.async_load(False)
        result = {
            "url_path": url_path or "",
            "mode": dashboard.mode,
            "sha256": _sha(config),
            "config": config,
        }
        if hasattr(dashboard, "path"):
            try:
                result["source_path"] = str(Path(dashboard.path).relative_to(self.root))
            except Exception:
                result["source_path"] = str(dashboard.path)
        return result

    def _backup(self, url_path: str | None, config: dict[str, Any], change_id: str) -> str:
        safe_name = (url_path or "default").replace("/", "_")
        path = self.backup_dir / change_id / f"{safe_name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        return path.relative_to(self.root).as_posix()

    def _journal(self, record: dict[str, Any]) -> None:
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"timestamp": datetime.now(timezone.utc).isoformat(), **record},
                    ensure_ascii=False,
                    default=str,
                )
                + "\n"
            )

    async def save_dashboard(
        self,
        url_path: str | None,
        config: dict[str, Any],
        *,
        expected_sha256: str | None,
        reason: str,
    ) -> dict[str, Any]:
        if not self.settings.get("write_enabled", True):
            raise HomeAssistantError("Writes are disabled")
        dashboard = self._get(url_path)
        if dashboard.mode != MODE_STORAGE:
            source = getattr(dashboard, "path", None)
            raise HomeAssistantError(
                f"Dashboard is YAML-backed and cannot be saved via Lovelace storage API. Edit its YAML file instead: {source}"
            )
        current = await dashboard.async_load(False)
        current_sha = _sha(current)
        if self.settings.get("require_hash_for_writes", True):
            if not expected_sha256:
                raise HomeAssistantError(
                    f"expected_sha256 is required. Read dashboard first and use {current_sha}."
                )
            if expected_sha256 != current_sha:
                raise HomeAssistantError("Dashboard changed since it was read. Re-read before writing.")
        if not isinstance(config, dict) or not isinstance(config.get("views", []), list):
            raise HomeAssistantError("Dashboard config must be an object with a views list")

        change_id = uuid.uuid4().hex
        backup = self._backup(url_path, current, change_id)
        await dashboard.async_save(config)
        saved = await dashboard.async_load(True)
        new_sha = _sha(saved)
        self._journal(
            {
                "change_id": change_id,
                "kind": "dashboard",
                "url_path": url_path or "",
                "reason": reason,
                "backup": backup,
                "old_sha256": current_sha,
                "new_sha256": new_sha,
            }
        )
        return {
            "ok": True,
            "change_id": change_id,
            "url_path": url_path or "",
            "old_sha256": current_sha,
            "new_sha256": new_sha,
            "backup": backup,
        }

    async def patch_dashboard(
        self,
        url_path: str | None,
        operations: list[dict[str, Any]],
        *,
        expected_sha256: str | None,
        reason: str,
    ) -> dict[str, Any]:
        current = await self.get_dashboard(url_path)
        patched = apply_patch(current["config"], operations)
        return await self.save_dashboard(
            url_path,
            patched,
            expected_sha256=expected_sha256,
            reason=reason,
        )

    async def restore_dashboard_change(self, change: dict[str, Any]) -> dict[str, Any]:
        if change.get("kind") != "dashboard":
            raise HomeAssistantError("Change is not a dashboard change")
        backup = self.root / str(change.get("backup", ""))
        if not backup.is_file():
            raise HomeAssistantError("Dashboard backup is missing")
        config = json.loads(backup.read_text(encoding="utf-8"))
        dashboard = self._get(str(change.get("url_path") or ""))
        if dashboard.mode != MODE_STORAGE:
            raise HomeAssistantError("Dashboard is no longer storage-backed")
        current = await dashboard.async_load(False)
        return await self.save_dashboard(
            str(change.get("url_path") or ""),
            config,
            expected_sha256=_sha(current),
            reason=f"Restore change {change['change_id']}",
        )
