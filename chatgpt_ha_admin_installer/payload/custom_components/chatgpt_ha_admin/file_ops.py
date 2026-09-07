"""Safe file operations with backup, hashing and rollback."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any
import uuid

from homeassistant import config as conf_util
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.yaml import Secrets, load_yaml

from .const import BACKUP_DIR, JOURNAL_FILE, SENSITIVE_NAMES, STATE_DIR_NAME


class ConfigFileManager:
    """Manage Home Assistant config files safely."""

    def __init__(self, hass: HomeAssistant, settings: dict[str, Any]) -> None:
        self.hass = hass
        self.settings = settings
        self.root = Path(hass.config.config_dir).resolve()
        self.state_dir = self.root / STATE_DIR_NAME
        self.backup_dir = self.state_dir / BACKUP_DIR
        self.journal_path = self.state_dir / JOURNAL_FILE
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def resolve(self, user_path: str, *, for_write: bool = False) -> Path:
        """Resolve a path inside /config and enforce sensitive-file rules."""
        raw = (user_path or "").strip().replace("\\", "/")
        if raw in {"", ".", "/config", "/config/"}:
            candidate = self.root
        else:
            if raw.startswith("/config/"):
                raw = raw[len("/config/") :]
            elif raw.startswith("/homeassistant/"):
                raw = raw[len("/homeassistant/") :]
            elif raw.startswith("/"):
                raise HomeAssistantError("Only paths inside /config are allowed")
            candidate = (self.root / raw).resolve(strict=False)

        if candidate != self.root and self.root not in candidate.parents:
            raise HomeAssistantError("Path traversal outside /config is blocked")

        relative = candidate.relative_to(self.root).as_posix() if candidate != self.root else "."
        parts = Path(relative).parts
        sensitive = ".storage" in parts or candidate.name in SENSITIVE_NAMES
        if sensitive and not self.settings.get("allow_sensitive_files", False):
            raise HomeAssistantError(
                "Sensitive Home Assistant storage/auth files are blocked. Use registry/dashboard tools instead."
            )
        if for_write and ".storage" in parts:
            raise HomeAssistantError(
                "Direct writes to .storage are blocked to prevent corruption. Use dedicated dashboard/registry APIs."
            )
        return candidate

    def list_files(
        self,
        path: str = ".",
        *,
        recursive: bool = True,
        max_results: int = 500,
    ) -> list[dict[str, Any]]:
        base = self.resolve(path)
        if not base.exists():
            raise HomeAssistantError(f"Path not found: {path}")
        paths = base.rglob("*") if recursive and base.is_dir() else base.glob("*") if base.is_dir() else [base]
        results: list[dict[str, Any]] = []
        for item in paths:
            if len(results) >= max_results:
                break
            try:
                rel = self._relative(item)
            except ValueError:
                continue
            if rel.startswith(f"{STATE_DIR_NAME}/"):
                continue
            if ".storage" in item.parts and not self.settings.get("allow_sensitive_files", False):
                continue
            if item.is_file():
                try:
                    size = item.stat().st_size
                except OSError:
                    continue
                results.append({"path": rel, "size": size, "suffix": item.suffix.lower()})
        return results

    def read_text(self, path: str) -> dict[str, Any]:
        target = self.resolve(path)
        if not target.is_file():
            raise HomeAssistantError(f"File not found: {path}")
        data = target.read_bytes()
        limit = int(self.settings.get("max_read_bytes", 2_000_000))
        if len(data) > limit:
            raise HomeAssistantError(
                f"File is {len(data)} bytes, exceeding max_read_bytes={limit}. Search it instead."
            )
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as err:
            raise HomeAssistantError("File is not UTF-8 text") from err
        return {
            "path": self._relative(target),
            "sha256": self.sha256_bytes(data),
            "size": len(data),
            "content": text,
        }

    def search_text(
        self,
        query: str,
        *,
        path: str = ".",
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        if not query:
            raise HomeAssistantError("query is required")
        results: list[dict[str, Any]] = []
        q = query.casefold()
        for info in self.list_files(path, recursive=True, max_results=3000):
            if len(results) >= max_results:
                break
            file_path = self.root / info["path"]
            if info["size"] > int(self.settings.get("max_read_bytes", 2_000_000)):
                continue
            try:
                text = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if q in line.casefold():
                    results.append(
                        {
                            "path": info["path"],
                            "line": line_no,
                            "text": line[:1000],
                        }
                    )
                    if len(results) >= max_results:
                        break
        return results

    def _backup(self, target: Path, change_id: str) -> str | None:
        if not target.exists():
            return None
        rel = self._relative(target)
        destination = self.backup_dir / change_id / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, destination)
        return destination.relative_to(self.root).as_posix()

    def _journal(self, record: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **record,
        }
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    async def check_config(self) -> dict[str, Any]:
        """Run Home Assistant's full core configuration validation."""
        errors = await conf_util.async_check_ha_config_file(self.hass)
        return {"valid": errors is None, "errors": errors}

    async def _validate_yaml_syntax(self, target: Path) -> None:
        if target.suffix.lower() not in {".yaml", ".yml"}:
            return
        secrets = Secrets(self.root)
        try:
            await self.hass.async_add_executor_job(load_yaml, target, secrets)
        except Exception as err:  # Home Assistant YAML parser has several exception types
            raise HomeAssistantError(f"YAML validation failed: {err}") from err

    async def write_text(
        self,
        path: str,
        content: str,
        *,
        expected_sha256: str | None = None,
        reason: str = "MCP change",
        run_core_check: bool = True,
    ) -> dict[str, Any]:
        if not self.settings.get("write_enabled", True):
            raise HomeAssistantError("Writes are disabled in ChatGPT Home Assistant Admin settings")
        target = self.resolve(path, for_write=True)
        existed = target.exists()
        old_data = target.read_bytes() if existed and target.is_file() else None
        old_sha = self.sha256_bytes(old_data) if old_data is not None else None
        if existed and not target.is_file():
            raise HomeAssistantError("Target exists but is not a file")
        if existed and self.settings.get("require_hash_for_writes", True):
            if not expected_sha256:
                raise HomeAssistantError(
                    f"expected_sha256 is required. Read the file first and use its sha256 ({old_sha})."
                )
            if expected_sha256 != old_sha:
                raise HomeAssistantError(
                    "File changed since it was read. Re-read it before writing to avoid overwriting newer changes."
                )

        change_id = uuid.uuid4().hex
        backup = self._backup(target, change_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.{change_id}.tmp")
        tmp.write_text(content, encoding="utf-8", newline="\n")
        tmp.replace(target)

        try:
            await self._validate_yaml_syntax(target)
            config_result = {"valid": True, "errors": None, "checked": False}
            if run_core_check and target.suffix.lower() in {".yaml", ".yml"}:
                config_result = await self.check_config()
                config_result["checked"] = True
                if not config_result["valid"]:
                    raise HomeAssistantError(
                        f"Home Assistant configuration invalid after change: {config_result['errors']}"
                    )
        except Exception:
            if old_data is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(old_data)
            raise

        new_data = target.read_bytes()
        new_sha = self.sha256_bytes(new_data)
        self._journal(
            {
                "change_id": change_id,
                "kind": "file",
                "path": self._relative(target),
                "reason": reason,
                "backup": backup,
                "existed_before": existed,
                "old_sha256": old_sha,
                "new_sha256": new_sha,
            }
        )
        return {
            "ok": True,
            "change_id": change_id,
            "path": self._relative(target),
            "old_sha256": old_sha,
            "new_sha256": new_sha,
            "backup": backup,
            "config_check": config_result,
        }

    async def replace_text(
        self,
        path: str,
        old: str,
        new: str,
        *,
        expected_sha256: str | None,
        replace_all: bool = False,
        reason: str = "MCP text replacement",
    ) -> dict[str, Any]:
        current = self.read_text(path)
        count = current["content"].count(old)
        if count == 0:
            raise HomeAssistantError("Text to replace was not found")
        if count > 1 and not replace_all:
            raise HomeAssistantError(
                f"Text occurs {count} times. Set replace_all=true or provide a more specific match."
            )
        content = current["content"].replace(old, new, -1 if replace_all else 1)
        return await self.write_text(
            path,
            content,
            expected_sha256=expected_sha256,
            reason=reason,
        )

    def list_changes(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.journal_path.exists():
            return []
        lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        result: list[dict[str, Any]] = []
        for line in reversed(lines[-max(limit, 1) :]):
            try:
                value = json.loads(line)
            except ValueError:
                continue
            result.append(value)
        return result

    def find_change(self, change_id: str) -> dict[str, Any] | None:
        for item in self.list_changes(10000):
            if item.get("change_id") == change_id:
                return item
        return None

    async def restore_file_change(self, change: dict[str, Any]) -> dict[str, Any]:
        if change.get("kind") != "file":
            raise HomeAssistantError("Change is not a file change")
        target = self.resolve(str(change["path"]), for_write=True)
        backup = change.get("backup")
        restore_change_id = uuid.uuid4().hex
        current_backup = self._backup(target, restore_change_id)
        if backup:
            backup_path = self.resolve(str(backup))
            if not backup_path.is_file():
                raise HomeAssistantError("Backup file is missing")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, target)
        elif change.get("existed_before") is False:
            target.unlink(missing_ok=True)
        else:
            raise HomeAssistantError("No restorable backup was recorded")

        check = await self.check_config()
        if not check["valid"]:
            if current_backup:
                shutil.copy2(self.resolve(current_backup), target)
            raise HomeAssistantError(f"Rollback would make configuration invalid: {check['errors']}")

        self._journal(
            {
                "change_id": restore_change_id,
                "kind": "restore_file",
                "path": change["path"],
                "restored_change_id": change["change_id"],
                "backup": current_backup,
            }
        )
        return {
            "ok": True,
            "change_id": restore_change_id,
            "restored_change_id": change["change_id"],
            "path": change["path"],
            "config_check": check,
        }
