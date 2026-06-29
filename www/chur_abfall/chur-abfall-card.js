class ChurAbfallCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error('entity is required');
    this.config = {title: 'Chur Abfall', compact: false, show_countdown: true, show_timeline: true, timeline_items: 5, animate: true, icon_size: 44, ...config};
  }
  set hass(hass) { this._hass = hass; this.render(); }
  getCardSize() { return this.config?.compact ? 2 : 4; }
  countdown(days) { if (days === 0) return 'Heute'; if (days === 1) return 'Morgen'; return `in ${days} Tagen`; }
  icon(type) { const t=(type||'').toLowerCase(); if(t.includes('papier')) return 'mdi:newspaper'; if(t.includes('karton')) return 'mdi:package-variant'; if(t.includes('kompost')||t.includes('grün')) return 'mdi:leaf'; if(t.includes('kehricht')) return 'mdi:trash-can'; return 'mdi:recycle'; }
  color(type) { const t=(type||'').toLowerCase(); if(t.includes('papier')) return '#3f7dd5'; if(t.includes('karton')) return '#b7791f'; if(t.includes('kompost')||t.includes('grün')) return '#2f855a'; if(t.includes('kehricht')) return '#4a5568'; return 'var(--primary-color)'; }
  render() {
    if (!this._hass || !this.config) return;
    const state = this._hass.states[this.config.entity];
    const attrs = state?.attributes || {};
    const events = (attrs.next_events || []).slice(0, this.config.timeline_items);
    const type = events[0]?.waste_type || attrs.waste_type || 'Abfall';
    const days = attrs.days ?? events[0]?.days;
    const animate = this.config.animate && (days === 0 || days === 1) ? 'pulse' : '';
    this.innerHTML = `<ha-card><style>
      .wrap{padding:18px;color:var(--primary-text-color)} .head{display:flex;gap:16px;align-items:center}.badge{width:${this.config.icon_size}px;height:${this.config.icon_size}px;border-radius:18px;display:grid;place-items:center;background:${this.color(type)}22;color:${this.color(type)}}
      ha-icon{--mdc-icon-size:${Math.max(24, this.config.icon_size-12)}px}.title{font-size:1.05rem;font-weight:600}.date{font-size:1.7rem;font-weight:700;margin-top:2px}.muted{color:var(--secondary-text-color)}.count{margin-top:6px;display:inline-flex;padding:5px 10px;border-radius:999px;background:var(--primary-color);color:var(--text-primary-color);font-weight:600}.timeline{margin-top:18px;display:grid;gap:8px}.row{display:grid;grid-template-columns:36px 1fr auto;align-items:center;padding:10px;border-radius:16px;background:var(--ha-card-background,var(--card-background-color));border:1px solid var(--divider-color)}.row ha-icon{--mdc-icon-size:22px}.pulse{animation:pulse 1.6s ease-in-out 2}@keyframes pulse{50%{transform:scale(1.035);filter:brightness(1.08)}}@media(max-width:420px){.date{font-size:1.35rem}.wrap{padding:14px}}
    </style><div class="wrap ${animate}"><div class="head"><div class="badge"><ha-icon icon="${this.icon(type)}"></ha-icon></div><div><div class="title">${this.config.title}</div><div class="date">${attrs.swiss_date || state?.state || 'Keine Termine'}</div><div class="muted">${attrs.weekday || ''} ${attrs.street ? ' · '+attrs.street : ''}</div>${this.config.show_countdown && days !== undefined ? `<div class="count">${this.countdown(days)}</div>` : ''}</div></div>${this.config.show_timeline ? `<div class="timeline">${events.map(e => `<div class="row"><ha-icon style="color:${this.color(e.waste_type)}" icon="${this.icon(e.waste_type)}"></ha-icon><div><b>${e.waste_type}</b><div class="muted">${e.street || ''}</div></div><div><b>${new Date(e.date).toLocaleDateString('de-CH')}</b><div class="muted">${this.countdown(e.days)}</div></div></div>`).join('')}</div>` : ''}</div></ha-card>`;
  }
}
customElements.define('chur-abfall-card', ChurAbfallCard);
window.customCards = window.customCards || [];
window.customCards.push({type: 'chur-abfall-card', name: 'Chur Abfall Card', description: 'Native Karte für Churer Abfalltermine'});
