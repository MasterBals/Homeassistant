const CHUR_ABFALL_TYPES = ["Karton", "Papier", "Kompost", "Kehricht"];
const CHUR_ABFALL_META = {
  karton: {
    label: "Karton",
    icon: "mdi:package-variant-closed",
    color: "#b7791f",
    accent: "#fff3d8",
  },
  papier: {
    label: "Papier",
    icon: "mdi:newspaper-variant-multiple-outline",
    color: "#2563eb",
    accent: "#e0ecff",
  },
  kompost: {
    label: "Kompost",
    icon: "mdi:leaf-circle-outline",
    color: "#15803d",
    accent: "#def7e6",
  },
  kehricht: {
    label: "Kehricht",
    icon: "mdi:trash-can-outline",
    color: "#475569",
    accent: "#e9eef5",
  },
  abfall: {
    label: "Abfall",
    icon: "mdi:recycle",
    color: "var(--primary-color)",
    accent: "rgba(var(--rgb-primary-color), 0.12)",
  },
};

const normalizeWasteType = (value) => {
  const text = String(value || "").toLowerCase();
  if (text.includes("karton")) return "karton";
  if (text.includes("papier")) return "papier";
  if (text.includes("kompost") || text.includes("grün")) return "kompost";
  if (text.includes("kehricht") || text.includes("hauskehricht")) return "kehricht";
  return "abfall";
};

const metaForType = (type) => CHUR_ABFALL_META[normalizeWasteType(type)] || CHUR_ABFALL_META.abfall;

const parseLocalDate = (value) => {
  if (!value) return null;
  const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
};

const daysUntil = (value) => {
  const target = parseLocalDate(value);
  if (!target) return undefined;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86400000);
};

const dateWithoutYear = (value) => {
  const date = parseLocalDate(value);
  if (!date) return "";
  return new Intl.DateTimeFormat("de-CH", { day: "2-digit", month: "long" }).format(date);
};

const relativeDate = (event) => {
  const days = Number.isFinite(event.days) ? event.days : daysUntil(event.date);
  if (days === 0) return "Heute";
  if (days === 1) return "Morgen";
  if (days === 2) return "in zwei Tagen";
  if (days === 3) return "in drei Tagen";
  if (days === 4) return "in vier Tagen";
  return dateWithoutYear(event.date);
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

class ChurAbfallCard extends HTMLElement {
  static async getConfigElement() {
    return document.createElement("chur-abfall-card-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass?.states || {}).find(
      (entityId) =>
        entityId === "sensor.chur_abfall_nachste_abfuhr" ||
        entityId.startsWith("sensor.chur_abfall_nachste_")
    );
    return {
      type: "custom:chur-abfall-card",
      entity,
      title: "Chur Abfall",
      waste_types: ["Karton", "Papier", "Kompost"],
      animate: true,
    };
  }

  setConfig(config) {
    this.config = {
      title: "Chur Abfall",
      entity: undefined,
      waste_types: CHUR_ABFALL_TYPES,
      animate: true,
      compact: false,
      show_street: true,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return this.config?.compact ? 3 : 4;
  }

  getEvents() {
    const states = this._hass?.states || {};
    const configured = this.config?.entity ? states[this.config.entity] : undefined;
    const sources = [];
    if (configured) sources.push(configured);
    Object.entries(states).forEach(([entityId, state]) => {
      if (
        entityId.startsWith("sensor.chur_abfall_") &&
        Array.isArray(state.attributes?.next_events) &&
        state !== configured
      ) {
        sources.push(state);
      }
    });

    const selected = new Set(
      (this.config?.waste_types || CHUR_ABFALL_TYPES).map((type) => normalizeWasteType(type))
    );
    const seen = new Set();
    const events = [];

    sources.forEach((state) => {
      (state.attributes?.next_events || []).forEach((event) => {
        const typeKey = normalizeWasteType(event.waste_type);
        if (!selected.has(typeKey)) return;
        const days = Number.isFinite(event.days) ? event.days : daysUntil(event.date);
        if (!event.date || days < 0) return;
        const key = `${event.date}|${typeKey}|${event.street_id || event.street || ""}`;
        if (seen.has(key)) return;
        seen.add(key);
        events.push({
          ...event,
          days,
          typeKey,
          sortDate: parseLocalDate(event.date)?.getTime() || 0,
        });
      });
    });

    return events.sort((a, b) => a.sortDate - b.sortDate || a.typeKey.localeCompare(b.typeKey));
  }

  nextByType(events) {
    const grouped = new Map();
    events.forEach((event) => {
      if (!grouped.has(event.typeKey)) grouped.set(event.typeKey, event);
    });
    return [...grouped.values()].sort((a, b) => a.sortDate - b.sortDate);
  }

  renderHero(event) {
    const meta = metaForType(event.waste_type);
    const urgent = event.days <= 1 ? " urgent" : "";
    const animation = this.config.animate ? " animated" : "";
    return `
      <section class="hero${urgent}${animation}" style="--type-color:${meta.color};--type-accent:${meta.accent}">
        <div class="hero-icon"><ha-icon icon="${meta.icon}"></ha-icon></div>
        <div class="hero-copy">
          <div class="eyebrow">Nächste Abfuhr</div>
          <div class="hero-title">${escapeHtml(meta.label)}</div>
          <div class="hero-date">${escapeHtml(relativeDate(event))}</div>
          ${this.config.show_street && event.street ? `<div class="street">${escapeHtml(event.street)}</div>` : ""}
        </div>
      </section>`;
  }

  renderTypeTile(event, isHero) {
    const meta = metaForType(event.waste_type);
    return `
      <div class="type-tile${isHero ? " current" : ""}" style="--type-color:${meta.color};--type-accent:${meta.accent}">
        <div class="tile-icon"><ha-icon icon="${meta.icon}"></ha-icon></div>
        <div class="tile-body">
          <div class="tile-name">${escapeHtml(meta.label)}</div>
          <div class="tile-date">${escapeHtml(isHero ? relativeDate(event) : dateWithoutYear(event.date))}</div>
        </div>
      </div>`;
  }

  render() {
    if (!this._hass || !this.config) return;
    const events = this.getEvents();
    const hero = events[0];
    const tiles = this.nextByType(events);

    this.innerHTML = `<ha-card><style>
      .wrap{padding:18px;color:var(--primary-text-color)}
      .header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
      .card-title{font-size:1.05rem;font-weight:700;line-height:1.2}
      .selected{color:var(--secondary-text-color);font-size:.82rem;text-align:right}
      .hero{display:grid;grid-template-columns:86px 1fr;gap:16px;align-items:center;padding:18px;border-radius:18px;background:linear-gradient(135deg,var(--type-accent),var(--card-background-color));border:1px solid color-mix(in srgb,var(--type-color) 32%,var(--divider-color));overflow:hidden;position:relative}
      .hero:after{content:"";position:absolute;inset:auto -40px -58px auto;width:140px;height:140px;border-radius:999px;background:var(--type-color);opacity:.08}
      .hero-icon{width:76px;height:76px;border-radius:22px;display:grid;place-items:center;background:var(--type-color);color:white;box-shadow:0 12px 24px color-mix(in srgb,var(--type-color) 24%,transparent)}
      .hero-icon ha-icon{--mdc-icon-size:44px}
      .animated .hero-icon ha-icon{animation:floaty 2.8s ease-in-out infinite}
      .urgent.animated .hero-icon{animation:attention 1.6s ease-in-out infinite}
      .eyebrow{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--secondary-text-color);font-weight:700}
      .hero-title{font-size:1.25rem;font-weight:800;margin-top:2px}
      .hero-date{font-size:2rem;font-weight:900;line-height:1.05;margin-top:2px;color:var(--type-color)}
      .street{margin-top:6px;color:var(--secondary-text-color);font-size:.9rem}
      .tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}
      .type-tile{display:grid;grid-template-columns:42px 1fr;align-items:center;gap:10px;padding:10px;border-radius:14px;background:var(--card-background-color);border:1px solid var(--divider-color)}
      .type-tile.current{border-color:color-mix(in srgb,var(--type-color) 46%,var(--divider-color));background:var(--type-accent)}
      .tile-icon{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;background:color-mix(in srgb,var(--type-color) 14%,transparent);color:var(--type-color)}
      .tile-icon ha-icon{--mdc-icon-size:24px}
      .tile-name{font-weight:700;font-size:.92rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .tile-date{font-size:.86rem;color:var(--secondary-text-color);margin-top:1px}
      .empty{display:flex;align-items:center;gap:14px;padding:18px;color:var(--secondary-text-color)}
      .empty ha-icon{--mdc-icon-size:34px;color:var(--primary-color)}
      @keyframes floaty{0%,100%{transform:translateY(0) rotate(0deg)}50%{transform:translateY(-3px) rotate(-5deg)}}
      @keyframes attention{0%,100%{transform:scale(1)}50%{transform:scale(1.06)}}
      @media(max-width:460px){.wrap{padding:14px}.hero{grid-template-columns:64px 1fr;padding:14px}.hero-icon{width:58px;height:58px;border-radius:18px}.hero-icon ha-icon{--mdc-icon-size:34px}.hero-date{font-size:1.55rem}.tiles{grid-template-columns:1fr}}
    </style><div class="wrap">
      <div class="header">
        <div class="card-title">${escapeHtml(this.config.title)}</div>
        <div class="selected">${escapeHtml((this.config.waste_types || CHUR_ABFALL_TYPES).join(" · "))}</div>
      </div>
      ${hero ? this.renderHero(hero) : `<div class="empty"><ha-icon icon="mdi:calendar-alert"></ha-icon><div><b>Keine Termine</b><br>Prüfe Entität und ausgewählte Arten.</div></div>`}
      ${tiles.length ? `<div class="tiles">${tiles.map((event) => this.renderTypeTile(event, hero && event.typeKey === hero.typeKey)).join("")}</div>` : ""}
    </div></ha-card>`;
  }
}

class ChurAbfallCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = {
      title: "Chur Abfall",
      waste_types: CHUR_ABFALL_TYPES,
      animate: true,
      show_street: true,
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
    const selected = new Set(this._config.waste_types || CHUR_ABFALL_TYPES);
    this.innerHTML = `<style>
      .editor{display:grid;gap:16px;padding:8px 0}
      .field{display:grid;gap:6px}.label{font-weight:600;color:var(--primary-text-color)}
      .types{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
      .type-option{display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--divider-color);border-radius:10px}
      .toggles{display:grid;gap:8px}
    </style><div class="editor">
      <div class="field"><div class="label">Entität mit Terminen</div><ha-entity-picker allow-custom-entity></ha-entity-picker></div>
      <div class="field"><div class="label">Titel</div><ha-textfield></ha-textfield></div>
      <div class="field"><div class="label">Anzeigen</div><div class="types">${CHUR_ABFALL_TYPES.map((type) => `<label class="type-option"><ha-checkbox data-type="${type}" ${selected.has(type) ? "checked" : ""}></ha-checkbox><span>${type}</span></label>`).join("")}</div></div>
      <div class="toggles">
        <label class="type-option"><ha-switch data-key="animate" ${this._config.animate ? "checked" : ""}></ha-switch><span>Animationen</span></label>
        <label class="type-option"><ha-switch data-key="show_street" ${this._config.show_street ? "checked" : ""}></ha-switch><span>Strasse anzeigen</span></label>
        <label class="type-option"><ha-switch data-key="compact" ${this._config.compact ? "checked" : ""}></ha-switch><span>Kompakt</span></label>
      </div>
    </div>`;

    const picker = this.querySelector("ha-entity-picker");
    if (picker) {
      picker.hass = this._hass;
      picker.value = this._config.entity || "";
      picker.includeDomains = ["sensor"];
      picker.addEventListener("value-changed", (event) => {
        this.updateConfig({ entity: event.detail.value });
      });
    }

    const title = this.querySelector("ha-textfield");
    if (title) {
      title.value = this._config.title || "";
      title.addEventListener("input", (event) => {
        this.updateConfig({ title: event.target.value });
      });
    }

    this.querySelectorAll("ha-checkbox[data-type]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const next = new Set(this._config.waste_types || CHUR_ABFALL_TYPES);
        if (checkbox.checked) next.add(checkbox.dataset.type);
        else next.delete(checkbox.dataset.type);
        this.updateConfig({ waste_types: [...next] });
      });
    });

    this.querySelectorAll("ha-switch[data-key]").forEach((toggle) => {
      toggle.addEventListener("change", () => {
        this.updateConfig({ [toggle.dataset.key]: toggle.checked });
      });
    });
  }
}

customElements.define("chur-abfall-card", ChurAbfallCard);
customElements.define("chur-abfall-card-editor", ChurAbfallCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "chur-abfall-card",
  name: "Chur Abfall Card",
  description: "Animierte Karte für Churer Abfalltermine mit visueller Auswahl der Entsorgungsarten",
});
