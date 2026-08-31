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
from datetime import date
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
PHUKET_DEALS_ID = '1BlsjXe5ni0yO_AbeASg9l9Intflhl2WQP66mQnkk_9A'

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

# ── 6. Пхукет: штат, сделки, реклама, воронки ────────────
print('6. Fetch Phuket...')

PHUKET_ADS_RE = r'phuket'


def money(x):
    """Числа в пхукетском листе идут в двух форматах: 141 964,91 и 188114.0421."""
    x = (x or '').replace('\xa0', '').replace(' ', '').replace('$', '')
    if re.search(r',\d{1,2}$', x):
        x = x.replace('.', '').replace(',', '.')
    else:
        x = x.replace(',', '')
    x = re.sub(r'[^0-9.\-]', '', x)
    try:
        return float(x)
    except ValueError:
        return 0.0


def source_class(s):
    """Откуда пришёл лид. Для окупаемости считаем только 'ads' —
    остальное рекламных денег не стоило."""
    s = (s or '').lower()
    if 'прямой трафик' in s or 'таргет' in s: return 'ads'
    if 'самолет' in s or 'партнер' in s or 'партнёр' in s or 'b2b' in s: return 'partner'
    if 'свой клиент' in s or 'рекоменд' in s or 'повтор' in s: return 'own'
    if 'бали' in s: return 'bali'
    if 'база' in s or 'органик' in s or 'ютуб' in s or 'телеграм' in s: return 'base'
    return 'other'


SOURCE_LABELS = {'ads': 'Реклама', 'partner': 'Партнёры', 'own': 'Свои клиенты',
                 'bali': 'Передано из Бали', 'base': 'База и органика', 'other': 'Прочее'}

# 6.1 штат — у вкладки Пхукета своя раскладка колонок, не как у Бали
ph_staff, ph_dates = [], {}
for r in sh_staff.worksheet('staff Tailand').get_all_values()[1:]:
    r = r + [''] * 20
    name = r[2].strip()
    if not name: continue
    dismissed = bool(r[13].strip() or r[15].strip())   # «ис» или дата увольнения
    pos = r[5].strip().lower()
    if r[0].strip():                                   # даты нужны и по уволенным — их сделки в таблице
        ph_dates[name] = {'start': r[0].strip(), 'position': pos, 'left': r[15].strip()}
    if dismissed: continue
    ph_staff.append({'name': name, 'pos': pos, 'dept': r[11].strip()})
ph_norm = {norm(x['name']): x for x in ph_staff}

# 6.2 сделки
def _zero_deal():
    return {'deals': 0, 'turnover': 0.0, 'commission': 0.0, 'margin': 0.0, 'margin_known': 0}


ph_deals, ph_by_broker, ph_sources = defaultdict(_zero_deal), {}, {}
ph_months = defaultdict(lambda: defaultdict(_zero_deal))
ph_ad_margin = defaultdict(lambda: defaultdict(float))   # маржа с рекламных сделок, по годам
for r in gc.open_by_key(PHUKET_DEALS_ID).worksheet('ОП').get_all_values()[1:]:
    r = r + [''] * 62
    year = r[1].strip()
    if not re.fullmatch(r'20\d\d', year): continue          # отсекаем строки-итоги «маркет»/«прочее»
    mgr, price = r[3].strip(), money(r[11])
    if not mgr or price <= 0: continue
    comm, cls, margin = money(r[15]), source_class(r[5]), money(r[32])
    month = (r[0].strip().split('.')[0] or '0')
    for bucket in (ph_deals[year],
                   ph_by_broker.setdefault(year, {}).setdefault(mgr, dict(_zero_deal(), sources={})),
                   ph_sources.setdefault(year, {}).setdefault(cls, _zero_deal()),
                   ph_months[year][month]):
        bucket['deals'] += 1; bucket['turnover'] += price; bucket['commission'] += comm
        bucket['margin'] += margin
        if margin: bucket['margin_known'] += 1
    br = ph_by_broker[year][mgr]['sources']
    br[cls] = br.get(cls, 0) + 1
    if cls == 'ads': ph_ad_margin[year][mgr] += margin

# 6.3 реклама из BigQuery — регион зашит в название кампании
ph_ads, ph_campaigns = {}, defaultdict(lambda: {'spend': 0.0, 'leads': 0})
q_ads = f"""
SELECT EXTRACT(YEAR FROM date) y, campaign_name, SUM(spend) spend, SUM(lead) leads
FROM `disco-bedrock-428721-f8.main.main`
WHERE REGEXP_CONTAINS(LOWER(campaign_name), r'{PHUKET_ADS_RE}')
GROUP BY y, campaign_name
"""
for r in bq.query(q_ads).result():
    y = str(r.y)
    a = ph_ads.setdefault(y, {'spend': 0.0, 'leads': 0})
    a['spend'] += float(r.spend or 0); a['leads'] += int(r.leads or 0)
    c = ph_campaigns[(y, r.campaign_name)]
    c['spend'] += float(r.spend or 0); c['leads'] += int(r.leads or 0)

# 6.3b реклама в разрезе брокера: цена лида по его объявлениям × его лиды.
# Точного «расхода на брокера» нигде нет, поэтому это атрибуция, а не факт.
ph_broker_spend = defaultdict(lambda: defaultdict(float))
q_attr = """
WITH lead_ads AS (
  SELECT manager, CAST(ad_id AS STRING) aid, EXTRACT(YEAR FROM createdAt) y, COUNT(*) n
  FROM `disco-bedrock-428721-f8.deals_bali.deals_bali`
  WHERE manager IS NOT NULL AND ad_id IS NOT NULL AND createdAt IS NOT NULL
    AND (LOWER(pipeline) LIKE '%таиланд%' OR LOWER(pipeline) LIKE '%thailand%')
  GROUP BY manager, aid, y
), ad_cost AS (
  SELECT CAST(ad_id AS STRING) aid, SUM(spend) spend, SUM(lead) leads
  FROM `disco-bedrock-428721-f8.main.main`
  WHERE ad_id IS NOT NULL GROUP BY aid
)
SELECT l.manager, l.y, SUM(l.n * SAFE_DIVIDE(a.spend, NULLIF(a.leads, 0))) spend
FROM lead_ads l JOIN ad_cost a USING (aid)
GROUP BY l.manager, l.y
"""
for r in bq.query(q_attr).result():
    if r.spend:
        ph_broker_spend[str(r.y)][norm(r.manager)] += float(r.spend)

# 6.4 окупаемость — только по сделкам с рекламных лидов
ph_roi = {}
for y, ads in ph_ads.items():
    ad_deals = (ph_sources.get(y) or {}).get('ads', {'deals': 0, 'commission': 0.0, 'turnover': 0.0})
    spend = ads['spend']
    ph_roi[y] = {
        'spend': round(spend), 'leads': ads['leads'],
        'cpl': round(spend / ads['leads'], 1) if ads['leads'] else 0,
        'ad_deals': ad_deals['deals'], 'ad_commission': round(ad_deals['commission']),
        'ad_turnover': round(ad_deals['turnover']),
        'roi_pct': round(100 * (ad_deals['commission'] - spend) / spend, 1) if spend else 0,
        'total_commission': round((ph_deals.get(y) or {}).get('commission', 0)),
    }

# 6.5 воронки — те же данные BQ, но матчим по пхукетской штатке
ph_funnels = []
for mgr, periods in per_broker.items():
    match = ph_norm.get(norm(mgr))
    if not match: continue
    total_all = sum(sum(v['n'] for v in stgs.values()) for stgs in periods.get('all', {}).values())
    if total_all < 20: continue
    pos = match.get('pos', '')
    per_out = {}
    for pname, regions in periods.items():
        regs, tot_n, tot_b = {}, defaultdict(int), defaultdict(float)
        for region, stages in regions.items():
            regs[region] = {stg: {'n': v['n'], 'budget': v['budget']} for stg, v in stages.items()}
            for stg, v in stages.items():
                tot_n[stg] += v['n']; tot_b[stg] += v['budget']
        regs['ALL'] = {stg: {'n': tot_n[stg], 'budget': tot_b[stg]} for stg in tot_n}
        per_out[pname] = regs
    fl = first_last.get(mgr, ('', ''))
    ph_funnels.append({'name': match['name'], 'role': 'qualifier' if 'квалификатор' in pos else 'broker',
                       'position': pos, 'first_lead': fl[0], 'last_lead': fl[1], 'periods': per_out})
for b in ph_funnels:                                    # тот же пересчёт WON по дате закрытия
    src = nwbn.get(norm(b['name']), {})
    for period, regs in b.get('periods', {}).items():
        override = src.get(period, {})
        all_n = sum(v['n'] for v in override.values()); all_b = sum(v['budget'] for v in override.values())
        for rn, stages in regs.items():
            if rn == 'ALL': stages['WON'] = {'n': all_n, 'budget': all_b}
            else:
                v = override.get(rn, {'n': 0, 'budget': 0})
                stages['WON'] = {'n': v['n'], 'budget': v['budget']}

# 6.4b доходность брокера — та же формула, что в «Статистике по брокерам» Бали:
# (маржа − реклама) / выручка. Выручка на Пхукете — это комиссия компании.
for year, brokers in ph_by_broker.items():
    for name, d in brokers.items():
        spend = ph_broker_spend.get(year, {}).get(norm(name), 0.0)
        d['ad_spend'] = round(spend, 2)
        d['yield_pct'] = round(100 * (d['margin'] - spend) / d['commission'], 1) if d['commission'] else None
        ad_m = ph_ad_margin.get(year, {}).get(name, 0.0)
        d['ad_margin'] = round(ad_m, 2)
        d['romi'] = round(ad_m / spend, 2) if spend else None
        d['margin'] = round(d['margin'], 2)

top_campaigns = sorted(({'year': y, 'name': n, **v} for (y, n), v in ph_campaigns.items()),
                       key=lambda c: -c['spend'])[:25]
(DATA / 'phuket.json').write_text(json.dumps({
    'staff': ph_staff, 'dates': ph_dates,
    'totals': {y: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items()} for y, d in ph_deals.items()},
    'by_broker': ph_by_broker, 'sources': ph_sources, 'source_labels': SOURCE_LABELS,
    'months': {y: dict(m) for y, m in ph_months.items()},
    'ads': ph_ads, 'roi': ph_roi, 'campaigns': top_campaigns, 'funnels': ph_funnels,
    'broker_spend': {y: dict(v) for y, v in ph_broker_spend.items()},
}, ensure_ascii=False, indent=2))
print(f'   phuket: {len(ph_staff)} в штате, {sum(d["deals"] for d in ph_deals.values())} сделок, '
      f'{len(ph_funnels)} воронок, реклама по {len(ph_campaigns)} кампаниям')

# ── 7. Рейтинг брокеров: сделки Бали × актуальная штатка ─
print('7. Fetch broker rating...')

# 7.1 актуальная штатка: верхний блок листа «staff Bali» до строки «Подрядчики»
#     (ниже неё идут подрядчики и блок уволенных), плюс пустая дата увольнения.
RATING_SHEETS_OP = ['ОП1', 'ОП2', 'ОП3', 'ОП4', 'Другие']       # отделы: полный реестр
RATING_SHEETS_ALL = ['ВСЕ сделки весь период', ' ВСЕ сделки 2025',
                     'ВСЕ сделки сентябрь-май']                  # сводные: почти целиком дубли ОП
LEAD_POS = ('руководитель отдела продаж', 'head of product')
DEAL_ALIASES = {'семчук': 'Владислав Семчук'}                    # как записано в реестре сделок

rt_staff, rt_rows = [], gc.open_by_key(STAFF_ID).worksheet('staff Bali').get_all_values()
for r in rt_rows[1:]:
    r = r + [''] * 20
    name = r[2].strip()
    if name == 'Подрядчики': break                               # конец блока действующих
    if not name: continue
    if re.search(r'\d{4}', r[16]): continue                      # дата увольнения (не почта из съехавшей строки)
    pos = r[6].strip()
    low = pos.lower()
    role = ('broker' if 'менеджер по продажам' in low
            else 'lead' if any(k in low for k in LEAD_POS) else None)
    if not role: continue                                        # квалификаторы, ассистенты, бэк-офис
    rt_staff.append({'name': name, 'pos': pos, 'role': role, 'dept': r[12].strip(),
                     'head': r[5].strip(), 'start': r[0].strip(), 'tenure_months': num(r[1])})
rt_by_norm = {norm(s['name']): s for s in rt_staff}

# 7.2 сделки: строка = сделка, если есть менеджер и цена объекта > 0, а год похож на год
#     (так отсекаются строки-итоги «маркет»/«прочее»). Всё после «НАРАБОТКИ» — воронка, не сделки.
sh_sd = gc.open_by_key(SDELKI_ID)


def rt_deals(title):
    out = []
    for i, r in enumerate(sh_sd.worksheet(title).get_all_values()):
        if i == 0: continue
        r = r + [''] * 70
        if any('НАРАБОТКИ' in c for c in r[:5]): break
        year, month, mgr, price = r[1].strip(), r[0].strip(), r[3].strip(), num(r[9])
        if not re.fullmatch(r'20\d\d', year) or not mgr or not price or price <= 0: continue
        out.append({'y': int(year), 'm': int(num(month) or 0), 'mgr': DEAL_ALIASES.get(mgr.lower(), mgr),
                    'price': price, 'comm': num(r[13]) or 0.0,
                    'key': (int(year), int(num(month) or 0), round(price),
                            re.sub(r'\s+', ' ', r[8].strip().lower()),
                            re.sub(r'\W+', '', r[7].lower()))})
    return out


rt_seen, rt_deal_rows = set(), []
for title in RATING_SHEETS_OP + RATING_SHEETS_ALL:      # ОП идут первыми: они и есть источник правды
    for d in rt_deals(title):
        if d['key'] in rt_seen: continue                # тот же клиент, объект, месяц и сумма — одна сделка
        rt_seen.add(d['key'])
        rt_deal_rows.append(d)

CUR_Y, CUR_M = date.today().year, date.today().month
rt_future = sum(1 for d in rt_deal_rows if (d['y'], d['m']) > (CUR_Y, CUR_M))
rt_deal_rows = [d for d in rt_deal_rows if (d['y'], d['m']) <= (CUR_Y, CUR_M)]


def rt_bucket():
    return defaultdict(lambda: [0, 0.0, 0.0])           # 'YYYY-MM' → [сделок, оборот, комиссия]


rt_months, rt_company, rt_outside = defaultdict(rt_bucket), rt_bucket(), defaultdict(lambda: [0, 0.0, 0.0])
for d in rt_deal_rows:
    mk = f"{d['y']}-{d['m']:02d}"
    who = rt_by_norm.get(norm(d['mgr']))
    for b in ([rt_company[mk]] + ([rt_months[who['name']][mk]] if who else [rt_outside[mk]])):
        b[0] += 1; b[1] += d['price']; b[2] += d['comm']

for s in rt_staff:
    s['months'] = {k: [v[0], round(v[1], 2), round(v[2], 2)]
                   for k, v in sorted(rt_months.get(s['name'], {}).items())}

(DATA / 'rating.json').write_text(json.dumps({
    'cur_year': CUR_Y, 'cur_month': CUR_M,
    'brokers': rt_staff,
    'company': {k: [v[0], round(v[1], 2), round(v[2], 2)] for k, v in sorted(rt_company.items())},
    'outside': {k: [v[0], round(v[1], 2), round(v[2], 2)] for k, v in sorted(rt_outside.items())},
}, ensure_ascii=False, indent=2))
print(f'   rating: {len(rt_staff)} действующих ({sum(1 for s in rt_staff if s["role"] == "broker")} брокеров), '
      f'{len(rt_deal_rows)} сделок в реестре, {rt_future} отброшено как будущие месяцы')


# ── 8. План на месяц: СНГ vs Международное ───────────
print('8. Fetch monthly plan (СНГ / международное)...')

LEADS_REQUEST_ID = '1tMJKZI4Jt1OZQxIlXs_Mx-mt1G2tdlT34H-uCbQ-cI0'
LEADS_REQUEST_SHEET = 'Запрос на лиды сентябрь 2026'   # обновлять вручную с новым месяцем


def lr_find(rows, label):
    for r in rows:
        if len(r) > 1 and r[1].strip() == label:
            return r
    return None


def lr_get(row, idx):
    return num(row[idx]) if row and len(row) > idx else None


lr_rows = gc.open_by_key(LEADS_REQUEST_ID).worksheet(LEADS_REQUEST_SHEET).get_all_values()
lr_sng, lr_intl, lr_total = (lr_find(lr_rows, 'План СНГ + PL'), lr_find(lr_rows, 'План Англ'),
                              lr_find(lr_rows, 'Всего'))
lr_month_label = re.sub(r'^Запрос на лиды\s*', '', LEADS_REQUEST_SHEET).strip()

month_plan = {
    'month_label': lr_month_label,
    'segments': [
        {'key': 'sng', 'label': 'СНГ + PL', 'leads': lr_get(lr_sng, 3), 'conv': lr_get(lr_sng, 4),
         'avg_check': lr_get(lr_sng, 5), 'plan': lr_get(lr_sng, 6)},
        {'key': 'intl', 'label': 'Международное (англ)', 'leads': lr_get(lr_intl, 3), 'conv': lr_get(lr_intl, 4),
         'avg_check': lr_get(lr_intl, 5), 'plan': lr_get(lr_intl, 6)},
    ],
    'total_plan': lr_get(lr_total, 6),
}
(DATA / 'month_plan.json').write_text(json.dumps(month_plan, ensure_ascii=False, indent=2))
print(f'   month plan ({lr_month_label}): СНГ ${month_plan["segments"][0]["plan"]:,.0f}, '
      f'Intl ${month_plan["segments"][1]["plan"]:,.0f}')

print('\nAll data fetched to data/*.json')
