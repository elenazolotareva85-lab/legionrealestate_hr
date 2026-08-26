#!/usr/bin/env python3
"""Fetch all data from Google Sheets and BigQuery, save to data/*.json.

Reads env vars:
  SHEETS_KEY_PATH — path to service account JSON for Sheets
  BQ_KEY_PATH     — path to service account JSON for BigQuery
"""
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import gspread
from google.cloud import bigquery
from google.oauth2.service_account import Credentials

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / 'data'
DATA.mkdir(exist_ok=True)

SHEETS_KEY = os.environ['SHEETS_KEY_PATH']
BQ_KEY = os.environ['BQ_KEY_PATH']

SCOPES_SHEETS = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/drive.readonly',
]

sheets_creds = Credentials.from_service_account_file(SHEETS_KEY, scopes=SCOPES_SHEETS)
gc = gspread.authorize(sheets_creds)
bq_creds = Credentials.from_service_account_file(BQ_KEY)
bq = bigquery.Client(credentials=bq_creds, project='disco-bedrock-428721-f8')

STAFF_ID = '1TLoMnXpgYWZwh0_0PupxWOCbibe37lwsMmibhBgbxs8'
PRIMARY_ID = '12TNumdNXr-dy-Gx5z0H9p-zsH0GmV6yrkZ_aGhdb3HU'
SDELKI_ID = '12_D7HbtiuZDoHQRiVrSG6Q-4_wbCBN5xiRo2iYScCPk'
RAZBORY_ID = '1EaMMe22qY2OtCLSls1MOdjw3rDgqV3Tq'

NON_BROKERS = {'Роман Безносюк', 'Владислав Семчук'}


def num(x):
    if not x: return None
    raw = str(x).strip()
    if not raw or raw == '-': return None
    is_pct = raw.endswith('%')
    if is_pct: raw = raw[:-1].strip()
    s = raw.replace('\xa0', ' ')
    if re.match(r'^-?\d{1,3}(,\d{3})+(\.\d+)?$', s):
        return float(s.replace(',', ''))
    if re.match(r'^-?\d{1,3}([ .]\d{3})+,\d{1,2}$', s):
        return float(s.replace(' ', '').replace('.', '').replace(',', '.'))
    if re.match(r'^-?\d{1,3}( \d{3})+$', s):
        return float(s.replace(' ', ''))
    if re.match(r'^-?\d+,\d{1,2}$', s):
        return float(s.replace(',', '.'))
    if re.match(r'^-?\d+(\.\d+)?$', s):
        return float(s)
    return None


def norm(n):
    n = (n or '').strip().lower().replace('і', 'и').replace('ї', 'и').replace('є', 'е').replace('ы', 'и')
    return ' '.join(sorted(n.split()))


# ── 1. Staff ─────────────────────────────────────────────
print('1. Fetch staff...')
sh_staff = gc.open_by_key(STAFF_ID)
vals = sh_staff.worksheet('staff Bali').get_all_values()
staff_dates, active_brokers = {}, []
for r in vals[1:]:
    if len(r) < 17: continue
    name = r[2].strip()
    pos = r[6].strip().lower() if len(r) > 6 else ''
    dept = r[12].strip() if len(r) > 12 else ''
    dism = r[16].strip() if len(r) > 16 else ''
    start = r[0].strip()
    if not name or dism: continue
    is_sales = dept.startswith('sales') or 'менеджер по продажам' in pos or 'ассистент отдела продаж' in pos
    if is_sales:
        active_brokers.append({'name': name, 'pos': pos, 'dept': dept})
        if start:
            staff_dates[name] = {'start': start, 'position': pos}
(DATA / 'staff_dates.json').write_text(json.dumps(staff_dates, ensure_ascii=False, indent=2))
(DATA / 'active_brokers.json').write_text(json.dumps(active_brokers, ensure_ascii=False, indent=2))
print(f'   staff: {len(active_brokers)} active, {len(staff_dates)} with dates')

# ── 2. Primary sheet: Statistics + declined + greens ─────
print('2. Fetch primary sheet...')
sh_prim = gc.open_by_key(PRIMARY_ID)
stat = sh_prim.worksheet('Статистика по брокерам').get_all_values()


def parse_stat(rng):
    out = {}
    for i in rng:
        r = stat[i]
        if len(r) < 20: continue
        n = r[1].strip()
        if not n: continue
        out[n] = {
            'leads': num(r[3]) or 0, 'deals': num(r[4]) or 0,
            'conv': num(r[5]) or 0, 'turnover': num(r[6]) or 0,
            'avg_check': num(r[7]) or 0, 'revenue': num(r[8]) or 0,
            'margin_cb': num(r[10]) or 0, 'mkt_spend': num(r[11]) or 0,
            'avg_lead_price': num(r[13]) or 0, 'yield_pct': num(r[14]) or 0,
            'partner_rev': num(r[15]) or 0, 'final_yield': num(r[18]) or 0,
        }
    return out


combined = parse_stat(range(4, 38))
block2 = parse_stat(range(51, 80))
(DATA / 'stat.json').write_text(json.dumps({'combined': combined, 'block2': block2}, ensure_ascii=False, indent=2, sort_keys=True))

# Declined
declined = []
for n, c in combined.items():
    b = block2.get(n, {})
    if b.get('deals', 0) == 0: continue
    rev25 = max(0, c['revenue'] - b.get('revenue', 0))
    mar25 = max(0, c['margin_cb'] - b.get('margin_cb', 0))
    if rev25 == 0: continue
    y25 = 100 * mar25 / rev25
    y26 = b.get('final_yield', 0)
    drop = y25 - y26
    if drop >= 10:
        declined.append({'name': n, 'y25': round(y25, 1), 'y26': round(y26, 1), 'drop': round(drop, 1)})
declined.sort(key=lambda x: (-x['drop'], x['name']))
(DATA / 'declined.json').write_text(json.dumps(declined, ensure_ascii=False, indent=2))

# Greens (green zone 2026)
greens = []
for i in range(51, 80):
    r = stat[i]
    if len(r) < 20: continue
    n = r[1].strip()
    if not n: continue
    y26 = num(r[18]) or 0
    deals = num(r[4]) or 0
    rev = num(r[8]) or 0
    if y26 >= 45 and deals > 0:
        # Only include active brokers
        if norm(n) in {norm(x['name']) for x in active_brokers}:
            greens.append({'name': n, 'yield': round(y26, 1), 'deals': int(deals), 'revenue': round(rev)})
greens.sort(key=lambda x: (-x['yield'], x['name']))
(DATA / 'greens.json').write_text(json.dumps(greens, ensure_ascii=False, indent=2))
print(f'   declined: {len(declined)}, greens: {len(greens)}')

# ── 3. Razbory (dashboard + registry) ────────────────────
print('3. Fetch razbory...')
# Try via gspread first — but the file is .xlsx, so we'll rely on cached copy in data/razbory_raw.txt
# Actually the file was uploaded as .xlsx; try opening via Drive API fallback.
# For simplicity: skip if not cached — this is the file most likely to fail.
try:
    razbory_dump = (DATA / 'razbory_raw.txt').read_text()
    print('   using cached razbory raw dump')
except FileNotFoundError:
    print('   WARNING: no razbory_raw.txt cached — razbory block will be empty')
    razbory_dump = ''


def parse_razbory(raw):
    if not raw: return None
    m = re.search(r'Брокер,Команда,Сдано записей.*?Ожидают разбора,?', raw)
    if not m: return None
    start = m.end()
    end_m = re.search(r'\s*(Материалы|Учёт|Реестр|Правила разбора|Спикер|Задачи по итогу|Комментарии)', raw[start:])
    end = start + end_m.start() if end_m else start + 8000
    chunk = raw[start:end]
    NAME = r'[А-ЯЁІЇ][а-яёіїєґ]+(?:[- ][А-ЯЁІЇ][а-яёіїєґ]+)?'
    pat = re.compile(
        rf'({NAME}\s+{NAME}),\s*(Рома|Макс|Влад)'
        r',\s*(\d+),\s*([✓✗]),\s*(\d+),\s*([\d.]+|—),\s*(\d+)'
        r',\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)'
        r',\s*(E\d+|—),\s*(\d+)'
    )
    brokers = []
    for m in pat.finditer(chunk):
        brokers.append({
            'name': m.group(1).strip(), 'team': m.group(2),
            'records_submitted': int(m.group(3)),
            'norm_met': m.group(4) == '✓',
            'razbory_count': int(m.group(5)),
            'last_razbor_date': m.group(6) if m.group(6) != '—' else None,
            'open_tasks_count': int(m.group(7)),
            'errors': {f'E{i + 1}': int(m.group(8 + i)) for i in range(7)},
            'top_error': m.group(15) if m.group(15) != '—' else None,
            'awaiting_review': int(m.group(16)),
        })

    # Global counters
    def find_int(label):
        mm = re.search(rf'{label}[^\d]*(\d+)', raw)
        return int(mm.group(1)) if mm else 0

    summary = {
        'norm_target': 2,
        'submitted_total': find_int('Сдано записей за период'),
        'materials_total': find_int('Материалов всего'),
        'razbory_total': find_int('Разборов за период'),
        'awaiting_total': find_int(r'Ожидают разбора \(всего\)'),
        'open_tasks_total': find_int(r'Открытых задач \(всего\)'),
        'norm_met_pct': find_int('Выполнили норматив'),
    }
    return {
        'period': {'start': '01.08.2026', 'end': '31.08.2026'},
        'summary': summary,
        'brokers': brokers,
    }


def parse_agreements(raw):
    if not raw: return {}
    m = re.search(r'Задачи по итогу разбора или анализа', raw)
    if not m: return {}
    start = m.end()
    end_m = re.search(r'\s+(Правила разбора|Учет посещаемости|Учёт |Спикер|Комментарии)', raw[start:])
    end = start + end_m.start() if end_m else len(raw)
    chunk = raw[start:end]
    NAME = r'[А-ЯЁІЇ][а-яёіїєґ]+(?:\s+[А-ЯЁІЇ][а-яёіїєґ]+)?'
    pat = re.compile(
        r'(?:([KRTD]-\d{3})|\s|,)?[,\s]*'
        r'(\d{1,2}\.\d{1,2}\.\d{4})'
        r',\s*(' + NAME + r'\s+' + NAME + r')'
        r',\s*(' + NAME + r'(?:\s+' + NAME + ')?' + r')?'
        r',\s*(Zoom|Файл|Youtube|YouTube|запись звонка|—|\s*)'
        r',\s*("[^"]*"|[^,]*)'
        r',\s*("[^"]*"|[^,]*)'
        r',\s*(Разобрано|Обещан|Ожидает разбора|Готово|—|\s*)'
        r',\s*("[^"]*"|[^,]*)'
        r',\s*(\d{1,2}\.\d{1,2}\.\d{4}|—|\s*)'
        r',\s*("[^"]*"|[^,]*)'
        r',\s*("[^"]*"|[^,]*)',
        re.DOTALL,
    )

    def clean(s):
        s = (s or '').strip()
        if s.startswith('"') and s.endswith('"'): s = s[1:-1]
        s = re.sub(r'\\?\[даты ориентировочные — уточнить по Drive\\?\]\s*', '', s)
        s = re.sub(r'\\_', '_', s)
        return s.strip()

    entries = []
    for m in pat.finditer(chunk):
        ra = clean(m.group(9))
        tk = clean(m.group(12))
        ra = re.sub(r'\s*[KRTD]-\d{3}\s*$', '', ra).strip()
        tk = re.sub(r'\s*[KRTD]-\d{3}\s*$', '', tk).strip()
        if not ra and not tk: continue
        entries.append({
            'id': m.group(1) or '(no-id)',
            'date': clean(m.group(2)),
            'broker': clean(m.group(3)),
            'reviewer': clean(m.group(4)),
            'type': clean(m.group(5)),
            'result_analysis': ra,
            'date_razbor': clean(m.group(10)),
            'tasks': tk,
        })
    for idx, e in enumerate(entries):
        e['_order'] = idx
    per_broker = defaultdict(list)
    for e in entries:
        if e['broker']: per_broker[e['broker']].append(e)

    def dt(s):
        if not s or s == '—': return (0, 0, 0)
        parts = s.split('.')
        try: return (int(parts[2]), int(parts[1]), int(parts[0]))
        except: return (0, 0, 0)

    for b in per_broker:
        per_broker[b].sort(key=lambda x: (dt(x.get('date_razbor') or x.get('date')), x['_order']), reverse=True)
    result = {}
    for b, l in per_broker.items():
        last = l[0]
        result[b] = {
            'entries_count': len(l),
            'last_id': last['id'], 'last_date': last.get('date_razbor') or last.get('date') or '',
            'last_reviewer': last['reviewer'], 'last_type': last['type'],
            'last_result_analysis': last['result_analysis'], 'last_tasks': last['tasks'],
            'all': [{'id': e['id'], 'date': e.get('date_razbor') or e.get('date') or '',
                     'reviewer': e['reviewer'], 'type': e['type'],
                     'result': e['result_analysis'], 'tasks': e['tasks']} for e in l],
        }
    return result


razbory = parse_razbory(razbory_dump)
if razbory:
    for b in razbory['brokers']:
        b['last_agreement'] = parse_agreements(razbory_dump).get(b['name']) or \
            parse_agreements(razbory_dump).get(b['name'].replace('Максим', 'Макс')) or \
            parse_agreements(razbory_dump).get(b['name'].replace('Макс', 'Максим'))
    (DATA / 'razbory.json').write_text(json.dumps(razbory, ensure_ascii=False, indent=2))
    print(f'   razbory: {len(razbory["brokers"])} brokers')
else:
    (DATA / 'razbory.json').write_text('null')
    print('   razbory: SKIPPED (no raw dump)')

# ── 4. Funnels from BigQuery ─────────────────────────────
print('4. Fetch funnels from BQ...')
STAGE_MAP = [
    ('успешно реализовано', 'WON'), ('agreement received', 'WON'),
    ('deposit received', 'OFFER'), ('presentation defended', 'OFFER'), ('оффер принят', 'OFFER'),
    ('presentation confirmed', 'PRESENTATION'), ('презентация проведена', 'PRESENTATION'),
    ('warm-up started', 'PRESENTATION'), ('прогрев запущен', 'PRESENTATION'),
    ('interest in cooperating', 'QUALIFIED'), ('intetrest in cooperating', 'QUALIFIED'),
    ('интерес сотрудничать', 'QUALIFIED'), ('qualified', 'QUALIFIED'),
    ('квалифицирован', 'QUALIFIED'), ('обработан', 'QUALIFIED'), ('processed', 'QUALIFIED'),
    ('дозвон', 'QUALIFIED'),
    ('deferred demand', 'DEFERRED'), ('отложенный спрос', 'DEFERRED'), ('reactivate', 'DEFERRED'),
    ('реактивация', 'DEFERRED'), ('pended demand', 'DEFERRED'),
    ('got to work', 'NEW'), ('взято в работу', 'NEW'), ('взял в работу', 'NEW'),
    ('new lead', 'NEW'), ('новый лид', 'NEW'), ('новый', 'NEW'),
    ('закрыто и не реализовано', 'LOST'), ('не интересно', 'LOST'), ('не купил', 'LOST'),
]
SALES_PIPES = {'Сделки Бали', 'Europe Deals', 'Сделки Таиланд', 'Thailand Deals', 'Долевое участие Бали'}
LEADS_PIPES = {'Лиды Бали', 'Лиды Таиланд', 'Leads Europe', 'Leads Thailand', 'Лиды Австралия', 'Лиды Европа'}
PIPELINE_REGION = {'Сделки Бали': 'Bali', 'Долевое участие Бали': 'Bali',
                    'Сделки Таиланд': 'Thailand', 'Thailand Deals': 'Thailand', 'Europe Deals': 'Europe',
                    'Лиды Бали': 'Bali', 'Лиды Таиланд': 'Thailand', 'Leads Europe': 'Europe',
                    'Leads Thailand': 'Thailand', 'Лиды Австралия': 'Australia', 'Лиды Европа': 'Europe'}


def classify(s):
    s = (s or '').lower().strip()
    for pat, st in STAGE_MAP:
        if pat in s: return st
    return 'OTHER'


L3M = {(2026, 5), (2026, 6), (2026, 7)}
EXCLUDE_2026 = {8, 9}


def periods_for(y, m):
    ps = ['all']
    if y == 2025: ps.append('y2025')
    if y == 2026 and m not in EXCLUDE_2026: ps.append('y2026')
    if (y, m) in L3M: ps.append('l3m')
    return ps


q = """
SELECT manager, pipeline, status,
       EXTRACT(YEAR FROM createdAt) y, EXTRACT(MONTH FROM createdAt) m,
       COUNT(*) n, SUM(budget) total_budget
FROM `disco-bedrock-428721-f8.deals_bali.deals_bali`
WHERE manager IS NOT NULL AND manager != '' AND createdAt IS NOT NULL
GROUP BY manager, pipeline, status, y, m
"""
rows = list(bq.query(q).result())


def zs(): return {'n': 0, 'budget': 0}
def sd(): return defaultdict(zs)
def rd(): return defaultdict(sd)
def pd_(): return defaultdict(rd)


per_broker = defaultdict(pd_)
for r in rows:
    stg = classify(r.status)
    reg = PIPELINE_REGION.get(r.pipeline, 'Другое')
    if r.y is None or r.m is None: continue
    if r.pipeline in LEADS_PIPES and stg == 'WON': stg = 'QUALIFIED'
    if r.pipeline not in SALES_PIPES and r.pipeline not in LEADS_PIPES: continue
    for p in periods_for(int(r.y), int(r.m)):
        per_broker[r.manager][p][reg][stg]['n'] += r.n
        per_broker[r.manager][p][reg][stg]['budget'] += (r.total_budget or 0)

# Fetch first/last per manager
q2 = """SELECT manager, MIN(DATE(createdAt)) mn, MAX(DATE(createdAt)) mx
FROM `disco-bedrock-428721-f8.deals_bali.deals_bali`
WHERE manager IS NOT NULL AND manager != '' AND createdAt IS NOT NULL GROUP BY manager"""
first_last = {r.manager: (str(r.mn), str(r.mx)) for r in bq.query(q2).result()}

# Build per-broker records (matched to active)
active_norm = {norm(x['name']): x for x in active_brokers}
funnels = []
for mgr, periods in per_broker.items():
    key = norm(mgr)
    match = active_norm.get(key) or active_norm.get(key.replace('макс', 'максим')) or active_norm.get(key.replace('максим', 'макс'))
    if not match: continue
    if match['name'] in NON_BROKERS: continue
    total_all = sum(sum(v['n'] for v in stgs.values()) for stgs in periods.get('all', {}).values())
    if total_all < 20: continue
    # Determine role
    pos = match.get('pos', '').lower()
    role = 'qualifier' if 'квалификатор' in pos or 'контроля качества' in pos else 'broker'
    per_out = {}
    for pname, regions in periods.items():
        regs = {}
        totals_p = defaultdict(int); tb_p = defaultdict(float)
        for region, stages in regions.items():
            reg_data = {}
            for stg, v in stages.items():
                reg_data[stg] = {'n': v['n'], 'budget': v['budget']}
                totals_p[stg] += v['n']; tb_p[stg] += v['budget']
            regs[region] = reg_data
        regs['ALL'] = {stg: {'n': totals_p[stg], 'budget': tb_p[stg]} for stg in totals_p}
        per_out[pname] = regs
    fl = first_last.get(mgr, ('', ''))
    funnels.append({
        'name': match['name'], 'role': role, 'position': match.get('pos', ''),
        'first_lead': fl[0], 'last_lead': fl[1],
        'periods': per_out,
    })

# Patch WON with real close-date counting (status_id=142 + current status successful)
print('   patching WON with close-date...')
q_won = """
WITH won_events AS (
  SELECT deal_id, MIN(event_created_at) AS won_at
  FROM `disco-bedrock-428721-f8.deals_bali.deals_status`
  WHERE deal_status_id = 142 AND event_type = 'lead_status_changed'
  GROUP BY deal_id
)
SELECT d.manager, d.pipeline, d.budget,
       EXTRACT(YEAR FROM w.won_at) yr, EXTRACT(MONTH FROM w.won_at) mo
FROM won_events w
JOIN `disco-bedrock-428721-f8.deals_bali.deals_bali` d ON SAFE_CAST(d.orderId AS INT64) = w.deal_id
WHERE d.pipeline IN ('Сделки Бали','Europe Deals','Сделки Таиланд','Thailand Deals','Долевое участие Бали')
  AND LOWER(d.status) LIKE '%успешно%'
"""
def _zr(): return {'n': 0, 'budget': 0}
def _new_pd(): return defaultdict(lambda: defaultdict(_zr))
new_won = defaultdict(_new_pd)
for r in bq.query(q_won).result():
    if r.yr is None or r.mo is None: continue
    reg = PIPELINE_REGION.get(r.pipeline, 'Другое')
    for p in periods_for(int(r.yr), int(r.mo)):
        new_won[r.manager][p][reg]['n'] += 1
        new_won[r.manager][p][reg]['budget'] += (r.budget or 0)
nwbn = defaultdict(_new_pd)
for m, p in new_won.items():
    for pk, s in p.items():
        for sk, v in s.items():
            nwbn[norm(m)][pk][sk]['n'] += v['n']; nwbn[norm(m)][pk][sk]['budget'] += v['budget']
for b in funnels:
    src = nwbn.get(norm(b['name']), {})
    for period, regs in b.get('periods', {}).items():
        override = src.get(period, {})
        all_n = sum(v['n'] for v in override.values())
        all_b = sum(v['budget'] for v in override.values())
        for rn, stages in regs.items():
            if rn == 'ALL':
                stages['WON'] = {'n': all_n, 'budget': all_b}
            else:
                v = override.get(rn, {'n': 0, 'budget': 0})
                stages['WON'] = {'n': v['n'], 'budget': v['budget']}

(DATA / 'funnels.json').write_text(json.dumps(funnels, ensure_ascii=False, indent=2))
print(f'   funnels: {len(funnels)} brokers')

# ── 5. Leads by source ──────────────────────────────────
print('5. Fetch leads by source...')
q_lead = """
SELECT manager,
       EXTRACT(YEAR FROM createdAt) yr, EXTRACT(MONTH FROM createdAt) mo,
       COALESCE(NULLIF(TRIM(utmSource), ''), '(нет)') source, COUNT(*) n
FROM `disco-bedrock-428721-f8.deals_bali.deals_bali`
WHERE manager IS NOT NULL AND manager != '' AND createdAt IS NOT NULL
GROUP BY manager, yr, mo, source
"""

def ns(s):
    s = (s or '').lower().strip()
    if s == '(нет)' or not s: return 'Без метки'
    if s == 'ig' or 'instagram' in s: return 'Instagram'
    if s == 'fb' or 'facebook' in s: return 'Facebook'
    if 'google' in s: return 'Google Ads'
    if 'tik' in s or s == 'tt': return 'TikTok'
    if 'telegram' in s: return 'Telegram'
    if 'youtube' in s: return 'YouTube'
    if 'yandex' in s: return 'Yandex'
    if any(k in s for k in ['usyk', 'philipp', 'ozdo', 'lgn_', 'avalon']): return 'Кампании'
    return 'Другое'

brokers = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
for r in bq.query(q_lead).result():
    if r.yr is None: continue
    src = ns(r.source); yr = int(r.yr); mo = int(r.mo) if r.mo else 0
    for p in ['all', f'y{yr}'] + ([f'{yr}-{mo:02d}'] if mo else []):
        brokers[r.manager][p][src] += r.n

# WON per source
q_wsrc = """
WITH won_events AS (SELECT deal_id, MIN(event_created_at) AS won_at FROM `disco-bedrock-428721-f8.deals_bali.deals_status` WHERE deal_status_id=142 AND event_type='lead_status_changed' GROUP BY deal_id)
SELECT d.manager, EXTRACT(YEAR FROM w.won_at) yr, EXTRACT(MONTH FROM w.won_at) mo,
  COALESCE(NULLIF(TRIM(d.utmSource),''),'(нет)') source, d.budget
FROM won_events w JOIN `disco-bedrock-428721-f8.deals_bali.deals_bali` d ON SAFE_CAST(d.orderId AS INT64)=w.deal_id
WHERE d.pipeline IN ('Сделки Бали','Europe Deals','Сделки Таиланд','Thailand Deals','Долевое участие Бали') AND LOWER(d.status) LIKE '%успешно%'
"""
wons = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: {'n': 0, 'budget': 0})))
for r in bq.query(q_wsrc).result():
    if r.yr is None: continue
    src = ns(r.source); yr = int(r.yr); mo = int(r.mo) if r.mo else 0
    for p in ['all', f'y{yr}'] + ([f'{yr}-{mo:02d}'] if mo else []):
        wons[r.manager][p][src]['n'] += 1
        wons[r.manager][p][src]['budget'] += (r.budget or 0)

out = []
for mgr, periods in brokers.items():
    key = norm(mgr)
    match = active_norm.get(key) or active_norm.get(key.replace('макс', 'максим')) or active_norm.get(key.replace('максим', 'макс'))
    if not match: continue
    if match['name'] in NON_BROKERS: continue
    total = sum(periods.get('all', {}).values())
    if total < 5: continue
    w = wons.get(mgr) or wons.get(mgr.replace('Максим', 'Макс')) or wons.get(mgr.replace('Макс', 'Максим')) or {}
    out.append({
        'name': match['name'], 'total_leads_all': total,
        'periods': {p: dict(srcs) for p, srcs in periods.items()},
        'wons': {p: {s: dict(v) for s, v in srcs.items()} for p, srcs in w.items()},
    })
out.sort(key=lambda x: -x['total_leads_all'])
(DATA / 'leads_by_source.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(f'   leads_by_source: {len(out)} brokers')

print('\nAll data fetched to data/*.json')
