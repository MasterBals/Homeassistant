"""Parser for Chur Kultur agenda fragments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urljoin

from .const import SOURCE_URL

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class CultureEvent:
    """Single Chur Kultur event."""

    id: str
    title: str
    date: date
    url: str
    category: str = ""
    location: str = ""
    image: str = ""
    summary: str = ""
    description: str = ""

    def as_dict(self) -> dict[str, str]:
        """Return a serialisable representation."""
        return {**asdict(self), "date": self.date.isoformat()}


def clean_html(value: str) -> str:
    """Return compact plain text from an HTML snippet."""
    text = _TAG_RE.sub(" ", value)
    text = _SPACE_RE.sub(" ", unescape(text)).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", text)


def _attr(fragment: str, name: str) -> str:
    match = re.search(rf'{name}="([^"]*)"', fragment)
    return unescape(match.group(1)) if match else ""


def _class_text(fragment: str, class_name: str) -> str:
    match = re.search(
        rf'<[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>(.*?)</[^>]+>',
        fragment,
        flags=re.DOTALL,
    )
    return clean_html(match.group(1)) if match else ""


def _title(fragment: str) -> str:
    match = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", fragment, flags=re.DOTALL)
    return clean_html(match.group(1)) if match else ""


class _AgendaParser(HTMLParser):
    """Extract date groups and event cards from the agenda fragment."""

    def __init__(self) -> None:
        super().__init__()
        self.current_date: date | None = None
        self.events: list[CultureEvent] = []
        self._in_time = False
        self._capture_card = False
        self._card_depth = 0
        self._card_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        classes = attrs_dict.get("class", "")
        if tag == "time" and attrs_dict.get("datetime"):
            self.current_date = date.fromisoformat(attrs_dict["datetime"][:10])
            self._in_time = True
        if tag == "div" and "item-wide" in classes and attrs_dict.get("data-id"):
            self._capture_card = True
            self._card_depth = 1
            self._card_parts = [self.get_starttag_text() or ""]
            return
        if self._capture_card:
            self._card_depth += 1
            self._card_parts.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "time":
            self._in_time = False
        if self._capture_card:
            self._card_parts.append(f"</{tag}>")
            self._card_depth -= 1
            if self._card_depth == 0:
                self._append_card("".join(self._card_parts))
                self._capture_card = False

    def handle_data(self, data: str) -> None:
        if self._capture_card:
            self._card_parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._capture_card:
            self._card_parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._capture_card:
            self._card_parts.append(f"&#{name};")

    def _append_card(self, fragment: str) -> None:
        if self.current_date is None:
            return
        event_id = _attr(fragment, "data-id")
        href_match = re.search(r'<a[^>]+href="([^"]+)"', fragment)
        href = unescape(href_match.group(1)) if href_match else ""
        title = _title(fragment)
        if not event_id or not href or not title:
            return
        image = _attr(fragment, "data-imgsrc") or _attr(fragment, "src")
        self.events.append(
            CultureEvent(
                id=event_id,
                title=title,
                date=self.current_date,
                url=urljoin(SOURCE_URL, href),
                category=_class_text(fragment, "category"),
                location=_class_text(fragment, "location"),
                image=image.replace("{0}", "500")
                .replace("{1}", "300")
                .replace("{2}", "1"),
                summary=_class_text(fragment, "somethingelse"),
            )
        )


def parse_agenda_fragment(html: str) -> list[CultureEvent]:
    """Parse agenda search result HTML."""
    parser = _AgendaParser()
    parser.feed(html)
    return parser.events


def parse_detail_page(html: str) -> dict[str, str]:
    """Parse a detail page for popup-friendly content."""
    details: dict[str, str] = {}
    for key, prop in {
        "title": "og:title",
        "summary": "og:description",
        "image": "og:image",
    }.items():
        match = re.search(
            rf'<meta[^>]+property="{prop}"[^>]+content="([^"]*)"', html, re.DOTALL
        )
        if match:
            details[key] = clean_html(match.group(1))
    description = re.search(
        r'<span[^>]+itemprop="description"[^>]*>(.*?)</span>', html, re.DOTALL
    )
    if description:
        details["description"] = clean_html(description.group(1))
    location = re.search(r"<h3[^>]*>(.*?)</h3>", html, re.DOTALL)
    if location:
        details["location"] = clean_html(location.group(1))
    return details
