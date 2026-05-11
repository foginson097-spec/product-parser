from flask import Flask, render_template, request, jsonify
from models import db, Store, Category, Product, Price
from datetime import datetime
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///products.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Branding
APP_NAME = "ПродСкаут"
APP_SUBTITLE = "Реальный парсинг цен через Camofox. Магнит — live, остальные — демо."

# Нормы: взрослый человек ~2500 ккал/сутки
DAILY_CALORIES = 2500
# Примерный набор продуктов на день с ~2500 ккал (средние значения)
DEFAULT_BASKET = {
    "Хлеб": 200,           # грамм
    "Молоко": 500,
    "Яйца": 100,           # ~2 яйца
    "Куриная грудка": 200,
    "Гречка / Рис": 100,
    "Картофель": 200,
    "Масло подсолнечное": 30,
    "Сахар": 30,
    "Овощи (помидоры/огурцы)": 300,
    "Фрукты (яблоки/бананы)": 200,
    "Творог": 150,
    "Сыр": 50,
}

@app.route('/')
def index():
    stores = Store.query.filter_by(active=True).all()
    categories = Category.query.all()
    return render_template('index.html', stores=stores, categories=categories,
                           default_basket=DEFAULT_BASKET, daily_calories=DAILY_CALORIES,
                           app_name=APP_NAME, app_subtitle=APP_SUBTITLE)

@app.route('/api/basket/calculate', methods=['POST'])
def calculate_basket():
    """Рассчитать стоимость корзины во всех магазинах."""
    data = request.get_json()
    items = data.get('items', DEFAULT_BASKET)  # {product_name_ru: grams}
    
    stores = Store.query.filter_by(active=True).all()
    all_products = Product.query.all()  # fetch all — match in Python (SQLite LIKE broken on Cyrillic)
    result = []
    
    for store in stores:
        store_total = 0.0
        store_calories = 0.0
        store_items = []
        missing = []
        
        for product_name, grams_needed in items.items():
            # Найти продукт — Python-side matching (Cyrillic-safe)
            product = None
            search = product_name.lower().strip()
            for p in all_products:
                if search in p.name.lower():
                    product = p
                    break
            
            if not product:
                missing.append(product_name)
                continue
            
            # Найти актуальную цену в этом магазине
            price = Price.query.filter_by(
                product_id=product.id, store_id=store.id, in_stock=True
            ).order_by(Price.scraped_at.desc()).first()
            
            if not price:
                missing.append(f"{product_name} (нет в наличии)")
                continue
            
            # Сколько упаковок нужно
            if product.weight_grams and product.weight_grams > 0:
                packs = grams_needed / product.weight_grams
            else:
                packs = 1  # без веса — 1 единица
            
            cost = round(packs * price.price_rub, 2)
            store_total += cost
            
            # Калории
            if product.calories_per_100g:
                item_cal = (grams_needed / 100) * product.calories_per_100g
                store_calories += item_cal
            
            store_items.append({
                'product': product.name,
                'grams': grams_needed,
                'packs': round(packs, 2),
                'weight_per_pack': product.weight_grams,
                'price_per_pack': price.price_rub,
                'cost': cost,
                'url': price.url or '',
                'calories_per_100g': product.calories_per_100g or 0,
                'composition': product.composition or '',
            })
        
        result.append({
            'store': store.name,
            'city': store.city,
            'total': round(store_total, 2),
            'calories': round(store_calories),
            'items': store_items,
            'missing': missing,
        })
    
    # Сортировка: от дешёвого к дорогому
    result.sort(key=lambda x: x['total'] if x['total'] > 0 else float('inf'))
    
    return jsonify({'basket': result, 'daily_target': DAILY_CALORIES})

@app.route('/api/status', methods=['GET'])
def scraper_status():
    """Статус парсинга по всем магазинам."""
    stores = Store.query.filter_by(active=True).all()
    result = []
    for s in stores:
        status_icon = {"ok": "✅", "empty": "⚠️", "error": "❌", "demo": "🔸", "pending": "⏳"}.get(s.scrape_status, "❓")
        result.append({
            "id": s.id,
            "name": s.name,
            "status": s.scrape_status or "pending",
            "icon": status_icon,
            "last_scrape": s.last_scrape_at.isoformat() if s.last_scrape_at else None,
            "products_scraped": s.products_scraped or 0,
            "url": s.url or ""
        })
    return jsonify(result)

@app.route('/api/products', methods=['GET'])
def list_products():
    category = request.args.get('category')
    store_id = request.args.get('store_id')
    
    query = Product.query
    if category:
        query = query.join(Category).filter(Category.slug == category)
    
    products = query.all()
    result = []
    for p in products:
        price = None
        if store_id:
            price = Price.query.filter_by(
                product_id=p.id, store_id=int(store_id), in_stock=True
            ).order_by(Price.scraped_at.desc()).first()
        
        result.append({
            'id': p.id,
            'name': p.name,
            'brand': p.brand,
            'weight_grams': p.weight_grams,
            'calories_per_100g': p.calories_per_100g,
            'price': price.price_rub if price else None,
            'in_stock': price.in_stock if price else False,
            'composition': p.composition,
        })
    
    return jsonify(result)

@app.route('/api/scrape', methods=['POST'])
def trigger_scrape():
    """Запустить парсинг магазина."""
    data = request.get_json()
    store_id = data.get('store_id')
    if not store_id:
        return jsonify({'error': 'store_id required'}), 400
    
    store = Store.query.get(store_id)
    if not store:
        return jsonify({'error': 'store not found'}), 404
    
    # Импорт и запуск скрапера
    from scraper import scrape_store
    import asyncio
    try:
        result = scrape_store(store)
    except RuntimeError as e:
        if 'event loop' in str(e).lower():
            # Flask already has an event loop — run in thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(scrape_store, store)
                result = future.result(timeout=120)
        else:
            raise
    return jsonify(result)

@app.route('/api/products/add', methods=['POST'])
def add_product():
    """Добавить продукт с ценой (используется Camofox-парсером)."""
    data = request.get_json()
    store_id = data.get('store_id')
    name = data.get('name', '').strip()
    price_rub = float(data.get('price', 0))
    category_slug = data.get('category', 'products')
    
    if not name or price_rub <= 0:
        return jsonify({'status': 'error', 'msg': 'name and price required'}), 400
    
    # Категория
    cat = Category.query.filter_by(slug=category_slug).first()
    if not cat:
        cat = Category(name=category_slug, slug=category_slug)
        db.session.add(cat)
        db.session.flush()
    
    # Продукт
    product = Product.query.filter_by(name=name).first()
    if not product:
        product = Product(
            name=name, category_id=cat.id,
            weight_grams=float(data.get('weight', 0) or 0),
            calories_per_100g=float(data.get('kcal', 0) or 0),
            brand=data.get('brand', ''),
            composition=data.get('composition', '')
        )
        db.session.add(product)
        db.session.flush()
    else:
        # Update existing
        if data.get('weight'): product.weight_grams = float(data['weight'])
        if data.get('kcal'): product.calories_per_100g = float(data['kcal'])
        if data.get('composition'): product.composition = data['composition']
    
    # Цена
    existing = Price.query.filter_by(product_id=product.id, store_id=store_id).order_by(Price.scraped_at.desc()).first()
    if existing:
        existing.price_rub = price_rub
        existing.scraped_at = datetime.utcnow()
        existing.in_stock = data.get('in_stock', True)
        if data.get('url'): existing.url = data['url']
    else:
        db.session.add(Price(
            product_id=product.id, store_id=store_id,
            price_rub=price_rub, in_stock=data.get('in_stock', True),
            url=data.get('url', '')
        ))
    
    # Update store status
    store = Store.query.get(store_id)
    if store:
        store.last_scrape_at = datetime.utcnow()
        store.scrape_status = 'ok'
        store.products_scraped = Price.query.filter_by(store_id=store_id).count()
    
    db.session.commit()
    return jsonify({'status': 'ok', 'product_id': product.id})

# ---------- SEED DATA ----------

def seed_default_data():
    """Заполнить базу демо-данными (если пусто)."""
    if Store.query.count() > 0:
        return
    
    # Магазины Дзержинска (реальные, по данным 2GIS/Яндекс.Карты)
    stores = [
        Store(name='Пятёрочка', url='https://5ka.ru', city='Дзержинск'),
        Store(name='Магнит', url='https://magnit.ru', city='Дзержинск'),
        Store(name='Spar', url='https://spar.ru', city='Дзержинск'),
        Store(name='Перекрёсток', url='https://perekrestok.ru', city='Дзержинск'),
        Store(name='ВкусВилл', url='https://vkusvill.ru', city='Дзержинск'),
        Store(name='Бристоль', url='https://bristol.ru', city='Дзержинск'),
    ]
    db.session.add_all(stores)
    
    # Категории
    categories = [
        Category(name='Хлеб и выпечка', slug='bread'),
        Category(name='Молочные продукты', slug='dairy'),
        Category(name='Мясо и птица', slug='meat'),
        Category(name='Крупы и макароны', slug='grains'),
        Category(name='Овощи и фрукты', slug='vegetables'),
        Category(name='Масло и жиры', slug='oils'),
        Category(name='Бакалея', slug='grocery'),
    ]
    db.session.add_all(categories)
    db.session.flush()
    
    # Продукты с демо-ценами (средние по НН)
    products_data = [
        # name, category_slug, brand, weight_g, kcal/100g, proteins, fats, carbs, composition
        ('Хлеб белый нарезной', 'bread', 'Каравай', 400, 265, 7.6, 2.8, 51.0, 'мука пшеничная, вода, дрожжи, соль, сахар'),
        ('Хлеб ржаной', 'bread', 'Дарница', 500, 210, 6.5, 1.2, 42.0, 'мука ржаная, мука пшеничная, вода, дрожжи, соль'),
        ('Молоко 3.2%', 'dairy', 'Простоквашино', 930, 58, 2.8, 3.2, 4.7, 'молоко цельное, молоко обезжиренное'),
        ('Молоко 2.5%', 'dairy', 'Село Зелёное', 930, 52, 2.8, 2.5, 4.7, 'молоко цельное, молоко обезжиренное'),
        ('Яйца куриные С0', 'dairy', 'Окское', 600, 157, 12.7, 11.5, 0.7, 'яйца куриные'),
        ('Куриная грудка', 'meat', 'Петелинка', 1000, 113, 23.6, 1.9, 0.4, 'филе куриное'),
        ('Куриное филе', 'meat', 'Троекурово', 900, 110, 23.0, 2.0, 0.5, 'филе куриное'),
        ('Гречка ядрица', 'grains', 'Мистраль', 900, 343, 13.0, 3.4, 71.5, 'крупа гречневая'),
        ('Рис круглозёрный', 'grains', 'Националь', 900, 330, 7.0, 1.0, 74.0, 'рис шлифованный'),
        ('Картофель', 'vegetables', '', 1000, 77, 2.0, 0.4, 16.3, 'картофель свежий'),
        ('Помидоры', 'vegetables', '', 500, 18, 0.9, 0.2, 3.9, 'томаты свежие'),
        ('Огурцы', 'vegetables', '', 400, 15, 0.8, 0.1, 2.8, 'огурцы свежие'),
        ('Яблоки', 'vegetables', '', 1000, 52, 0.3, 0.2, 14.0, 'яблоки свежие'),
        ('Бананы', 'vegetables', '', 1000, 89, 1.1, 0.3, 23.0, 'бананы свежие'),
        ('Масло подсолнечное', 'oils', 'Слобода', 1000, 899, 0, 99.9, 0, 'масло подсолнечное рафинированное'),
        ('Сахар-песок', 'grocery', 'Русский сахар', 1000, 387, 0, 0, 99.8, 'сахар'),
        ('Творог 5%', 'dairy', 'Простоквашино', 200, 145, 21.0, 5.0, 3.0, 'творог, молоко цельное, молоко обезжиренное, закваска'),
        ('Сыр Российский', 'dairy', 'Ламбер', 200, 364, 23.0, 29.0, 0, 'молоко, соль, закваска, фермент'),
    ]
    
    price_samples = {
        # Цены на основе bdex.ru (Дзержинск) и 3Pulse (Россия, апрель 2026)
        # Хлеб б, Хлеб рж, Молоко 3.2%, Молоко 2.5%, Яйца С0, Грудка, Филе, Гречка, Рис, Картоф, Помид, Огурцы, Яблоки, Бананы, Масло, Сахар, Творог, Сыр
        'Пятёрочка':    [44, 40, 89, 85, 119, 330, 320, 98, 90, 32, 149, 125, 105, 128, 142, 76, 95, 155],
        'Магнит':       [46, 41, 92, 88, 125, 340, 325, 102, 92, 34, 152, 128, 108, 132, 145, 78, 98, 158],
        'Spar':         [52, 47, 98, 93, 142, 360, 350, 108, 98, 38, 168, 145, 118, 145, 155, 84, 108, 178],
        'Перекрёсток':  [55, 50, 105, 99, 150, 375, 365, 112, 102, 42, 175, 150, 122, 150, 160, 88, 112, 185],
        'ВкусВилл':     [62, 55, 112, 105, 175, 420, 405, 125, 115, 48, 195, 168, 138, 165, 175, 95, 125, 210],
        'Бристоль':     [48, 43, 94, 89, 130, 350, 335, 105, 94, 36, 158, 132, 112, 136, 148, 80, 102, 162],
    }
    
    for pdata in products_data:
        cat = Category.query.filter_by(slug=pdata[1]).first()
        product = Product(
            name=pdata[0], category_id=cat.id, brand=pdata[2],
            weight_grams=pdata[3], calories_per_100g=pdata[4],
            proteins_per_100g=pdata[5], fats_per_100g=pdata[6],
            carbs_per_100g=pdata[7], composition=pdata[8]
        )
        db.session.add(product)
        db.session.flush()
        
        # Добавить цены во все магазины со ссылками
        idx = products_data.index(pdata)
        for store in stores:
            if store.name in price_samples:
                # Генерируем ссылку — поиск товара в каталоге магазина
                store_url = _get_store_product_url(store.name, pdata[0])
                price = Price(
                    product_id=product.id,
                    store_id=store.id,
                    price_rub=price_samples[store.name][idx],
                    in_stock=True,
                    url=store_url
                )
                db.session.add(price)
    
    db.session.commit()
    print("[Seeder] Added 18 products, 6 stores (Дзержинск), 7 categories.")


def _get_store_product_url(store_name: str, product_name: str) -> str:
    """Ссылка на поиск товара в каталоге магазина."""
    from urllib.parse import quote
    encoded = quote(product_name)
    urls = {
        'Пятёрочка':    f'https://5ka.ru/search/?q={encoded}',
        'Магнит':       f'https://magnit.ru/catalog/?q={encoded}',
        'Spar':         f'https://spar.ru/search/?q={encoded}',
        'Перекрёсток':  f'https://www.perekrestok.ru/cat/search?q={encoded}',
        'ВкусВилл':     f'https://vkusvill.ru/goods/?q={encoded}',
        'Бристоль':     f'https://bristol.ru/catalog/?q={encoded}',
    }
    return urls.get(store_name, '')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_default_data()
    app.run(host='0.0.0.0', port=5050, debug=True)
