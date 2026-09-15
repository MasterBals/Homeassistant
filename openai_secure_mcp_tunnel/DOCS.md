# OpenAI Secure MCP Tunnel

Diese Home-Assistant-App startet den offiziellen `openai/tunnel-client` und verbindet einen lokalen MCP-Server ueber eine ausgehende Verbindung mit einem OpenAI Secure MCP Tunnel.

Es ist keine Portweiterleitung am Router erforderlich.

## Voraussetzungen

- OpenAI Tunnel ID (`tunnel_...`)
- OpenAI Runtime API Key mit mindestens `Tunnels Read` und `Tunnels Use`
- Laufender lokaler MCP-Server

Fuer `ChatGPT Home Assistant Admin + Intelligence` ist der lokale MCP-Endpunkt standardmaessig:

`http://127.0.0.1:8765/mcp`

## Konfiguration

- `tunnel_id`: ID des bereits in OpenAI Platform angelegten Tunnels.
- `runtime_api_key`: Eingeschraenkter Runtime API Key fuer den Tunnel. Kein Admin-Key verwenden.
- `mcp_server_url`: Lokaler MCP-Endpunkt. Fuer die EP/Home-Assistant-Bridge ist der Standard bereits korrekt.
- `mcp_bearer_token`: Derselbe MCP-Token, der in `ChatGPT Home Assistant Admin + Intelligence` konfiguriert ist.
- `log_level`: Log-Level des offiziellen Tunnel-Clients.

Der Bearer-Token wird nicht als Klartext-Kommandozeilenargument an den Tunnel-Client uebergeben. Er wird ueber eine Environment-Referenz fuer `MCP_EXTRA_HEADERS` und `MCP_DISCOVERY_EXTRA_HEADERS` bereitgestellt.

## ChatGPT

Nach erfolgreichem Start muss in ChatGPT derselbe OpenAI Tunnel ausgewaehlt bzw. dieselbe Tunnel-ID verwendet werden. Die ChatGPT-Verbindung selbst benoetigt dann keine direkte Erreichbarkeit deiner Home-Assistant-IP.

## Sicherheit

- Port 8765 nicht am Router freigeben.
- Fuer den dauerhaft laufenden Tunnel einen eingeschraenkten Runtime API Key verwenden.
- Den OpenAI Admin API Key nicht in dieser App hinterlegen.
- `runtime_api_key` und `mcp_bearer_token` niemals in Logs oder Chats posten.

## Upstream

Die App verwendet den offiziellen OpenAI `tunnel-client` aus:

https://github.com/openai/tunnel-client

Der OpenAI `tunnel-client` ist unter Apache License 2.0 veroeffentlicht. Der Wrapper in diesem Repository wurde unabhaengig fuer Home Assistant erstellt und uebernimmt keinen Code aus der Community-Integration `norpol/hass-codex-tunnel-mcp`.
