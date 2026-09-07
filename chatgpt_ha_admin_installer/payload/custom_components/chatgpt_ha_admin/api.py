"""ChatGPT Home Assistant Admin LLM API."""
from __future__ import annotations
from collections.abc import Awaitable, Callable
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm
from homeassistant.util.json import JsonObjectType
from .handlers import AdminHandlers

Handler = Callable[[dict[str, Any], llm.LLMContext], Awaitable[JsonObjectType]]

def jsonify(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)): return value
    if isinstance(value, Enum): return jsonify(value.value)
    if isinstance(value, Path): return str(value)
    if isinstance(value, dict): return {str(k): jsonify(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)): return [jsonify(v) for v in value]
    if is_dataclass(value): return jsonify(asdict(value))
    fn=getattr(value,"as_dict",None)
    if callable(fn):
        try: return jsonify(fn())
        except Exception: pass
    return str(value)

class AdminTool(llm.Tool):
    def __init__(self,name:str,description:str,parameters:vol.Schema,handler:Handler)->None:
        self.name=name; self.description=description; self.parameters=parameters; self._handler=handler
    async def async_call(self,hass:HomeAssistant,tool_input:llm.ToolInput,llm_context:llm.LLMContext)->JsonObjectType:
        return jsonify(await self._handler(tool_input.tool_args,llm_context))

class ChatGPTHomeAssistantAdminAPI(llm.API):
    def __init__(self,*,hass:HomeAssistant,id:str,name:str,settings:dict[str,Any])->None:
        super().__init__(hass=hass,id=id,name=name); self.settings=settings; self._handlers=AdminHandlers(hass,settings)
    async def async_get_api_instance(self,llm_context:llm.LLMContext)->llm.APIInstance:
        prompt=("Administrative Home Assistant access. Inspect live state/config before changes. "
                "Read files/dashboards first and pass their SHA-256 on writes. Prefer minimal targeted edits. "
                "Never edit .storage directly. Use dedicated dashboard/registry tools. Validate YAML changes. "
                "Every write creates a backup and change_id; use RestoreChange when a verified change must be reverted.")
        return llm.APIInstance(api=self,api_prompt=prompt,llm_context=llm_context,tools=self._handlers.tools(AdminTool))
