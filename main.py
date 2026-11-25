import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from ai_parser import parse_estimate_with_ai
from database import (
    BASE_DIR,
    compute_next_service,
    fetch_order_full,
    generate_token,
    get_connection,
    init_db,
    reset_demo_data,
)

load_dotenv(BASE_DIR / ".env")

UPLOADS_DIR = BASE_DIR / "uploads"
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "demo_photos").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="CheckSTO — Цифровой заказ-наряд для СТО", version="1.0.0")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

DEMO_PHOTO_PRESETS = {
    "before": [
        {
            "file_path": "/static/demo_photos/cv_boot_tear.svg",
            "caption": "Трещина пыльника ШРУС, вытекла смазка — требуется срочная замена",
        },
        {
            "file_path": "/static/demo_photos/brake_pads_worn.svg",
            "caption": "Критический износ передних тормозных колодок (остаток < 2 мм)",
        },
        {
            "file_path": "/static/demo_photos/oil_leak_gasket.svg",
            "caption": "Течь моторного масла по прокладке клапанной крышки",
        },
        {
            "file_path": "/static/demo_photos/shock_absorber_leak.svg",
            "caption": "Потёк передний амортизатор, потеря герметичности штока",
        },
    ],
    "after": [
        {
            "file_path": "/static/demo_photos/new_cv_boot_after.svg",
            "caption": "Установлен новый пыльник ШРУС, заложена свежая смазка и обжаты хомуты",
        },
        {
            "file_path": "/static/demo_photos/new_brake_pads_after.svg",
            "caption": "Установлены новые тормозные колодки, суппорт очищен и смазан",
        },
        {
            "file_path": "/static/demo_photos/engine_bay_clean_after.svg",
            "caption": "Прокладка заменена, следы масла полностью удалены",
        },
        {
            "file_path": "/static/demo_photos/suspension_fixed_after.svg",
            "caption": "Установлены новые стойки и выполнена регулировка развал-схождения",
        },
    ],
}


# ---------------------------------------------------------------------------
# Pydantic-схемы
# ---------------------------------------------------------------------------
class OrderItemIn(BaseModel):
    title: str
    category: str = "mandatory"
    price: int = 0
    is_approved: bool = True


class OrderCreate(BaseModel):
    plate_number: str
    car_model: str
    mileage: int = 0
    client_name: str
    client_phone: str
    status: str = "pending_approval"
    master_note: str = ""
    estimated_completion: str = "Сегодня до 18:30"
    items: List[OrderItemIn] = Field(default_factory=list)


class OrderUpdate(BaseModel):
    plate_number: Optional[str] = None
    car_model: Optional[str] = None
    mileage: Optional[int] = None
    client_name: Optional[str] = None
    client_phone: Optional[str] = None
    status: Optional[str] = None
    master_note: Optional[str] = None
    estimated_completion: Optional[str] = None
    items: Optional[List[OrderItemIn]] = None


class StatusUpdate(BaseModel):
    status: str


class AIParseRequest(BaseModel):
    note: str
    car_model: str = ""


class ClientApproveRequest(BaseModel):
    approved_item_ids: List[int] = Field(default_factory=list)


class DemoPhotoRequest(BaseModel):
    photo_type: str = "before"
    index: Optional[int] = None


# ---------------------------------------------------------------------------
# Инициализация БД при старте
# ---------------------------------------------------------------------------
@app.on_event("startup")
def on_startup() -> None:
    init_db()


# ---------------------------------------------------------------------------
# HTML-страницы
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html", {"request": request})


@app.get("/client/{token}", response_class=HTMLResponse)
async def client_page(request: Request, token: str) -> HTMLResponse:
    conn = get_connection()
    try:
        order = fetch_order_full(conn, "token = ?", (token,))
    finally:
        conn.close()
    return templates.TemplateResponse(request, "client.html", {"request": request, "token": token, "order_exists": order is not None},
    )


# ---------------------------------------------------------------------------
# API: Заказ-наряды и KPI для панели мастера
# ---------------------------------------------------------------------------
@app.get("/api/orders")
def list_orders(status: Optional[str] = None, search: Optional[str] = None) -> Dict[str, Any]:
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id FROM orders ORDER BY id DESC").fetchall()
        all_orders = [fetch_order_full(conn, "id = ?", (r["id"],)) for r in rows]
        all_orders = [o for o in all_orders if o is not None]

        # Динамический расчёт KPI
        active_in_box = sum(1 for o in all_orders if o["status"] in ("diagnostics", "pending_approval", "approved"))
        waiting_approval = sum(1 for o in all_orders if o["status"] == "pending_approval")
        approved_revenue = sum(
            o["total_approved"] for o in all_orders if o["status"] in ("approved", "completed")
        )

        # Клиенты к возврату на ТО (оценочный средний чек планового ТО 38 000 ₸)
        retention_clients = _build_retention_list(all_orders)
        retention_potential = sum(c["estimated_check"] for c in retention_clients)
        retention_returned = sum(c["estimated_check"] for c in retention_clients if c["reminder_sent"])

        # Фильтрация списка
        filtered = all_orders
        if status and status != "all":
            filtered = [o for o in filtered if o["status"] == status]
        if search and search.strip():
            q = search.strip().lower()
            filtered = [
                o
                for o in filtered
                if q in o["plate_number"].lower()
                or q in o["client_name"].lower()
                or q in o["car_model"].lower()
                or q in o["client_phone"].lower()
            ]

        return {
            "orders": filtered,
            "kpi": {
                "active_in_box": active_in_box,
                "waiting_approval": waiting_approval,
                "approved_revenue": approved_revenue,
                "retention_count": len(retention_clients),
                "retention_potential": retention_potential,
                "retention_returned": retention_returned,
            },
            "retention": retention_clients,
        }
    finally:
        conn.close()


def _build_retention_list(all_orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Формирует список клиентов с ближайшим плановым ТО для вкладки «Автовозврат ТО»."""
    result: List[Dict[str, Any]] = []
    now = datetime.now()
    for o in all_orders:
        days_left = 180
        try:
            dt = datetime.strptime(o["next_service_date"], "%d.%m.%Y")
            days_left = (dt - now).days
        except Exception:
            days_left = 30

        urgency = "soon" if days_left <= 14 else "planned"
        reason = (
            "Замена масла ДВС + сезонная диагностика"
            if days_left <= 14
            else "Плановое ТО через +8 000 км"
        )
        result.append(
            {
                "order_id": o["id"],
                "token": o["token"],
                "client_name": o["client_name"],
                "client_phone": o["client_phone"],
                "plate_number": o["plate_number"],
                "car_model": o["car_model"],
                "mileage": o["mileage"],
                "next_service_date": o["next_service_date"],
                "next_service_mileage": o["next_service_mileage"],
                "days_left": days_left,
                "urgency": urgency,
                "reason": reason,
                "estimated_check": 38500 if urgency == "soon" else 34000,
                "reminder_sent": o["reminder_sent"],
            }
        )
    result.sort(key=lambda x: x["days_left"])
    return result


@app.get("/api/orders/{order_id}")
def get_order(order_id: int) -> Dict[str, Any]:
    conn = get_connection()
    try:
        order = fetch_order_full(conn, "id = ?", (order_id,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")
        return order
    finally:
        conn.close()


@app.post("/api/orders")
def create_order(payload: OrderCreate) -> Dict[str, Any]:
    conn = get_connection()
    try:
        token = generate_token()
        next_date, next_mileage = compute_next_service(payload.mileage)
        created_at = datetime.now().strftime("%d.%m.%Y %H:%M")

        status = payload.status if payload.status in (
            "diagnostics",
            "pending_approval",
            "approved",
            "completed",
            "rejected",
        ) else "pending_approval"

        total_approved = (
            sum(i.price for i in payload.items if i.is_approved)
            if status in ("approved", "completed")
            else 0
        )

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO orders (
                token, plate_number, car_model, mileage, client_name, client_phone,
                status, master_note, estimated_completion, approved_at, total_approved,
                next_service_date, next_service_mileage, reminder_sent, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                token,
                payload.plate_number.strip().upper(),
                payload.car_model.strip(),
                int(payload.mileage),
                payload.client_name.strip(),
                payload.client_phone.strip(),
                status,
                payload.master_note.strip(),
                payload.estimated_completion.strip() or "Сегодня до 18:30",
                None,
                total_approved,
                next_date,
                next_mileage,
                created_at,
            ),
        )
        order_id = cursor.lastrowid

        for item in payload.items:
            if not item.title.strip():
                continue
            cat = item.category if item.category in ("mandatory", "recommended") else "mandatory"
            cursor.execute(
                """
                INSERT INTO order_items (order_id, title, category, price, is_approved)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, item.title.strip(), cat, max(0, int(item.price)), 1 if item.is_approved else 0),
            )

        conn.commit()
        order = fetch_order_full(conn, "id = ?", (order_id,))
        return order
    finally:
        conn.close()


@app.put("/api/orders/{order_id}")
def update_order(order_id: int, payload: OrderUpdate) -> Dict[str, Any]:
    conn = get_connection()
    try:
        existing = fetch_order_full(conn, "id = ?", (order_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")

        plate_number = (payload.plate_number or existing["plate_number"]).strip().upper()
        car_model = (payload.car_model or existing["car_model"]).strip()
        mileage = int(payload.mileage) if payload.mileage is not None else existing["mileage"]
        client_name = (payload.client_name or existing["client_name"]).strip()
        client_phone = (payload.client_phone or existing["client_phone"]).strip()
        status = payload.status or existing["status"]
        master_note = payload.master_note if payload.master_note is not None else existing["master_note"]
        estimated_completion = payload.estimated_completion or existing["estimated_completion"]
        next_date, next_mileage = compute_next_service(mileage)

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE orders
            SET plate_number = ?, car_model = ?, mileage = ?, client_name = ?,
                client_phone = ?, status = ?, master_note = ?, estimated_completion = ?,
                next_service_date = ?, next_service_mileage = ?
            WHERE id = ?
            """,
            (
                plate_number,
                car_model,
                mileage,
                client_name,
                client_phone,
                status,
                master_note,
                estimated_completion,
                next_date,
                next_mileage,
                order_id,
            ),
        )

        if payload.items is not None:
            cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
            for item in payload.items:
                if not item.title.strip():
                    continue
                cat = item.category if item.category in ("mandatory", "recommended") else "mandatory"
                cursor.execute(
                    """
                    INSERT INTO order_items (order_id, title, category, price, is_approved)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (order_id, item.title.strip(), cat, max(0, int(item.price)), 1 if item.is_approved else 0),
                )

            if status in ("approved", "completed"):
                new_total = sum(max(0, int(i.price)) for i in payload.items if i.is_approved and i.title.strip())
                cursor.execute("UPDATE orders SET total_approved = ? WHERE id = ?", (new_total, order_id))

        conn.commit()
        return fetch_order_full(conn, "id = ?", (order_id,))
    finally:
        conn.close()


@app.patch("/api/orders/{order_id}/status")
def update_order_status(order_id: int, payload: StatusUpdate) -> Dict[str, Any]:
    if payload.status not in ("diagnostics", "pending_approval", "approved", "completed", "rejected"):
        raise HTTPException(status_code=400, detail="Некорректный статус")

    conn = get_connection()
    try:
        existing = fetch_order_full(conn, "id = ?", (order_id,))
        if not existing:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")

        cursor = conn.cursor()
        if payload.status == "completed":
            total = existing["total_approved"] or existing["selected_total"]
            cursor.execute(
                "UPDATE orders SET status = ?, total_approved = ?, estimated_completion = ? WHERE id = ?",
                (payload.status, total, "Готово к выдаче", order_id),
            )
            # Добавляем запись в сервисную книжку, если её ещё не добавляли сегодня
            today = datetime.now().strftime("%d.%m.%Y")
            dup = cursor.execute(
                "SELECT id FROM service_history WHERE plate_number = ? AND visit_date = ?",
                (existing["plate_number"], today),
            ).fetchone()
            if not dup:
                approved_titles = [i["title"] for i in existing["items"] if i["is_approved"]]
                summary = ", ".join(approved_titles[:3]) or "Выполнен ремонт по заказ-наряду"
                cursor.execute(
                    """
                    INSERT INTO service_history (plate_number, visit_date, mileage, summary, total_cost)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (existing["plate_number"], today, existing["mileage"], summary, total),
                )
        else:
            cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (payload.status, order_id))

        conn.commit()
        return fetch_order_full(conn, "id = ?", (order_id,))
    finally:
        conn.close()


@app.post("/api/orders/{order_id}/reminder")
def mark_reminder_sent(order_id: int) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET reminder_sent = 1 WHERE id = ?", (order_id,))
        conn.commit()
        order = fetch_order_full(conn, "id = ?", (order_id,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")
        return {"ok": True, "order": order}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Фотофиксация (загрузка реального файла + быстрое демо-фото)
# ---------------------------------------------------------------------------
@app.post("/api/orders/{order_id}/photos")
async def upload_order_photo(
    order_id: int,
    file: UploadFile = File(...),
    photo_type: str = Form("before"),
    caption: str = Form(""),
) -> Dict[str, Any]:
    conn = get_connection()
    try:
        order = fetch_order_full(conn, "id = ?", (order_id,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")

        ptype = photo_type if photo_type in ("before", "after") else "before"
        ext = Path(file.filename or "photo.jpg").suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"):
            ext = ".jpg"

        filename = f"order_{order_id}_{ptype}_{secrets.token_hex(4)}{ext}"
        save_path = UPLOADS_DIR / filename
        content = await file.read()
        save_path.write_bytes(content)

        public_path = f"/uploads/{filename}"
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO order_photos (order_id, photo_type, file_path, caption)
            VALUES (?, ?, ?, ?)
            """,
            (order_id, ptype, public_path, caption.strip() or "Фотофиксация мастера"),
        )
        conn.commit()
        return fetch_order_full(conn, "id = ?", (order_id,))
    finally:
        conn.close()


@app.post("/api/orders/{order_id}/demo-photo")
def add_demo_photo(order_id: int, payload: DemoPhotoRequest) -> Dict[str, Any]:
    conn = get_connection()
    try:
        order = fetch_order_full(conn, "id = ?", (order_id,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")

        ptype = payload.photo_type if payload.photo_type in ("before", "after") else "before"
        presets = DEMO_PHOTO_PRESETS[ptype]
        existing_count = sum(1 for p in order["photos"] if p["photo_type"] == ptype)
        idx = payload.index if payload.index is not None else existing_count
        chosen = presets[idx % len(presets)]

        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO order_photos (order_id, photo_type, file_path, caption)
            VALUES (?, ?, ?, ?)
            """,
            (order_id, ptype, chosen["file_path"], chosen["caption"]),
        )
        conn.commit()
        return fetch_order_full(conn, "id = ?", (order_id,))
    finally:
        conn.close()


@app.delete("/api/orders/{order_id}/photos/{photo_id}")
def delete_order_photo(order_id: int, photo_id: int) -> Dict[str, Any]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM order_photos WHERE id = ? AND order_id = ?", (photo_id, order_id))
        conn.commit()
        order = fetch_order_full(conn, "id = ?", (order_id,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")
        return order
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: ИИ-смета за 3 секунды
# ---------------------------------------------------------------------------
@app.post("/api/ai/parse-estimate")
def ai_parse_estimate(payload: AIParseRequest) -> Dict[str, Any]:
    if not payload.note.strip():
        raise HTTPException(status_code=400, detail="Введите заметку мастера для разбора")
    return parse_estimate_with_ai(payload.note, payload.car_model)


# ---------------------------------------------------------------------------
# API: Клиентская страница (/client/{token})
# ---------------------------------------------------------------------------
@app.get("/api/client/{token}")
def get_client_order(token: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        order = fetch_order_full(conn, "token = ?", (token,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд по этой ссылке не найден")
        return order
    finally:
        conn.close()


@app.post("/api/client/{token}/approve")
def client_approve_order(token: str, payload: ClientApproveRequest) -> Dict[str, Any]:
    conn = get_connection()
    try:
        order = fetch_order_full(conn, "token = ?", (token,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")

        approved_set = set(payload.approved_item_ids)
        cursor = conn.cursor()
        total_approved = 0

        for item in order["items"]:
            # Обязательные позиции всегда входят в согласование
            is_checked = True if item["category"] == "mandatory" else (item["id"] in approved_set)
            cursor.execute(
                "UPDATE order_items SET is_approved = ? WHERE id = ?",
                (1 if is_checked else 0, item["id"]),
            )
            if is_checked:
                total_approved += int(item["price"])

        approved_at = datetime.now().strftime("%d.%m.%Y в %H:%M")
        cursor.execute(
            """
            UPDATE orders
            SET status = 'approved', approved_at = ?, total_approved = ?
            WHERE id = ?
            """,
            (approved_at, total_approved, order["id"]),
        )
        conn.commit()
        return fetch_order_full(conn, "id = ?", (order["id"],))
    finally:
        conn.close()


@app.post("/api/client/{token}/reject")
def client_reject_order(token: str) -> Dict[str, Any]:
    conn = get_connection()
    try:
        order = fetch_order_full(conn, "token = ?", (token,))
        if not order:
            raise HTTPException(status_code=404, detail="Заказ-наряд не найден")

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE orders SET status = 'rejected', total_approved = 0 WHERE id = ?",
            (order["id"],),
        )
        conn.commit()
        return fetch_order_full(conn, "id = ?", (order["id"],))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# API: Сброс демо-данных перед выступлением
# ---------------------------------------------------------------------------
@app.post("/api/demo/reset")
def api_reset_demo() -> JSONResponse:
    reset_demo_data()
    return JSONResponse({"ok": True, "message": "Демо-данные успешно восстановлены"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
