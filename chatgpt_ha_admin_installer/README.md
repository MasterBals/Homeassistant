# ChatGPT Home Assistant Admin

Ein-Klick-Installer für eine administrative Home-Assistant-MCP-API.

Die App installiert eine Custom Integration unter `custom_components/chatgpt_ha_admin`, trägt sie automatisch in `configuration.yaml` ein, prüft die komplette Home-Assistant-Konfiguration und startet Home Assistant bei Bedarf neu.

Der MCP-Endpunkt läuft anschliessend direkt über Home Assistant:

`/api/mcp/chatgpt_ha_admin`

Es wird kein zusätzlicher Netzwerkport und kein separater API-Key benötigt. Die Authentifizierung erfolgt über Home Assistant.
