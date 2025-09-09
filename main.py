
import os
import json
import base64
import httpx
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from lxml import etree
from telegram import Bot

# Read env
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
INSALES_SHOP_DOMAIN = os.getenv("INSALES_SHOP_DOMAIN")
INSALES_API_KEY = os.getenv("INSALES_API_KEY")
INSALES_API_PASSWORD = os.getenv("INSALES_API_PASSWORD")

# Log missing envs to help debugging on Render
_missing = [k for k, v in {
    "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    "INSALES_SHOP_DOMAIN": INSALES_SHOP_DOMAIN,
    "INSALES_API_KEY": INSALES_API_KEY,
    "INSALES_API_PASSWORD": INSALES_API_PASSWORD,
}.items() if not v]
if _missing:
    print("Missing env vars:", ", ".join(_missing))

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
app = FastAPI(title="InSales → Telegram notifier")

def basic_auth_header(api_key: str, password: str) -> Dict[str, str]:
    token = base64.b64encode(f"{api_key}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

async def fetch_order(order_id: int) -> Optional[Dict[str, Any]]:
    \"\"\"Fetch order details from InSales Admin API.\"\"\"
    if not all([INSALES_SHOP_DOMAIN, INSALES_API_KEY, INSALES_API_PASSWORD]):
        return None
    url = f"https://{INSALES_SHOP_DOMAIN}/admin/orders/{order_id}.json"
    headers = {"Accept": "application/json", **basic_auth_header(INSALES_API_KEY, INSALES_API_PASSWORD)}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
        return None

async def send_tg(text: str) -> None:
    if bot and TELEGRAM_CHAT_ID:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, disable_web_page_preview=True)

def parse_order_id_from_xml(xml_bytes: bytes) -> Optional[int]:
    try:
        root = etree.fromstring(xml_bytes)
        candidates = root.xpath("//*[local-name()='order-id' or local-name()='order_id' or local-name()='id']")
        for el in candidates:
            try:
                return int((el.text or "").strip())
            except Exception:
                continue
    except Exception:
        return None
    return None

def format_order_message(order: Dict[str, Any]) -> str:
    number = order.get("number") or order.get("id")
    total = order.get("total_price") or order.get("total-price") or order.get("total")
    currency = order.get("currency") or order.get("currency_code") or ""
    client = order.get("client") or {}
    email = client.get("email") or order.get("email") or "—"
    phone = client.get("phone") or order.get("phone") or "—"
    name = (client.get("name") or client.get("full_name") or "—").strip()
    items = order.get("line_items") or order.get("line-items") or []
    items_lines = []
    for it in items:
        title = it.get("title") or it.get("product_title") or "Товар"
        qty = it.get("quantity") or it.get("quantity_value") or 1
        price = it.get("price") or it.get("sale_price") or ""
        items_lines.append(f"• {title} × {qty} @ {price}")
    items_text = "\\n".join(items_lines) if items_lines else "(позиции не распознаны)"
    return (
        f"🛒 Новый заказ #{number}\\n"
        f"Сумма: {total} {currency}\\n"
        f"Покупатель: {name}\\n"
        f"Email: {email} | Тел: {phone}\\n\\n"
        f"Товары:\\n{items_text}"
    )

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/insales/webhooks")
async def insales_webhook(request: Request, content_type: Optional[str] = Header(default=None, alias="Content-Type")):
    body = await request.body()
    order_id: Optional[int] = None

    # Try JSON
    if content_type and "json" in content_type.lower():
        try:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict):
                if "order" in payload and isinstance(payload["order"], dict):
                    order_id = payload["order"].get("id") or payload["order"].get("order_id")
                order_id = order_id or payload.get("id") or payload.get("order_id")
        except Exception:
            pass

    # Fallback to XML
    if order_id is None:
        order_id = parse_order_id_from_xml(body)

    if order_id is None:
        return JSONResponse({"status": "ignored", "reason": "order_id_not_found"}, status_code=202)

    order = await fetch_order(int(order_id))
    if not order:
        await send_tg(f"🛎 Получено событие по заказу ID {order_id}, но детали не удалось загрузить по API.")
        return {"ok": True, "fetched": False}

    text = format_order_message(order)
    await send_tg(text)
    return {"ok": True}
