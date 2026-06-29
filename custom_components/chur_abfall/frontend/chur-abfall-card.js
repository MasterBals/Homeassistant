const TYPES = ["Karton", "Papier", "Kompost", "Kehricht"];
const ASSET_BASE = "/chur_abfall_static/assets";
const ASSET_VERSION = "1.0.5";
const META = {
  karton: { label: "Karton", icon: "mdi:package-variant-closed", asset: `${ASSET_BASE}/karton.svg?v=${ASSET_VERSION}`, color: "#b7791f", accent: "#fff3d8" },
  papier: { label: "Papier", icon: "mdi:newspaper-variant-multiple-outline", asset: `${ASSET_BASE}/papier.svg?v=${ASSET_VERSION}`, color: "#2563eb", accent: "#e0ecff" },
  kompost: { label: "Kompost", icon: "mdi:leaf-circle-outline", asset: `${ASSET_BASE}/kompost.svg?v=${ASSET_VERSION}`, color: "#15803d", accent: "#def7e6" },
  kehricht: { label: "Kehricht", icon: "mdi:trash-can-outline", asset: `${ASSET_BASE}/kehricht.svg?v=${ASSET_VERSION}`, color: "#475569", accent: "#e9eef5" },
  abfall: { label: "Abfall", icon: "mdi:recycle", asset: "", color: "var(--primary-color)", accent: "rgba(var(--rgb-primary-color), .12)" },
};

const keyFor = (value) => {
  const text = String(value || "").toLowerCase();
  if (text.includes("karton")) return "karton";
  if (text.includes("papier")) return "papier";
  if (text.includes("kompost") || text.includes("grün")) return "kompost";
  if (text.includes("kehricht") || text.includes("hauskehricht")) return "kehricht";
  return "abfall";
};
const metaFor = (value) => META[keyFor(value)] || META.abfall;
const localDate = (value) => {
  const [year, month, day] = String(value || "").slice(0, 10).split("-").map(Number);
  return year && month && day ? new Date(year, month - 1, day) : null;
};
const daysUntil = (value) => {
  const target = localDate(value);
  if (!target) return undefined;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target.getTime() - today.getTime()) / 86400000);
};
const dateText = (value) => {
  const date = localDate(value);
  return date ? new Intl.DateTimeFormat("de-CH", { day: "2-digit", month: "long" }).format(date) : "";
};
const relativeText = (event) => {
  const days = Number.isFinite(event.days) ? event.days : daysUntil(event.date);
  if (days === 0) return "Heute";
  if (days === 1) return "Morgen";
  if (days === 2) return "in zwei Tagen";
  if (days === 3) return "in drei Tagen";
  if (days === 4) return "in vier Tagen";
  return dateText(event.date);
};
const esc = (value) => String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const art = (meta, klass) => meta.asset ? `<img class="art ${klass}" src="${meta.asset}" alt="${esc(meta.label)}" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false"><ha-icon class="fallback" icon="${meta.icon}" hidden></ha-icon>` : `<ha-icon class="fallback" icon="${meta.icon}"></ha-icon>`;

class ChurAbfallCard extends HTMLElement {
  static async getConfigElement() { return document.createElement("chur-abfall-card-editor"); }
  static getStubConfig(hass) {
    const entity = Object.keys(hass?.states || {}).find((id) => id === "sensor.chur_abfall_nachste_abfuhr" || id.startsWith("sensor.chur_abfall_nachste_"));
    return { type: "custom:chur-abfall-card", entity, title: "Chur Abfall", waste_types: TYPES, animate: true, show_street: true };
  }
  setConfig(config) {
    this.config = { title: "Chur Abfall", entity: undefined, waste_types: TYPES, animate: true, compact: false, show_street: true, ...config };
  }
  set hass(hass) { this._hass = hass; this.render(); }
  getCardSize() { return this.config?.compact ? 3 : 4; }
  events() {
    const states = this._hass?.states || {};
    const configured = this.config?.entity ? states[this.config.entity] : undefined;
    const sources = configured ? [configured] : [];
    Object.entries(states).forEach(([id, state]) => {
      if (id.startsWith("sensor.chur_abfall_") && Array.isArray(state.attributes?.next_events) && state !== configured) sources.push(state);
    });
    const selected = new Set((this.config?.waste_types || TYPES).map(keyFor));
    const seen = new Set();
    const result = [];
    sources.forEach((state) => (state.attributes?.next_events || []).forEach((event) => {
      const typeKey = keyFor(event.waste_type || event.type || state.attributes?.friendly_name);
      const numericDays = Number(event.days);
      const days = Number.isFinite(numericDays) ? numericDays : daysUntil(event.date);
      if (!selected.has(typeKey) || !event.date || !Number.isFinite(days) || days < 0) return;
      const key = `${event.date}|${typeKey}|${event.street_id || event.street || ""}`;
      if (seen.has(key)) return;
      seen.add(key);
      result.push({ ...event, days, typeKey, sortDate: localDate(event.date)?.getTime() || 0, waste_type: event.waste_type || META[typeKey]?.label });
    }));
    return result.sort((a, b) => a.sortDate - b.sortDate || a.typeKey.localeCompare(b.typeKey));
  }
  byType(events) {
    const grouped = new Map();
    events.forEach((event) => { if (!grouped.has(event.typeKey)) grouped.set(event.typeKey, event); });
    return [...grouped.values()].sort((a, b) => a.sortDate - b.sortDate);
  }
  hero(event) {
    const meta = metaFor(event.waste_type);
    return `<section class="hero ${this.config.animate ? "animated" : ""} ${event.days <= 1 ? "urgent" : ""}" style="--c:${meta.color};--a:${meta.accent}">
      <div class="hero-art">${art(meta, "hero-img")}</div>
      <div><div class="eyebrow">Nächste Abfuhr</div><div class="hero-name">${esc(meta.label)}</div><div class="hero-date">${esc(relativeText(event))}</div>${this.config.show_street && event.street ? `<div class="street">${esc(event.street)}</div>` : ""}</div>
    </section>`;
  }
  tile(event, current) {
    const meta = metaFor(event.waste_type);
    return `<div class="tile ${current ? "current" : ""}" style="--c:${meta.color};--a:${meta.accent}"><div class="tile-art">${art(meta, "tile-img")}</div><div><div class="tile-name">${esc(meta.label)}</div><div class="tile-date">${esc(current ? relativeText(event) : dateText(event.date))}</div></div></div>`;
  }
  render() {
    if (!this._hass || !this.config) return;
    const events = this.events();
    const hero = events[0];
    const tiles = this.byType(events);
    this.innerHTML = `<ha-card><style>
      .wrap{padding:18px;color:var(--primary-text-color)}.top{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.title{font-size:1.05rem;font-weight:700}.selected{font-size:.82rem;color:var(--secondary-text-color);text-align:right}
      .hero{display:grid;grid-template-columns:112px 1fr;gap:16px;align-items:center;padding:18px;border-radius:18px;background:linear-gradient(135deg,var(--a),var(--card-background-color));border:1px solid color-mix(in srgb,var(--c) 32%,var(--divider-color));overflow:hidden}.hero-art{width:106px;height:96px;display:grid;place-items:center;filter:drop-shadow(0 12px 12px color-mix(in srgb,var(--c) 18%,transparent))}.art{width:100%;height:100%;object-fit:contain}.fallback{color:var(--c);--mdc-icon-size:42px}.eyebrow{font-size:.78rem;text-transform:uppercase;color:var(--secondary-text-color);font-weight:700}.hero-name{font-size:1.25rem;font-weight:800}.hero-date{font-size:2rem;font-weight:900;line-height:1.05;color:var(--c)}.street{margin-top:6px;color:var(--secondary-text-color);font-size:.9rem}
      .tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px}.tile{display:grid;grid-template-columns:52px 1fr;align-items:center;gap:10px;padding:10px;border-radius:14px;background:var(--card-background-color);border:1px solid var(--divider-color)}.tile.current{border-color:color-mix(in srgb,var(--c) 46%,var(--divider-color));background:var(--a)}.tile-art{width:48px;height:42px;display:grid;place-items:center;filter:drop-shadow(0 6px 6px color-mix(in srgb,var(--c) 12%,transparent))}.tile-name{font-weight:700;font-size:.92rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tile-date{font-size:.86rem;color:var(--secondary-text-color);margin-top:1px}.empty{display:flex;align-items:center;gap:14px;padding:18px;color:var(--secondary-text-color)}.empty ha-icon{--mdc-icon-size:34px;color:var(--primary-color)}
      @media(max-width:460px){.wrap{padding:14px}.hero{grid-template-columns:78px 1fr;padding:14px}.hero-art{width:74px;height:68px}.hero-date{font-size:1.55rem}.tiles{grid-template-columns:1fr}}
    </style><div class="wrap"><div class="top"><div class="title">${esc(this.config.title)}</div><div class="selected">${esc((this.config.waste_types || TYPES).join(" · "))}</div></div>${hero ? this.hero(hero) : `<div class="empty"><ha-icon icon="mdi:calendar-alert"></ha-icon><div><b>Keine Termine</b><br>Prüfe Entität und ausgewählte Arten.</div></div>`}${tiles.length ? `<div class="tiles">${tiles.map((event) => this.tile(event, hero && event.typeKey === hero.typeKey)).join("")}</div>` : ""}</div></ha-card>`;
  }
}

class ChurAbfallCardEditor extends HTMLElement {
  setConfig(config) { this._config = { title: "Chur Abfall", waste_types: TYPES, animate: true, show_street: true, ...config }; this.render(); }
  set hass(hass) { this._hass = hass; this.render(); }
  updateConfig(changes) { this._config = { ...this._config, ...changes }; this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true })); this.render(); }
  render() {
    if (!this._config) return;
    const selected = new Set((this._config.waste_types || TYPES).map(keyFor));
    this.innerHTML = `<style>.editor{display:grid;gap:16px;padding:8px 0}.field{display:grid;gap:6px}.label{font-weight:600}.types{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}.row{display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--divider-color);border-radius:10px}.toggles{display:grid;gap:8px}</style><div class="editor"><div class="field"><div class="label">Entität mit Terminen</div><ha-entity-picker allow-custom-entity></ha-entity-picker></div><div class="field"><div class="label">Titel</div><ha-textfield></ha-textfield></div><div class="field"><div class="label">Anzeigen</div><div class="types">${TYPES.map((type) => `<label class="row"><ha-checkbox data-type="${type}" ${selected.has(keyFor(type)) ? "checked" : ""}></ha-checkbox><span>${type}</span></label>`).join("")}</div></div><div class="toggles"><label class="row"><ha-switch data-key="animate" ${this._config.animate ? "checked" : ""}></ha-switch><span>Animationen</span></label><label class="row"><ha-switch data-key="show_street" ${this._config.show_street ? "checked" : ""}></ha-switch><span>Strasse anzeigen</span></label><label class="row"><ha-switch data-key="compact" ${this._config.compact ? "checked" : ""}></ha-switch><span>Kompakt</span></label></div></div>`;
    const picker = this.querySelector("ha-entity-picker");
    if (picker) { picker.hass = this._hass; picker.value = this._config.entity || ""; picker.includeDomains = ["sensor"]; picker.addEventListener("value-changed", (event) => this.updateConfig({ entity: event.detail.value })); }
    const title = this.querySelector("ha-textfield");
    if (title) { title.value = this._config.title || ""; title.addEventListener("input", (event) => this.updateConfig({ title: event.target.value })); }
    this.querySelectorAll("ha-checkbox[data-type]").forEach((checkbox) => checkbox.addEventListener("change", () => {
      const next = new Set((this._config.waste_types || TYPES).map(keyFor));
      const typeKey = keyFor(checkbox.dataset.type);
      if (checkbox.checked) next.add(typeKey); else next.delete(typeKey);
      this.updateConfig({ waste_types: TYPES.filter((type) => next.has(keyFor(type))) });
    }));
    this.querySelectorAll("ha-switch[data-key]").forEach((toggle) => toggle.addEventListener("change", () => this.updateConfig({ [toggle.dataset.key]: toggle.checked })));
  }
}

customElements.define("chur-abfall-card", ChurAbfallCard);
customElements.define("chur-abfall-card-editor", ChurAbfallCardEditor);
window.customCards = window.customCards || [];
window.customCards.push({ type: "chur-abfall-card", name: "Chur Abfall Card", description: "Animierte Karte für Churer Abfalltermine mit visueller Auswahl der Entsorgungsarten" });
