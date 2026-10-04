from __future__ import annotations

import main as base
from yealink_lab import register_yealink_tools

# Keep the stable Home Assistant inventory/network bridge intact and extend it with
# opt-in Yealink lab tools. This wrapper avoids invasive changes to the proven bridge.
base.VERSION = '0.3.0'
register_yealink_tools(base.mcp, base.OPT)

if __name__ == '__main__':
    base.uvicorn.run(
        base.app(),
        host=base.BIND,
        port=base.PORT,
        log_level=str(base.OPT.get('log_level', 'INFO')).lower(),
    )
