const DEFAULT_ENTITY = "sensor.chur_kultur_veranstaltungen";

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

const parseDate = (value) => {
  const [year, month, day] = String(value || "").slice(0, 10).split("-").map(Number);
  return year && month && day ? new Date(year, month - 1, day) : null;
};

const formatDate = (value) => {
  const date = parseDate(value);
  if (!date) return "";
  return new Intl.DateTimeFormat("de-CH", {
    weekday: "short",
    day: "2-digit",
    month: "long",
  }).format(date);
};

class ChurKulturCard extends HTMLElement {
  static async getConfigElement() {
    return document.createElement("chur-kultur-card-editor");
  }

  static getStubConfig(hass) {
    const entity =
      Object.keys(hass?.states || {}).find((id) => id === DEFAULT_ENTITY) ||
      Object.keys(hass?.states || {}).find((id) => id.startsWith("sensor.chur_kultur"));
    return {
      type: "custom:chur-kultur-card",
      entity,
      title: "Chur Kultur",
      max_items: 8,
      show_images: true,
    };
  }

  setConfig(config) {
    this.config = {
      entity: DEFAULT_ENTITY,
      title: "Chur Kultur",
      max_items: 8,
      show_images: true,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return Math.min(6, Math.max(2, Math.ceil(this.events().length / 2) + 1));
  }

  events() {
    const state = this._hass?.states?.[this.config?.entity];
    const events = Array.isArray(state?.attributes?.events) ? state.attributes.events : [];
    return events.slice(0, Number(this.config.max_items) || 8);
  }

  openDetails(index) {
    this._selected = this.events()[index];
    this.render();
  }

  closeDetails() {
    this._selected = undefined;
    this.render();
  }

  eventRow(event, index) {
    const image = this.config.show_images && event.image;
    return `<button class="event" data-index="${index}">
      ${image ? `<img src="${escapeHtml(event.image)}" alt="">` : `<ha-icon icon="mdi:calendar-star"></ha-icon>`}
      <span class="event-body">
        <span class="date">${escapeHtml(formatDate(event.date))}</span>
        <span class="name">${escapeHtml(event.title)}</span>
        <span class="meta">${escapeHtml([event.category, event.location].filter(Boolean).join(" · "))}</span>
      </span>
    </button>`;
  }

  popup() {
    const event = this._selected;
    if (!event) return "";
    const description = event.description || event.summary || "";
    return `<div class="overlay" data-close="true">
      <article class="dialog">
        <button class="close" data-close="true" aria-label="Schliessen"><ha-icon icon="mdi:close"></ha-icon></button>
        ${event.image ? `<img class="hero-img" src="${escapeHtml(event.image)}" alt="">` : ""}
        <div class="dialog-body">
          <div class="date">${escapeHtml(formatDate(event.date))}</div>
          <h2>${escapeHtml(event.title)}</h2>
          ${event.location ? `<p class="location"><ha-icon icon="mdi:map-marker"></ha-icon>${escapeHtml(event.location)}</p>` : ""}
          ${event.category ? `<p class="chip">${escapeHtml(event.category)}</p>` : ""}
          ${description ? `<p class="description">${escapeHtml(description)}</p>` : ""}
          <a class="more" href="${escapeHtml(event.url)}" target="_blank" rel="noreferrer">Auf chur-kultur.ch öffnen</a>
        </div>
      </article>
    </div>`;
  }

  render() {
    if (!this._hass || !this.config) return;
    const state = this._hass.states[this.config.entity];
    const events = this.events();
    const days = state?.attributes?.days;
    this.innerHTML = `<ha-card><style>
      .wrap{padding:18px;color:var(--primary-text-color)}
      .top{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:14px}
      .title{font-size:1.08rem;font-weight:800}
      .sub{font-size:.82rem;color:var(--secondary-text-color);text-align:right}
      .list{display:grid;gap:10px}
      .event{width:100%;display:grid;grid-template-columns:72px 1fr;gap:12px;align-items:center;text-align:left;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);border-radius:14px;padding:10px;cursor:pointer}
      .event:hover{border-color:var(--primary-color);background:rgba(var(--rgb-primary-color),.06)}
      .event img,.event ha-icon{width:72px;height:54px;border-radius:10px;object-fit:cover;background:rgba(var(--rgb-primary-color),.08)}
      .event ha-icon{display:grid;place-items:center;color:var(--primary-color);--mdc-icon-size:32px}
      .event-body{display:grid;gap:2px;min-width:0}
      .date{font-size:.78rem;font-weight:800;text-transform:uppercase;color:var(--primary-color)}
      .name{font-size:1rem;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .meta{font-size:.86rem;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .empty{display:flex;align-items:center;gap:12px;color:var(--secondary-text-color);padding:18px 4px}
      .empty ha-icon{color:var(--primary-color);--mdc-icon-size:34px}
      .overlay{position:fixed;inset:0;z-index:20;background:rgba(0,0,0,.45);display:grid;place-items:center;padding:18px}
      .dialog{width:min(560px,100%);max-height:min(720px,90vh);overflow:auto;border-radius:18px;background:var(--card-background-color);box-shadow:0 24px 80px rgba(0,0,0,.35);position:relative}
      .close{position:absolute;right:10px;top:10px;border:0;border-radius:999px;background:rgba(0,0,0,.55);color:white;width:40px;height:40px;display:grid;place-items:center;cursor:pointer}
      .hero-img{width:100%;height:220px;object-fit:cover;display:block}
      .dialog-body{padding:18px}
      h2{font-size:1.35rem;line-height:1.18;margin:4px 0 12px}
      .location{display:flex;gap:6px;align-items:center;color:var(--secondary-text-color);margin:0 0 10px}
      .location ha-icon{--mdc-icon-size:18px}
      .chip{display:inline-block;border-radius:999px;padding:5px 10px;background:rgba(var(--rgb-primary-color),.1);color:var(--primary-color);font-weight:700;font-size:.82rem;margin:0 0 12px}
      .description{line-height:1.5;color:var(--primary-text-color)}
      .more{display:inline-flex;margin-top:10px;color:var(--primary-color);font-weight:800;text-decoration:none}
      @media(max-width:460px){.wrap{padding:14px}.event{grid-template-columns:56px 1fr}.event img,.event ha-icon{width:56px;height:48px}.hero-img{height:170px}}
    </style><div class="wrap">
      <div class="top"><div class="title">${escapeHtml(this.config.title)}</div><div class="sub">${days ? `${escapeHtml(days)} Tage` : ""}${state ? ` · ${escapeHtml(state.state)} Treffer` : ""}</div></div>
      ${events.length ? `<div class="list">${events.map((event, index) => this.eventRow(event, index)).join("")}</div>` : `<div class="empty"><ha-icon icon="mdi:calendar-search"></ha-icon><div>Keine passenden Veranstaltungen gefunden.</div></div>`}
    </div>${this.popup()}</ha-card>`;

    this.querySelectorAll(".event").forEach((button) => {
      button.addEventListener("click", () => this.openDetails(Number(button.dataset.index)));
    });
    this.querySelectorAll("[data-close]").forEach((element) => {
      element.addEventListener("click", (event) => {
        if (event.target === element || element.classList.contains("close")) {
          this.closeDetails();
        }
      });
    });
  }
}

class ChurKulturCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      entity: DEFAULT_ENTITY,
      title: "Chur Kultur",
      max_items: 8,
      show_images: true,
      ...config,
    };
    this.render();
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  updateConfig(changes) {
    this._config = { ...this._config, ...changes };
    this.dispatchEvent(
      new CustomEvent("config-changed", {
        detail: { config: this._config },
        bubbles: true,
        composed: true,
      })
    );
    this.render();
  }

  render() {
    if (!this._config) return;
    this.innerHTML = `<style>
      .editor{display:grid;gap:16px;padding:8px 0}
      .field{display:grid;gap:6px}.label{font-weight:600}
      .row{display:flex;align-items:center;gap:8px}
    </style><div class="editor">
      <div class="field"><div class="label">Entität</div><ha-entity-picker allow-custom-entity></ha-entity-picker></div>
      <div class="field"><div class="label">Titel</div><ha-textfield></ha-textfield></div>
      <div class="field"><div class="label">Anzahl Einträge</div><ha-textfield type="number"></ha-textfield></div>
      <label class="row"><ha-switch ${this._config.show_images ? "checked" : ""}></ha-switch><span>Bilder anzeigen</span></label>
    </div>`;
    const picker = this.querySelector("ha-entity-picker");
    if (picker) {
      picker.hass = this._hass;
      picker.value = this._config.entity || "";
      picker.includeDomains = ["sensor"];
      picker.addEventListener("value-changed", (event) => this.updateConfig({ entity: event.detail.value }));
    }
    const [title, maxItems] = this.querySelectorAll("ha-textfield");
    if (title) {
      title.value = this._config.title || "";
      title.addEventListener("input", (event) => this.updateConfig({ title: event.target.value }));
    }
    if (maxItems) {
      maxItems.value = String(this._config.max_items || 8);
      maxItems.addEventListener("input", (event) => this.updateConfig({ max_items: Number(event.target.value) || 8 }));
    }
    const toggle = this.querySelector("ha-switch");
    if (toggle) {
      toggle.addEventListener("change", () => this.updateConfig({ show_images: toggle.checked }));
    }
  }
}

customElements.define("chur-kultur-card", ChurKulturCard);
customElements.define("chur-kultur-card-editor", ChurKulturCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "chur-kultur-card",
  name: "Chur Kultur Card",
  description: "Gefilterte Chur-Kultur-Veranstaltungen mit Detail-Popup",
});
