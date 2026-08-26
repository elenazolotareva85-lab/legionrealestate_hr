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
active_brokers = load('active_brokers.json', [])

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

# ── 4b. Status/band must count ledger deals too ──────
# The table already prints max(stat.deals, ledger.deals), but bandFor/statusLabel
# looked only at stat.deals — so a broker with ledger-only deals (РОП с партнёрских
# сделок) showed «Нет сделок» рядом с оборотом и доходностью.
_old_band = """function bandFor(r) {
  const s = statFor(r);
  const deals = s.deals || 0;"""
_new_band = """function bandFor(r) {
  const s = statFor(r);
  const deals = Math.max(s.deals || 0, ledgerDealsFor(r).deals || 0);
  if (deals > 0 && !(s.deals || 0) && !(s.final_yield || s.yield_pct)) return 'neutral';"""

_old_status = """function statusLabel(r) {
  const s = statFor(r);
  if ((s.deals||0) === 0) return 'Нет сделок';"""
_new_status = """function statusLabel(r) {
  const s = statFor(r);
  const _d = Math.max(s.deals||0, ledgerDealsFor(r).deals||0);
  if (_d === 0) return 'Нет сделок';
  // Сделки есть только в ledger, доходность по ним не считалась — не выдаём 0% за «ниже нормы».
  if (!(s.deals || 0) && !(s.final_yield || s.yield_pct)) return 'Нет данных';"""

for _o, _n, _what in ((_old_band, _new_band, 'bandFor'), (_old_status, _new_status, 'statusLabel')):
    if _o in src:
        src = src.replace(_o, _n)
    else:
        print(f'   WARNING: {_what} not patched — статус может расходиться с колонкой «Сделки»')

# ── 5. Rewrite signal-bar with fresh data ────────────
# The base komissia ships a hardcoded signal-bar (a snapshot). Rebuild all four
# cards from data/stat.json + staff files and swap the whole block.

BURN_MIN_LEADS = 20   # below this a zero-deal broker is noise, not a signal
GREEN_ZONE = 45       # % final yield — same threshold as greens.json


def _norm(n):
    """Same normalisation as fetch_data.norm — ru/ua spelling of the same name."""
    n = (n or '').strip().lower().replace('і', 'и').replace('ї', 'и').replace('є', 'е').replace('ы', 'и')
    return ' '.join(sorted(n.split()))


def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _int(n):
    return f'{round(n or 0):,}'.replace(',', ' ')


def _money(n):
    n = round(n or 0)
    return f'${round(n / 1000)} тыс' if n >= 1000 else f'${n}'


def _plural(n, forms):
    n = abs(int(n)) % 100
    if 11 <= n <= 14:
        return forms[2]
    n %= 10
    if n == 1:
        return forms[0]
    if 2 <= n <= 4:
        return forms[1]
    return forms[2]


def _names(names, limit=4):
    shown = ' · '.join(_esc(n) for n in names[:limit])
    rest = len(names) - limit
    if rest > 0:
        shown += f' <span style="opacity:.6">и ещё {rest}</span>'
    return shown


def compute_signals():
    combined = stat.get('combined') or {}
    active = {_norm(b['name']) for b in active_brokers if b.get('name')}

    # Уволенных не считаем: по ним уже нечего решать, а деньги искажают сигнал.
    burn = sorted(
        (dict(v, name=n) for n, v in combined.items()
         if v.get('deals', 0) == 0 and v.get('leads', 0) >= BURN_MIN_LEADS
         and _norm(n) in active),
        key=lambda b: -b.get('mkt_spend', 0))


    # partner_rev > 0 — брокер участвовал в сделках как партнёр, «без сделок» про него неверно.
    nodeals = [n for n, v in combined.items()
               if v.get('deals', 0) == 0 and v.get('partner_rev', 0) <= 0
               and _norm(n) in active]

    return burn, list(greens), nodeals


SIGNAL_VISIBLE = 3   # остальные строки — по клику


def _item_list(rows, render, shown=SIGNAL_VISIBLE):
    """Первые `shown` строк видны сразу, остальные разворачиваются кнопкой."""
    if not rows:
        return ''
    out = [render(r, ' signal-item-extra' if i >= shown else '') for i, r in enumerate(rows)]
    if len(rows) > shown:
        out.append(f'<button type="button" class="signal-more" data-total="{len(rows)}">'
                   f'Показать всех {len(rows)} →</button>')
    return ''.join(out)


SIGNAL_ASSETS = """<style>
.signal-item-extra { display: none; }
.signal.expanded .signal-item-extra { display: grid; }
.signal-more {
  align-self: flex-start; background: none; border: none; padding: 6px 0 0; margin: 0;
  cursor: pointer; font-family: var(--font-mono); font-size: 10.5px;
  letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); text-align: left;
}
.signal-more:hover { color: var(--ink); text-decoration: underline; }
</style>
<script>
document.addEventListener('click', function (e) {
  var btn = e.target.closest('.signal-more');
  if (!btn) return;
  var card = btn.closest('.signal');
  var open = card.classList.toggle('expanded');
  btn.textContent = open ? 'Свернуть \u2191' : 'Показать всех ' + btn.dataset.total + ' \u2192';
});
</script>
"""


def render_signals():
    burn, green_zone, nodeals = compute_signals()

    burn_leads = sum(b.get('leads', 0) for b in burn)
    burn_spend = sum(b.get('mkt_spend', 0) for b in burn)
    per_lead = round(burn_spend / burn_leads) if burn_leads else 0

    declined_items = _item_list(declined, lambda d, ex:
        f'<div class="signal-item{ex}"><span class="name">{_esc(d["name"])}</span>'
        f'<span class="delta">▼ {d["drop"]:.1f} п.п.</span>'
        f'<span class="detail">{d["y25"]:.0f}% → {d["y26"]:.0f}%</span></div>')

    green_items = _item_list(green_zone, lambda g, ex:
        f'<div class="signal-item{ex}"><span class="name">{_esc(g["name"])}</span>'
        f'<span class="delta rise">▲ {g["yield"]:.0f}%</span>'
        f'<span class="detail">{g["deals"]:.0f} сд · {_money(g["revenue"])}</span></div>')

    return SIGNAL_ASSETS + f'''<div class="signal-bar">
    <div class="signal critical">
      <span class="signal-tag">🚨 Жгут бюджет</span>
      <div class="signal-hero">{_money(burn_spend)}<span class="signal-hero-unit">$</span></div>
      <p class="signal-headline">{len(burn)} {_plural(len(burn), ("брокер", "брокера", "брокеров"))} получили {_int(burn_leads)} {_plural(burn_leads, ("лид", "лида", "лидов"))} и не закрыли ни одной сделки</p>
      <p class="signal-detail">Средняя стоимость нерезультативного лида — ${per_lead}. Считаем действующих, у кого от {BURN_MIN_LEADS} лидов.</p>
      <div class="signal-names">{_names([b["name"] for b in burn])}</div>
      <div class="signal-action">Аудит потока лидов + лимит новых лидов до выхода в конверсию.</div>
    </div>
    <div class="signal warn">
      <span class="signal-tag">📉 Просели</span>
      <div class="signal-hero">{len(declined)}<span class="signal-hero-unit">{_plural(len(declined), ("брокер", "брокера", "брокеров"))}</span></div>
      <p class="signal-headline">Доходность 2026 упала на ≥10 п.п. к 2025</p>
      {declined_items}
      <div class="signal-action">Разбор с РОПом причин + KPI-план с недельным контролем.</div>
    </div>
    <div class="signal good">
      <span class="signal-tag">⭐ Зелёная зона</span>
      <div class="signal-hero">{len(green_zone)}<span class="signal-hero-unit">{_plural(len(green_zone), ("брокер", "брокера", "брокеров"))}</span></div>
      <p class="signal-headline">Окупаемость 2026 — {GREEN_ZONE}% и выше</p>
      {green_items}
      <div class="signal-action">Расширить поток лидов + кандидаты на наставничество.</div>
    </div>
  </div>
  <div class="signal-bar wide">
    <div class="signal warn">
      <span class="signal-tag">⏳ Актуальные без сделок</span>
      <p class="signal-headline">{len(nodeals)} {_plural(len(nodeals), ("действующий сотрудник", "действующих сотрудника", "действующих сотрудников"))} без единой сделки за 2025-2026</p>
      <p class="signal-detail">Причины: новички, недавно на позиции, или не в продажах напрямую (QC, клиент-сервис, стажировка).</p>
      <div class="signal-names">{_names(nodeals)}</div>
    </div>
  </div>'''


# Only swap when the stats actually loaded — a failed fetch must not blank the cards.
if stat.get('combined'):
    _m = re.search(r'<div class="signal-bar">.*?(?=<div class="planfact-section">)', src, re.S)
    if _m:
        src = src[:_m.start()] + render_signals() + '\n\n  ' + src[_m.end():]
        _burn, _green, _nodeals = compute_signals()
        print(f'   signals: burn={len(_burn)}, declined={len(declined)}, '
              f'green-zone={len(_green)}, no-deals={len(_nodeals)}')
    else:
        print('   WARNING: signal-bar block not found in template — cards left as snapshot')
else:
    print('   WARNING: stat.json empty — signal cards left as snapshot')

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
