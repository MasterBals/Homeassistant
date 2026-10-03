# ChatGPT Home Assistant Admin + Intelligence

Eine einzige Home-Assistant-App für:

- Home-Assistant-Inventar (Entitäten, Geräte, Räume, Bereiche/Floors)
- sichere YAML-/Konfigurationszugriffe mit Backup und Hash-Prüfung
- Lovelace-Dashboard lesen, ändern und wiederherstellen
- Services, Templates, Repairs und Logs
- persistentes technisches **Second Brain** für verifizierte Erkenntnisse
- strukturiertes **MCP-Protokoll** mit Filtern für ChatGPT-Toolaufrufe
- private LAN-/VLAN-Erkennung und Geräteabgleich
- offiziellen OpenAI Secure MCP Tunnel

## Architektur

Alle eigentlichen MCP-Dienste werden ausschliesslich auf `127.0.0.1` betrieben. Es muss kein MCP-Port am Router oder im LAN freigegeben werden.

Die App führt den Home-Assistant-Admin-MCP und den Intelligence-/Netzwerk-MCP zu einem einzigen MCP-Endpunkt zusammen. Der offizielle OpenAI `tunnel-client` verbindet diesen internen MCP ausgehend mit OpenAI.

Zusätzlich stellt die App über Home-Assistant-Ingress eine lokale Bedienoberfläche **ChatGPT MCP** bereit. Diese Seite ist nur über Home Assistant erreichbar und enthält das gefilterte MCP-Protokoll sowie eine lesbare Second-Brain-Suche.

## Second Brain

Ab Version 2.2.0 besitzt die App eine persistente SQLite-Wissensdatenbank unter `/data/second_brain.sqlite3`. `/data` bleibt bei normalen App-Updates erhalten.

Native MCP-Tools:

- `SecondBrainSearch`: bestehende Erkenntnisse durchsuchen
- `SecondBrainGet`: einen Eintrag inkl. optionaler Historie lesen
- `SecondBrainUpsert`: Erkenntnis erstellen oder über einen stabilen `topic`/`key` aktualisieren
- `SecondBrainStatus`: Anzahl Einträge, Revisionen und Themen anzeigen

Jeder aktualisierte Eintrag wird vor dem Überschreiben in einer Revisionshistorie archiviert. Für technische Erkenntnisse soll zwischen `verified`, `probable` und `hypothesis` unterschieden werden.

Die MCP-Server-Instruktionen fordern ChatGPT explizit dazu auf, bei fortgesetzten Projekten zuerst im Second Brain zu suchen und verifizierte, dauerhaft relevante Erkenntnisse wieder abzuspeichern.

**Nicht ins Second Brain gehören:** Passwörter, API-Keys, Tokens oder andere Geheimnisse. Private/personenbezogene Zuordnungen sollen ebenfalls nicht unnötig als allgemeines technisches Wissen gespeichert werden.

## MCP-Protokoll

Alle Toolaufrufe, die ChatGPT über den Unified MCP ausführt, werden strukturiert unter `/data/mcp_audit.sqlite3` protokolliert. Normale Container-/Systemlogs werden nicht in diese Ansicht gemischt. Dadurch kann beispielsweise effektiv nur nachvollzogen werden, welche MCP-Befehle ChatGPT ausgeführt hat.

In der Home-Assistant-Ingress-Seite **ChatGPT MCP > MCP-Protokoll** stehen Filter für folgende Kriterien zur Verfügung:

- Quelle: Admin, Intelligence oder lokale MCP-Tools
- Typ: Lesezugriff, Schreib-/Servicebefehl, Aktion/Scan, Second Brain oder Protokollabfrage
- Toolname, z.B. `CallService`, `WriteConfigFile` oder `bluetooth_scan`
- Ergebnis: erfolgreich oder Fehler
- Zeitraum: 1 Stunde, 6 Stunden, 24 Stunden, 7 Tage oder Gesamt
- maximale Anzahl Treffer

Zusätzlich stehen `McpAuditQuery` und `McpAuditStatus` direkt als MCP-Tools zur Verfügung.

Das Audit enthält Zeitpunkt, Quelle, öffentlichen Toolnamen, Upstream-Tool, Typ, Erfolg/Fehler, Laufzeit und bereinigte Argumente. Schlüssel wie Token, Passwort, Secret, API-Key, Authorization und Credentials werden redigiert. Grosse Felder wie Dateiinhalt, `old`, `new` oder Templates werden nur als Länge plus SHA-256-Kurzfingerprint gespeichert.

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

`auto_restart` ist standardmässig deaktiviert. Wenn sich die gebündelte Admin-Integration geändert hat, erkennt die App dies über den Komponenten-Hash und führt den notwendigen Core-Neustart aus.

## ChatGPT verbinden

Nachdem im App-Log der OpenAI-Tunnel erfolgreich gestartet wurde:

1. In ChatGPT den Bereich für Apps/Connectors öffnen.
2. Eine MCP-Verbindung über **Tunnel** erstellen.
3. Dieselbe `tunnel_id` auswählen/eintragen.
4. Tools scannen/aktualisieren.
5. Die Verbindung autorisieren, falls ChatGPT dies verlangt.

ChatGPT sollte danach über einen einzigen Connector sowohl Admin-, Intelligence-, Audit- als auch Second-Brain-Tools sehen.

## Sicherheit

- Keine Portweiterleitung für 8765 oder 18765 einrichten.
- `runtime_api_key` nicht in Chats, Logs oder Screenshots veröffentlichen.
- `allow_sensitive_files` standardmässig deaktiviert lassen.
- Schreiboperationen verwenden Backups und Hash-Prüfungen.
- Direkte Änderungen an Home Assistants `.storage` bleiben blockiert.
- Das Protokoll redigiert bekannte Geheimnisfelder und speichert grosse Schreibinhalte nicht vollständig.

## Drittkomponente

Die App bündelt den offiziellen OpenAI `tunnel-client` v0.0.14. Lizenz und NOTICE befinden sich als `OPENAI_TUNNEL_CLIENT_LICENSE.txt` und `OPENAI_TUNNEL_CLIENT_NOTICE.txt` im App-Verzeichnis und werden in das Container-Image übernommen.
