# Legion Real Estate — HR Dashboard

Ежедневно обновляемая сводка по команде брокеров Legion. Собирает данные из Google Sheets (маркетинг + разборы + штат) и BigQuery (CRM funnels + сделки), генерирует статический HTML, публикуется на GitHub Pages.

**URL**: https://elenazolotareva85-lab.github.io/legionrealestate_hr/

## Что показывает

- **Комиссия** — KPI команды, сигналы (жгут бюджет / просели / зелёная зона), таблица брокеров с разбором каждого
- **Воронки CRM** — 5 стадий (лид → квал → презентация → оффер → WON) на живых данных BigQuery
- **Разборы** — статистика записей + последние договорённости с ревьюером
- **Лиды по источникам** — `leads.html` — отдельный экран, разбивка по каналам + конверсия

## Как обновляется

GitHub Actions workflow (`.github/workflows/rebuild.yml`) запускается:
- Ежедневно в **06:00 UTC** (09:00 Europe/Sofia)
- Или вручную: **Actions → Rebuild dashboard → Run workflow**

Пайплайн:
1. `scripts/fetch_data.py` — тянет свежие данные из Sheets + BQ, пишет в `data/*.json`
2. `scripts/build.py` — собирает `index.html` и `leads.html` из шаблонов + данных
3. Автоматический commit + push, GitHub Pages сам подхватывает

## Секреты

Нужны два service account ключа в **Settings → Secrets → Actions**:

- `SHEETS_KEY` — доступ к Google Sheets (Turnir/Sheets/Staff/Razbory). Email: `sheets-reader@hermes-legion-helper.iam.gserviceaccount.com`
- `BQ_KEY` — доступ к BigQuery (`disco-bedrock-428721-f8`). Email: `dashboard-reader-ira@disco-bedrock-428721-f8.iam.gserviceaccount.com`

## Ручной запуск локально

```bash
export SHEETS_KEY_PATH=~/.config/legion-sheets/key.json
export BQ_KEY_PATH=~/.config/legion-sheets/ira-key.json
pip install -r scripts/requirements.txt
python scripts/fetch_data.py
python scripts/build.py
open index.html
```

## Файлы

```
├── .github/workflows/rebuild.yml    # ежедневный cron
├── scripts/
│   ├── fetch_data.py                # Sheets + BQ → data/*.json
│   ├── build.py                     # data/*.json + templates → index.html
│   └── requirements.txt
├── templates/
│   ├── komissia_base.html           # снапшот основного дашборда (обновляется вручную при структурных изменениях)
│   └── leads_base.html              # шаблон для leads.html
├── data/                            # генерируемые JSON (обновляются каждый прогон)
├── index.html                       # генерируемый — основной дашборд
└── leads.html                       # генерируемый — лиды по источникам
```

## Ограничения текущей версии

1. **Основная таблица Комиссии** (KPI / поперек лидов и сделок / доходность) берётся из шаблона `templates/komissia_base.html` — это снапшот. Ежедневно обновляются только **воронки CRM**, **разборы**, **сигналы**, **штат**, **даты стартов**, **лиды по источникам**.
   - Чтобы полностью автоматизировать пересбор таблицы из «Статистика по брокерам» — надо реализовать `render_komissia.py` (не в MVP-версии).
2. **Учёт разборов** (`razbory.json`) читает `data/razbory_raw.txt` — cached Markdown-дамп файла `Учет_разборов_брокеров.xlsx`. Обновляется вручную (Drive MCP → txt), либо через отдельную интеграцию с Drive API. В MVP — cached.
3. Публичный Pages = данные брокеров, ROI, выручка видны всем по URL. Не показывать URL публично.

## TODO / roadmap

- [ ] Отдельный скрипт для полного ре-рендера komissia_base.html
- [ ] Ротация razbory_raw.txt через Drive API (xlsx → text)
- [ ] Приватный Pages (требует GitHub Pro)
- [ ] E-mail нотификация о значительных дельтах день-ко-дню
