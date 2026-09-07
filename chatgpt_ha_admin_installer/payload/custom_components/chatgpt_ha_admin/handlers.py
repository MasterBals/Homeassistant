"""MCP handlers for Home Assistant administration."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er, issue_registry as ir, llm, service as svc
from homeassistant.helpers.template import Template
from homeassistant.util.json import JsonObjectType
from .const import BLOCKED_SERVICE_CALLS
from .dashboard_ops import DashboardManager
from .file_ops import ConfigFileManager
from .tool_specs import specs

class AdminHandlers:
    def __init__(self,hass:HomeAssistant,settings:dict[str,Any])->None:
        self.hass=hass; self.settings=settings; self.files=ConfigFileManager(hass,settings); self.dashboards=DashboardManager(hass,settings)
    def tools(self,tool_cls): return [tool_cls(n,d,p,getattr(self,h)) for n,d,p,h in specs()]
    async def get_overview(self,a,c):
        states=list(self.hass.states.async_all()); domains={}; bad=[]
        for s in states:
            d=s.entity_id.split('.',1)[0]; domains[d]=domains.get(d,0)+1
            if s.state in {'unavailable','unknown'}: bad.append(s.entity_id)
        return {'home_assistant_version':HA_VERSION,'time_zone':self.hass.config.time_zone,'entity_count':len(states),'domain_counts':dict(sorted(domains.items())),'unavailable_or_unknown_count':len(bad),'sample':bad[:100],'settings':self.settings,'mcp_endpoint':'/api/mcp/chatgpt_ha_admin'}
    async def search_entities(self,a,c):
        q=a.get('query','').casefold(); out=[]
        for s in self.hass.states.async_all():
            if a.get('domain') and not s.entity_id.startswith(a['domain']+'.'): continue
            if a.get('state') and s.state!=a['state']: continue
            if q and q not in f"{s.entity_id} {s.attributes.get('friendly_name','')} {s.state}".casefold(): continue
            out.append(s.as_dict())
            if len(out)>=a.get('limit',100): break
        return {'count':len(out),'entities':out}
    async def get_entity(self,a,c):
        s=self.hass.states.get(a['entity_id'])
        if s is None: raise HomeAssistantError('Entity not found')
        return s.as_dict()
    async def list_registries(self,a,c):
        q=a.get('query','').casefold(); lim=a.get('limit',250); which=a.get('registry','all'); out={}
        def f(vals):
            r=[]
            for x in vals:
                if q and q not in str(x).casefold(): continue
                r.append(x)
                if len(r)>=lim: break
            return r
        if which in {'all','areas'}: out['areas']=f(ar.async_get(self.hass).areas.values())
        if which in {'all','devices'}: out['devices']=f(dr.async_get(self.hass).devices.values())
        if which in {'all','entities'}: out['entities']=f(er.async_get(self.hass).entities.values())
        return out
    async def list_services(self,a,c):
        desc=await svc.async_get_all_descriptions(self.hass); d=a.get('domain')
        return {k:v for k,v in desc.items() if not d or k==d}
    async def list_config_files(self,a,c):
        r=self.files.list_files(a.get('path','.'),recursive=a.get('recursive',True),max_results=a.get('limit',500)); return {'count':len(r),'files':r}
    async def read_config_file(self,a,c): return self.files.read_text(a['path'])
    async def search_config(self,a,c):
        r=self.files.search_text(a['query'],path=a.get('path','.'),max_results=a.get('limit',100)); return {'count':len(r),'matches':r}
    async def check_config(self,a,c): return await self.files.check_config()
    async def write_config_file(self,a,c): return await self.files.write_text(a['path'],a['content'],expected_sha256=a.get('expected_sha256'),reason=a.get('reason','ChatGPT MCP change'))
    async def replace_config_text(self,a,c): return await self.files.replace_text(a['path'],a['old'],a['new'],expected_sha256=a.get('expected_sha256'),replace_all=a.get('replace_all',False),reason=a.get('reason','ChatGPT MCP text replacement'))
    async def list_dashboards(self,a,c):
        r=await self.dashboards.list_dashboards(); return {'count':len(r),'dashboards':r}
    async def get_dashboard(self,a,c): return await self.dashboards.get_dashboard(a.get('url_path',''))
    async def save_dashboard(self,a,c): return await self.dashboards.save_dashboard(a.get('url_path',''),a['config'],expected_sha256=a.get('expected_sha256'),reason=a.get('reason','ChatGPT MCP dashboard change'))
    async def patch_dashboard(self,a,c): return await self.dashboards.patch_dashboard(a.get('url_path',''),a['operations'],expected_sha256=a.get('expected_sha256'),reason=a.get('reason','ChatGPT MCP dashboard patch'))
    async def render_template(self,a,c): return {'result':str(await Template(a['template'],self.hass).async_render(parse_result=False))}
    async def call_service(self,a,c):
        if not self.settings.get('allow_service_calls',True): raise HomeAssistantError('Service calls disabled')
        key=(a['domain'],a['service'])
        if key in BLOCKED_SERVICE_CALLS: raise HomeAssistantError('Restart/stop services are blocked')
        if not self.hass.services.has_service(*key): raise HomeAssistantError('Service not found')
        data=dict(a.get('service_data') or {}); data.update(a.get('target') or {})
        await self.hass.services.async_call(*key,data,blocking=True,context=c.context); return {'ok':True,'domain':key[0],'service':key[1]}
    async def get_repairs(self,a,c):
        r=ir.async_get(self.hass).issues; return {'count':len(r),'issues':list(r.values())}
    async def get_logs(self,a,c):
        q=a.get('filter','').casefold(); n=a.get('lines',300); lines=[]; sources=[]
        for name in ('home-assistant.log','home-assistant.log.1'):
            p=Path(self.hass.config.path(name))
            if p.is_file():
                sources.append(name); lines.extend(p.read_text(encoding='utf-8',errors='replace').splitlines())
        if q: lines=[x for x in lines if q in x.casefold()]
        return {'available':bool(sources),'sources':sources,'lines':lines[-n:]}
    async def list_changes(self,a,c):
        r=self.files.list_changes(a.get('limit',100)); return {'count':len(r),'changes':r}
    async def restore_change(self,a,c):
        ch=self.files.find_change(a['change_id'])
        if not ch: raise HomeAssistantError('change_id not found')
        if ch.get('kind')=='file': return await self.files.restore_file_change(ch)
        if ch.get('kind')=='dashboard': return await self.dashboards.restore_dashboard_change(ch)
        raise HomeAssistantError('Change type cannot be restored')
