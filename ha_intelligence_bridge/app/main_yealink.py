from __future__ import annotations

import main as base
import yealink_lab
from network_correlation import install_enhanced_correlation
from second_brain_tools import register_second_brain_tools
from bootstrap_second_brain import main as bootstrap_second_brain
from yealink_lab import register_yealink_tools
from yealink_wifi_profile import register_target_wifi_tools

# Keep the stable Home Assistant inventory/network bridge intact and extend it with
# enhanced correlation, revisioned Second Brain access and opt-in Yealink lab tools.
base.VERSION = '0.5.0'

# Home Assistant's USB discovery and the physical VCM36-W report Yealink VID
# 0x6993. Earlier lab builds accidentally treated 6993 as decimal and converted
# it again to 0x1b51, which prevented the lab inventory from seeing the device.
yealink_lab.YEALINK_VID = '6993'

# Backfill the verified VCM36-W findings exactly once. Future corrections are made
# through second_brain_upsert with the same stable topic/key so history is preserved.
bootstrap_second_brain()

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
