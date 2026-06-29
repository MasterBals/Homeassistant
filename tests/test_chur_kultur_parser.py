"""Tests for the Chur Kultur parser."""

from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "custom_components.chur_kultur"

package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "custom_components/chur_kultur")]
sys.modules[PACKAGE] = package

for module_name in ("const", "parser"):
    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE}.{module_name}",
        ROOT / f"custom_components/chur_kultur/{module_name}.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

parse_agenda_fragment = sys.modules[f"{PACKAGE}.parser"].parse_agenda_fragment
parse_detail_page = sys.modules[f"{PACKAGE}.parser"].parse_detail_page


def test_parse_agenda_fragment_groups_events_by_date() -> None:
    html = """
    <section>
      <div class="sort-headline"><time datetime="2026-07-03">
        <span class="day">03</span><span class="month">Juli</span>
      </time></div>
      <div class="item-wide image favorite-holder" data-id="123">
        <a href="/de/agenda-extended/demo-chur_Aabc">
          <img data-imgsrc="https://ik.imagekit.io/guidle/tr:w-{0},h-{1},dpr-{2}/demo.jpg" />
          <p class="category">Konzert</p>
          <h5>Sommerkonzert</h5>
          <p class="location">Theater Chur</p>
        </a>
      </div>
    </section>
    """
    events = parse_agenda_fragment(html)
    assert len(events) == 1
    assert events[0].id == "123"
    assert events[0].title == "Sommerkonzert"
    assert events[0].date == date(2026, 7, 3)
    assert events[0].category == "Konzert"
    assert events[0].location == "Theater Chur"
    assert (
        events[0].url == "https://www.chur-kultur.ch/de/agenda-extended/demo-chur_Aabc"
    )
    assert "{0}" not in events[0].image


def test_parse_detail_page_extracts_popup_content() -> None:
    html = """
    <meta property="og:title" content="Sommerkonzert" />
    <meta property="og:description" content="Kurztext &amp; Zusatz" />
    <meta property="og:image" content="https://example.test/image.jpg" />
    <h3>Theater Chur, Chur</h3>
    <span itemprop="description">Langer <strong>Beschreibungstext</strong>.</span>
    """
    details = parse_detail_page(html)
    assert details == {
        "title": "Sommerkonzert",
        "summary": "Kurztext & Zusatz",
        "image": "https://example.test/image.jpg",
        "description": "Langer Beschreibungstext.",
        "location": "Theater Chur, Chur",
    }
