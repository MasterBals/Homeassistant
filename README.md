# Homeassistant
Dashboards und Cards
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

Kopiere `custom_components/chur_abfall` nach `<config>/custom_components/chur_abfall` und starte Home Assistant neu. Die Lovelace Card und ihre Bilder werden automatisch aus der Integration ausgeliefert.

## Konfiguration

Der Config Flow lädt die Strassenliste live von der offiziellen Churer Seite. Wähle eine oder mehrere Strassen und optional Sammelarten wie Papier, Karton, Kompost und Kehricht.

## Dashboard

Die Lovelace Card wird von der Integration automatisch als Frontend-Modul registriert. Eine manuelle Ressource unter `/local/chur_abfall/chur-abfall-card.js` ist nicht nötig.

Beispielkarte:

```yaml
type: custom:chur-abfall-card
entity: sensor.chur_abfall_nachste_abfuhr
title: Chur Abfall
waste_types:
  - Karton
  - Papier
  - Kompost
  - Kehricht
animate: true
show_street: true
compact: false
```

## Services

- `chur_abfall.refresh`: Daten sofort aktualisieren.
- `chur_abfall.reload`: Integration neu laden.
- `chur_abfall.export`: Termine als Service-Antwort exportieren.

# Chur Kultur

Home Assistant Custom Integration für Veranstaltungen von `https://www.chur-kultur.ch/de/agenda`.
Die Integration lädt die Agenda mit konfigurierbarem Zeitraum, Tag-IDs und optionalem Suchtext.

## Dashboard Karte

Die Lovelace Card wird automatisch als Frontend-Modul registriert.

```yaml
type: custom:chur-kultur-card
entity: sensor.chur_kultur_veranstaltungen
title: Chur Kultur
max_items: 8
show_images: true
```

Ein Klick auf einen Eintrag öffnet ein Detail-Popup mit Bild, Ort, Kategorie, Beschreibung und Link zur Originalseite.

## Troubleshooting

- Wenn keine Strassen erscheinen, prüfe die Erreichbarkeit der offiziellen Churer Webseite aus Home Assistant.
- Nach Änderungen an der Card Browser-Cache leeren oder Home Assistant neu starten.
- Logs für `custom_components.chur_abfall` aktivieren, um Parser- und Netzwerkhinweise zu sehen.

## Lizenz

MIT
