"""Scraper framework for store product data.
Each store gets its own function. Add new stores by creating a function
and registering it in STORE_SCRAPERS dict."""

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from models import db, Store, Product, Category, Price, ScrapeLog

# Store-specific scrapers go here
# Template:
# def scrape_<store_name>(store: Store) -> dict:
#     """Returns {products_found: int, errors: str}"""
#     ... fetch HTML ...
#     ... parse products ...
#     ... save to DB ...

def scrape_pyaterochka(store: Store) -> dict:
    """Пятёрочка — пример парсера. Реальный URL требует авторизации/API.
    Для MVP: возвращает заглушку с демо-данными."""
    log = ScrapeLog(store_id=store.id, started_at=datetime.utcnow())
    try:
        # TODO: реальный запрос к каталогу Пятёрочки
        # url = f"https://5ka.ru/api/catalog/category/milk/"
        # resp = requests.get(url, headers={'User-Agent': '...'})
        # data = resp.json()
        # for item in data['products']:
        #     save_product(item)
        
        # Пока — демонстрационный режим
        count = update_demo_prices(store)
        log.products_found = count
        log.finished_at = datetime.utcnow()
        db.session.add(log)
        db.session.commit()
        return {'products_found': count, 'errors': ''}
    except Exception as e:
        log.errors = str(e)
        log.finished_at = datetime.utcnow()
        db.session.add(log)
        db.session.commit()
        return {'products_found': 0, 'errors': str(e)}


def scrape_magnit(store: Store) -> dict:
    """Магнит — заглушка для демо."""
    log = ScrapeLog(store_id=store.id, started_at=datetime.utcnow())
    try:
        count = update_demo_prices(store)
        log.products_found = count
        log.finished_at = datetime.utcnow()
        db.session.add(log)
        db.session.commit()
        return {'products_found': count, 'errors': ''}
    except Exception as e:
        log.errors = str(e)
        log.finished_at = datetime.utcnow()
        db.session.add(log)
        db.session.commit()
        return {'products_found': 0, 'errors': str(e)}


def scrape_generic(store: Store) -> dict:
    """Универсальный парсер для любого магазина (заглушка)."""
    return {'products_found': 0, 'errors': 'Scraper not implemented for ' + store.name}


# Registry — все магазины Дзержинска используют заглушку (пока не подключены реальные API/парсеры)
STORE_SCRAPERS = {
    'Пятёрочка': scrape_pyaterochka,
    'Магнит': scrape_magnit,
    'Spar': scrape_magnit,          # заглушка
    'Перекрёсток': scrape_magnit,   # заглушка
    'ВкусВилл': scrape_magnit,     # заглушка
    'Бристоль': scrape_magnit,     # заглушка
}

def scrape_store(store: Store) -> dict:
    """Запустить скрапер для конкретного магазина."""
    scraper = STORE_SCRAPERS.get(store.name, scrape_generic)
    return scraper(store)


def update_demo_prices(store: Store) -> int:
    """Обновить демо-цены (случайное колебание ±10%).
    Для реального парсера — заменить на парсинг HTML/API."""
    products = Product.query.all()
    count = 0
    for product in products:
        # Найти существующую цену
        existing = Price.query.filter_by(
            product_id=product.id, store_id=store.id
        ).order_by(Price.scraped_at.desc()).first()
        
        if existing:
            # Обновить с небольшим колебанием
            import random
            variation = 1.0 + random.uniform(-0.1, 0.1)
            new_price = round(existing.price_rub * variation, 2)
            existing.price_rub = new_price
            existing.scraped_at = datetime.utcnow()
            existing.in_stock = random.random() > 0.05  # 5% out of stock
        count += 1
    
    db.session.commit()
    return count
