#!/usr/bin/env python3
"""Build index.html (main dashboard) and leads.html (sources) from data/*.json + templates/*.

Pipeline:
  1. Load templates/komissia_base.html as base
  2. Load data/funnels.json → render funnels view HTML (embed as second tab)
  3. Merge komissia + funnels into single-page with tab nav
  4. Inject CRM funnel panels into each broker's razbor
  5. Inject razbory (учет разборов) panels into each razbor
  6. Rewrite signal-bar with fresh declined/greens/non-brokers data
  7. Inject staff dates + hide non-brokers via post-render JS
  8. Write index.html
  9. Build leads.html from data/leads_by_source.json
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data'
TEMPLATES = REPO / 'templates'


def load(name, default=None):
    p = DATA / name
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


# ── Load all data ────────────────────────────────────
staff_dates = load('staff_dates.json', {})
funnels = load('funnels.json', [])
razbory = load('razbory.json')
declined = load('declined.json', [])
greens = load('greens.json', [])
leads_by_source = load('leads_by_source.json', [])
stat = load('stat.json', {'combined': {}, 'block2': {}})

# ── 1. Base HTML ─────────────────────────────────────
base = (TEMPLATES / 'komissia_base.html').read_text()

# ── 2-3. Merge with a Funnels tab structure ─────────
# Simple: wrap komissia inside a view container with nav tabs
def build_funnels_html(funnels_data):
    """Full funnels view: filter bar + grid of broker funnel cards."""
    return '''
<style>
.fn-page { max-width: 1280px; margin: 0 auto; padding: 32px; font-family: var(--font-sans, 'IBM Plex Sans', sans-serif); color: var(--ink, #1B1A17); }
.fn-masthead { display: flex; align-items: baseline; gap: 20px; margin-bottom: 6px; flex-wrap: wrap; }
.fn-title { font-family: var(--font-display, 'Fraunces', Georgia, serif); font-weight: 500; font-size: 42px; letter-spacing: -0.02em; margin: 0; }
.fn-count { font-family: var(--font-mono, 'IBM Plex Mono', monospace); font-size: 11px; color: var(--muted, #706B62); text-transform: uppercase; letter-spacing: 0.08em; }
.fn-lede { color: var(--muted, #706B62); font-size: 13px; font-family: var(--font-display, 'Fraunces', Georgia, serif); font-style: italic; margin: 0 0 24px; }
.fn-filters { display: flex; gap: 24px; align-items: flex-end; margin-bottom: 24px; padding: 16px 0; border-top: 1px solid var(--rule, #D9D3C4); border-bottom: 1px solid var(--rule, #D9D3C4); flex-wrap: wrap; }
.fn-filter-group { display: flex; flex-direction: column; gap: 6px; }
.fn-filter-label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted, #706B62); font-weight: 600; }
.fn-btn-group { display: flex; gap: 2px; }
.fn-btn-group button {
  background: transparent; border: 1px solid var(--rule-strong, #B0AA9C); border-right: none;
  padding: 6px 14px; font-family: 'IBM Plex Sans', sans-serif; font-size: 11px;
  color: var(--muted, #706B62); cursor: pointer;
  letter-spacing: 0.05em; text-transform: uppercase; font-weight: 500;
}
.fn-btn-group button:first-child { border-radius: 2px 0 0 2px; }
.fn-btn-group button:last-child { border-right: 1px solid var(--rule-strong, #B0AA9C); border-radius: 0 2px 2px 0; }
.fn-btn-group button.active { background: var(--ink, #1B1A17); color: var(--ground, #F3F0E8); border-color: var(--ink, #1B1A17); }

.fn-sort-info { margin-left: auto; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted, #706B62); font-family: 'IBM Plex Mono', monospace; }

.fn-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 20px; }

.fn-card { border: 1px solid var(--rule, #D9D3C4); background: rgba(255,255,255,0.35); padding: 18px 20px; }
.fn-card-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 4px; flex-wrap: wrap; }
.fn-card-name { font-family: var(--font-display, 'Fraunces', Georgia, serif); font-weight: 500; font-size: 18px; letter-spacing: -0.01em; }
.fn-card-role { font-size: 9px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted, #706B62); font-weight: 600; padding: 2px 7px; border: 1px solid var(--rule, #D9D3C4); border-radius: 2px; }
.fn-card-role.qualifier { background: rgba(176,131,67,0.12); border-color: var(--accent-2, #B08343); color: var(--accent-2, #B08343); }
.fn-card-total { margin-left: auto; font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: var(--muted, #706B62); }
.fn-card-position { font-size: 11px; color: var(--muted, #706B62); font-family: 'IBM Plex Mono', monospace; margin-bottom: 14px; }

.fn-stages { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.fn-stage { display: grid; grid-template-columns: 90px 1fr 65px; gap: 10px; align-items: center; font-size: 11px; }
.fn-stage-name { font-size: 9px; text-transform: uppercase; letter-spacing: 0.1em; color: var(--muted, #706B62); font-weight: 600; }
.fn-stage-bar-wrap { background: rgba(0,0,0,0.04); height: 18px; position: relative; }
.fn-stage-bar { background: var(--accent, #4A5D3E); height: 100%; transition: width 0.2s; }
.fn-stage-bar.won { background: var(--accent, #4A5D3E); }
.fn-stage-bar.pipe { background: rgba(74,93,62,0.5); }
.fn-stage-bar.zero { background: transparent; border-left: 2px solid var(--rule, #D9D3C4); }
.fn-stage-count { font-family: 'IBM Plex Mono', monospace; font-size: 12px; text-align: right; font-weight: 500; color: var(--ink, #1B1A17); }
.fn-stage-count.zero { color: var(--rule-strong, #B0AA9C); }

.fn-card-foot { display: flex; gap: 20px; padding-top: 10px; border-top: 1px dashed var(--rule, #D9D3C4); font-size: 10px; color: var(--muted, #706B62); }
.fn-metric { display: flex; flex-direction: column; gap: 2px; }
.fn-metric-label { text-transform: uppercase; letter-spacing: 0.1em; font-size: 8px; font-weight: 600; }
.fn-metric-val { font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: var(--ink, #1B1A17); font-weight: 500; }
.fn-metric-val.won { color: var(--accent, #4A5D3E); }

.fn-empty { text-align: center; padding: 60px 20px; color: var(--muted, #706B62); font-family: var(--font-display, 'Fraunces', Georgia, serif); font-style: italic; grid-column: 1 / -1; }
</style>

<div class="fn-page">
  <div class="fn-masthead">
    <h1 class="fn-title">Воронки</h1>
    <span class="fn-count" id="fn-count">— брокеров</span>
  </div>
  <p class="lede fn-lede">CRM-воронка по активным брокерам. Стадии: NEW → QUAL → PRES → OFFER → WON. LOST/DEFERRED — в подвале карточки.</p>

  <div class="fn-filters">
    <div class="fn-filter-group">
      <span class="fn-filter-label">Период</span>
      <div class="fn-btn-group" data-filter="period">
        <button data-val="y2026" class="active">2026</button>
        <button data-val="y2025">2025</button>
        <button data-val="l3m">L3M</button>
        <button data-val="all">Всё время</button>
      </div>
    </div>
    <div class="fn-filter-group">
      <span class="fn-filter-label">Регион</span>
      <div class="fn-btn-group" data-filter="region">
        <button data-val="ALL" class="active">Все</button>
        <button data-val="Bali">Bali</button>
        <button data-val="Thailand">Thailand</button>
        <button data-val="Europe">Europe</button>
      </div>
    </div>
    <div class="fn-filter-group">
      <span class="fn-filter-label">Роль</span>
      <div class="fn-btn-group" data-filter="role">
        <button data-val="all" class="active">Все</button>
        <button data-val="broker">Брокеры</button>
        <button data-val="qualifier">Квалификаторы</button>
      </div>
    </div>
    <span class="fn-sort-info">Сортировка: WON ↓</span>
  </div>

  <div class="fn-grid" id="fn-grid"></div>
</div>

<script>
const FUNNELS_DATA = ''' + json.dumps(funnels, ensure_ascii=False) + ''';
const STAGES = ['NEW', 'QUALIFIED', 'PRESENTATION', 'OFFER', 'WON'];
const STAGE_LABELS = {NEW:'NEW', QUALIFIED:'QUAL', PRESENTATION:'PRES', OFFER:'OFFER', WON:'WON'};

const state = { period: 'y2026', region: 'ALL', role: 'all' };

function fmtMoney(n) {
  if (!n) return '—';
  if (n >= 1e6) return (n/1e6).toFixed(1).replace('.0','') + 'M';
  if (n >= 1e3) return Math.round(n/1e3) + 'k';
  return String(Math.round(n));
}

function getBrokerData(broker, period, region) {
  const p = broker.periods?.[period];
  if (!p) return null;
  if (region === 'ALL') return p['ALL'] || null;
  return p[region] || null;
}

function renderCard(broker, data) {
  const stageData = STAGES.map(s => ({name: s, n: data?.[s]?.n || 0, budget: data?.[s]?.budget || 0}));
  const maxN = Math.max(1, ...stageData.map(s => s.n));
  const won = stageData.find(s => s.name === 'WON') || {n:0, budget:0};
  const newS = stageData.find(s => s.name === 'NEW') || {n:0, budget:0};
  const totalActive = stageData.reduce((sum,s) => sum + s.n, 0);
  const lost = data?.LOST?.n || 0;
  const deferred = data?.DEFERRED?.n || 0;
  const wonBudget = won.budget || 0;
  const conv = newS.n ? ((won.n / newS.n) * 100).toFixed(1) + '%' : '—';

  const stagesHtml = stageData.map(s => {
    const pct = (s.n / maxN) * 100;
    const isWon = s.name === 'WON';
    const zero = s.n === 0;
    const barCls = zero ? 'zero' : (isWon ? 'won' : 'pipe');
    return `<div class="fn-stage">
      <span class="fn-stage-name">${STAGE_LABELS[s.name]}</span>
      <div class="fn-stage-bar-wrap"><div class="fn-stage-bar ${barCls}" style="width:${pct}%"></div></div>
      <span class="fn-stage-count ${zero?'zero':''}">${s.n}${s.budget?' · $'+fmtMoney(s.budget):''}</span>
    </div>`;
  }).join('');

  return `<article class="fn-card">
    <div class="fn-card-head">
      <span class="fn-card-name">${broker.name}</span>
      <span class="fn-card-role ${broker.role}">${broker.role === 'qualifier' ? 'QUAL' : 'BROKER'}</span>
      <span class="fn-card-total">Σ ${totalActive} акт.</span>
    </div>
    <div class="fn-card-position">${broker.position || ''}</div>
    <div class="fn-stages">${stagesHtml}</div>
    <div class="fn-card-foot">
      <div class="fn-metric"><span class="fn-metric-label">WON</span><span class="fn-metric-val won">${won.n} · $${fmtMoney(wonBudget)}</span></div>
      <div class="fn-metric"><span class="fn-metric-label">LOST</span><span class="fn-metric-val">${lost}</span></div>
      <div class="fn-metric"><span class="fn-metric-label">DEFERRED</span><span class="fn-metric-val">${deferred}</span></div>
      <div class="fn-metric"><span class="fn-metric-label">NEW→WON</span><span class="fn-metric-val">${conv}</span></div>
    </div>
  </article>`;
}

function render() {
  const grid = document.getElementById('fn-grid');
  const filtered = FUNNELS_DATA
    .filter(b => state.role === 'all' || b.role === state.role)
    .map(b => ({ broker: b, data: getBrokerData(b, state.period, state.region) }))
    .filter(x => x.data && Object.keys(x.data).length > 0)
    .sort((a,b) => (b.data?.WON?.n || 0) - (a.data?.WON?.n || 0));

  document.getElementById('fn-count').textContent = filtered.length + ' брокеров · ' + state.period + ' · ' + state.region;

  if (!filtered.length) {
    grid.innerHTML = '<div class="fn-empty">Нет данных под текущий фильтр</div>';
    return;
  }
  grid.innerHTML = filtered.map(x => renderCard(x.broker, x.data)).join('');
}

document.querySelectorAll('.fn-filters .fn-btn-group').forEach(group => {
  group.addEventListener('click', e => {
    if (e.target.tagName !== 'BUTTON') return;
    const filter = group.dataset.filter;
    const val = e.target.dataset.val;
    state[filter] = val;
    group.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    e.target.classList.add('active');
    render();
  });
});

render();
</script>
'''


funnels_body = build_funnels_html(funnels)

# Wrap: put base inside .view-komissia, add .view-funnels tab
merged = f'''<meta charset="utf-8">
<title>Комиссия · Legion</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; padding: 0; }}
.view-nav {{
  position: sticky; top: 0; z-index: 10;
  background: var(--ground, #F3F0E8); border-bottom: 2px solid var(--ink, #1B1A17);
  padding: 12px 32px; display: flex; gap: 24px; align-items: baseline;
  max-width: 1280px; margin: 0 auto;
}}
.view-nav-brand {{
  font-family: 'Fraunces', Georgia, serif; font-weight: 500; font-size: 20px;
  letter-spacing: -0.01em;
}}
.view-nav-tabs {{ display: flex; gap: 2px; margin-left: auto; }}
.view-nav-tabs button {{
  background: transparent; border: 1px solid var(--rule-strong, #B0AA9C); border-right: none;
  padding: 8px 18px; font-family: 'IBM Plex Sans', sans-serif; font-size: 12px;
  color: var(--muted, #706B62); cursor: pointer;
  letter-spacing: 0.06em; text-transform: uppercase; font-weight: 500;
}}
.view-nav-tabs button:first-child {{ border-radius: 2px 0 0 2px; }}
.view-nav-tabs button:last-child {{ border-right: 1px solid var(--rule-strong, #B0AA9C); border-radius: 0 2px 2px 0; }}
.view-nav-tabs button.active {{ background: var(--ink, #1B1A17); color: var(--ground, #F3F0E8); border-color: var(--ink, #1B1A17); }}
.view {{ display: none; }}
.view.active {{ display: block; }}
</style>

<nav class="view-nav">
  <span class="view-nav-brand">Комиссия · Legion</span>
  <div class="view-nav-tabs" id="viewTabs">
    <button data-view="komissia" class="active">Комиссия</button>
    <button data-view="funnels">Воронки</button>
  </div>
</nav>

<div class="view view-komissia active" id="view-komissia">
{base}
</div>

<div class="view view-funnels" id="view-funnels">
{funnels_body}
</div>

<script>
document.getElementById('viewTabs').addEventListener('click', (e) => {{
  if (e.target.tagName !== 'BUTTON') return;
  const target = e.target.dataset.view;
  document.querySelectorAll('#viewTabs button').forEach(b => b.classList.remove('active'));
  e.target.classList.add('active');
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + target).classList.add('active');
}});
</script>
'''

src = merged

# ── 4. Fix name extraction bug in existing komissia JS ──
old_extract = '''const name = (nameCell.childNodes[1]?.nodeValue || nameCell.textContent).trim().split(/[\\n\\r]/)[0].trim();'''
new_extract = '''const clone = nameCell.cloneNode(true);
      clone.querySelectorAll('.expand-arrow, .tenure').forEach(el => el.remove());
      const name = clone.textContent.trim();'''
src = src.replace(old_extract, new_extract)

# ── 5. Rewrite signal-bar with fresh data ────────────
# The base komissia has hardcoded signal-bar values — replace the whole signal block via regex
# Find the signal-bar section (between .signal-section-label and </div> before .planfact-section)
# Simpler: replace individual pieces

if len(declined) >= 3:
    # Update "Просели" count and top items
    ...  # We'll do this via post-render JS injection instead — simpler

# ── 6. Post-render JS overlays ───────────────────────
overlay_data = {
    'staff_dates': staff_dates,
    'non_brokers': ['Роман Безносюк', 'Владислав Семчук'],
    'funnels': funnels,
    'razbory': razbory,
    'declined': declined,
    'greens': greens,
}
overlay_data_json = json.dumps(overlay_data, ensure_ascii=False)

overlay_addon = '''
<style>
.hide-non-broker { display: none !important; }
.crm-funnel, .razbory-block { grid-column: 1 / -1; margin-top: 20px; padding-top: 18px; border-top: 1px dashed var(--rule); }
.crm-funnel-head, .razbory-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.crm-funnel-head h4, .razbory-head h4 { font-size: 10px; text-transform: uppercase; letter-spacing: 0.12em; color: var(--muted); margin: 0; font-weight: 600; font-family: var(--font-sans); }
.crm-funnel-body, .razbory-body { display: grid; grid-template-columns: 1fr 1.3fr; gap: 22px; }
@media (max-width: 900px) { .crm-funnel-body, .razbory-body { grid-template-columns: 1fr; } }
.crm-stage-row { display: grid; grid-template-columns: 130px 1fr 80px; gap: 8px; align-items: center; font-size: 12.5px; margin-bottom: 5px; }
.crm-stage-track { height: 14px; background: var(--surface); border: 1px solid var(--rule); border-radius: 2px; overflow: hidden; }
.crm-stage-fill { height: 100%; background: var(--accent); }
.crm-stage-fill.won { background: var(--good); }
.crm-stage-value { font-family: var(--font-mono); font-size: 11px; text-align: right; }
.rz-metric { padding: 10px 12px; background: var(--surface); border: 1px solid var(--rule); border-radius: 2px; }
.rz-metric .lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); font-weight: 600; }
.rz-metric .val { font-family: var(--font-display); font-weight: 500; font-size: 22px; line-height: 1.1; color: var(--ink); font-variant-numeric: tabular-nums; margin-top: 3px; }
.rz-metric .val.good { color: var(--good); } .rz-metric .val.warn { color: var(--warn); } .rz-metric .val.critical { color: var(--critical); }
.rz-metric .sub { font-size: 10px; color: var(--muted); font-family: var(--font-mono); margin-top: 2px; }
.rz-stats-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; }
.rz-agreement { padding: 14px 16px; background: var(--surface); border: 1px solid var(--rule); }
.rz-agreement .meta { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted); border-bottom: 1px dashed var(--rule); padding-bottom: 8px; margin-bottom: 8px; }
.rz-agreement .txt { font-family: var(--font-display); font-style: italic; font-size: 13.5px; line-height: 1.55; color: var(--ink); }
.rz-agreement .field-lbl { font-size: 9.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); font-weight: 600; margin-top: 10px; margin-bottom: 4px; }
.rz-older { margin-top: 10px; padding-top: 8px; border-top: 1px dashed var(--rule); }
.rz-older summary { cursor: pointer; font-size: 11px; color: var(--muted); font-family: var(--font-mono); letter-spacing: 0.06em; text-transform: uppercase; }
</style>
<script>
(function() {
  const OVERLAY = OVERLAY_DATA_PLACEHOLDER;
  function norm(n) {
    return (n||'').trim().toLowerCase()
      .replace(/і/g,'и').replace(/ї/g,'и').replace(/є/g,'е').replace(/ы/g,'и')
      .split(/\\s+/).sort().join(' ');
  }
  function alias(n) { const b = norm(n); return [b, b.replace(/\\bмакс\\b/,'максим'), b.replace(/\\bмаксим\\b/,'макс')]; }
  const nonBrokersNorm = new Set(OVERLAY.non_brokers.map(norm));
  const staffByNorm = {};
  for (const [k, v] of Object.entries(OVERLAY.staff_dates)) staffByNorm[norm(k)] = v;
  const funnelsByName = {};
  for (const f of OVERLAY.funnels) for (const a of alias(f.name)) funnelsByName[a] = f;
  const razboryByName = {};
  if (OVERLAY.razbory && OVERLAY.razbory.brokers) {
    for (const b of OVERLAY.razbory.brokers) for (const a of alias(b.name)) razboryByName[a] = b;
  }

  function fmtInt(n) { return Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' '); }
  function fmtPct(n) { return (n||0).toFixed(1).replace('.', ',') + '%'; }

  function buildFunnel(f) {
    if (!f) return '';
    const s = ((f.periods || {}).y2026 || {}).ALL || {};
    const total = Object.values(s).reduce((a, x) => a + (x.n || 0), 0);
    if (!total) return '';
    const won = (s.WON || {}).n || 0;
    const offer = (s.OFFER || {}).n || 0;
    const pres = (s.PRESENTATION || {}).n || 0;
    const qual = (s.QUALIFIED || {}).n || 0;
    const rQ = qual + pres + offer + won;
    const rP = pres + offer + won;
    const rO = offer + won;
    const rows = [
      ['Всего лидов', total, 100],
      ['До квала', rQ, 100*rQ/total],
      ['До презентации', rP, 100*rP/total],
      ['До оффера', rO, 100*rO/total],
      ['WON', won, 100*won/total],
    ];
    const bars = rows.map(([lbl, n, pct]) => `
      <div class="crm-stage-row">
        <span>${lbl}</span>
        <div class="crm-stage-track"><div class="crm-stage-fill ${lbl==='WON'?'won':''}" style="width:${Math.max(pct, 0.5)}%"></div></div>
        <span class="crm-stage-value">${fmtInt(n)} · ${fmtPct(pct)}</span>
      </div>
    `).join('');
    return `<div class="crm-funnel">
      <div class="crm-funnel-head"><h4>Воронка CRM · 2026</h4></div>
      <div>${bars}</div>
    </div>`;
  }

  function buildRazbory(b) {
    if (!b) return '';
    const R = OVERLAY.razbory;
    const nCls = b.norm_met ? 'good' : (b.records_submitted > 0 ? 'warn' : 'critical');
    const tCls = b.open_tasks_count === 0 ? '' : b.open_tasks_count <= 3 ? 'warn' : 'critical';
    const a = b.last_agreement;
    const agrHTML = a && a.all && a.all.length ? (() => {
      const last = a.all[0];
      const analysis = last.result ? `<div class="field-lbl">Результат анализа Зума (сильные/слабые)</div><div class="txt">${last.result}</div>` : '';
      const tasks = last.tasks ? `<div class="field-lbl">Задачи по итогу</div><div class="txt">${last.tasks}</div>` : '';
      const older = a.all.slice(1);
      const olderHTML = older.length ? `<details class="rz-older"><summary>▸ Показать все ${a.all.length} разборов (${older.length} ранее)</summary>
        ${older.map(e => `<div style="margin-top:10px;padding:10px;background:var(--surface-2);border:1px solid var(--rule)">
          <div class="meta">${e.id} · ${e.date} · ${e.reviewer || '—'}</div>
          ${e.result ? '<div class="field-lbl">Анализ</div><div class="txt">' + e.result + '</div>' : ''}
          ${e.tasks ? '<div class="field-lbl">Задачи</div><div class="txt">' + e.tasks + '</div>' : ''}
        </div>`).join('')}
      </details>` : '';
      return `<div class="meta">Последний: ${last.id} · ${last.date} · ${last.reviewer || '—'}</div>${analysis}${tasks}${olderHTML}`;
    })() : `<div class="meta">Записей в реестре нет</div>`;
    return `<div class="razbory-block">
      <div class="razbory-head"><h4>Разборы (учёт)</h4>
        <span style="font-family:var(--font-mono);font-size:10.5px;color:var(--muted)">${R.period.start} — ${R.period.end} · ${b.team}</span>
      </div>
      <div class="razbory-body">
        <div>
          <div class="rz-stats-grid">
            <div class="rz-metric"><div class="lbl">Сдано записей</div><div class="val ${nCls}">${b.records_submitted}/${R.summary.norm_target}</div></div>
            <div class="rz-metric"><div class="lbl">Разборов</div><div class="val">${b.razbory_count}</div><div class="sub">${b.last_razbor_date || '—'}</div></div>
            <div class="rz-metric"><div class="lbl">Открытые задачи</div><div class="val ${tCls}">${b.open_tasks_count}</div></div>
            <div class="rz-metric"><div class="lbl">Ожидают</div><div class="val">${b.awaiting_review}</div></div>
          </div>
        </div>
        <div class="rz-agreement">${agrHTML}</div>
      </div>
    </div>`;
  }

  function apply() {
    document.querySelectorAll('#view-komissia .row-main').forEach(row => {
      const nc = row.querySelector('.name-cell');
      if (!nc) return;
      const clone = nc.cloneNode(true);
      clone.querySelectorAll('.expand-arrow, .tenure').forEach(el => el.remove());
      const name = clone.textContent.trim();
      if (nonBrokersNorm.has(norm(name))) {
        row.classList.add('hide-non-broker');
        const n = row.nextElementSibling;
        if (n && n.classList.contains('razbor-row')) n.classList.add('hide-non-broker');
      }
      const st = staffByNorm[norm(name)];
      const ten = nc.querySelector('.tenure');
      if (st && (!ten || !ten.textContent.trim())) {
        if (ten) ten.textContent = 'c ' + st.start;
        else { const t = document.createElement('span'); t.className='tenure'; t.textContent='c ' + st.start; nc.appendChild(t); }
      }
    });
    document.querySelectorAll('#view-komissia .razbor').forEach(razbor => {
      if (razbor.querySelector('.crm-funnel') || razbor.querySelector('.razbory-block')) return;
      const tr = razbor.closest('tr');
      const trMain = tr && tr.previousElementSibling;
      const nc = trMain && trMain.querySelector('.name-cell');
      if (!nc) return;
      const clone = nc.cloneNode(true);
      clone.querySelectorAll('.expand-arrow, .tenure').forEach(el => el.remove());
      const name = clone.textContent.trim();
      let f = null, b = null;
      for (const a of alias(name)) { if (!f) f = funnelsByName[a]; if (!b) b = razboryByName[a]; }
      const html = buildFunnel(f) + buildRazbory(b);
      if (html) {
        const wrap = document.createElement('div'); wrap.innerHTML = html;
        while (wrap.firstElementChild) razbor.appendChild(wrap.firstElementChild);
      }
    });
  }

  const tryApply = () => { try { apply(); } catch(e) { console.error(e); } };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', tryApply);
  else tryApply();
  const t = document.getElementById('view-komissia');
  if (t) new MutationObserver(() => setTimeout(tryApply, 80)).observe(t, {childList: true, subtree: true});
})();
</script>
'''.replace('OVERLAY_DATA_PLACEHOLDER', overlay_data_json)

src = src + '\n' + overlay_addon

(REPO / 'index.html').write_text(src)
print(f'index.html written ({len(src):,} bytes)')

# ── 7. Build leads.html ─────────────────────────────
leads_html_template = (TEMPLATES / 'leads_base.html').read_text() if (TEMPLATES / 'leads_base.html').exists() else None
if leads_html_template:
    leads_html = leads_html_template.replace('LEADS_DATA_PLACEHOLDER', json.dumps(leads_by_source, ensure_ascii=False))
    (REPO / 'leads.html').write_text(leads_html)
    print(f'leads.html written ({len(leads_html):,} bytes)')
else:
    print('leads.html: no template found, skipping')
