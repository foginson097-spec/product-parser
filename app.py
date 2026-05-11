from flask import Flask, render_template, request, jsonify
from models import db, Store, Category, Product, Price
from datetime import datetime
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///products.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

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
                           default_basket=DEFAULT_BASKET, daily_calories=DAILY_CALORIES)

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
    result = scrape_store(store)
    return jsonify(result)

# ---------- SEED DATA ----------

def seed_default_data():
    """Заполнить базу демо-данными (если пусто)."""
    if Store.query.count() > 0:
        return
    
    # Магазины
    stores = [
        Store(name='Пятёрочка', url='https://5ka.ru', city='Нижний Новгород'),
        Store(name='Магнит', url='https://magnit.ru', city='Нижний Новгород'),
        Store(name='Лента', url='https://lenta.com', city='Нижний Новгород'),
        Store(name='Ашан', url='https://auchan.ru', city='Нижний Новгород'),
        Store(name='Spar', url='https://spar.ru', city='Нижний Новгород'),
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
        'Пятёрочка': [42, 38, 89, 85, 129, 320, 310, 95, 88, 35, 150, 120, 110, 130, 140, 75, 95, 150],
        'Магнит': [45, 40, 92, 88, 135, 330, 315, 99, 90, 38, 145, 115, 115, 135, 145, 78, 98, 155],
        'Лента': [40, 35, 85, 82, 125, 310, 305, 90, 85, 32, 140, 110, 105, 125, 135, 72, 90, 145],
        'Ашан': [44, 39, 88, 84, 130, 340, 320, 92, 86, 36, 155, 125, 112, 132, 142, 76, 92, 148],
        'Spar': [48, 42, 95, 90, 140, 350, 330, 100, 92, 40, 160, 130, 118, 138, 148, 80, 100, 160],
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
        
        # Добавить цены во все магазины
        idx = products_data.index(pdata)
        for store in stores:
            if store.name in price_samples:
                price = Price(
                    product_id=product.id,
                    store_id=store.id,
                    price_rub=price_samples[store.name][idx],
                    in_stock=True
                )
                db.session.add(price)
    
    db.session.commit()
    print("[Seeder] Added 18 products, 5 stores, 7 categories with demo prices.")

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed_default_data()
    app.run(host='0.0.0.0', port=5050, debug=True)
