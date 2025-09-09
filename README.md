
# InSales → Telegram Bot (Render-ready)

Получает вебхуки InSales о новых/обновлённых заказах и отправляет уведомления в Telegram.

## Быстрый старт (онлайн, через Render)

1. **Подготовь данные**  
   - Токен бота Telegram от @BotFather (`TELEGRAM_BOT_TOKEN`)  
   - Твой `chat_id` (в @userinfobot) → `TELEGRAM_CHAT_ID`  
   - InSales: домен магазина (`INSALES_SHOP_DOMAIN`, например `yourshop.myinsales.ru`), `INSALES_API_KEY`, `INSALES_API_PASSWORD`

2. **Залей этот репозиторий на GitHub**  
   - Создай пустой репозиторий на GitHub (public).  
   - Загрузите файлы из этого архива (можно прямо через веб‑интерфейс GitHub).

3. **Деплой на Render (бесплатный план)**  
   Вариант А (через Render Blueprint `render.yaml`):  
   - Перейди на https://dashboard.render.com → New + → **Blueprint** → подключи свой GitHub и выбери этот репозиторий.  
   - Render прочитает `render.yaml` и предложит развернуть сервис.  
   - На шаге Environment добавь переменные:  
     - `TELEGRAM_BOT_TOKEN`  
     - `TELEGRAM_CHAT_ID`  
     - `INSALES_SHOP_DOMAIN`  
     - `INSALES_API_KEY`  
     - `INSALES_API_PASSWORD`  

   Вариант Б (Web Service вручную):  
   - New + → **Web Service** → выбрать репозиторий.  
   - Environment: **Python 3**  
   - Build Command:  
     ```
     pip install -r requirements.txt
     ```
   - Start Command:  
     ```
     uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
   - Plan: **Free**  
   - Добавь те же переменные окружения.

4. **Получить URL веб‑приложения**  
   - После деплоя на странице сервиса Render будет Public URL вида `https://<name>.onrender.com`  
   - Вебхук для InSales: `https://<name>.onrender.com/insales/webhooks`

5. **Включить вебхуки в InSales**  
   - В админке InSales создай вебхуки:  
     - Тема **orders/create** → URL `/insales/webhooks`  
     - Тема **orders/update** → URL `/insales/webhooks`

6. **Проверка**  
   - Нажми **Start** в чате с твоим Telegram‑ботом.  
   - Создай тестовый заказ в InSales.  
   - В Telegram придёт сообщение с деталями заказа.

## Переменные окружения

Пример — см. `.env.example`.

- `TELEGRAM_BOT_TOKEN` — токен бота
- `TELEGRAM_CHAT_ID` — ID чата/пользователя/канала (для канала: разреши боту писать в канал и укажи ID канала)
- `INSALES_SHOP_DOMAIN` — домен магазина `*.myinsales.ru`
- `INSALES_API_KEY` — API key
- `INSALES_API_PASSWORD` — API password

## Локальный запуск (по желанию)
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
# health-check
curl http://127.0.0.1:8000/health
```

## Безопасность
- Держи токены в переменных окружения, НЕ коммить в Git.
- Ограничь доступ к админ‑ключам InSales.
