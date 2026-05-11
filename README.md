# ПродСкаут (ProdScout) — агрегатор цен + калькулятор калорий

Сравнение цен на продукты питания в магазинах Дзержинска с калькулятором дневной корзины (2500 ккал).

## Возможности

- Сравнение цен в 6 магазинах (Пятёрочка, Магнит, Spar, Перекрёсток, ВкусВилл, Бристоль)
- Калькулятор калорий: прямой и обратный расчёт
- Поиск продуктов по названию, сортировка по цене/калориям
- Корзина с прогресс-баром 2500 ккал
- Сохранение/загрузка корзин (localStorage)
- Реальные ссылки на товары Магнита (product pages)
- Статус парсинга: дата и время обновления, количество товаров
- Mobile-responsive

## Технологии

- Python 3.12 + Flask + SQLAlchemy
- SQLite (база продуктов и цен)
- Playwright + Camofox (антидетект-парсинг)
- Vanilla JS (фронтенд, без фреймворков)
- Docker + Docker Compose

## Запуск

```bash
# Локально
cd product-parser
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 -m playwright install chromium  # для парсинга
python app.py
# → http://localhost:5050

# Docker
docker-compose up -d
# → http://localhost:5050
```

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | /api/status | Статус парсинга по магазинам |
| GET | /api/products | Список продуктов |
| POST | /api/basket/calculate | Расчёт корзины |
| POST | /api/scrape | Запуск парсинга магазина |
| POST | /api/products/add | Добавление продукта с ценой |

## Парсинг

Магнит — реальный парсинг через Camofox (Playwright + антидетект). X5 Group (Пятёрочка/Перекрёсток) блокируют IP датацентров. Рекомендуется запускать скрапер с домашнего ПК через VPN.

## Архитектура

```
app.py              # Flask-бэкенд
models.py           # SQLAlchemy модели (Store, Product, Price, Category)
scraper.py          # Camofox/Playwright парсеры
templates/index.html # SPA-фронтенд (vanilla JS)
requirements.txt    # Зависимости
Dockerfile          # Docker-образ
docker-compose.yml  # Деплой
```
