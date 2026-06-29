"""HTML parser for the Chur waste collection page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
import logging
import re

_LOGGER = logging.getLogger(__name__)
_DATE_PATTERNS = ("%Y-%m-%d", "%Y%m%d", "%d.%m.%Y", "%d.%m.%y", "%d.%m")
_WASTE_WORDS = (
    "Papier",
    "Karton",
    "Kompost",
    "Kehricht",
    "Grüngut",
    "Metall",
    "Glas",
    "Textil",
    "Sperrgut",
)


@dataclass(frozen=True, slots=True)
class Street:
    """Street entry from the source page."""

    id: str
    name: str


@dataclass(frozen=True, slots=True)
class WasteEvent:
    """Waste collection event."""

    date: date
    waste_type: str
    street: str
    street_id: str


class ChurWasteHTMLParser(HTMLParser):
    """Lenient DOM-like parser that keeps tags, attributes and text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.nodes: list[dict[str, object]] = []
        self._stack: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node: dict[str, object] = {
            "tag": tag,
            "attrs": dict(attrs),
            "text": "",
            "children": [],
        }
        if self._stack:
            self._stack[-1]["children"].append(node)  # type: ignore[index,union-attr]
        self.nodes.append(node)
        self._stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1]["text"] = f"{self._stack[-1]['text']} {data}"


def _node_text(node: dict[str, object]) -> str:
    parts = [str(node.get("text", ""))]
    for child in node.get("children", []):
        parts.append(_node_text(child))
    return " ".join(parts).strip()


def parse_date(value: str, today: date | None = None) -> date | None:
    """Parse a Swiss or machine-readable date."""
    text = re.sub(r"\s+", " ", value.strip())
    year = (today or date.today()).year
    candidates = [
        match.group(0)
        for match in re.finditer(
            r"\d{4}-\d{1,2}-\d{1,2}|\d{8}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}\.\d{1,2}\.",
            text,
        )
    ]
    if not candidates and re.fullmatch(
        r"\d{4}-\d{1,2}-\d{1,2}|\d{8}|\d{1,2}\.\d{1,2}\.\d{2,4}|\d{1,2}\.\d{1,2}\.",
        text,
    ):
        candidates.append(text)
    for candidate in candidates:
        candidate = candidate.strip()
        for pattern in _DATE_PATTERNS:
            try:
                parsed = datetime.strptime(candidate, pattern).date()
            except ValueError:
                continue
            if pattern == "%d.%m":
                parsed = parsed.replace(year=year)
                if today and parsed < today:
                    parsed = parsed.replace(year=year + 1)
            return parsed
    return None


def parse_streets(html: str) -> list[Street]:
    """Extract street names and ids from selects, links and data attributes."""
    parser = ChurWasteHTMLParser()
    parser.feed(html)
    streets: dict[str, Street] = {}
    for node in parser.nodes:
        attrs: dict[str, str | None] = node.get("attrs", {})  # type: ignore[assignment]
        text = re.sub(r"\s+", " ", _node_text(node)).strip()
        ident = (
            attrs.get("value")
            or attrs.get("data-id")
            or attrs.get("data-street-id")
            or attrs.get("data-strassenabschnitt-id")
        )
        if not ident:
            href = attrs.get("href") or ""
            match = re.search(r"(?:street|strasse|abschnitt|id)[=_/-](\d+)", href, re.I)
            ident = match.group(1) if match else None
        if ident and text and not parse_date(text) and 2 < len(text) < 100:
            key = str(ident).strip()
            streets[key] = Street(id=key, name=text)
    return sorted(streets.values(), key=lambda item: item.name.lower())


def parse_events(
    html: str, streets: list[Street], today: date | None = None
) -> list[WasteEvent]:
    """Extract future collection events for selected streets."""
    parser = ChurWasteHTMLParser()
    parser.feed(html)
    today = today or date.today()
    events: set[WasteEvent] = set()
    street_by_id = {street.id: street for street in streets}
    street_by_name = {street.name.lower(): street for street in streets}
    for node in parser.nodes:
        attrs: dict[str, str | None] = node.get("attrs", {})  # type: ignore[assignment]
        full_text = re.sub(r"\s+", " ", _node_text(node)).strip()
        date_text = attrs.get("data-order") or attrs.get("datetime") or full_text
        event_date = parse_date(date_text, today)
        if not event_date or event_date < today:
            continue
        waste_type = next(
            (word for word in _WASTE_WORDS if re.search(word, full_text, re.I)),
            "Abfall",
        )
        street = None
        attr_street_id = attrs.get("data-street-id") or attrs.get(
            "data-strassenabschnitt-id"
        )
        if attr_street_id in street_by_id:
            street = street_by_id[attr_street_id]
        if street is None:
            street = next(
                (
                    candidate
                    for name, candidate in street_by_name.items()
                    if name in full_text.lower()
                ),
                None,
            )
        if street is None and len(streets) == 1:
            street = streets[0]
        if street is not None:
            events.add(WasteEvent(event_date, waste_type, street.name, street.id))
    specific = {
        (event.date, event.street_id)
        for event in events
        if event.waste_type != "Abfall"
    }
    filtered = [
        event
        for event in events
        if event.waste_type != "Abfall" or (event.date, event.street_id) not in specific
    ]
    return sorted(
        filtered, key=lambda event: (event.date, event.waste_type, event.street)
    )
