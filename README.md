# Loki + Grafana — мониторинг логов криптобиржи

Стек для сбора, хранения и визуализации логов тестового приложения (эмулятор криптобиржи) с прямой отправкой логов в Loki через HTTP POST — **без Promtail**.

## Архитектура

```
┌─────────────┐    HTTP POST     ┌──────────┐    ┌──────────┐
│  app        │ ──────────────►  │  Loki    │ ◄─ │ Grafana  │
│  (Python)   │  /loki/api/v1/   │  :3100   │    │  :3000   │
│  crypto-    │  push            │          │    │          │
│  backend    │                  └──────────┘    └──────────┘
└─────────────┘
```

| Компонент | Образ | Порт | Назначение |
|-----------|-------|------|------------|
| **app** (crypto-backend) | Python 3.12-slim | — | Эмулятор криптобиржи, отправляет логи напрямую в Loki |
| **Loki** | grafana/loki:3.0.0 | 3100 | Хранилище логов |
| **Grafana** | grafana/grafana:11.0.0 | 3000 | Визуализация (дашборды, Explore) |

## Структура проекта

```
Loki+Grafana/
├── docker-compose.yml              # Оркестрация сервисов
├── app/
│   ├── Dockerfile                  # Образ Python + requests
│   └── main.py                     # Эмулятор криптобиржи + send_log_to_loki()
├── config/
│   ├── loki.yaml                   # Конфигурация Loki
│   ├── grafana-datasources.yaml    # Автопровижининг Data Source Loki (uid: loki-ds)
│   ├── grafana-dashboards.yaml     # Автопровижининг дашбордов
│   ├── promtail.yaml               # Конфиг Promtail (не используется, оставлен для справки)
│   └── dashboards/
│       └── loki-logs-dashboard.json  # Дашборд: таблица логов + 2 pie chart
```

## Быстрый старт

### 1. Запуск стека

```bash
cd Loki+Grafana
docker compose up -d --build
```

### 2. Проверка компонентов

```bash
# Loki готов?
curl http://localhost:3100/ready
# Ожидается: ready

# Логи приложения идут?
docker logs --tail 10 crypto-backend

# Логи дошли в Loki?
curl -s -G "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={service="crypto-backend"}' \
  --data-urlencode "start=$(date -d '5 min ago' +%s)000000000" \
  --data-urlencode "end=$(date +%s)000000000" \
  --data-urlencode 'limit=3'
```

### 3. Grafana

- URL: `http://<server-ip>:3000`
- Логин/пароль: `admin` / `admin`
- Data Source **Loki** (uid `loki-ds`) создаётся автоматически
- Дашборд **«Crypto Backend — Loki Logs»** загружается автоматически
- Explore: выберите datasource **Loki**, запрос `{service="crypto-backend"}`

## Прямая отправка логов в Loki (без Promtail)

### Структура payload

```json
{
  "streams": [
    {
      "stream": {
        "service": "crypto-backend",
        "level": "info"
      },
      "values": [
        ["1787171267380718968", "{\"event\": \"price_tick\", ...}"]
      ]
    }
  ]
}
```

- `stream` — labels (ключ-значение)
- `values` — массив `[timestamp_ns, message]`, timestamp в наносекундах (строка)

### Ручная отправка через curl

```bash
TS=$(python3 -c "import time; print(time.time_ns())")

curl -X POST "http://localhost:3100/loki/api/v1/push" \
  -H "Content-Type: application/json" \
  -d "{
    \"streams\": [{
      \"stream\": {\"service\": \"crypto-backend\", \"level\": \"warning\"},
      \"values\": [[\"$TS\", \"Manual test log message\"]]
    }]
  }"
```

Ожидаемый ответ: **HTTP 204** (No Content — успех).

### В приложении (main.py)

Функция `send_log_to_loki()` отправляет каждое лог-событие через `requests.post()`.
Класс `LokiHandler(logging.Handler)` автоматически перехватывает все записи логгера и дублирует их в Loki.

```python
# Переменная окружения (опционально)
LOKI_URL=http://loki:3100/loki/api/v1/push   # по умолчанию (внутри Docker)
LOKI_URL=http://localhost:3100/loki/api/v1/push  # при запуске с хоста
```

## Запуск приложения без Docker

```bash
cd app
pip install requests
LOKI_URL="http://localhost:3100/loki/api/v1/push" python -u main.py
```

Остановить: `Ctrl+C`

## Дашборд

**«Crypto Backend — Loki Logs»** (uid: `crypto-backend-loki-logs`)

| Панель | Тип | LogQL |
|--------|-----|-------|
| Service logs (real-time) | Таблица логов | `{service="crypto-backend"}` |
| Log levels distribution | Pie chart | `sum by (level) (count_over_time({service="crypto-backend"}[$__auto]))` |
| Events distribution | Donut chart | `sum by (event) (count_over_time({service="crypto-backend"} \| json \| __error__="" [$__auto]))` |

- Автообновление: каждые **5 секунд**
- Временной диапазон: последние **15 минут**

## LogQL — полезные запросы

```logql
# Все логи
{service="crypto-backend"}

# Только ошибки
{service="crypto-backend"} |= "error"

# По уровню
{service="crypto-backend", level="error"}

# Количество логов по уровням за 15 минут
sum by (level) (count_over_time({service="crypto-backend"}[15m]))

# Количество событий (JSON-поле event)
sum by (event) (count_over_time({service="crypto-backend"} | json | __error__="" [15m]))

# Фильтр по конкретному событию
{service="crypto-backend"} | json | event="order_created"
```

## Управление стеком

```bash
# Остановить
docker compose down

# Остановить и удалить данные (volumes)
docker compose down -v

# Пересобрать приложение после изменений
docker compose up -d --build app

# Перезапустить Grafana
docker compose restart grafana
```

## Технологии

- Docker Compose
- Loki 3.0.0 (boltdb-shipper, filesystem storage)
- Grafana 11.0.0 (автопровижининг datasources + dashboards)
- Python 3.12 + requests (прямая отправка логов через HTTP POST)
