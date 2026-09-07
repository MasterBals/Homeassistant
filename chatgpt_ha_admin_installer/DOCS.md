# Installation

1. Dieses GitHub-Repository im Home-Assistant-App-Store als benutzerdefiniertes Repository hinzufügen.
2. **ChatGPT Home Assistant Admin** installieren.
3. App starten.
4. Die App installiert die Integration, prüft die Konfiguration und startet Home Assistant einmal neu.
5. Danach ist die API unter `/api/mcp/chatgpt_ha_admin` verfügbar.

## Sicherheit

- Der spezifische MCP-Endpunkt wird von Home Assistant authentifiziert und erfordert einen Administrator:Innen-Zugang.
- Direkter Zugriff auf `.storage` ist über die Dateitools gesperrt.
- `secrets.yaml` und sensible Dateien sind standardmässig gesperrt.
- Änderungen werden gesichert und können über eine Änderungs-ID zurückgerollt werden.
- Home-Assistant-Neustart und Stop sind nicht über den MCP-Service-Call erlaubt.
