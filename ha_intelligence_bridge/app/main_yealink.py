from __future__ import annotations

import json
import os
from pathlib import Path

import main as base
import yealink_lab
from network_correlation import install_enhanced_correlation
from second_brain_tools import register_second_brain_tools
from bootstrap_second_brain import main as bootstrap_second_brain
from state_store import brain_get, brain_search
from yealink_lab import register_yealink_tools
from yealink_wifi_profile import register_target_wifi_tools

# Keep the stable Home Assistant inventory/network bridge intact and extend it with
# enhanced correlation, revisioned Second Brain access and opt-in Yealink lab tools.
base.VERSION = '0.5.1'

# Home Assistant's USB discovery and the physical VCM36-W report Yealink VID
# 0x6993. Earlier lab builds accidentally treated 6993 as decimal and converted
# it again to 0x1b51, which prevented the lab inventory from seeing the device.
yealink_lab.YEALINK_VID = '6993'


def export_yealink_second_brain() -> None:
    """Write a read-only diagnostic snapshot of Yealink knowledge into /config.

    The live Second Brain remains authoritative in /data. This snapshot exists only
    so the existing Admin MCP can read the Yealink investigation state even when the
    client tool projection does not expose second_brain_* calls. WLAN credentials are
    never sourced from add-on options and therefore cannot enter this export.
    """
    path = Path('/homeassistant/yealink_second_brain_export.json')
    entries = []
    for row in brain_search('', topic='yealink', limit=200):
        full = brain_get('yealink', str(row.get('key') or ''), include_history=True) or row
        entries.append(full)
    payload = {
        'schema': 1,
        'topic': 'yealink',
        'read_only_snapshot': True,
        'secrets_source_included': False,
        'entry_count': len(entries),
        'entries': entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.new')
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# Backfill the verified VCM36-W findings exactly once. Future corrections are made
# through second_brain_upsert with the same stable topic/key so history is preserved.
bootstrap_second_brain()
export_yealink_second_brain()

install_enhanced_correlation(base)
register_second_brain_tools(base.mcp)
register_yealink_tools(base.mcp, base.OPT)
register_target_wifi_tools(base.mcp, base.OPT)

if __name__ == '__main__':
    base.uvicorn.run(
        base.app(),
        host=base.BIND,
        port=base.PORT,
        log_level=str(base.OPT.get('log_level', 'INFO')).lower(),
    )
