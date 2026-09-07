"""MCP tool schemas."""
from __future__ import annotations
import voluptuous as vol

def specs():
    R=vol.Required; O=vol.Optional; A=vol.All; G=vol.Range
    return [
      ("GetOverview","Home Assistant overview, counts and safety settings",vol.Schema({}),"get_overview"),
      ("SearchEntities","Search current entities by id, name, domain or state",vol.Schema({O("query",default=""):str,O("domain"):str,O("state"):str,O("limit",default=100):A(int,G(min=1,max=500))}),"search_entities"),
      ("GetEntity","Get one entity state and attributes",vol.Schema({R("entity_id"):str}),"get_entity"),
      ("ListRegistries","Read area, device and entity registries",vol.Schema({O("registry",default="all"):vol.In(["all","areas","devices","entities"]),O("query",default=""):str,O("limit",default=250):A(int,G(min=1,max=1000))}),"list_registries"),
      ("ListServices","List registered actions/services",vol.Schema({O("domain"):str}),"list_services"),
      ("ListConfigFiles","List files under /config",vol.Schema({O("path",default="."):str,O("recursive",default=True):bool,O("limit",default=500):A(int,G(min=1,max=2000))}),"list_config_files"),
      ("ReadConfigFile","Read UTF-8 config file and SHA-256 before writing",vol.Schema({R("path"):str}),"read_config_file"),
      ("SearchConfig","Search text across /config",vol.Schema({R("query"):str,O("path",default="."):str,O("limit",default=100):A(int,G(min=1,max=500))}),"search_config"),
      ("CheckConfig","Run full Home Assistant config validation",vol.Schema({}),"check_config"),
      ("WriteConfigFile","Safely create/replace a config file with hash, backup and rollback",vol.Schema({R("path"):str,R("content"):str,O("expected_sha256"):str,O("reason",default="ChatGPT MCP change"):str}),"write_config_file"),
      ("ReplaceConfigText","Safely replace exact text with hash protection",vol.Schema({R("path"):str,R("old"):str,R("new"):str,O("expected_sha256"):str,O("replace_all",default=False):bool,O("reason",default="ChatGPT MCP text replacement"):str}),"replace_config_text"),
      ("ListDashboards","List Lovelace dashboards and hashes",vol.Schema({}),"list_dashboards"),
      ("GetDashboard","Read complete Lovelace dashboard and hash",vol.Schema({O("url_path",default=""):str}),"get_dashboard"),
      ("SaveDashboard","Safely replace a storage Lovelace dashboard",vol.Schema({O("url_path",default=""):str,R("config"):dict,O("expected_sha256"):str,O("reason",default="ChatGPT MCP dashboard change"):str}),"save_dashboard"),
      ("PatchDashboard","Patch dashboard via add/replace/remove JSON pointer operations",vol.Schema({O("url_path",default=""):str,R("operations"):[dict],O("expected_sha256"):str,O("reason",default="ChatGPT MCP dashboard patch"):str}),"patch_dashboard"),
      ("RenderTemplate","Render/test a Home Assistant Jinja template",vol.Schema({R("template"):str}),"render_template"),
      ("CallService","Call a Home Assistant service; restart/stop are blocked",vol.Schema({R("domain"):str,R("service"):str,O("service_data",default={}):dict,O("target",default={}):dict}),"call_service"),
      ("GetRepairs","Read Home Assistant Repairs issues",vol.Schema({}),"get_repairs"),
      ("GetLogs","Read/filter recent home-assistant.log lines if available",vol.Schema({O("filter",default=""):str,O("lines",default=300):A(int,G(min=1,max=3000))}),"get_logs"),
      ("ListChanges","List MCP changes and change IDs",vol.Schema({O("limit",default=100):A(int,G(min=1,max=1000))}),"list_changes"),
      ("RestoreChange","Restore a previous file/dashboard change by ID",vol.Schema({R("change_id"):str}),"restore_change"),
    ]
