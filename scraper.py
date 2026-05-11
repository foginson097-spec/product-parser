"""ПродСкаут — Camofox Scraper Engine v2.
Uses Playwright + Camofox for anti-detection browser automation.
Магнит: scrapes homepage product cards. Others: demo mode.
"""

import os, re
from datetime import datetime
from models import db, Store, Product, Category, Price, ScrapeLog
from playwright.sync_api import sync_playwright


def scrape_magnit(store: Store) -> dict:
    """Scrape Magnit homepage — extract product cards from recommendations."""
    log = ScrapeLog(store_id=store.id, started_at=datetime.utcnow())
    count = 0
    errors = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_timeout(20000)

            # 1. Load homepage
            page.goto("https://magnit.ru", wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            # 2. Dismiss location popup if present
            try:
                dismiss_btn = page.query_selector('button:has-text("Не сейчас")')
                if dismiss_btn: dismiss_btn.click(); page.wait_for_timeout(1000)
            except: pass

            # 3. Extract ALL product cards from the page
            # Magnit uses <article> elements for product cards
            cards = page.query_selector_all("article")

            for card in cards[:30]:
                try:
                    text = (card.inner_text() or "").strip()
                    lines = [l.strip() for l in text.split("\n") if l.strip()]

                    # Find price (contains ₽)
                    price_line = ""
                    for line in lines:
                        if "₽" in line:
                            price_line = line
                            break
                    if not price_line: continue

                    price_rub = _parse_price(price_line)
                    if price_rub <= 0: continue

                    # Find name — longest line without ₽, before the price
                    name = ""
                    price_idx = lines.index(price_line) if price_line in lines else -1
                    for line in lines[:price_idx]:
                        if "₽" not in line and len(line) > len(name) and len(line) > 5:
                            name = line[:120]
                    if not name: continue

                    # Try to get product link
                    link_el = card.query_selector("a[href]")
                    product_url = ""
                    if link_el:
                        href = link_el.get_attribute("href") or ""
                        product_url = href if href.startswith("http") else f"https://magnit.ru{href}"

                    # Save
                    cat = Category.query.filter_by(slug="products").first()
                    if not cat:
                        cat = Category(name="Продукты", slug="products")
                        db.session.add(cat); db.session.flush()

                    product = Product.query.filter_by(name=name).first()
                    if not product:
                        product = Product(name=name, category_id=cat.id)
                        db.session.add(product); db.session.flush()

                    _save_price(product.id, store.id, price_rub, url=product_url)
                    count += 1
                except: continue

            # 4. Also scrape specific category pages that are known to work
            category_urls = [
                "https://magnit.ru/catalog/molochnye-produkty-yaico",
                "https://magnit.ru/catalog/ovoshchi-frukty",
                "https://magnit.ru/catalog/khleb-vypechka",
            ]
            for cat_url in category_urls[:2]:  # Limit to 2 categories to avoid timeout
                try:
                    page.goto(cat_url, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    cards2 = page.query_selector_all("article")
                    for card in cards2[:10]:
                        try:
                            text = (card.inner_text() or "").strip()
                            price_rub = _parse_price(text)
                            if price_rub <= 0: continue
                            name = text.split("\n")[0][:120] if "\n" in text else text[:120]
                            if len(name) < 5: continue

                            cat_obj = Category.query.filter_by(slug="products").first()
                            product = Product.query.filter_by(name=name).first()
                            if not product:
                                product = Product(name=name, category_id=cat_obj.id)
                                db.session.add(product); db.session.flush()
                            _save_price(product.id, store.id, price_rub)
                            count += 1
                        except: continue
                except Exception as e:
                    errors.append(str(e)[:60])

            browser.close()

        log.products_found = count
        log.errors = "; ".join(errors) if errors else None
        log.finished_at = datetime.utcnow()
        db.session.add(log); db.session.commit()

        store.last_scrape_at = datetime.utcnow()
        store.scrape_status = "ok" if count > 0 else "empty"
        store.products_scraped = Price.query.filter_by(store_id=store.id).count()
        db.session.commit()

        return {"products_found": count, "errors": "; ".join(errors) if errors else ""}

    except Exception as e:
        db.session.rollback()
        log.errors = str(e)[:500]; log.finished_at = datetime.utcnow()
        db.session.add(log); db.session.commit()
        store.scrape_status = "error"; store.last_scrape_at = datetime.utcnow()
        db.session.commit()
        return {"products_found": count, "errors": str(e)[:200]}


def update_demo_prices(store: Store) -> int:
    import random
    products = Product.query.all()
    updated = 0
    for product in products:
        existing = Price.query.filter_by(product_id=product.id, store_id=store.id).order_by(Price.scraped_at.desc()).first()
        if existing and existing.price_rub > 0:
            variation = 1.0 + random.uniform(-0.08, 0.08)
            existing.price_rub = round(existing.price_rub * variation, 2)
            existing.scraped_at = datetime.utcnow()
            updated += 1
    db.session.commit()
    store.last_scrape_at = datetime.utcnow(); store.scrape_status = "demo"
    store.products_scraped = updated; db.session.commit()
    return updated


def _save_price(product_id: int, store_id: int, price_rub: float, url: str = "") -> None:
    existing = Price.query.filter_by(product_id=product_id, store_id=store_id).order_by(Price.scraped_at.desc()).first()
    if existing:
        existing.price_rub = price_rub; existing.scraped_at = datetime.utcnow(); existing.in_stock = True
        if url: existing.url = url
    else:
        db.session.add(Price(product_id=product_id, store_id=store_id, price_rub=price_rub, in_stock=True, url=url))


def _parse_price(text: str) -> float:
    clean = text.replace(",", ".").replace(" ", "").replace("₽", "").replace("руб", "")
    match = re.search(r'[\d.]+', clean)
    return float(match.group()) if match else 0.0


STORE_SCRAPERS = {"Магнит": scrape_magnit}


def scrape_store(store: Store) -> dict:
    scraper = STORE_SCRAPERS.get(store.name)
    if scraper: return scraper(store)
    count = update_demo_prices(store)
    return {"products_found": count, "errors": "", "note": "demo"}
