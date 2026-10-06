from __future__ import annotations

import main as base
from network_correlation import install_enhanced_correlation
from yealink_lab import register_yealink_tools
from yealink_wifi_profile import register_target_wifi_tools

# Keep the stable Home Assistant inventory/network bridge intact and extend it with
# enhanced correlation plus opt-in Yealink lab tools.
base.VERSION = '0.4.2'
install_enhanced_correlation(base)
register_yealink_tools(base.mcp, base.OPT)
register_target_wifi_tools(base.mcp, base.OPT)

if __name__ == '__main__':
    base.uvicorn.run(
        base.app(),
        host=base.BIND,
        port=base.PORT,
        log_level=str(base.OPT.get('log_level', 'INFO')).lower(),
    )
