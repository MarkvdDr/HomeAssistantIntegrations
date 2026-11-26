/*
 * toon-program-card
 *
 * Lovelace card for the Toon Program integration: the week program of a Toon
 * thermostat as a heating landscape, with editing of days and presets.
 *
 * No build step and no dependencies. It is served by the integration and
 * loaded on every dashboard automatically.
 */

const CARD_VERSION = "1.1.0";

const PRESETS = ["comfort", "home", "sleep", "away", "holiday"];
// Toon day numbering: 0 = Sunday.
const DAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const SHORT_EN = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DEFAULT_COLORS = {
  comfort: "#f08a24",
  home: "#3fae6a",
  sleep: "#4a78d6",
  away: "#8f9bb3",
  holiday: "#19a7b8",
};

const I18N = {
  nl: {
    title: "Weekprogramma",
    presets: { comfort: "Comfort", home: "Thuis", sleep: "Slapen", away: "Weg", holiday: "Vakantie" },
    until: "tot {time}",
    then: "daarna {preset}",
    edit: "Bewerken",
    edit_day: "Dag bewerken",
    close: "Sluiten",
    save: "Opslaan",
    cancel: "Annuleren",
    saving: "Bezig met opslaan…",
    saved: "Opgeslagen op de Toon",
    add_block: "Blok toevoegen",
    remove_block: "Blok verwijderen",
    copy_to: "Ook toepassen op",
    carried: "Vanaf middernacht: {preset}, doorlopend van {day}",
    no_blocks: "Geen blokken: de vorige dag loopt de hele dag door.",
    temperatures: "Temperaturen",
    higher: "Warmer",
    lower: "Kouder",
    err_time: "Vul bij elk blok een tijd in.",
    err_dup: "Twee blokken beginnen op hetzelfde tijdstip.",
    unavailable: "Het weekprogramma is nu niet beschikbaar.",
    wrong_entity: "Kies de sensor “Weekprogramma” van Toon Program.",
    missing_entity: "Entiteit niet gevonden: {entity}",
    now: "Nu",
    start: "Begint om",
    preset: "Preset",
    editor: { entity: "Weekprogramma-sensor", title: "Titel", week_start: "Week begint op", editable: "Bewerken toestaan", show_legend: "Temperaturen tonen", monday: "Maandag", sunday: "Zondag" },
  },
  en: {
    title: "Week program",
    presets: { comfort: "Comfort", home: "Home", sleep: "Sleep", away: "Away", holiday: "Holiday" },
    until: "until {time}",
    then: "then {preset}",
    edit: "Edit",
    edit_day: "Edit day",
    close: "Close",
    save: "Save",
    cancel: "Cancel",
    saving: "Saving…",
    saved: "Saved to the Toon",
    add_block: "Add block",
    remove_block: "Remove block",
    copy_to: "Also apply to",
    carried: "From midnight: {preset}, continuing from {day}",
    no_blocks: "No blocks: the previous day continues all day.",
    temperatures: "Temperatures",
    higher: "Warmer",
    lower: "Colder",
    err_time: "Enter a time for every block.",
    err_dup: "Two blocks start at the same time.",
    unavailable: "The week program is not available right now.",
    wrong_entity: "Pick the “Week program” sensor of Toon Program.",
    missing_entity: "Entity not found: {entity}",
    now: "Now",
    start: "Starts at",
    preset: "Preset",
    editor: { entity: "Week program sensor", title: "Title", week_start: "Week starts on", editable: "Allow editing", show_legend: "Show temperatures", monday: "Monday", sunday: "Sunday" },
  },
};

const pad = (n) => String(n).padStart(2, "0");
const fmtMin = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
const toMin = (t) => {
  const [h, m] = String(t).split(":").map(Number);
  return h * 60 + m;
};
const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fill = (text, values) => text.replace(/\{(\w+)\}/g, (_, k) => (values[k] ?? ""));

const STYLE = `
  :host { display: block; }
  ha-card { padding: 16px; box-sizing: border-box; color: var(--primary-text-color); }
  * { box-sizing: border-box; }
  button { font: inherit; color: inherit; }
  button:focus-visible, select:focus-visible, input:focus-visible {
    outline: 2px solid var(--primary-color); outline-offset: 2px;
  }

  .head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
  .title { font-size: .875rem; color: var(--secondary-text-color); margin: 0 0 6px; font-weight: 400; }
  .now { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 12px; }
  .temp { font-size: 2.25rem; font-weight: 500; line-height: 1; font-variant-numeric: tabular-nums; color: var(--primary-text-color); }
  .preset { display: inline-flex; align-items: center; gap: 6px; font-size: 1.0625rem; color: var(--primary-text-color); }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
  .sub { margin-top: 6px; font-size: .875rem; color: var(--secondary-text-color); }
  .sub b { font-weight: 500; color: var(--primary-text-color); }
  .iconbtn {
    display: inline-flex; align-items: center; justify-content: center;
    width: 40px; height: 40px; border-radius: 50%; border: 0; padding: 0; cursor: pointer;
    background: transparent; color: var(--secondary-text-color); flex: none;
  }
  .iconbtn:hover { background: var(--divider-color); color: var(--primary-text-color); }
  .iconbtn[disabled] { opacity: .4; cursor: default; }

  .grid { margin-top: 18px; display: grid; grid-template-columns: 2.6em minmax(0, 1fr); gap: 5px 10px; }
  .dow { align-self: center; font-size: .8125rem; color: var(--secondary-text-color); }
  .dow.today { color: var(--primary-text-color); font-weight: 600; }
  .row {
    position: relative; display: block; width: 100%; height: 32px; padding: 0; border: 0; border-radius: 6px;
    overflow: hidden; text-align: left; background-color: color-mix(in srgb, var(--divider-color) 30%, transparent);
    background-image: linear-gradient(90deg, var(--divider-color) 0 1px, transparent 1px);
    background-size: 25% 100%; cursor: default;
  }
  button.row { cursor: pointer; }
  button.row:hover { box-shadow: 0 0 0 2px color-mix(in srgb, var(--primary-color) 55%, transparent); }
  .row[aria-current="true"] { box-shadow: 0 0 0 2px var(--primary-color); }
  .row.today { box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-text-color) 35%, transparent); }
  .seg { position: absolute; bottom: 0; border-radius: 3px 3px 0 0; border-left: 1px solid var(--ha-card-background, var(--card-background-color, #fff)); }
  .seg:first-of-type { border-left: 0; }
  .nowline { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; background: var(--primary-text-color); border-radius: 1px; pointer-events: none; }
  .nowline::before { content: ""; position: absolute; top: 0; left: -2px; width: 6px; height: 6px; border-radius: 50%; background: var(--primary-text-color); }
  .axis { position: relative; height: 1.1em; font-size: .6875rem; color: var(--secondary-text-color); font-variant-numeric: tabular-nums; }
  .axis span { position: absolute; transform: translateX(-50%); }
  .axis span:first-child { transform: none; }
  .axis span:last-child { transform: translateX(-100%); }

  .legend { margin-top: 14px; display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; }
  .legend .item { display: inline-flex; align-items: center; gap: 6px; font-size: .8125rem; color: var(--secondary-text-color); }
  .legend .item b { font-weight: 500; color: var(--primary-text-color); font-variant-numeric: tabular-nums; }
  .textbtn {
    display: inline-flex; align-items: center; gap: 4px; margin-left: auto; padding: 6px 10px; border: 0; border-radius: 8px;
    background: transparent; color: var(--primary-color); cursor: pointer; font-size: .8125rem; font-weight: 500;
  }
  .textbtn:hover { background: color-mix(in srgb, var(--primary-color) 12%, transparent); }

  .panel { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--divider-color); }
  .panel h3 { margin: 0; font-size: 1.0625rem; font-weight: 500; color: var(--primary-text-color); }
  .panel .top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
  .carried { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; font-size: .8125rem; color: var(--secondary-text-color); }
  .blocks { display: grid; gap: 8px; }
  .block { display: grid; grid-template-columns: auto minmax(7.5em, 10.5em) minmax(2.5em, 1fr) auto; gap: 4px; align-items: center; }
  .param { font-variant-numeric: tabular-nums; font-size: .875rem; color: var(--primary-text-color); }
  input.field[type="time"] { width: 7em; }
  .field {
    height: 40px; padding: 0 10px; border: 1px solid var(--divider-color); border-radius: 8px;
    background: var(--card-background-color, transparent); color: var(--primary-text-color); font: inherit; min-width: 0;
  }
  input.field { font-variant-numeric: tabular-nums; }
  .field.bad { border-color: var(--error-color, #db4437); }
  .selectwrap { position: relative; display: flex; align-items: center; min-width: 0; }
  .selectwrap .dot { position: absolute; left: 9px; pointer-events: none; }
  .selectwrap select { width: 100%; padding-left: 24px; }

  /* Fallback: stack when the measured row does not fit (JS sets .stacked). */
  .blocks.stacked .block {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas: "time del" "preset temp";
    gap: 6px 8px;
  }
  .blocks.stacked .block > input.field { grid-area: time; justify-self: start; }
  .blocks.stacked .block > .selectwrap { grid-area: preset; }
  .blocks.stacked .block > .param { grid-area: temp; justify-self: end; }
  .blocks.stacked .block > .iconbtn { grid-area: del; justify-self: end; }
  .hint { margin: 4px 0 0; font-size: .8125rem; color: var(--secondary-text-color); }
  .label { margin: 14px 0 6px; font-size: .8125rem; color: var(--secondary-text-color); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    min-width: 44px; height: 34px; padding: 0 10px; border-radius: 17px; cursor: pointer;
    border: 1px solid var(--divider-color); background: transparent; color: var(--primary-text-color); font-size: .8125rem;
  }
  .chip[aria-pressed="true"] { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .preview { margin-top: 14px; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
  .btn { height: 40px; padding: 0 18px; border-radius: 20px; border: 1px solid var(--divider-color); background: transparent; cursor: pointer; font-weight: 500; }
  .btn.primary { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
  .btn[disabled] { opacity: .5; cursor: default; }
  .status { min-height: 1.2em; margin-top: 10px; font-size: .875rem; color: var(--secondary-text-color); }
  .status.error { color: var(--error-color, #db4437); }
  .status.ok { color: var(--success-color, #43a047); }

  .steppers { display: grid; gap: 6px; }
  .stepper { display: grid; grid-template-columns: minmax(0, 1fr) auto auto auto; gap: 8px; align-items: center; }
  .stepper .name { display: inline-flex; align-items: center; gap: 8px; }
  .stepper .val { min-width: 4.2em; text-align: center; font-variant-numeric: tabular-nums; font-weight: 500; }
  .stepper .val.changed { color: var(--primary-color); }
  .message { padding: 8px 0; color: var(--secondary-text-color); }

  @media (prefers-reduced-motion: no-preference) {
    .row, .iconbtn, .textbtn, .chip, .btn { transition: background-color .12s, box-shadow .12s; }
  }
`;

class ToonProgramCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._edit = null; // {day, blocks:[{id,time,preset}], copy:Set, busy, error}
    this._temps = null; // {values:{preset:number}, busy, error}
    this._status = null; // {text, kind}
    this._lastState = null;
    this._nextId = 1;
    this._timer = null;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
  }

  // -- Lovelace API ---------------------------------------------------------

  static getConfigElement() {
    return document.createElement("toon-program-card-editor");
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass?.states ?? {}).find(
      (id) => id.startsWith("sensor.") && hass.states[id].attributes?.blocks && hass.states[id].attributes?.preset_temperatures,
    );
    return { entity: entity ?? "" };
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("Set `entity` to the week program sensor of Toon Program.");
    }
    this._config = {
      week_start: "monday",
      editable: true,
      show_legend: true,
      ...config,
    };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const state = hass.states?.[this._config?.entity];
    if (first || state !== this._lastState) {
      this._lastState = state;
      if (!this._edit && !this._temps) this._render();
    }
  }

  connectedCallback() {
    this._timer = setInterval(() => {
      if (!this._edit && !this._temps) this._render();
    }, 30000);
    this._ro = new ResizeObserver(() => this._fitRows());
    this._ro.observe(this);
  }

  /** Stack a block row only when the widest preset label would not fit next to the other columns. */
  _fitRows() {
    const wrap = this.shadowRoot && this.shadowRoot.querySelector(".blocks");
    if (!wrap) return;
    const block = wrap.querySelector(".block");
    const sel = block && block.querySelector("select");
    if (!sel) return;
    const time = block.querySelector('input[type="time"]');
    const param = block.querySelector(".param");
    const del = block.querySelector(".iconbtn");
    const selCs = getComputedStyle(sel);
    const size = parseFloat(selCs.fontSize) || 14;
    const canvas = (this._measureCanvas ||= document.createElement("canvas"));
    const ctx = canvas.getContext("2d");
    ctx.font = selCs.font || `${selCs.fontWeight} ${selCs.fontSize} ${selCs.fontFamily}`;
    let widest = 0;
    for (const option of sel.options) widest = Math.max(widest, ctx.measureText(option.textContent).width);
    const px = (el) => (el ? el.getBoundingClientRect().width : 0);
    // 52px covers the dot gutter, the native dropdown arrow and a small safety margin.
    const selectMin = Math.max(widest + 52, size * 7.5, 96);
    const need = px(time) + px(param) + px(del) + 12 + selectMin;
    if (!wrap.clientWidth) return;
    wrap.classList.toggle("stacked", wrap.clientWidth < need);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._timer = null;
    if (this._ro) {
      this._ro.disconnect();
      this._ro = null;
    }
  }

  getCardSize() {
    return this._edit ? 9 : 6;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  // -- Data -----------------------------------------------------------------

  get _lang() {
    return (this._hass?.locale?.language || this._hass?.language || "en").split("-")[0];
  }

  _t(key, values) {
    const table = I18N[this._lang] || I18N.en;
    const text = key.split(".").reduce((o, k) => o?.[k], table) ?? key.split(".").reduce((o, k) => o?.[k], I18N.en) ?? key;
    return values ? fill(text, values) : text;
  }

  _dayName(day, style = "short") {
    // 2024-01-07 is a Sunday: Toon day 0.
    const name = new Date(2024, 0, 7 + day).toLocaleDateString(this._lang, { weekday: style });
    return style === "long" ? name.charAt(0).toUpperCase() + name.slice(1) : name;
  }

  _color(preset) {
    return this._config?.colors?.[preset] || DEFAULT_COLORS[preset] || "var(--primary-color)";
  }

  _program() {
    const state = this._hass?.states?.[this._config.entity];
    if (!state) return { error: this._t("missing_entity", { entity: this._config.entity }) };
    const attrs = state.attributes || {};
    if (!attrs.blocks || !attrs.preset_temperatures) return { error: this._t("wrong_entity") };
    if (["unavailable", "unknown"].includes(state.state)) return { error: this._t("unavailable") };

    const blocks = attrs.blocks
      .map((b) => ({ day: DAYS.indexOf(b.day), min: toMin(b.time), preset: b.preset }))
      .filter((b) => b.day >= 0)
      .map((b) => ({ ...b, week: b.day * 1440 + b.min }))
      .sort((a, b) => a.week - b.week);
    if (!blocks.length) return { error: this._t("unavailable") };
    return {
      blocks,
      temps: attrs.preset_temperatures,
      entities: attrs.preset_entities || {},
      timezone: attrs.timezone || undefined,
    };
  }

  /** Segments {from, to, preset} that make up one day, including the part carried over from the day before. */
  _segments(blocks, day) {
    const dayStart = day * 1440;
    let active = null;
    for (const b of blocks) if (b.week <= dayStart) active = b;
    if (!active) active = blocks[blocks.length - 1];
    const segs = [];
    let cursor = 0;
    let current = active.preset;
    for (const b of blocks.filter((x) => x.day === day)) {
      if (b.min > cursor) segs.push({ from: cursor, to: b.min, preset: current });
      cursor = b.min;
      current = b.preset;
    }
    segs.push({ from: cursor, to: 1440, preset: current });
    return segs;
  }

  /** The block that continues into midnight of ``day`` when that day has no block of its own at 00:00. */
  _carried(blocks, day) {
    const others = blocks.filter((b) => b.day !== day);
    if (!others.length) return null;
    const dayStart = day * 1440;
    let found = null;
    for (const b of others) if (b.week < dayStart) found = b;
    return found || others[others.length - 1];
  }

  _clock(timezone) {
    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: timezone, weekday: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
      }).formatToParts(new Date());
      const get = (type) => parts.find((p) => p.type === type)?.value;
      const day = SHORT_EN.indexOf(get("weekday"));
      return { day, min: Number(get("hour")) * 60 + Number(get("minute")) };
    } catch (_err) {
      const now = new Date();
      return { day: now.getDay(), min: now.getHours() * 60 + now.getMinutes() };
    }
  }

  _temp(value) {
    if (value === undefined || value === null) return "–";
    return `${Number(value).toLocaleString(this._lang, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}°`;
  }

  // -- Rendering ------------------------------------------------------------

  /** Bar height in percent: the warmer the preset, the taller the bar. Only presets that are in use set the scale. */
  _heightFor(preset, temps) {
    const used = (this._usedPresets || PRESETS).map((p) => Number(temps[p])).filter((t) => isFinite(t));
    const lo = Math.min(...used);
    const hi = Math.max(...used);
    const t = Number(temps[preset]);
    if (!isFinite(t) || hi === lo) return 70;
    return Math.max(24, Math.min(100, 32 + (68 * (t - lo)) / (hi - lo)));
  }

  _rowHtml(segs, temps, extra = "") {
    const bars = segs
      .map((s) => {
        const left = (s.from / 1440) * 100;
        const width = ((s.to - s.from) / 1440) * 100;
        const label = `${fmtMin(s.from)}–${s.to === 1440 ? "24:00" : fmtMin(s.to)} · ${this._t(`presets.${s.preset}`)} · ${this._temp(temps[s.preset])}`;
        return `<span class="seg" title="${esc(label)}" style="left:${left}%;width:${width}%;height:${this._heightFor(s.preset, temps)}%;background:${this._color(s.preset)}"></span>`;
      })
      .join("");
    return bars + extra;
  }

  _render() {
    if (!this._config) return;
    const root = this.shadowRoot;
    const program = this._hass ? this._program() : { error: "…" };
    let body;
    if (program.error) {
      body = `<div class="message" role="status">${esc(program.error)}</div>`;
    } else {
      body = this._bodyHtml(program);
    }
    root.innerHTML = `<style>${STYLE}</style><ha-card>${body}</ha-card>`;
    this._fitRows();
  }

  _bodyHtml(program) {
    const { blocks, temps, timezone } = program;
    this._usedPresets = [...new Set(blocks.map((b) => b.preset))];
    const clock = this._clock(timezone);
    const editable = this._config.editable !== false;

    // Current state of the program
    const todaySegs = this._segments(blocks, clock.day);
    const active = todaySegs.find((s) => clock.min >= s.from && clock.min < s.to) || todaySegs[0];
    const nowWeek = clock.day * 1440 + clock.min;
    const next = blocks.find((b) => b.week > nowWeek) || blocks[0];
    const nextTime = next.day === clock.day && next.week > nowWeek ? fmtMin(next.min) : `${this._dayName(next.day)} ${fmtMin(next.min)}`;

    const title = this._config.title ?? this._t("title");
    const head = `
      <div class="head">
        <div>
          <p class="title">${esc(title)}</p>
          <div class="now">
            <span class="temp">${this._temp(temps[active.preset])}</span>
            <span class="preset"><span class="dot" style="background:${this._color(active.preset)}"></span>${esc(this._t(`presets.${active.preset}`))}</span>
          </div>
          <div class="sub"><b>${esc(this._t("until", { time: nextTime }))}</b>, ${esc(this._t("then", { preset: `${this._t(`presets.${next.preset}`)} ${this._temp(temps[next.preset])}` }))}</div>
        </div>
        ${editable && !this._edit && !this._temps ? `<button class="iconbtn" data-action="open-temps" aria-label="${esc(this._t("temperatures"))}" title="${esc(this._t("temperatures"))}"><ha-icon icon="mdi:thermometer"></ha-icon></button>` : ""}
      </div>`;

    // Week grid
    const order = this._config.week_start === "sunday" ? [0, 1, 2, 3, 4, 5, 6] : [1, 2, 3, 4, 5, 6, 0];
    const rows = order
      .map((day) => {
        const isToday = day === clock.day;
        const marker = isToday ? `<span class="nowline" style="left:${(clock.min / 1440) * 100}%" title="${esc(this._t("now"))} ${fmtMin(clock.min)}"></span>` : "";
        const selected = this._edit && this._edit.day === day;
        const inner = this._rowHtml(this._segments(blocks, day), temps, marker);
        const label = `<span class="dow ${isToday ? "today" : ""}">${esc(this._dayName(day))}</span>`;
        const cls = `row ${isToday ? "today" : ""}`;
        const cell = editable
          ? `<button class="${cls}" data-action="edit-day" data-day="${day}" aria-label="${esc(this._t("edit_day"))}: ${esc(this._dayName(day, "long"))}" ${selected ? 'aria-current="true"' : ""}>${inner}</button>`
          : `<div class="${cls}">${inner}</div>`;
        return label + cell;
      })
      .join("");
    const axis = `<span></span><div class="axis" aria-hidden="true">${[0, 6, 12, 18, 24].map((h) => `<span style="left:${(h / 24) * 100}%">${h}</span>`).join("")}</div>`;
    const grid = `<div class="grid">${rows}${axis}</div>`;

    // Legend
    let legend = "";
    if (this._config.show_legend !== false && !this._temps) {
      legend = `<div class="legend">${PRESETS.filter((p) => temps[p] !== undefined)
        .map((p) => `<span class="item"><span class="dot" style="background:${this._color(p)}"></span>${esc(this._t(`presets.${p}`))} <b>${this._temp(temps[p])}</b></span>`)
        .join("")}</div>`;
    }

    const status = this._status ? `<div class="status ${this._status.kind}" role="status" aria-live="polite">${esc(this._status.text)}</div>` : "";
    const panel = this._edit ? this._dayPanelHtml(program) : this._temps ? this._tempsPanelHtml(program) : "";
    return head + grid + legend + panel + (this._edit || this._temps ? "" : status);
  }

  _dayPanelHtml(program) {
    const edit = this._edit;
    const { blocks, temps } = program;
    const sorted = [...edit.blocks].sort((a, b) => toMin(a.time || "00:00") - toMin(b.time || "00:00"));
    const carried = this._carried(blocks, edit.day);
    const hasMidnight = edit.blocks.some((b) => b.time === "00:00");
    const prevDay = (edit.day + 6) % 7;

    const rows = edit.blocks
      .map((b) => {
        const dup = edit.blocks.filter((x) => x.time && x.time === b.time).length > 1;
        const options = PRESETS.map((p) => `<option value="${p}" ${p === b.preset ? "selected" : ""}>${esc(this._t(`presets.${p}`))}</option>`).join("");
        return `
          <div class="block">
            <input class="field ${!b.time || dup ? "bad" : ""}" type="time" step="60" value="${esc(b.time)}" data-field="time" data-id="${b.id}" aria-label="${esc(this._t("start"))}" ${edit.busy ? "disabled" : ""}>
            <span class="selectwrap"><span class="dot" style="background:${this._color(b.preset)}"></span>
              <select class="field" data-field="preset" data-id="${b.id}" aria-label="${esc(this._t("preset"))}" ${edit.busy ? "disabled" : ""}>${options}</select></span>
            <span class="param" aria-label="${esc(this._t("temperatures"))}">${this._temp(temps[b.preset])}</span>
            <button class="iconbtn" data-action="remove-block" data-id="${b.id}" aria-label="${esc(this._t("remove_block"))}" title="${esc(this._t("remove_block"))}" ${edit.busy ? "disabled" : ""}><ha-icon icon="mdi:delete-outline"></ha-icon></button>
          </div>`;
      })
      .join("");

    const carriedLine = carried && !hasMidnight
      ? `<p class="carried"><span class="dot" style="background:${this._color(carried.preset)}"></span>${esc(this._t("carried", { preset: this._t(`presets.${carried.preset}`), day: this._dayName(prevDay, "long").toLowerCase() }))}</p>`
      : "";

    const others = [1, 2, 3, 4, 5, 6, 0].filter((d) => d !== edit.day);
    const chips = others
      .map((d) => `<button class="chip" data-action="toggle-copy" data-day="${d}" aria-pressed="${edit.copy.has(d)}" aria-label="${esc(this._dayName(d, "long"))}" ${edit.busy ? "disabled" : ""}>${esc(this._dayName(d))}</button>`)
      .join("");

    // Preview of the day as it would be after saving
    const draft = this._draftBlocks(blocks, edit);
    const previewSegs = draft ? this._segments(draft, edit.day) : [];
    const preview = previewSegs.length ? `<div class="row preview" aria-hidden="true">${this._rowHtml(previewSegs, temps)}</div>` : "";

    return `
      <div class="panel">
        <div class="top"><h3>${esc(this._dayName(edit.day, "long"))}</h3>
          <button class="iconbtn" data-action="cancel" aria-label="${esc(this._t("close"))}" title="${esc(this._t("close"))}" ${edit.busy ? "disabled" : ""}><ha-icon icon="mdi:close"></ha-icon></button></div>
        ${carriedLine}
        <div class="blocks">${rows || `<p class="hint">${esc(this._t("no_blocks"))}</p>`}</div>
        <div class="actions" style="justify-content:flex-start"><button class="textbtn" style="margin-left:-10px" data-action="add-block" ${edit.busy ? "disabled" : ""}><ha-icon icon="mdi:plus"></ha-icon>${esc(this._t("add_block"))}</button></div>
        ${preview}
        <div class="label">${esc(this._t("copy_to"))}</div>
        <div class="chips">${chips}</div>
        <div class="status ${edit.error ? "error" : ""}" role="status" aria-live="polite">${esc(edit.error || (edit.busy ? this._t("saving") : ""))}</div>
        <div class="actions">
          <button class="btn" data-action="cancel" ${edit.busy ? "disabled" : ""}>${esc(this._t("cancel"))}</button>
          <button class="btn primary" data-action="save-day" ${edit.busy ? "disabled" : ""}>${esc(this._t("save"))}</button>
        </div>
      </div>`;
  }

  _tempsPanelHtml(program) {
    const t = this._temps;
    const rows = PRESETS.filter((p) => program.temps[p] !== undefined)
      .map((p) => {
        const changed = Number(t.values[p]) !== Number(program.temps[p]);
        return `
          <div class="stepper">
            <span class="name"><span class="dot" style="background:${this._color(p)}"></span>${esc(this._t(`presets.${p}`))}</span>
            <button class="iconbtn" data-action="step" data-preset="${p}" data-delta="-0.5" aria-label="${esc(this._t("lower"))}: ${esc(this._t(`presets.${p}`))}" ${t.busy ? "disabled" : ""}><ha-icon icon="mdi:minus"></ha-icon></button>
            <span class="val ${changed ? "changed" : ""}">${this._temp(t.values[p])}</span>
            <button class="iconbtn" data-action="step" data-preset="${p}" data-delta="0.5" aria-label="${esc(this._t("higher"))}: ${esc(this._t(`presets.${p}`))}" ${t.busy ? "disabled" : ""}><ha-icon icon="mdi:plus"></ha-icon></button>
          </div>`;
      })
      .join("");
    return `
      <div class="panel">
        <div class="top"><h3>${esc(this._t("temperatures"))}</h3></div>
        <div class="steppers">${rows}</div>
        <div class="status ${t.error ? "error" : ""}" role="status" aria-live="polite">${esc(t.error || (t.busy ? this._t("saving") : ""))}</div>
        <div class="actions">
          <button class="btn" data-action="cancel-temps" ${t.busy ? "disabled" : ""}>${esc(this._t("cancel"))}</button>
          <button class="btn primary" data-action="save-temps" ${t.busy ? "disabled" : ""}>${esc(this._t("save"))}</button>
        </div>
      </div>`;
  }

  // -- Editing --------------------------------------------------------------

  _draftBlocks(blocks, edit) {
    const valid = edit.blocks.filter((b) => /^\d{2}:\d{2}$/.test(b.time));
    const times = valid.map((b) => b.time);
    if (new Set(times).size !== times.length) return null;
    const others = blocks.filter((b) => b.day !== edit.day);
    const mine = valid.map((b) => ({ day: edit.day, min: toMin(b.time), preset: b.preset, week: edit.day * 1440 + toMin(b.time) }));
    const all = [...others, ...mine].sort((a, b) => a.week - b.week);
    return all.length ? all : null;
  }

  _openDay(day) {
    const program = this._program();
    if (program.error) return;
    this._status = null;
    this._temps = null;
    this._edit = {
      day,
      blocks: program.blocks.filter((b) => b.day === day).map((b) => ({ id: this._nextId++, time: fmtMin(b.min), preset: b.preset })),
      copy: new Set(),
      busy: false,
      error: "",
    };
    this._render();
  }

  _addBlock() {
    const edit = this._edit;
    const last = [...edit.blocks].map((b) => toMin(b.time || "00:00")).sort((a, b) => a - b).pop();
    const minutes = last === undefined ? 7 * 60 : Math.min(last + 60, 23 * 60 + 30);
    const lastBlock = [...edit.blocks].sort((a, b) => toMin(a.time) - toMin(b.time)).pop();
    edit.blocks.push({ id: this._nextId++, time: fmtMin(minutes), preset: lastBlock?.preset === "home" ? "away" : "home" });
    edit.error = "";
    this._render();
  }

  async _saveDay() {
    const edit = this._edit;
    const program = this._program();
    if (program.error) return;
    if (edit.blocks.some((b) => !/^\d{2}:\d{2}$/.test(b.time))) {
      edit.error = this._t("err_time");
      return this._render();
    }
    const times = edit.blocks.map((b) => b.time);
    if (new Set(times).size !== times.length) {
      edit.error = this._t("err_dup");
      return this._render();
    }
    const mine = [...edit.blocks].sort((a, b) => toMin(a.time) - toMin(b.time)).map((b) => ({ time: b.time, preset: b.preset }));
    edit.busy = true;
    edit.error = "";
    this._render();
    try {
      if (edit.copy.size === 0) {
        await this._hass.callService("toon_program", "set_day", { entity_id: this._config.entity, day: DAYS[edit.day], blocks: mine });
      } else {
        const targets = new Set([edit.day, ...edit.copy]);
        const all = program.blocks.filter((b) => !targets.has(b.day)).map((b) => ({ day: DAYS[b.day], time: fmtMin(b.min), preset: b.preset }));
        for (const day of targets) for (const b of mine) all.push({ day: DAYS[day], time: b.time, preset: b.preset });
        await this._hass.callService("toon_program", "set_schedule", { entity_id: this._config.entity, blocks: all });
      }
      this._edit = null;
      this._status = { text: this._t("saved"), kind: "ok" };
      this._render();
      setTimeout(() => {
        if (this._status?.kind === "ok") {
          this._status = null;
          if (!this._edit && !this._temps) this._render();
        }
      }, 4000);
    } catch (err) {
      edit.busy = false;
      edit.error = err?.message || String(err);
      this._render();
    }
  }

  _presetEntity(program, preset) {
    if (program.entities[preset]) return program.entities[preset];
    const entities = this._hass.entities || {};
    const self = entities[this._config.entity];
    return Object.keys(entities).find(
      (id) => id.startsWith("number.") && entities[id].platform === "toon_program" && entities[id].translation_key === `preset_${preset}` && (!self || entities[id].device_id === self.device_id),
    );
  }

  async _saveTemps() {
    const program = this._program();
    const t = this._temps;
    if (program.error) return;
    t.busy = true;
    t.error = "";
    this._render();
    try {
      for (const p of PRESETS) {
        if (program.temps[p] === undefined || Number(t.values[p]) === Number(program.temps[p])) continue;
        const entity_id = this._presetEntity(program, p);
        if (!entity_id) throw new Error(`No number entity for ${p}`);
        await this._hass.callService("number", "set_value", { entity_id, value: t.values[p] });
      }
      this._temps = null;
      this._status = { text: this._t("saved"), kind: "ok" };
      this._render();
      setTimeout(() => {
        if (this._status?.kind === "ok") {
          this._status = null;
          if (!this._edit && !this._temps) this._render();
        }
      }, 4000);
    } catch (err) {
      t.busy = false;
      t.error = err?.message || String(err);
      this._render();
    }
  }

  // -- Events ---------------------------------------------------------------

  _onClick(ev) {
    const el = ev.target.closest("[data-action]");
    if (!el || el.disabled) return;
    const { action, day, id, preset, delta } = el.dataset;
    switch (action) {
      case "edit-day":
        return this._openDay(Number(day));
      case "cancel":
        this._edit = null;
        return this._render();
      case "add-block":
        return this._addBlock();
      case "remove-block":
        this._edit.blocks = this._edit.blocks.filter((b) => String(b.id) !== id);
        return this._render();
      case "toggle-copy": {
        const d = Number(day);
        if (this._edit.copy.has(d)) this._edit.copy.delete(d);
        else this._edit.copy.add(d);
        return this._render();
      }
      case "save-day":
        return this._saveDay();
      case "open-temps": {
        const program = this._program();
        if (program.error) return;
        this._edit = null;
        this._status = null;
        this._temps = { values: { ...program.temps }, busy: false, error: "" };
        return this._render();
      }
      case "step": {
        const next = Math.round((Number(this._temps.values[preset]) + Number(delta)) * 2) / 2;
        this._temps.values[preset] = Math.min(30, Math.max(5, next));
        return this._render();
      }
      case "cancel-temps":
        this._temps = null;
        return this._render();
      case "save-temps":
        return this._saveTemps();
      default:
    }
  }

  _onChange(ev) {
    const el = ev.target;
    if (!this._edit || !el.dataset?.field) return;
    const block = this._edit.blocks.find((b) => String(b.id) === el.dataset.id);
    if (!block) return;
    if (el.dataset.field === "time") block.time = el.value;
    if (el.dataset.field === "preset") block.preset = el.value;
    this._edit.error = "";
    this._render();
  }
}

// ---------------------------------------------------------------------------
// Visual editor
// ---------------------------------------------------------------------------

class ToonProgramCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  _t(key) {
    const lang = (this._hass?.locale?.language || "en").split("-")[0];
    return (I18N[lang] || I18N.en).editor[key] ?? key;
  }

  _render() {
    if (!this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.addEventListener("value-changed", (ev) => {
        const config = { ...ev.detail.value };
        for (const key of Object.keys(config)) if (config[key] === "" || config[key] === undefined) delete config[key];
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { week_start: "monday", editable: true, show_legend: true, ...this._config };
    this._form.computeLabel = (schema) => this._t(schema.name);
    this._form.schema = [
      { name: "entity", required: true, selector: { entity: { domain: "sensor", integration: "toon_program" } } },
      { name: "title", selector: { text: {} } },
      {
        name: "week_start",
        selector: { select: { mode: "dropdown", options: [{ value: "monday", label: this._t("monday") }, { value: "sunday", label: this._t("sunday") }] } },
      },
      { name: "editable", selector: { boolean: {} } },
      { name: "show_legend", selector: { boolean: {} } },
    ];
  }
}

if (!customElements.get("toon-program-card")) {
  customElements.define("toon-program-card", ToonProgramCard);
  customElements.define("toon-program-card-editor", ToonProgramCardEditor);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "toon-program-card")) {
  window.customCards.push({
    type: "toon-program-card",
    name: "Toon Program",
    description: "Week program of a Toon thermostat as a heating landscape, with editing.",
    preview: true,
    documentationURL: "https://github.com/MarkvdDr/ToonThermostaatApps",
  });
}

console.info(`%c TOON-PROGRAM-CARD %c ${CARD_VERSION} `, "background:#18222e;color:#fff;border-radius:3px 0 0 3px", "background:#3fae6a;color:#fff;border-radius:0 3px 3px 0");
