import os
import json
import base64
import httpx
from typing import Optional, Dict, Any, List, Tuple, Union
from fastapi import FastAPI, Request, Header
from fastapi.responses import JSONResponse
from lxml import etree
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS_RAW = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
DEFAULT_CHAT_IDS: List[str] = [cid.strip() for cid in TELEGRAM_CHAT_IDS_RAW.split(",") if cid.strip()]

INSALES_SHOP_DOMAIN = os.getenv("INSALES_SHOP_DOMAIN")
INSALES_API_KEY = os.getenv("INSALES_API_KEY")
INSALES_API_PASSWORD = os.getenv("INSALES_API_PASSWORD")

STATUS_FIELD = os.getenv("STATUS_FIELD", "").strip()
ALLOW_VALUES = [v.strip() for v in os.getenv("ALLOW_VALUES", "").split(",") if v.strip()]

STORES_JSON_RAW = os.getenv("STORES_JSON", "").strip()
STORES: Dict[str, Dict[str, Any]] = {}
if STORES_JSON_RAW:
    try:
        parsed = json.loads(STORES_JSON_RAW)
        for entry in parsed:
            domain = entry.get("domain")
            if domain:
                STORES[domain] = {
                    "api_key": entry.get("api_key"),
                    "api_password": entry.get("api_password"),
                    "chat_ids": entry.get("chat_ids"),
                }
    except Exception as e:
        print("Failed to parse STORES_JSON:", e)

bot = Bot(token=TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None
app = FastAPI(title="InSales -> Telegram notifier (Pro)")

def basic_auth_header(api_key: str, password: str) -> Dict[str, str]:
    token = base64.b64encode(f"{api_key}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

def resolve_store(headers: Dict[str, str]) -> Tuple[str, str, str, List[str]]:
    # Пытаемся вытащить домен магазина из заголовков вебхука
    shop_header_keys = ["X-Insales-Shop", "X-Insales-Domain", "X-Shop-Domain"]
    domain_header = None
    for k in shop_header_keys:
        for actual_key, val in headers.items():
            if actual_key.lower() == k.lower():
                domain_header = val.strip()
                break
        if domain_header:
            break

    if domain_header and domain_header in STORES:
        cfg = STORES[domain_header]
        chat_ids = cfg.get("chat_ids")
        if isinstance(chat_ids, list):
            chat_ids_use = [str(x) for x in chat_ids]
        elif isinstance(chat_ids, str):
            chat_ids_use = [x.strip() for x in chat_ids.split(",") if x.strip()]
        else:
            chat_ids_use = DEFAULT_CHAT_IDS
        return domain_header, cfg.get("api_key"), cfg.get("api_password"), chat_ids_use

    # дефолтная конфигурация из переменных окружения
    return INSALES_SHOP_DOMAIN or "", INSALES_API_KEY or "", INSALES_API_PASSWORD or "", DEFAULT_CHAT_IDS

async def fetch_order(order_id: int, domain: str, api_key: str, api_password: str) -> Optional[Dict[str, Any]]:
    if not (domain and api_key and api_password):
        return None
    url = f"https://{domain}/admin/orders/{order_id}.json"
    headers = {"Accept": "application/json", **basic_auth_header(api_key, api_password)}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
        return None

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
    items_text = "\n".join(items_lines) if items_lines else "(позиции не распознаны)"
    status_info = []
    for key in ["financial_status", "fulfillment_status", "status"]:
        if order.get(key) is not None:
            status_info.append(f"{key}: {order.get(key)}")
    status_line = ("\n" + " | ".join(status_info)) if status_info else ""
    return (
        f"🛒 Новый заказ #{number}\n"
        f"Сумма: {total} {currency}\n"
        f"Покупатель: {name}\n"
        f"Email: {email} | Тел: {phone}{status_line}\n\n"
        f"Товары:\n{items_text}"
    )

def make_admin_url(domain: str, order_id: Union[int, str]) -> str:
    return f"https://{domain}/admin/orders/{order_id}"

async def send_to_chats(text: str, chat_ids: List[str], button_url: Optional[str] = None, button_text: str = "Открыть в админке"):
    if not bot:
        return
    reply_markup = None
    if button_url:
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, url=button_url)]])
    for cid in chat_ids:
        try:
            await bot.send_message(chat_id=cid, text=text, reply_markup=reply_markup, disable_web_page_preview=True)
        except Exception as e:
            print(f"Failed to send to {cid}: {e}")

def pass_filter(order: Dict[str, Any]) -> bool:
    if not STATUS_FIELD or not ALLOW_VALUES:
        return True
    val = order.get(STATUS_FIELD)
    val_str = str(val).strip().lower() if val is not None else ""
    allow_lower = [v.lower() for v in ALLOW_VALUES]
    return val_str in allow_lower

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/insales/webhooks")
async def insales_webhook(request: Request, content_type: Optional[str] = Header(default=None, alias="Content-Type")):
    headers = {k: v for k, v in request.headers.items()}
    body = await request.body()
    order_id: Optional[int] = None

    # JSON-путь
    if content_type and "json" in content_type.lower():
        try:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, dict):
                if "order" in payload and isinstance(payload["order"], dict):
                    order_id = payload["order"].get("id") or payload["order"].get("order_id")
                order_id = order_id or payload.get("id") or payload.get("order_id")
        except Exception:
            pass

    # XML-путь
    if order_id is None:
        order_id = parse_order_id_from_xml(body)

    # Определяем магазин/чаты
    domain, api_key, api_password, chat_ids = resolve_store(headers)

    if order_id is None:
        return JSONResponse({"status": "ignored", "reason": "order_id_not_found"}, status_code=202)

    order = await fetch_order(int(order_id), domain, api_key, api_password)
    if not order:
        await send_to_chats(f"🛎 Вебхук по заказу ID {order_id} (магазин: {domain}), но детали не загрузились по API.", chat_ids)
        return {"ok": True, "fetched": False}

    if not pass_filter(order):
        return {"ok": True, "filtered": True}

    text = format_order_message(order)
    admin_url = make_admin_url(domain, order_id)
    await send_to_chats(text, chat_ids, button_url=admin_url, button_text="Открыть в админке")
    return {"ok": True}
