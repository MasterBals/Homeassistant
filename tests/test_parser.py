"""Tests for the Chur Abfall parser."""

from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import sys

_SPEC = importlib.util.spec_from_file_location(
    "chur_parser",
    Path(__file__).resolve().parents[1] / "custom_components/chur_abfall/parser.py",
)
assert _SPEC and _SPEC.loader
parser = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = parser
_SPEC.loader.exec_module(parser)
Street = parser.Street
parse_events = parser.parse_events
parse_streets = parser.parse_streets


def test_parse_streets_from_options() -> None:
    html = '<select><option value="12"> Bahnhofstrasse </option></select>'
    assert parse_streets(html) == [Street(id="12", name="Bahnhofstrasse")]


def test_parse_events_prefers_data_order() -> None:
    streets = [Street(id="12", name="Bahnhofstrasse")]
    html = '<tr data-street-id="12"><td data-order="2026-07-01">01.07.2026</td><td>Papier Bahnhofstrasse</td></tr>'
    events = parse_events(html, streets, today=date(2026, 6, 29))
    assert len(events) == 1
    assert events[0].date == date(2026, 7, 1)
    assert events[0].waste_type == "Papier"


def test_parse_events_filters_past() -> None:
    streets = [Street(id="12", name="Bahnhofstrasse")]
    html = '<div data-street-id="12">Kehricht Bahnhofstrasse 01.01.2026</div>'
    assert parse_events(html, streets, today=date(2026, 6, 29)) == []
