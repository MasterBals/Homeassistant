# Chur Abfall

Home Assistant Custom Integration für Abfalltermine der Stadt Chur. Die Integration liest ausschliesslich die offizielle Quelle `https://www.chur.ch/abfallstrassenabschnitte`, ermittelt Strassenabschnitte automatisch und stellt Termine als Sensoren, Kalender und Lovelace Card bereit.

## Screenshots

> Platzhalter: Screenshots können nach der Installation aus dem Dashboard ergänzt werden.

## Installation über HACS

1. HACS → Integrationen → Benutzerdefiniertes Repository.
2. Repository-URL eintragen und Kategorie **Integration** wählen.
3. **Chur Abfall** installieren.
4. Home Assistant neu starten.
5. Einstellungen → Geräte & Dienste → Integration hinzufügen → **Chur Abfall**.

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

- Wenn keine Strassen erscheinen, prüfe die Erreichbarkeit der offiziellen Churer Webseite aus Home Assistant.
- Nach Änderungen an der Card Browser-Cache leeren oder die Ressource neu laden.
- Logs für `custom_components.chur_abfall` aktivieren, um Parser- und Netzwerkhinweise zu sehen.

## Lizenz

MIT
