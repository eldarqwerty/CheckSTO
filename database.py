import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "checksto.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def generate_token() -> str:
    return f"sto-{secrets.token_hex(3)}"


def compute_next_service(mileage: int, base_dt: Optional[datetime] = None) -> tuple[str, int]:
    dt = base_dt or datetime.now()
    next_date = (dt + timedelta(days=180)).strftime("%d.%m.%Y")
    next_mileage = int(mileage) + 8000
    return next_date, next_mileage


def init_db() -> None:
    """Создаёт таблицы SQLite и заполняет демо-данными, если база пустая."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                plate_number TEXT NOT NULL,
                car_model TEXT NOT NULL,
                mileage INTEGER NOT NULL DEFAULT 0,
                client_name TEXT NOT NULL,
                client_phone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'diagnostics',
                master_note TEXT DEFAULT '',
                estimated_completion TEXT DEFAULT 'Сегодня до 18:30',
                approved_at TEXT DEFAULT NULL,
                total_approved INTEGER NOT NULL DEFAULT 0,
                next_service_date TEXT DEFAULT '',
                next_service_mileage INTEGER NOT NULL DEFAULT 0,
                reminder_sent INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'mandatory',
                price INTEGER NOT NULL DEFAULT 0,
                is_approved INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS order_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                photo_type TEXT NOT NULL DEFAULT 'before',
                file_path TEXT NOT NULL,
                caption TEXT DEFAULT '',
                FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS service_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                visit_date TEXT NOT NULL,
                mileage INTEGER NOT NULL,
                summary TEXT NOT NULL,
                total_cost INTEGER NOT NULL
            );
            """
        )
        conn.commit()

        count = cursor.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        if count == 0:
            seed_demo_data(conn)
    finally:
        conn.close()


def seed_demo_data(conn: sqlite3.Connection) -> None:
    """Заполняет базу 4 реалистичными заказами (Жезказган, область Ұлытау — регион 20)."""
    now = datetime.now()
    today_str = now.strftime("%d.%m.%Y %H:%M")
    yesterday_str = (now - timedelta(days=1)).strftime("%d.%m.%Y %H:%M")
    approved_time_str = (now - timedelta(hours=2, minutes=15)).strftime("%d.%m.%Y в %H:%M")
    completed_approved_str = (now - timedelta(days=1, hours=4)).strftime("%d.%m.%Y в %H:%M")

    # Даты следующего ТО: часть клиентов уже «подходит к ТО» для вкладки Автовозврат ТО
    due_soon_1 = (now + timedelta(days=5)).strftime("%d.%m.%Y")
    due_soon_2 = (now + timedelta(days=11)).strftime("%d.%m.%Y")
    future_date_1 = (now + timedelta(days=180)).strftime("%d.%m.%Y")
    future_date_2 = (now + timedelta(days=175)).strftime("%d.%m.%Y")

    orders_data: List[Dict[str, Any]] = [
        {
            "token": "sto-84a2f",
            "plate_number": "512 BDA 20",
            "car_model": "Toyota Camry 70 (2.5)",
            "mileage": 118400,
            "client_name": "Ерлан Сатыбалдин",
            "client_phone": "+77014582910",
            "status": "pending_approval",
            "master_note": "Камри 70, замена масла 5W-30 4.5л, фильтр масляный, порван передний левый пыльник ШРУС (вытекла смазка), передние тормозные колодки стерты до 2 мм, салонный фильтр грязный.",
            "estimated_completion": "Сегодня до 18:30",
            "approved_at": None,
            "total_approved": 0,
            "next_service_date": future_date_1,
            "next_service_mileage": 126400,
            "reminder_sent": 0,
            "created_at": today_str,
            "items": [
                {"title": "Замена пыльника наружного ШРУС (левого) + смазка", "category": "mandatory", "price": 18500, "is_approved": 1},
                {"title": "Замена передних тормозных колодок (комплект + работа)", "category": "mandatory", "price": 28000, "is_approved": 1},
                {"title": "Замена моторного масла Toyota 5W-30 (4.5 л) и фильтра", "category": "mandatory", "price": 32500, "is_approved": 1},
                {"title": "Замена салонного угольного фильтра", "category": "recommended", "price": 7500, "is_approved": 1},
                {"title": "Компьютерная диагностика и проверка развал-схождения", "category": "recommended", "price": 12000, "is_approved": 0},
            ],
            "photos": [
                {
                    "photo_type": "before",
                    "file_path": "/static/demo_photos/cv_boot_tear.svg",
                    "caption": "Сквозная трещина пыльника левого ШРУС — вытекла смазка, риск выхода гранаты из строя",
                },
                {
                    "photo_type": "before",
                    "file_path": "/static/demo_photos/brake_pads_worn.svg",
                    "caption": "Остаток передних тормозных колодок менее 2 мм — критический износ",
                },
            ],
        },
        {
            "token": "sto-39c7e",
            "plate_number": "304 KZA 20",
            "car_model": "Hyundai Tucson (2.0 AWD)",
            "mileage": 86200,
            "client_name": "Айгуль Нурпеисова",
            "client_phone": "+77027741855",
            "status": "approved",
            "master_note": "Туксон, стук в передней подвеске на кочках, потекла правая передняя стойка амортизатора, износ стоек стабилизатора, нужен развал-схождение.",
            "estimated_completion": "Сегодня до 19:00",
            "approved_at": approved_time_str,
            "total_approved": 74000,
            "next_service_date": due_soon_1,
            "next_service_mileage": 94200,
            "reminder_sent": 0,
            "created_at": today_str,
            "items": [
                {"title": "Замена передних амортизаторов (пара, KYB + работа)", "category": "mandatory", "price": 54000, "is_approved": 1},
                {"title": "Замена стоек стабилизатора (2 шт.)", "category": "mandatory", "price": 12000, "is_approved": 1},
                {"title": "Регулировка 3D развал-схождения", "category": "recommended", "price": 8000, "is_approved": 1},
            ],
            "photos": [
                {
                    "photo_type": "before",
                    "file_path": "/static/demo_photos/shock_absorber_leak.svg",
                    "caption": "Запотевание и течь масла на правом переднем амортизаторе",
                },
            ],
        },
        {
            "token": "sto-71d4b",
            "plate_number": "889 MNA 20",
            "car_model": "Kia K5 (2.5 GDI)",
            "mileage": 64500,
            "client_name": "Дамир Жумабеков",
            "client_phone": "+77773109422",
            "status": "completed",
            "master_note": "Киа К5, плановое ТО-60: замена масла в ДВС, замена тормозной жидкости, замена передних колодок, течь прокладки клапанной крышки.",
            "estimated_completion": "Готово к выдаче",
            "approved_at": completed_approved_str,
            "total_approved": 89500,
            "next_service_date": due_soon_2,
            "next_service_mileage": 72500,
            "reminder_sent": 0,
            "created_at": yesterday_str,
            "items": [
                {"title": "Замена прокладки клапанной крышки + очистка посадочной", "category": "mandatory", "price": 24000, "is_approved": 1},
                {"title": "Плановое ТО: масло 5W-30, масляный и воздушный фильтры", "category": "mandatory", "price": 34500, "is_approved": 1},
                {"title": "Замена передних тормозных колодок Hi-Q", "category": "mandatory", "price": 21000, "is_approved": 1},
                {"title": "Аппаратная замена тормозной жидкости DOT-4", "category": "recommended", "price": 10000, "is_approved": 1},
            ],
            "photos": [
                {
                    "photo_type": "before",
                    "file_path": "/static/demo_photos/oil_leak_gasket.svg",
                    "caption": "Подтёк масла по периметру прокладки клапанной крышки",
                },
                {
                    "photo_type": "before",
                    "file_path": "/static/demo_photos/brake_pads_worn.svg",
                    "caption": "Изношенные передние колодки до замены",
                },
                {
                    "photo_type": "after",
                    "file_path": "/static/demo_photos/engine_bay_clean_after.svg",
                    "caption": "Установлена новая прокладка, подтёки устранены, узел очищен",
                },
                {
                    "photo_type": "after",
                    "file_path": "/static/demo_photos/new_brake_pads_after.svg",
                    "caption": "Установлен новый комплект колодок, направляющие смазаны",
                },
            ],
        },
        {
            "token": "sto-52f9a",
            "plate_number": "147 VNA 20",
            "car_model": "Chevrolet Cobalt (1.5 AT)",
            "mileage": 142800,
            "client_name": "Максат Омаров",
            "client_phone": "+77056238190",
            "status": "diagnostics",
            "master_note": "Кобальт, жалобы на вибрацию на холостом ходу и повышенный расход топлива. Идёт диагностика свечей, катушки и дроссельной заслонки.",
            "estimated_completion": "Завтра до 13:00",
            "approved_at": None,
            "total_approved": 0,
            "next_service_date": future_date_2,
            "next_service_mileage": 150800,
            "reminder_sent": 0,
            "created_at": today_str,
            "items": [
                {"title": "Компьютерная диагностика ЭБУ и проверка зажигания", "category": "mandatory", "price": 6000, "is_approved": 1},
                {"title": "Чистка дроссельной заслонки с адаптацией", "category": "mandatory", "price": 9500, "is_approved": 1},
                {"title": "Замена комплекта свечей зажигания (4 шт., NGK)", "category": "recommended", "price": 14000, "is_approved": 1},
            ],
            "photos": [
                {
                    "photo_type": "before",
                    "file_path": "/static/demo_photos/oil_leak_gasket.svg",
                    "caption": "Нагар и масляный налёт в зоне дроссельного узла",
                },
            ],
        },
    ]

    cursor = conn.cursor()
    for order in orders_data:
        cursor.execute(
            """
            INSERT INTO orders (
                token, plate_number, car_model, mileage, client_name, client_phone,
                status, master_note, estimated_completion, approved_at, total_approved,
                next_service_date, next_service_mileage, reminder_sent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["token"],
                order["plate_number"],
                order["car_model"],
                order["mileage"],
                order["client_name"],
                order["client_phone"],
                order["status"],
                order["master_note"],
                order["estimated_completion"],
                order["approved_at"],
                order["total_approved"],
                order["next_service_date"],
                order["next_service_mileage"],
                order["reminder_sent"],
                order["created_at"],
            ),
        )
        order_id = cursor.lastrowid

        for item in order["items"]:
            cursor.execute(
                """
                INSERT INTO order_items (order_id, title, category, price, is_approved)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, item["title"], item["category"], item["price"], item["is_approved"]),
            )

        for photo in order["photos"]:
            cursor.execute(
                """
                INSERT INTO order_photos (order_id, photo_type, file_path, caption)
                VALUES (?, ?, ?, ?)
                """,
                (order_id, photo["photo_type"], photo["file_path"], photo["caption"]),
            )

    history_rows = [
        ("512 BDA 20", "14.05.2026", 110200, "Плановое ТО: замена масла 5W-30, масляный и воздушный фильтры, диагностика ходовой", 36500),
        ("512 BDA 20", "19.11.2025", 101800, "Подготовка к зиме: замена антифриза, свечи зажигания Denso, шиномонтаж", 58000),
        ("512 BDA 20", "08.04.2025", 93400, "Замена масла в АКПП (частичная), замена задних тормозных колодок", 64000),
        ("304 KZA 20", "03.05.2026", 78100, "Замена масла в ДВС 5W-30, фильтр салона, балансировка колёс", 34000),
        ("304 KZA 20", "22.10.2025", 70400, "Замена тормозной жидкости, чистка форсунок, диагностика AWD", 42500),
        ("889 MNA 20", "12.05.2026", 56200, "Плановое ТО-55: масло ДВС, фильтры, проверка АКБ", 33000),
        ("889 MNA 20", "10.11.2025", 48000, "Сезонное обслуживание, замена щёток и салонного фильтра", 19500),
        ("147 VNA 20", "29.04.2026", 134500, "Замена комплекта ремня ГРМ, роликов и помпы охлаждения", 72000),
        ("147 VNA 20", "15.10.2025", 126100, "Замена масла 5W-40, фильтры, замена передних рычагов", 61500),
    ]
    cursor.executemany(
        """
        INSERT INTO service_history (plate_number, visit_date, mileage, summary, total_cost)
        VALUES (?, ?, ?, ?, ?)
        """,
        history_rows,
    )
    conn.commit()


def reset_demo_data() -> None:
    """Полностью очищает таблицы и восстанавливает эталонные демо-данные для питча."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.executescript(
            """
            DELETE FROM order_photos;
            DELETE FROM order_items;
            DELETE FROM orders;
            DELETE FROM service_history;
            DELETE FROM sqlite_sequence WHERE name IN ('orders', 'order_items', 'order_photos', 'service_history');
            """
        )
        conn.commit()
        seed_demo_data(conn)
    finally:
        conn.close()


def fetch_order_full(conn: sqlite3.Connection, where_clause: str, params: tuple) -> Optional[Dict[str, Any]]:
    row = conn.execute(f"SELECT * FROM orders WHERE {where_clause}", params).fetchone()
    if not row:
        return None
    order = dict(row)
    items = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM order_items WHERE order_id = ? ORDER BY CASE WHEN category = 'mandatory' THEN 0 ELSE 1 END, id ASC",
            (order["id"],),
        ).fetchall()
    ]
    for item in items:
        item["is_approved"] = bool(item["is_approved"])

    photos = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM order_photos WHERE order_id = ? ORDER BY id ASC",
            (order["id"],),
        ).fetchall()
    ]
    history = [
        dict(r)
        for r in conn.execute(
            "SELECT * FROM service_history WHERE plate_number = ? ORDER BY id ASC",
            (order["plate_number"],),
        ).fetchall()
    ]

    order["items"] = items
    order["photos"] = photos
    order["service_history"] = history
    order["estimated_total"] = sum(i["price"] for i in items)
    order["mandatory_total"] = sum(i["price"] for i in items if i["category"] == "mandatory")
    order["selected_total"] = sum(i["price"] for i in items if i["is_approved"])
    order["reminder_sent"] = bool(order.get("reminder_sent", 0))
    return order
