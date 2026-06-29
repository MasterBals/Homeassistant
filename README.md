# Chur Abfall

Home Assistant Custom Integration für Abfalltermine der Stadt Chur. Die Integration liest ausschliesslich die offizielle Quelle `https://www.chur.ch/abfallstrassenabschnitte`, ermittelt Strassenabschnitte automatisch und stellt Termine als Sensoren, Kalender und Lovelace Card bereit.

## Screenshots

> Platzhalter: Screenshots können nach der Installation aus dem Dashboard ergänzt werden.

## Installation über HACS

> Wichtig: Dieses Repository ist eine **HACS Integration**. Es ist kein Home Assistant Add-on, kein AppDaemon-App-Repository und kein Supervisor-Repository. Wenn Home Assistant meldet `is not a valid app repository`, wurde beim Hinzufügen die falsche Kategorie gewählt.

1. In Home Assistant **HACS** öffnen, nicht den Supervisor Add-on Store.
2. HACS → **Integrationen** → Menü oben rechts → **Benutzerdefinierte Repositories**.
3. Repository-URL `https://github.com/MasterBals/Homeassistant` eintragen.
4. Kategorie zwingend **Integration** wählen. Nicht **AppDaemon**, **Plugin**, **Theme** oder **Add-on** wählen.
5. **Chur Abfall** installieren.
6. Home Assistant neu starten.
7. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Chur Abfall**.

Falls die Meldung weiterhin erscheint, prüfe zusätzlich, dass das GitHub-Repository öffentlich ist und eine Repository-Beschreibung sowie Topics gesetzt sind; HACS verlangt diese Metadaten für Custom Repositories.

## Manuelle Installation

Kopiere `custom_components/chur_abfall` nach `<config>/custom_components/chur_abfall` und `www/chur_abfall/chur-abfall-card.js` nach `<config>/www/chur_abfall/chur-abfall-card.js`.

## Konfiguration

Der Config Flow lädt die Strassenliste live von der offiziellen Churer Seite. Wähle eine oder mehrere Strassen und optional Sammelarten wie Papier, Karton, Kompost und Kehricht.

## Dashboard

Füge die Ressource hinzu:

```yaml
url: /local/chur_abfall/chur-abfall-card.js
type: module
```

Beispielkarte:

```yaml
type: custom:chur-abfall-card
entity: sensor.nachste_abfuhr
title: Chur Abfall
show_timeline: true
timeline_items: 5
animate: true
```

## Services

- `chur_abfall.refresh`: Daten sofort aktualisieren.
- `chur_abfall.reload`: Integration neu laden.
- `chur_abfall.export`: Termine als Service-Antwort exportieren.

## Troubleshooting

- `https://github.com/MasterBals/Homeassistant is not a valid app repository`: Das Repository wurde als App/AppDaemon oder im falschen Home-Assistant-Bereich hinzugefügt. Öffne HACS → Integrationen → Benutzerdefinierte Repositories und wähle als Kategorie **Integration**.
- Wenn keine Strassen erscheinen, prüfe die Erreichbarkeit der offiziellen Churer Webseite aus Home Assistant.
- Nach Änderungen an der Card Browser-Cache leeren oder die Ressource neu laden.
- Logs für `custom_components.chur_abfall` aktivieren, um Parser- und Netzwerkhinweise zu sehen.

## Lizenz

MIT
