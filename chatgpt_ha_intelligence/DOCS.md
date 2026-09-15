# ChatGPT Home Assistant Admin + Intelligence

Eine einzige Home-Assistant-App für:

- Home-Assistant-Inventar (Entitäten, Geräte, Räume, Bereiche/Floors)
- sichere YAML-/Konfigurationszugriffe mit Backup und Hash-Prüfung
- Lovelace-Dashboard lesen, ändern und wiederherstellen
- Services, Templates, Repairs und Logs
- private LAN-/VLAN-Erkennung und Geräteabgleich
- offiziellen OpenAI Secure MCP Tunnel

## Architektur

Alle internen MCP-Dienste werden ausschliesslich auf `127.0.0.1` betrieben. Es muss kein MCP-Port am Router oder im LAN freigegeben werden.

Die App führt den Home-Assistant-Admin-MCP und den Intelligence-/Netzwerk-MCP zu einem einzigen MCP-Endpunkt zusammen. Der offizielle OpenAI `tunnel-client` verbindet diesen internen `main`-MCP ausgehend mit OpenAI.

## Erforderliche Tunnel-Daten

Für die ChatGPT-Verbindung müssen nur diese beiden Felder gesetzt werden:

- `tunnel_id`: OpenAI Tunnel-ID, Format `tunnel_` + 32 kleine Hex-Zeichen
- `runtime_api_key`: eingeschränkter OpenAI Runtime API Key für den Tunnel

Der Runtime-Key sollte nur die für den laufenden Tunnel benötigten Berechtigungen besitzen (Tunnels Read + Use). Verwende für die dauerhaft laufende App keinen Admin-Key.

## Interne Authentifizierung

Die App erzeugt automatisch einen zufälligen internen MCP-Token und speichert ihn geschützt unter `/data`. Dieser Token wird nur zwischen den lokalen Prozessen innerhalb der Home-Assistant-App verwendet und muss nicht manuell konfiguriert werden.

Der OpenAI-Tunnel selbst authentifiziert sich mit `tunnel_id` + `runtime_api_key` beim OpenAI-Control-Plane. Der lokale Unified-MCP ist nur über Loopback erreichbar.

## Home-Assistant-Admin-Integration

Beim Start installiert/aktualisiert die App `chatgpt_ha_admin` unter `custom_components` und validiert danach die Home-Assistant-Konfiguration.

`auto_restart` ist standardmässig deaktiviert. Nach einer komplett neuen Erstinstallation kann deshalb ein einmaliger manueller Home-Assistant-Neustart erforderlich sein, damit die Admin-Integration geladen wird. Die Intelligence-/Netzwerkfunktionen können trotzdem bereits laufen.

## ChatGPT verbinden

Nachdem im App-Log der OpenAI-Tunnel erfolgreich gestartet wurde:

1. In ChatGPT den Bereich für Apps/Connectors öffnen.
2. Eine MCP-Verbindung über **Tunnel** erstellen.
3. Dieselbe `tunnel_id` auswählen/eintragen.
4. Tools scannen/aktualisieren.
5. Die Verbindung autorisieren, falls ChatGPT dies verlangt.

ChatGPT sollte danach über einen einzigen Connector sowohl die Admin- als auch die Intelligence-/Netzwerktools sehen.

## Sicherheit

- Keine Portweiterleitung für 8765 oder 18765 einrichten.
- `runtime_api_key` nicht in Chats, Logs oder Screenshots veröffentlichen.
- `allow_sensitive_files` standardmässig deaktiviert lassen.
- Schreiboperationen verwenden Backups und Hash-Prüfungen.
- Direkte Änderungen an Home Assistants `.storage` bleiben blockiert.

## Drittkomponente

Die App bündelt den offiziellen OpenAI `tunnel-client` v0.0.14. Lizenz und NOTICE befinden sich als `OPENAI_TUNNEL_CLIENT_LICENSE.txt` und `OPENAI_TUNNEL_CLIENT_NOTICE.txt` im App-Verzeichnis und werden in das Container-Image übernommen.
