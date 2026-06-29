# Changelog

## 1.1.0

- Add the Chur Kultur custom integration for filtered events from chur-kultur.ch.
- Add a Chur Kultur Lovelace card with image list and detail popup.

## 1.0.5

- Refine Lovelace card bin artwork with transparent SVGs and waste-type symbols on each bin.
- Animate only the waste items falling into the bin instead of moving the whole bin image.

## 1.0.4

- Bundle and auto-register the Lovelace card from the integration so Home Assistant no longer depends on a manually copied `/config/www` card file.
- Serve the illustrated waste assets from the integration package.

## 1.0.3

- Improve the Lovelace card with visual editor options for selecting waste types.
- Add separate illustrated assets for Karton, Papier, Kompost and Kehricht.
- Show the nearest collection more prominently with relative dates for upcoming collections.

## 1.0.2

- Remove binary brand icon so repository changes can be created in environments that reject binary files in pull requests.

## 1.0.1

- Fix HACS metadata for integration custom repositories.
- Document the required HACS category to avoid adding the repository as an app/add-on repository.

## 1.0.0

- Initial production-ready HACS custom integration for Chur waste collections.
- Adds config flow, sensors, calendar, services, diagnostics and Lovelace card.
