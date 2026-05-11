from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Store(db.Model):
    __tablename__ = 'stores'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500))
    city = db.Column(db.String(200), default='Нижний Новгород')
    active = db.Column(db.Boolean, default=True)
    # Scraping status
    last_scrape_at = db.Column(db.DateTime)
    scrape_status = db.Column(db.String(50), default='pending')  # pending/ok/empty/error/demo
    products_scraped = db.Column(db.Integer, default=0)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(500), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'))
    brand = db.Column(db.String(300))
    weight_grams = db.Column(db.Float)            # вес упаковки
    calories_per_100g = db.Column(db.Float)       # ккал на 100г
    proteins_per_100g = db.Column(db.Float)       # белки
    fats_per_100g = db.Column(db.Float)           # жиры
    carbs_per_100g = db.Column(db.Float)          # углеводы
    composition = db.Column(db.Text)              # состав
    
    category = db.relationship('Category', backref='products')

class Price(db.Model):
    __tablename__ = 'prices'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    price_rub = db.Column(db.Float, nullable=False)
    in_stock = db.Column(db.Boolean, default=True)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    url = db.Column(db.String(500))
    
    product = db.relationship('Product', backref='prices')
    store = db.relationship('Store', backref='prices')

class ScrapeLog(db.Model):
    __tablename__ = 'scrape_logs'
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    products_found = db.Column(db.Integer, default=0)
    errors = db.Column(db.Text)
