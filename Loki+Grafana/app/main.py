import logging
import random
import time
import json
import os
from datetime import datetime, timezone

import requests

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger("crypto-backend")

# === Прямая отправка логов в Loki (без Promtail) ===
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100/loki/api/v1/push")
SERVICE_NAME = "crypto-backend"


def send_log_to_loki(level: str, message: str, extra_labels: dict | None = None) -> bool:
    """
    Отправляет одно лог-событие напрямую в Loki через HTTP POST.
    Структура payload: streams -> stream(labels) -> values[[timestamp_ns, message]].
    Возвращает True при успехе, False при ошибке.
    """
    labels = {"service": SERVICE_NAME, "level": level}
    if extra_labels:
        labels.update(extra_labels)

    # Loki принимает timestamp в наносекундах (строка)
    ts_ns = str(time.time_ns())

    payload = {
        "streams": [
            {
                "stream": labels,
                "values": [[ts_ns, message]],
            }
        ]
    }

    try:
        resp = requests.post(LOKI_URL, json=payload, timeout=5)
        resp.raise_for_status()
        return True
    except Exception as exc:
        # Не роняем приложение при сбое Loki — выводим в stderr
        print(f"[send_log_to_loki] failed to push: {exc}", flush=True)
        return False


class LokiHandler(logging.Handler):
    """Обработчик логирования, дублирующий записи напрямую в Loki."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            level = record.levelname.lower()
            send_log_to_loki(level, message, extra_labels={"logger": record.name})
        except Exception:
            # Никогда не пробрасываем исключения из хендлера
            pass


# Подключаем Loki-хендлер к логгеру (вдобавок к консольному выводу)
logger.addHandler(LokiHandler())

# === Симулируемые данные ===
COINS = [
    {"symbol": "BTC",  "name": "Bitcoin",   "base_price": 67000.0},
    {"symbol": "ETH",  "name": "Ethereum",  "base_price": 3500.0},
    {"symbol": "BNB",  "name": "BNB",       "base_price": 600.0},
    {"symbol": "SOL",  "name": "Solana",    "base_price": 145.0},
    {"symbol": "XRP",  "name": "Ripple",    "base_price": 0.52},
    {"symbol": "ADA",  "name": "Cardano",   "base_price": 0.38},
    {"symbol": "DOGE", "name": "Dogecoin",  "base_price": 0.12},
    {"symbol": "AVAX", "name": "Avalanche", "base_price": 25.0},
]

USERS = ["user_001", "user_042", "user_1337", "user_2024", "user_777",
         "user_888", "user_055", "user_314", "user_271", "user_666"]

ORDER_TYPES = ["buy", "sell"]
ORDER_STATUSES = ["pending", "filled", "partial", "cancelled"]
ERROR_MESSAGES = [
    "Connection timeout to upstream node",
    "Rate limit exceeded for IP",
    "Insufficient liquidity in order book",
    "Invalid signature verification failed",
    "Database replication lag detected",
    "WebSocket connection dropped unexpectedly",
]


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def random_price(coin):
    """Генерирует цену с отклонением +-3% от базовой."""
    drift = random.uniform(-0.03, 0.03)
    return round(coin["base_price"] * (1 + drift), coin.get("decimals", 2))


def random_volume():
    """Случайный объём торгов."""
    return round(random.uniform(0.001, 15.0), 6)


def log_price_tick():
    """Эмуляция тика цены — как от ticker WebSocket потока."""
    coin = random.choice(COINS)
    price = random_price(coin)
    volume = random_volume()
    logger.info(
        json.dumps({
            "event": "price_tick",
            "symbol": coin["symbol"],
            "price": price,
            "volume_24h": volume,
            "timestamp": utcnow_iso(),
        })
    )


def log_order():
    """Эмуляция создания ордера пользователем."""
    coin = random.choice(COINS)
    order_type = random.choice(ORDER_TYPES)
    amount = round(random.uniform(0.01, 5.0), 6)
    price = random_price(coin)
    user = random.choice(USERS)
    status = random.choices(ORDER_STATUSES, weights=[10, 60, 15, 15])[0]
    order_id = f"ord_{random.randint(100000, 999999)}"

    logger.info(
        json.dumps({
            "event": "order_created",
            "order_id": order_id,
            "user": user,
            "symbol": coin["symbol"],
            "type": order_type,
            "amount": amount,
            "price": price,
            "total": round(amount * price, 2),
            "status": status,
            "timestamp": utcnow_iso(),
        })
    )

    # Иногда логируем дополнительное событие — частичное исполнение
    if status == "partial":
        filled = round(amount * random.uniform(0.2, 0.8), 6)
        logger.info(
            json.dumps({
                "event": "order_filled",
                "order_id": order_id,
                "filled_amount": filled,
                "remaining": round(amount - filled, 6),
                "timestamp": utcnow_iso(),
            })
        )


def log_balance_update():
    """Эмуляция обновления баланса кошелька."""
    user = random.choice(USERS)
    coin = random.choice(COINS)
    balance = round(random.uniform(0.001, 100.0), 6)
    change = round(random.uniform(-5.0, 5.0), 6)
    logger.info(
        json.dumps({
            "event": "balance_update",
            "user": user,
            "symbol": coin["symbol"],
            "balance": balance,
            "change": change,
            "timestamp": utcnow_iso(),
        })
    )


def log_api_request():
    """Эмуляция HTTP API запроса."""
    endpoints = ["/api/v1/ticker", "/api/v1/orderbook", "/api/v1/trades",
                 "/api/v1/balance", "/api/v1/order/create", "/api/v1/order/cancel",
                 "/api/v1/klines", "/api/v1/withdraw"]
    endpoint = random.choice(endpoints)
    method = random.choices(["GET", "POST", "DELETE"], weights=[60, 30, 10])[0]
    status_code = random.choices([200, 200, 200, 200, 400, 401, 429, 500], weights=[70, 5, 5, 5, 5, 3, 4, 3])[0]
    latency_ms = round(random.uniform(5, 350), 1)

    logger.info(
        json.dumps({
            "event": "api_request",
            "method": method,
            "endpoint": endpoint,
            "status": status_code,
            "latency_ms": latency_ms,
            "client_ip": f"192.168.{random.randint(1, 255)}.{random.randint(1, 255)}",
            "timestamp": utcnow_iso(),
        })
    )

    if status_code >= 500:
        logger.error(
            json.dumps({
                "event": "api_error",
                "endpoint": endpoint,
                "status": status_code,
                "error": random.choice(ERROR_MESSAGES),
                "timestamp": utcnow_iso(),
            })
        )


def log_withdrawal():
    """Эмуляция запроса на вывод средств."""
    user = random.choice(USERS)
    coin = random.choice(COINS)
    amount = round(random.uniform(0.01, 10.0), 6)
    tx_hash = "0x" + "".join(random.choices("0123456789abcdef", k=64))
    status = random.choices(["confirmed", "pending", "rejected"], weights=[70, 20, 10])[0]

    logger.info(
        json.dumps({
            "event": "withdrawal",
            "user": user,
            "symbol": coin["symbol"],
            "amount": amount,
            "tx_hash": tx_hash,
            "status": status,
            "timestamp": utcnow_iso(),
        })
    )


def log_system_health():
    """Эмуляция системных метрик."""
    logger.info(
        json.dumps({
            "event": "system_health",
            "cpu_load": round(random.uniform(5, 85), 1),
            "memory_mb": random.randint(200, 1800),
            "active_connections": random.randint(10, 500),
            "queue_size": random.randint(0, 120),
            "db_latency_ms": round(random.uniform(1, 45), 1),
            "timestamp": utcnow_iso(),
        })
    )


def main():
    """Главная функция — бесконечный цикл эмуляции работы криптобиржи."""
    logger.info(json.dumps({
        "event": "startup",
        "service": "crypto-backend",
        "version": "1.0.0",
        "message": "Crypto exchange backend started",
        "timestamp": utcnow_iso(),
    }))

    # Вероятности вызова разных событий
    events = [
        (log_price_tick,     35),  # чаще всего — тики цен
        (log_api_request,    25),  # API запросы
        (log_order,          15),  # ордера
        (log_balance_update, 10),  # обновления балансов
        (log_withdrawal,      5),  # выводы
        (log_system_health,  10),  # системные метрики
    ]

    tick = 0
    try:
        while True:
            # Выбираем событие по весам
            functions = [fn for fn, _ in events]
            weights = [w for _, w in events]
            fn = random.choices(functions, weights=weights)[0]
            fn()

            tick += 1

            # Каждые 50 тиков — краткая сводка
            if tick % 50 == 0:
                logger.info(json.dumps({
                    "event": "summary",
                    "tick": tick,
                    "message": f"Processed {tick} events",
                    "timestamp": utcnow_iso(),
                }))

            # Небольшая случайная задержка 0.2–1.5 сек
            time.sleep(random.uniform(0.2, 1.5))

    except KeyboardInterrupt:
        logger.info(json.dumps({
            "event": "shutdown",
            "message": "Crypto exchange backend stopped",
            "timestamp": utcnow_iso(),
        }))


if __name__ == "__main__":
    main()
