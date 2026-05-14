from __future__ import annotations

import csv
import io
import json
import sqlite3
import os
import secrets
import tempfile
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from flask import (
    Flask,
    Response,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "site.db"
DATA_FILE = DATA_DIR / "data.json"  # legacy JSON import; new data is stored in SQLite
UPLOAD_DIR = BASE_DIR / "uploads"
IMAGE_DIR = UPLOAD_DIR / "product_images"
FILE_DIR = UPLOAD_DIR / "product_files"
VACANCY_IMAGE_DIR = UPLOAD_DIR / "vacancy_images"
DATA_LOCK = threading.RLock()
ENTITY_TABLES = ["orders", "products", "packages", "testimonials", "faq", "users", "purchases", "vacancies"]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key-in-production")
app.config["JSON_AS_ASCII"] = False
app.config["MAX_CONTENT_LENGTH"] = 120 * 1024 * 1024

STATUS_NAMES = {
    "new": "Новая",
    "in_progress": "В работе",
    "completed": "Завершена",
    "cancelled": "Отменена",
}

PURCHASE_STATUS_NAMES = {
    "new": "Новая покупка",
    "paid": "Оплачено",
    "manual": "На проверке",
    "configuring": "Настройка",
    "vps": "Установка на VPS",
    "ready": "Готово к выдаче",
    "completed": "Завершено",
    "refunded": "Возврат",
    "cancelled": "Отменено",
}

CALCULATOR_PROJECT_KEYS = {
    "bot": ("Telegram бот", "🤖", "calc_project_bot", 10000),
    "website": ("Сайт", "🌐", "calc_project_website", 25000),
    "webapp": ("Web приложение", "⚡", "calc_project_webapp", 50000),
    "design": ("Дизайн", "🎨", "calc_project_design", 15000),
}

CALCULATOR_FEATURE_KEYS = {
    "admin": ("Админ-панель", "calc_feature_admin", 15000),
    "payment": ("Интеграция платежей", "calc_feature_payment", 10000),
    "api": ("API интеграции", "calc_feature_api", 12000),
    "auth": ("Система авторизации", "calc_feature_auth", 8000),
    "push": ("Push уведомления", "calc_feature_push", 5000),
    "analytics": ("Аналитика", "calc_feature_analytics", 7000),
    "database": ("База данных", "calc_feature_database", 6000),
    "responsive": ("Адаптивный дизайн", "calc_feature_responsive", 8000),
}

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "svg"}
FILE_EXTENSIONS = {"zip", "rar", "7z", "py", "js", "ts", "html", "css", "json", "txt", "pdf", "docx"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_products(created: str) -> list[dict[str, Any]]:
    rows = [
        ("Магазин товаров", "Telegram бот", "🛒", "Готовый бот для продажи цифровых товаров с корзиной и оплатой", "Каталог товаров\nКорзина\nОплата\nАдмин-панель", 15000, "Басик\nVIP\nPro", "ПОПУЛЯРНОЕ", "https://t.me/", 550, 1),
        ("CRM-система", "Telegram бот", "💾", "Управление клиентами и заявками через Telegram бота", "База клиентов\nВоронка продаж\nОтчеты\nИнтеграции", 25000, "Басик\nVIP\nPro", "", "https://t.me/", 900, 1),
        ("Быстрый старт", "Telegram бот", "⚡", "Базовый шаблон бота с основными функциями", "Меню\nFAQ\nРассылка\nСтатистика", 5000, "Басик\nVIP\nPro", "", "https://t.me/", 250, 1),
        ("Бот записи", "Telegram бот", "📅", "Запись клиентов на услуги с уведомлениями и расписанием", "Расписание\nУведомления\nКлиенты\nЭкспорт", 12000, "Басик\nVIP\nPro", "", "https://t.me/", 450, 1),
        ("Бот поддержки", "Telegram бот", "🎧", "Приём обращений, тикеты и быстрые ответы для поддержки", "Тикеты\nОператоры\nШаблоны ответов\nСтатусы", 18000, "Басик\nVIP\nPro", "", "https://t.me/", 700, 1),
        ("Лендинг под ключ", "Сайты", "🌐", "Современный продающий сайт с адаптивом и формами заявок", "Адаптив\nФорма заявки\nАнимации\nSEO-база", 22000, "Басик\nVIP\nPro", "", "https://example.com", None, 0),
        ("Web App для Telegram", "Веб-приложение", "📱", "Мини-приложение внутри Telegram с удобным интерфейсом", "Telegram Login\nКаталог\nПрофиль\nAPI", 30000, "Басик\nVIP\nPro", "НОВИНКА", "https://example.com", None, 0),
        ("Парсер данных", "Код с нуля", "🧠", "Скрипт для сбора и обработки данных из открытых источников", "Парсинг\nФильтры\nExcel/CSV\nАвтозапуск", 10000, "Басик\nVIP\nPro", "", "", None, 0),
        ("Авторассылка", "Telegram бот", "📣", "Рассылки по базе пользователей с сегментами и статистикой", "Сегменты\nПланировщик\nСтатистика\nШаблоны", 14000, "Басик\nVIP\nPro", "", "https://t.me/", 500, 1),
        ("Бот квиз", "Telegram бот", "❓", "Квизы, тесты и лид-магниты для сбора заявок", "Вопросы\nБаллы\nЛиды\nАдминка", 11000, "Басик\nVIP\nPro", "", "https://t.me/", 420, 1),
        ("Панель управления", "Сайты", "🧩", "Админ-панель для управления заявками, товарами и пользователями", "CRUD\nРоли\nФильтры\nЭкспорт", 28000, "Басик\nVIP\nPro", "", "https://example.com", None, 0),
        ("Интеграция API", "Код с нуля", "🔌", "Подключение платежей, CRM, таблиц и внешних сервисов", "REST API\nWebhook\nЛоги\nДокументация", 16000, "Басик\nVIP\nPro", "", "", None, 0),
    ]
    rows.extend(site_template_rows())
    products: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        title, category, icon, description, features, price, tariffs, badge, demo_url, rental_price, rent_available = row
        products.append({
            "id": index,
            "title": title,
            "category": category,
            "icon": icon,
            "description": description,
            "features": features,
            "price": price,
            "old_price": None,
            "badge": badge,
            "tariffs": tariffs,
            "image_path": "",
            "file_path": "",
            "file_original_name": "",
            "demo_url": demo_url,
            "rental_price": rental_price,
            "rent_available": rent_available,
            "price_basic": price,
            "price_vip": round(price * 1.35) if price else None,
            "price_pro": round(price * 1.75) if price else None,
            "rental_price_basic": rental_price,
            "rental_price_vip": round(rental_price * 1.35) if rental_price else None,
            "rental_price_pro": round(rental_price * 1.75) if rental_price else None,
            "sort_order": index * 10,
            "is_active": 1,
            "created_at": created,
            "updated_at": created,
        })
    return products


def site_template_rows() -> list[tuple[Any, ...]]:
    return [
        ("Aurora Landing", "Сайты", "🌌", "Премиальный лендинг с неоновыми секциями, анимациями и формой заявки", "Hero-блок\nАнимации\nФорма лидов\nАдаптив", 9000, "Басик\nVIP\nPro", "ШАБЛОН", "https://example.com/aurora", None, 0),
        ("SaaS Dashboard", "Сайты", "📊", "Шаблон сайта для IT-сервиса с тарифами, FAQ и блоками доверия", "Главная\nТарифы\nFAQ\nБлог\nФорма заявки", 12000, "Басик\nVIP\nPro", "", "https://example.com/saas", None, 0),
        ("Portfolio Pro", "Сайты", "🎨", "Красивое портфолио для дизайнера, разработчика или студии", "Кейсы\nО себе\nОтзывы\nКонтакты", 8000, "Басик\nVIP\nPro", "", "https://example.com/portfolio", None, 0),
        ("Shop Minimal", "Сайты", "🛍️", "Минималистичный шаблон магазина с карточками товаров", "Каталог\nКарточки\nКорзина-макет\nАдаптив", 14000, "Басик\nVIP\nPro", "", "https://example.com/shop", None, 0),
        ("Agency Motion", "Сайты", "🚀", "Сайт агентства с motion-анимациями и яркими CTA-кнопками", "Услуги\nКейсы\nКоманда\nЗаявки", 11000, "Басик\nVIP\nPro", "", "https://example.com/agency", None, 0),
        ("Restaurant Glow", "Сайты", "🍽️", "Стильный сайт ресторана, кафе или доставки еды", "Меню\nБронирование\nГалерея\nКонтакты", 9500, "Басик\nVIP\nPro", "", "https://example.com/restaurant", None, 0),
        ("Crypto Pulse", "Сайты", "₿", "Темный fintech-шаблон для крипто/финансового проекта", "Статистика\nПреимущества\nRoadmap\nFAQ", 13000, "Басик\nVIP\nPro", "", "https://example.com/crypto", None, 0),
        ("School Hub", "Сайты", "🎓", "Сайт онлайн-школы с программой курса и заявками", "Программа\nПреподаватели\nОтзывы\nФорма оплаты", 10500, "Басик\nVIP\nPro", "", "https://example.com/school", None, 0),
        ("Real Estate Lux", "Сайты", "🏙️", "Шаблон для недвижимости с каталогом объектов и заявками", "Объекты\nФильтры\nГалерея\nЗаявка", 15000, "Басик\nVIP\nPro", "", "https://example.com/estate", None, 0),
        ("Event Neon", "Сайты", "🎫", "Лендинг мероприятия с расписанием, спикерами и регистрацией", "Расписание\nСпикеры\nБилеты\nРегистрация", 8500, "Басик\nVIP\nPro", "", "https://example.com/event", None, 0),
    ]

def default_data() -> dict[str, Any]:
    created = now()
    products = default_products(created)
    return {
        "settings": {
            "site_name": "DevBots",
            "site_badge": "Профессиональная разработка",
            "hero_title_1": "Разработка ботов,",
            "hero_title_2": "сайтов и дизайна",
            "hero_subtitle": "От идеи до реализации: создаем современные решения для вашего бизнеса",
            "email": "hello@example.com",
            "telegram": "@your_username",
            "whatsapp": "+7 999 000-00-00",
            "currency": "₽",
            "demo_balance": 100000,
            "calc_project_bot_name": "Telegram бот",
            "calc_project_website_name": "Сайт",
            "calc_project_webapp_name": "Web приложение",
            "calc_project_design_name": "Дизайн",
            "calc_feature_admin_name": "Админ-панель",
            "calc_feature_payment_name": "Интеграция платежей",
            "calc_feature_api_name": "API интеграции",
            "calc_feature_auth_name": "Система авторизации",
            "calc_feature_push_name": "Push уведомления",
            "calc_feature_analytics_name": "Аналитика",
            "calc_feature_database_name": "База данных",
            "calc_feature_responsive_name": "Адаптивный дизайн",
            "calc_project_bot": 10000,
            "calc_project_website": 25000,
            "calc_project_webapp": 50000,
            "calc_project_design": 15000,
            "calc_feature_admin": 15000,
            "calc_feature_payment": 10000,
            "calc_feature_api": 12000,
            "calc_feature_auth": 8000,
            "calc_feature_push": 5000,
            "calc_feature_analytics": 7000,
            "calc_feature_database": 6000,
            "calc_feature_responsive": 8000,
            "admin_username": "admin",
            "admin_password_hash": generate_password_hash("admin123!"),
        },
        "counters": {
            "orders": 1,
            "products": len(products) + 1,
            "packages": 4,
            "testimonials": 7,
            "faq": 7,
            "users": 1,
            "purchases": 1,
            "vacancies": 1,
        },
        "orders": [],
        "users": [],
        "purchases": [],
        "vacancies": [],
        "products": products,
        "packages": [
            {
                "id": 1,
                "title": "Basic",
                "description": "Базовый план",
                "features": "Готовый бот\nНастройка текстов/кнопок\nПоддержка: 3 дня",
                "price": 5000,
                "badge": "",
                "sort_order": 10,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
            {
                "id": 2,
                "title": "VIP",
                "description": "Популярный выбор",
                "features": "Готовый бот\nПокупка с исходниками\nНастройка текстов/кнопок\nИзменение логики\nПоддержка: 7 дней",
                "price": 15000,
                "badge": "ПОПУЛЯРНЫЙ",
                "sort_order": 20,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
            {
                "id": 3,
                "title": "Pro",
                "description": "Всё включено",
                "features": "Готовый бот\nПокупка с исходниками\nWeb app\nНастройка текстов/кнопок\nИзменение логики\nИнтеграции API\nПоддержка: 14 дней\nУстановка на VPS",
                "price": 25000,
                "badge": "",
                "sort_order": 30,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
        ],
        "testimonials": [
            {
                "id": 1,
                "author": "Алексей М.",
                "role": "Магазин цифровых товаров",
                "text": "Заказывал бота для продажи курсов. Сделали быстро, все работает отлично. Админ-панель удобная, разобрался за 10 минут. Рекомендую!",
                "rating": 5,
                "sort_order": 10,
                "is_active": 1,
                "created_at": "15 апреля 2026",
                "updated_at": created,
            },
            {
                "id": 2,
                "author": "Мария К.",
                "role": "Сайт-визитка",
                "text": "Сделали красивый сайт для моего бизнеса. Дизайн современный, все адаптировано под телефон. Цена адекватная, сроки соблюдены.",
                "rating": 5,
                "sort_order": 20,
                "is_active": 1,
                "created_at": "28 марта 2026",
                "updated_at": created,
            },
            {
                "id": 3,
                "author": "Дмитрий П.",
                "role": "CRM-бот для компании",
                "text": "Взяли тариф Pro с интеграциями. Команда профессиональная, все доработки делали оперативно. Теперь весь учет клиентов в боте, очень удобно.",
                "rating": 5,
                "sort_order": 30,
                "is_active": 1,
                "created_at": "10 марта 2026",
                "updated_at": created,
            },
            {
                "id": 4,
                "author": "Екатерина В.",
                "role": "Landing page",
                "text": "Нужен был лендинг для акции. Сделали за 3 дня, включая правки. Конверсия выросла в 2 раза. Спасибо за качественную работу!",
                "rating": 5,
                "sort_order": 40,
                "is_active": 1,
                "created_at": "5 февраля 2026",
                "updated_at": created,
            },
            {
                "id": 5,
                "author": "Игорь С.",
                "role": "Бот-калькулятор",
                "text": "Заказал готовый бот с небольшими доработками. Все пожелания учли, работает стабильно. Поддержка отзывчивая, помогли с настройкой.",
                "rating": 5,
                "sort_order": 50,
                "is_active": 1,
                "created_at": "22 января 2026",
                "updated_at": created,
            },
            {
                "id": 6,
                "author": "Ольга Н.",
                "role": "Интернет-магазин",
                "text": "Делали с нуля магазин на React. Получилось стильно и функционально. Весь процесс был прозрачным, всегда знала на каком этапе находимся.",
                "rating": 5,
                "sort_order": 60,
                "is_active": 1,
                "created_at": "8 января 2026",
                "updated_at": created,
            },
        ],
        "faq": [
            {
                "id": 1,
                "question": "Как получить бота после покупки?",
                "answer": "После покупки товар появляется в личном кабинете. Если к товару прикреплён файл, его можно скачать сразу. Если нужна настройка, заявка также попадает администратору.",
                "sort_order": 10,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
            {
                "id": 2,
                "question": "Что такое демо-баланс?",
                "answer": "Демо-баланс нужен для тестирования покупок на локальном сайте. Администратор может изменить баланс пользователя в админ-панели.",
                "sort_order": 20,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
            {
                "id": 3,
                "question": "Можно ли доработать готового бота?",
                "answer": "Да, все готовые боты можно дорабатывать. В анкете покупки выберите тариф и укажите детали задачи.",
                "sort_order": 30,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
            {
                "id": 4,
                "question": "Какие сроки разработки?",
                "answer": "Готовые решения настраиваются за 1-3 дня. Индивидуальная разработка занимает от 1 до 4 недель в зависимости от сложности проекта.",
                "sort_order": 40,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
            {
                "id": 5,
                "question": "Возможна ли оплата частями?",
                "answer": "Для реальных проектов стоимостью от 30 000 рублей возможна оплата в два этапа: 50% предоплата и 50% после сдачи проекта.",
                "sort_order": 50,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
            {
                "id": 6,
                "question": "Что делать, если бот перестал работать?",
                "answer": "В течение периода поддержки мы бесплатно исправим технические проблемы. После поддержки можно оформить обслуживание.",
                "sort_order": 60,
                "is_active": 1,
                "created_at": created,
                "updated_at": created,
            },
        ],
    }


def migrate_data(data: dict[str, Any]) -> dict[str, Any]:
    """Add missing fields to older installations without removing existing user data."""
    changed = False
    defaults = default_data()
    for key in ["settings", "counters"]:
        data.setdefault(key, {})
        for sub_key, value in defaults[key].items():
            if sub_key not in data[key]:
                data[key][sub_key] = value
                changed = True
    for key in ENTITY_TABLES:
        if key not in data or not isinstance(data.get(key), list):
            data[key] = defaults[key]
            changed = True
    for product in data.get("products", []):
        for key, value in {
            "tariffs": "Басик\nVIP\nPro",
            "image_path": "",
            "file_path": "",
            "file_original_name": "",
            "badge": "",
            "old_price": None,
            "demo_url": "",
            "rental_price": None,
            "rent_available": 1 if "бот" in str(product.get("category", "")).lower() else 0,
            "price_basic": product.get("price"),
            "price_vip": round(to_float(product.get("price"), 0) * 1.35) if product.get("price") not in (None, "") else None,
            "price_pro": round(to_float(product.get("price"), 0) * 1.75) if product.get("price") not in (None, "") else None,
            "rental_price_basic": product.get("rental_price"),
            "rental_price_vip": round(to_float(product.get("rental_price"), 0) * 1.35) if product.get("rental_price") not in (None, "") else None,
            "rental_price_pro": round(to_float(product.get("rental_price"), 0) * 1.75) if product.get("rental_price") not in (None, "") else None,
        }.items():
            if key not in product:
                product[key] = value
                changed = True
    for user in data.get("users", []):
        for key, value in {"email": "", "contact": "", "role": "user", "balance": to_float(data.get("settings", {}).get("demo_balance", 100000), 100000), "is_active": 1}.items():
            if key not in user:
                user[key] = value
                changed = True

    existing_titles = {str(product.get("title", "")).strip().lower() for product in data.get("products", [])}
    created = now()
    next_id = max([int(item.get("id", 0) or 0) for item in data.get("products", [])] + [0]) + 1
    for offset, row in enumerate(site_template_rows()):
        title, category, icon, description, features, price, tariffs, badge, demo_url, rental_price, rent_available = row
        if title.lower() in existing_titles:
            continue
        data.setdefault("products", []).append({
            "id": next_id,
            "title": title,
            "category": category,
            "icon": icon,
            "description": description,
            "features": features,
            "price": price,
            "old_price": None,
            "badge": badge,
            "tariffs": tariffs,
            "image_path": "",
            "file_path": "",
            "file_original_name": "",
            "demo_url": demo_url,
            "rental_price": rental_price,
            "rent_available": rent_available,
            "price_basic": price,
            "price_vip": round(price * 1.35) if price else None,
            "price_pro": round(price * 1.75) if price else None,
            "rental_price_basic": rental_price,
            "rental_price_vip": round(rental_price * 1.35) if rental_price else None,
            "rental_price_pro": round(rental_price * 1.75) if rental_price else None,
            "sort_order": 1000 + offset * 10,
            "is_active": 1,
            "created_at": created,
            "updated_at": created,
        })
        next_id += 1
        changed = True

    counters = data.setdefault("counters", {})
    for key in ENTITY_TABLES:
        max_id = max([int(item.get("id", 0) or 0) for item in data.get(key, [])] + [0]) + 1
        if int(counters.get(key, 1) or 1) < max_id:
            counters[key] = max_id
            changed = True
    if changed:
        save_data(data)
    return data


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    FILE_DIR.mkdir(parents=True, exist_ok=True)
    VACANCY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def db_connect() -> sqlite3.Connection:
    ensure_dirs()
    connection = sqlite3.connect(DB_FILE, timeout=30, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def init_db() -> None:
    with DATA_LOCK:
        ensure_dirs()
        with db_connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (kind, name)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    table_name TEXT NOT NULL,
                    id INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT,
                    data TEXT NOT NULL,
                    PRIMARY KEY (table_name, id)
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_records_table_sort ON records(table_name, sort_order, id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_records_table_active ON records(table_name, is_active)")


def db_is_empty() -> bool:
    init_db()
    with db_connect() as connection:
        meta_count = connection.execute("SELECT COUNT(*) FROM meta").fetchone()[0]
        record_count = connection.execute("SELECT COUNT(*) FROM records").fetchone()[0]
    return int(meta_count or 0) == 0 and int(record_count or 0) == 0


def load_legacy_json() -> dict[str, Any] | None:
    if not DATA_FILE.exists():
        return None
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return None
    return None


def ensure_database() -> None:
    init_db()
    if db_is_empty():
        data = load_legacy_json() or default_data()
        save_data(data)
    else:
        migrate_data(load_data())


def ensure_data_file() -> None:
    """Backward compatible name used by older code; initializes the SQLite database now."""
    ensure_database()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_load(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def load_data() -> dict[str, Any]:
    with DATA_LOCK:
        init_db()
        with db_connect() as connection:
            settings_rows = connection.execute("SELECT name, value FROM meta WHERE kind = 'settings'").fetchall()
            counters_rows = connection.execute("SELECT name, value FROM meta WHERE kind = 'counters'").fetchall()
            data: dict[str, Any] = {
                "settings": {row["name"]: _json_load(row["value"]) for row in settings_rows},
                "counters": {row["name"]: int(_json_load(row["value"], 1) or 1) for row in counters_rows},
            }
            for table in ENTITY_TABLES:
                rows = connection.execute(
                    "SELECT data FROM records WHERE table_name = ? ORDER BY sort_order ASC, id ASC",
                    (table,),
                ).fetchall()
                data[table] = [item for item in (_json_load(row["data"], {}) for row in rows) if isinstance(item, dict)]
        if not data.get("settings") and all(not data.get(table) for table in ENTITY_TABLES):
            data = default_data()
            save_data(data)
        return deepcopy(data)


def save_data(data: dict[str, Any]) -> None:
    with DATA_LOCK:
        init_db()
        with db_connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM meta")
            connection.execute("DELETE FROM records")
            for key, value in data.get("settings", {}).items():
                connection.execute(
                    "INSERT INTO meta(kind, name, value) VALUES('settings', ?, ?)",
                    (key, _json_dump(value)),
                )
            for key, value in data.get("counters", {}).items():
                connection.execute(
                    "INSERT INTO meta(kind, name, value) VALUES('counters', ?, ?)",
                    (key, _json_dump(int(value or 1))),
                )
            for table in ENTITY_TABLES:
                for record in data.get(table, []):
                    record_id = int(record.get("id", 0) or 0)
                    if record_id <= 0:
                        continue
                    connection.execute(
                        """
                        INSERT INTO records(table_name, id, sort_order, is_active, updated_at, data)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            table,
                            record_id,
                            int(record.get("sort_order", 0) or 0),
                            int(record.get("is_active", 1) or 0),
                            str(record.get("updated_at", "") or ""),
                            _json_dump(record),
                        ),
                    )
            connection.commit()

def setting(key: str, default: Any = "") -> Any:
    data = load_data()
    value = data.get("settings", {}).get(key, default)
    return value if value is not None else default


def update_settings(fields: dict[str, Any]) -> None:
    data = load_data()
    data.setdefault("settings", {}).update(fields)
    save_data(data)


def all_records(table: str) -> list[dict[str, Any]]:
    data = load_data()
    items = list(data.get(table, []))
    items.sort(key=lambda item: (int(item.get("sort_order", 0) or 0), int(item.get("id", 0) or 0)))
    return items


def all_records_desc(table: str) -> list[dict[str, Any]]:
    items = all_records(table)
    items.sort(key=lambda item: int(item.get("id", 0) or 0), reverse=True)
    return items


def active_records(table: str) -> list[dict[str, Any]]:
    return [item for item in all_records(table) if int(item.get("is_active", 1) or 0) == 1]


def find_record(table: str, record_id: int) -> dict[str, Any] | None:
    for item in all_records(table):
        if int(item.get("id", 0) or 0) == record_id:
            return item
    return None


def insert_record(table: str, record: dict[str, Any]) -> int:
    data = load_data()
    counters = data.setdefault("counters", {})
    record_id = int(counters.get(table, 1) or 1)
    counters[table] = record_id + 1
    record.update({"id": record_id, "created_at": now(), "updated_at": now()})
    data.setdefault(table, []).append(record)
    save_data(data)
    return record_id


def update_record(table: str, record_id: int, fields: dict[str, Any]) -> bool:
    data = load_data()
    for item in data.get(table, []):
        if int(item.get("id", 0) or 0) == record_id:
            item.update(fields)
            item["updated_at"] = now()
            save_data(data)
            return True
    return False


def delete_record(table: str, record_id: int) -> bool:
    data = load_data()
    before = len(data.get(table, []))
    data[table] = [item for item in data.get(table, []) if int(item.get("id", 0) or 0) != record_id]
    save_data(data)
    return len(data.get(table, [])) != before


def count_records(table: str, predicate: Callable[[dict[str, Any]], bool] | None = None) -> int:
    items = all_records(table)
    return len([item for item in items if predicate(item)]) if predicate else len(items)


def is_admin() -> bool:
    return bool(session.get("admin_logged_in"))


def current_user() -> dict[str, Any] | None:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return find_record("users", int(user_id))


def user_identity_conflict(username: str, email: str, exclude_id: int = 0) -> str:
    username_norm = str(username or "").strip().lower()
    email_norm = str(email or "").strip().lower()
    admin_username = str(setting("admin_username", "admin") or "admin").strip().lower()
    if username_norm and username_norm == admin_username and not exclude_id:
        return "Такой логин занят администратором."
    for user in all_records("users"):
        if exclude_id and int(user.get("id", 0) or 0) == exclude_id:
            continue
        if username_norm and username_norm == str(user.get("username", "")).strip().lower():
            return "Пользователь с таким логином уже существует."
        if email_norm and email_norm == str(user.get("email", "")).strip().lower():
            return "Пользователь с такой почтой уже существует."
    return ""


def require_admin() -> None:
    if not is_admin():
        abort(403)


def require_user() -> dict[str, Any]:
    user = current_user()
    if not user:
        abort(403)
    return user


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def verify_csrf() -> None:
    submitted = request.form.get("csrf_token", "")
    if not submitted or submitted != session.get("csrf_token"):
        abort(400, "Неверный CSRF-токен. Обновите страницу и попробуйте снова.")


def to_number_or_none(value: Any) -> float | None:
    value = str(value or "").strip().replace(",", ".")
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value: Any, currency: str | None = None) -> str:
    currency = currency or str(setting("currency", "₽"))
    if value is None or value == "":
        return "по договорённости"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number.is_integer():
        formatted = f"{int(number):,}".replace(",", " ")
    else:
        formatted = f"{number:,.2f}".replace(",", " ").replace(".", ",")
    return f"{formatted} {currency}"


def lines(value: Any) -> list[str]:
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def tariff_key(label: Any) -> str:
    value = str(label or "").strip().lower()
    if value in {"basic", "base", "базик", "басик", "базовый"}:
        return "basic"
    if value in {"vip", "вип"}:
        return "vip"
    if value in {"pro", "про", "профи"}:
        return "pro"
    return value.replace(" ", "_") or "basic"


def product_tariff_price(product: dict[str, Any], tariff: Any, mode: str = "buy") -> float:
    key = tariff_key(tariff)
    if mode == "rent":
        preferred = product.get(f"rental_price_{key}")
        fallback = product.get("rental_price")
        if preferred in (None, "") and key == "vip":
            preferred = round(to_float(fallback, 0) * 1.35) if fallback not in (None, "") else None
        if preferred in (None, "") and key == "pro":
            preferred = round(to_float(fallback, 0) * 1.75) if fallback not in (None, "") else None
        return to_float(preferred if preferred not in (None, "") else fallback, 0.0)
    preferred = product.get(f"price_{key}")
    fallback = product.get("price")
    if preferred in (None, "") and key == "vip":
        preferred = round(to_float(fallback, 0) * 1.35) if fallback not in (None, "") else None
    if preferred in (None, "") and key == "pro":
        preferred = round(to_float(fallback, 0) * 1.75) if fallback not in (None, "") else None
    return to_float(preferred if preferred not in (None, "") else fallback, 0.0)


def product_tariff_prices(product: dict[str, Any], mode: str = "buy") -> dict[str, float]:
    result: dict[str, float] = {}
    for label in lines(product.get("tariffs", "")) or ["Басик", "VIP", "Pro"]:
        result[label] = product_tariff_price(product, label, mode)
    if not any(tariff_key(label) == "basic" for label in result):
        result = {"Басик": product_tariff_price(product, "Басик", mode), **result}
    return result


def calculator_payload() -> dict[str, Any]:
    project_types = []
    for item_id, (name, icon, key, default) in CALCULATOR_PROJECT_KEYS.items():
        project_types.append({
            "id": item_id,
            "name": str(setting(f"calc_project_{item_id}_name", name) or name),
            "icon": icon,
            "basePrice": to_float(setting(key, default), default),
        })
    features = []
    for item_id, (name, key, default) in CALCULATOR_FEATURE_KEYS.items():
        features.append({
            "id": item_id,
            "name": str(setting(f"calc_feature_{item_id}_name", name) or name),
            "price": to_float(setting(key, default), default),
        })
    return {"ok": True, "projectTypes": project_types, "features": features, "currency": str(setting("currency", "₽"))}


def public_file_url(path: str) -> str:
    return f"/{path}" if path else ""


def allowed_file(filename: str, allowed: set[str]) -> bool:
    if "." not in filename:
        return False
    return filename.rsplit(".", 1)[1].lower() in allowed


def save_upload(field_name: str, target_dir: Path, allowed: set[str], prefix: str) -> tuple[str, str] | None:
    upload = request.files.get(field_name)
    if not upload or not upload.filename:
        return None
    if not allowed_file(upload.filename, allowed):
        flash(f"Файл {upload.filename} имеет неподдерживаемое расширение.", "error")
        return None
    original = secure_filename(upload.filename)
    suffix = Path(original).suffix.lower()
    filename = f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(6)}{suffix}"
    target_dir.mkdir(parents=True, exist_ok=True)
    upload.save(target_dir / filename)
    relative = str((target_dir / filename).relative_to(BASE_DIR)).replace("\\", "/")
    return relative, upload.filename


@app.template_filter("money")
def money_filter(value: Any) -> str:
    return money(value)


@app.template_filter("lines")
def lines_filter(value: Any) -> list[str]:
    return lines(value)


@app.context_processor
def inject_helpers() -> dict[str, Any]:
    return {
        "csrf_token": csrf_token,
        "setting": setting,
        "status_names": STATUS_NAMES,
        "purchase_status_names": PURCHASE_STATUS_NAMES,
        "money": money,
        "current_user": current_user,
        "is_admin": is_admin,
    }


@app.route("/")
def index() -> Response:
    return send_from_directory(BASE_DIR / "dist", "index.html")


@app.route("/assets/<path:filename>")
def frontend_assets(filename: str) -> Response:
    return send_from_directory(BASE_DIR / "dist" / "assets", filename)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str) -> Response:
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/favicon.ico")
def favicon() -> Response:
    return Response(status=204)


@app.route("/vacancies")
def vacancies() -> str:
    vacancies_list = active_records("vacancies")
    return render_template("vacancies.html", title="Вакансии", vacancies=vacancies_list, active="vacancies")



@app.route("/terms")
def terms() -> str:
    return render_template("legal.html", title="Условия использования", active="terms", kind="terms")


@app.route("/privacy")
def privacy() -> str:
    return render_template("legal.html", title="Конфиденциальность", active="privacy", kind="privacy")


@app.route("/api/me")
def api_me() -> Response:
    if is_admin():
        return jsonify({"ok": True, "authenticated": True, "role": "admin", "username": str(setting("admin_username", "admin")), "balance": None, "accountUrl": "/admin/"})
    user = current_user()
    if not user:
        return jsonify({"ok": True, "authenticated": False})
    return jsonify({
        "ok": True,
        "authenticated": True,
        "role": user.get("role", "user"),
        "username": user.get("username", ""),
        "email": user.get("email", ""),
        "balance": to_float(user.get("balance", 0)),
        "accountUrl": "/account",
    })


@app.route("/api/products")
def api_products() -> Response:
    payload = []
    for product in active_records("products"):
        tariffs = lines(product.get("tariffs", "")) or ["VIP", "Pro"]
        if not any(t.lower() in {"basic", "басик"} for t in tariffs):
            tariffs = ["Басик"] + tariffs
        else:
            tariffs = ["Басик" if t.lower() == "basic" else t for t in tariffs]
        buy_prices = product_tariff_prices(product, "buy")
        rent_prices = product_tariff_prices(product, "rent")
        min_buy = min([value for value in buy_prices.values() if value > 0] or [to_float(product.get("price", 0), 0)])
        min_rent = min([value for value in rent_prices.values() if value > 0] or [to_float(product.get("rental_price", 0), 0)])
        payload.append({
            "id": product.get("id"),
            "title": product.get("title", ""),
            "category": product.get("category", ""),
            "icon": product.get("icon", "🤖"),
            "description": product.get("description", ""),
            "features": lines(product.get("features", "")),
            "price": min_buy,
            "old_price": product.get("old_price"),
            "priceLabel": money(min_buy),
            "oldPriceLabel": money(product.get("old_price")) if product.get("old_price") else "",
            "rentalPrice": min_rent,
            "rentalPriceLabel": money(min_rent) if min_rent else "",
            "rentAvailable": bool(int(product.get("rent_available", 0) or 0)),
            "tariffPrices": buy_prices,
            "rentalTariffPrices": rent_prices,
            "badge": product.get("badge", ""),
            "tariffs": tariffs,
            "imageUrl": public_file_url(product.get("image_path", "")),
            "demoUrl": product.get("demo_url", ""),
            "hasFile": bool(product.get("file_path")),
        })
    return jsonify({"ok": True, "products": payload, "currency": str(setting("currency", "₽"))})


@app.route("/api/calculator")
def api_calculator() -> Response:
    return jsonify(calculator_payload())


@app.route("/api/order", methods=["POST"])
def api_order() -> Response:
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    contact = str(payload.get("telegram", "")).strip()
    service = str(payload.get("projectType", "")).strip()
    message = str(payload.get("description", "")).strip()
    features = str(payload.get("features", "")).strip()
    if features:
        message = f"{message}\n\nЖелаемые функции: {features}"

    if len(name) < 2 or len(contact) < 2 or len(service) < 2 or len(message) < 5:
        return jsonify({"ok": False, "error": "Заполните имя, Telegram, тип проекта и описание."}), 400

    insert_record(
        "orders",
        {
            "name": name,
            "contact": contact,
            "contact_type": "Telegram",
            "service": service,
            "budget": "",
            "message": message,
            "status": "new",
            "admin_note": "",
            "user_id": session.get("user_id"),
        },
    )
    return jsonify({"ok": True})


@app.route("/api/purchase", methods=["POST"])
def api_purchase() -> Response:
    user = current_user()
    if not user:
        return jsonify({"ok": False, "authRequired": True, "error": "Для покупки войдите или создайте аккаунт."}), 401
    payload = request.get_json(silent=True) or {}
    product_id = to_int(payload.get("productId"), 0)
    product = find_record("products", product_id)
    if not product or int(product.get("is_active", 1) or 0) != 1:
        return jsonify({"ok": False, "error": "Товар не найден."}), 404
    contact = str(payload.get("contact", "")).strip()
    contact_type = str(payload.get("contactType", "Telegram")).strip() or "Telegram"
    tariff = str(payload.get("tariff", "")).strip() or "Basic"
    note = str(payload.get("note", "")).strip()
    if len(contact) < 2:
        return jsonify({"ok": False, "error": "Укажите контакт для связи."}), 400
    purchase_type = str(payload.get("purchaseType", payload.get("mode", "buy"))).strip().lower() or "buy"
    if purchase_type not in {"buy", "rent"}:
        purchase_type = "buy"
    rent_available = bool(int(product.get("rent_available", 0) or 0))
    if purchase_type == "rent" and not rent_available:
        return jsonify({"ok": False, "error": "Для этого товара аренда недоступна."}), 400
    rent_days = max(1, min(365, to_int(payload.get("rentDays"), 30))) if purchase_type == "rent" else 0
    unit_price = product_tariff_price(product, tariff, "rent" if purchase_type == "rent" else "buy")
    if purchase_type == "rent" and unit_price <= 0:
        unit_price = round(product_tariff_price(product, tariff, "buy") * 0.02, 2)
    price = round(unit_price * rent_days, 2) if purchase_type == "rent" else unit_price
    format_label = f"Аренда без исходного кода на {rent_days} дн." if purchase_type == "rent" else "Покупка с выдачей товара"
    balance = to_float(user.get("balance", 0), 0.0)
    if price > balance:
        return jsonify({"ok": False, "error": f"Недостаточно демо-баланса. Нужно {money(price)}, на балансе {money(balance)}."}), 400

    data = load_data()
    for item in data.get("users", []):
        if int(item.get("id", 0) or 0) == int(user.get("id", 0) or 0):
            item["balance"] = round(to_float(item.get("balance", 0), 0.0) - price, 2)
            item["updated_at"] = now()
            break
    purchase_id = int(data.setdefault("counters", {}).get("purchases", 1) or 1)
    data["counters"]["purchases"] = purchase_id + 1
    file_path = "" if purchase_type == "rent" else product.get("file_path", "")
    file_original_name = "" if purchase_type == "rent" else product.get("file_original_name", "")
    purchase = {
        "id": purchase_id,
        "user_id": user.get("id"),
        "username": user.get("username", ""),
        "product_id": product.get("id"),
        "product_title": product.get("title", ""),
        "tariff": tariff,
        "purchase_type": purchase_type,
        "format_label": format_label,
        "contact": contact,
        "contact_type": contact_type,
        "note": note,
        "rent_days": rent_days,
        "unit_price": unit_price,
        "amount": price,
        "status": "new" if purchase_type == "rent" else "paid",
        "file_path": file_path,
        "file_original_name": file_original_name,
        "created_at": now(),
        "updated_at": now(),
    }
    data.setdefault("purchases", []).append(purchase)
    order_id = int(data.setdefault("counters", {}).get("orders", 1) or 1)
    data["counters"]["orders"] = order_id + 1
    admin_hint = "Администрация сама настраивает бота и размещает его на VPS. Исходный код клиенту не выдаётся." if purchase_type == "rent" else "Выдать файл/исходники, если они прикреплены к товару."
    data.setdefault("orders", []).append({
        "id": order_id,
        "created_at": now(),
        "updated_at": now(),
        "name": user.get("username", ""),
        "contact": contact,
        "contact_type": contact_type,
        "service": f"{'Аренда' if purchase_type == 'rent' else 'Покупка'}: {product.get('title', '')}",
        "budget": money(price),
        "message": f"Формат: {format_label}\nТариф: {tariff}\nКомментарий: {note or 'нет'}\nПокупка #{purchase_id}\n{admin_hint}",
        "status": "new",
        "admin_note": "",
        "user_id": user.get("id"),
    })
    save_data(data)
    return jsonify({"ok": True, "purchaseId": purchase_id, "accountUrl": "/account", "hasFile": bool(file_path), "purchaseType": purchase_type, "amount": price})


@app.route("/order", methods=["POST"])
def order() -> Response:
    verify_csrf()
    name = request.form.get("name", "").strip()
    contact = request.form.get("contact", "").strip()
    service = request.form.get("service", "").strip()
    message = request.form.get("message", "").strip()
    features = request.form.get("features", "").strip()
    if features:
        message = f"{message}\n\nЖелаемые функции: {features}"

    if len(name) < 2 or len(contact) < 4 or len(service) < 2 or len(message) < 5:
        return redirect(url_for("index", error="1", _anchor="contact"))

    insert_record(
        "orders",
        {
            "name": name,
            "contact": contact,
            "contact_type": request.form.get("contact_type", "Telegram").strip(),
            "service": service,
            "budget": request.form.get("budget", "").strip(),
            "message": message,
            "status": "new",
            "admin_note": "",
            "user_id": session.get("user_id"),
        },
    )
    return redirect(url_for("index", sent="1", _anchor="contact"))


@app.route("/login")
def login_page() -> str:
    if is_admin():
        return redirect(url_for("admin_panel"))
    if current_user():
        return redirect(url_for("account"))
    return render_template("auth.html", mode=request.args.get("mode", "login"), next_url=request.args.get("next", ""))


@app.route("/login", methods=["POST"])
def login_post() -> Response:
    verify_csrf()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "")
    if username == str(setting("admin_username", "admin")) and check_password_hash(str(setting("admin_password_hash", "")), password):
        session["admin_logged_in"] = True
        session.pop("user_id", None)
        flash("Добро пожаловать в админ-панель.", "success")
        return redirect(url_for("admin_panel"))

    for user in all_records("users"):
        if (username.lower() in {str(user.get("username", "")).lower(), str(user.get("email", "")).lower()}
                and check_password_hash(str(user.get("password_hash", "")), password)
                and int(user.get("is_active", 1) or 0) == 1):
            session["user_id"] = int(user.get("id"))
            session.pop("admin_logged_in", None)
            flash("Вы вошли в личный кабинет.", "success")
            return redirect(next_url or url_for("account"))

    flash("Неверный логин или пароль.", "error")
    return redirect(url_for("login_page"))


@app.route("/register", methods=["POST"])
def register_post() -> Response:
    verify_csrf()
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip()
    contact = request.form.get("contact", "").strip()
    password = request.form.get("password", "")
    if len(username) < 3 or len(password) < 6:
        flash("Логин должен быть от 3 символов, пароль — от 6 символов.", "error")
        return redirect(url_for("login_page", mode="register"))
    if not email or "@" not in email or len(contact) < 2:
        flash("Укажите почту и username Telegram.", "error")
        return redirect(url_for("login_page", mode="register"))
    conflict = user_identity_conflict(username, email)
    if conflict:
        flash(conflict, "error")
        return redirect(url_for("login_page", mode="register"))
    user_id = insert_record("users", {
        "username": username,
        "email": email,
        "contact": contact,
        "password_hash": generate_password_hash(password),
        "role": "user",
        "balance": to_float(setting("demo_balance", 100000), 100000),
        "is_active": 1,
    })
    session["user_id"] = user_id
    session.pop("admin_logged_in", None)
    flash("Аккаунт создан. Демо-баланс начислен.", "success")
    return redirect(url_for("account"))


@app.route("/logout")
def logout() -> Response:
    session.pop("user_id", None)
    session.pop("admin_logged_in", None)
    flash("Вы вышли из аккаунта.", "success")
    return redirect(url_for("login_page"))


@app.route("/account")
def account() -> str | Response:
    user = current_user()
    if is_admin():
        return redirect(url_for("admin_panel"))
    if not user:
        return redirect(url_for("login_page", next="/account"))
    purchases = [p for p in all_records_desc("purchases") if int(p.get("user_id", 0) or 0) == int(user.get("id", 0) or 0)]
    orders = [o for o in all_records_desc("orders") if int(o.get("user_id", 0) or 0) == int(user.get("id", 0) or 0)]
    return render_template("account.html", user=user, purchases=purchases, orders=orders)


@app.route("/download/<int:purchase_id>")
def download_purchase(purchase_id: int) -> Response:
    purchase = find_record("purchases", purchase_id)
    if not purchase:
        abort(404)
    user = current_user()
    if not is_admin() and (not user or int(purchase.get("user_id", 0) or 0) != int(user.get("id", 0) or 0)):
        abort(403)
    file_path = str(purchase.get("file_path", ""))
    if not file_path:
        abort(404, "Для этой покупки файл не прикреплен.")
    full_path = (BASE_DIR / file_path).resolve()
    if not str(full_path).startswith(str(FILE_DIR.resolve())) or not full_path.exists():
        abort(404)
    return send_file(full_path, as_attachment=True, download_name=purchase.get("file_original_name") or full_path.name)


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login() -> Response | str:
    if request.method == "GET":
        return redirect(url_for("login_page", next="/admin/"))
    return login_post()


@app.route("/admin/logout")
def admin_logout() -> Response:
    session.pop("admin_logged_in", None)
    flash("Вы вышли из админ-панели.", "success")
    return redirect(url_for("login_page"))


@app.route("/admin/")
def admin_panel() -> str | Response:
    if not is_admin():
        return redirect(url_for("login_page", next="/admin/"))

    page = request.args.get("page", "dashboard")
    edit_id = to_int(request.args.get("edit"), 0)
    edit_item = None
    editable_tables = {
        "products": "products",
        "packages": "packages",
        "testimonials": "testimonials",
        "faq": "faq",
        "users": "users",
        "vacancies": "vacancies",
    }
    if page in editable_tables and edit_id:
        edit_item = find_record(editable_tables[page], edit_id)

    profile_user = None
    profile_orders: list[dict[str, Any]] = []
    profile_purchases: list[dict[str, Any]] = []
    if page == "profile":
        profile_id = to_int(request.args.get("user"), 0)
        profile_user = find_record("users", profile_id)
        if not profile_user:
            flash("Пользователь не найден.", "error")
            return redirect(url_for("admin_panel", page="users"))
        profile_orders = [o for o in all_records_desc("orders") if int(o.get("user_id", 0) or 0) == profile_id]
        profile_purchases = [p for p in all_records_desc("purchases") if int(p.get("user_id", 0) or 0) == profile_id]

    purchases = all_records_desc("purchases")
    data = {
        "orders": all_records_desc("orders"),
        "products": all_records("products"),
        "packages": all_records("packages"),
        "testimonials": all_records("testimonials"),
        "faqs": all_records("faq"),
        "users": all_records_desc("users"),
        "purchases": purchases,
        "vacancies": all_records("vacancies"),
        "profile_user": profile_user,
        "profile_orders": profile_orders,
        "profile_purchases": profile_purchases,
        "settings": load_data().get("settings", {}),
        "metrics": {
            "orders": count_records("orders"),
            "new_orders": count_records("orders", lambda item: item.get("status") == "new"),
            "products": count_records("products"),
            "active_products": count_records("products", lambda item: int(item.get("is_active", 1) or 0) == 1),
            "users": count_records("users"),
            "purchases": count_records("purchases"),
            "revenue": sum(to_float(item.get("amount", 0), 0) for item in purchases if item.get("status") == "paid"),
            "vacancies": count_records("vacancies"),
        },
    }
    return render_template("admin/panel.html", page=page, edit_item=edit_item, **data)


@app.route("/admin/export/orders")
def export_orders() -> Response:
    require_admin()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Дата", "Имя", "Контакт", "Тип контакта", "Услуга", "Бюджет", "Статус", "Сообщение", "Заметка"])
    for item in all_records_desc("orders"):
        writer.writerow([
            item.get("id", ""),
            item.get("created_at", ""),
            item.get("name", ""),
            item.get("contact", ""),
            item.get("contact_type", ""),
            item.get("service", ""),
            item.get("budget", ""),
            STATUS_NAMES.get(item.get("status", "new"), item.get("status", "")),
            item.get("message", ""),
            item.get("admin_note", ""),
        ])
    filename = f"orders-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/admin/export/purchases")
def export_purchases() -> Response:
    require_admin()
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID", "Дата", "Пользователь", "Товар", "Формат", "Тариф", "Дни аренды", "Контакт", "Сумма", "Статус"])
    for item in all_records_desc("purchases"):
        writer.writerow([item.get("id", ""), item.get("created_at", ""), item.get("username", ""), item.get("product_title", ""), item.get("format_label", "Аренда без исходного кода" if item.get("purchase_type") == "rent" else "Покупка"), item.get("tariff", ""), item.get("rent_days", ""), item.get("contact", ""), item.get("amount", ""), PURCHASE_STATUS_NAMES.get(item.get("status", "paid"), item.get("status", ""))])
    filename = f"purchases-{datetime.now().strftime('%Y-%m-%d')}.csv"
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv; charset=utf-8", headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/admin/order/update", methods=["POST"])
def admin_order_update() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    status = request.form.get("status", "new")
    if status not in STATUS_NAMES:
        status = "new"
    update_record("orders", record_id, {"status": status, "admin_note": request.form.get("admin_note", "").strip()})
    flash("Заявка обновлена.", "success")
    return redirect(url_for("admin_panel", page="orders"))


@app.route("/admin/order/delete", methods=["POST"])
def admin_order_delete() -> Response:
    require_admin()
    verify_csrf()
    delete_record("orders", to_int(request.form.get("id"), 0))
    flash("Заявка удалена.", "success")
    return redirect(url_for("admin_panel", page="orders"))


@app.route("/admin/purchase/update", methods=["POST"])
def admin_purchase_update() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    status = request.form.get("status", "paid")
    if status not in PURCHASE_STATUS_NAMES:
        status = "paid"
    update_record("purchases", record_id, {"status": status, "admin_note": request.form.get("admin_note", "").strip()})
    flash("Покупка обновлена.", "success")
    return redirect(url_for("admin_panel", page="purchases"))


@app.route("/admin/purchase/delete", methods=["POST"])
def admin_purchase_delete() -> Response:
    require_admin()
    verify_csrf()
    delete_record("purchases", to_int(request.form.get("id"), 0))
    flash("Покупка удалена.", "success")
    return redirect(url_for("admin_panel", page="purchases"))


@app.route("/admin/product/save", methods=["POST"])
def admin_product_save() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    existing = find_record("products", record_id) if record_id else {}
    payload = {
        "title": request.form.get("title", "").strip(),
        "category": request.form.get("category", "").strip(),
        "icon": request.form.get("icon", "🤖").strip() or "🤖",
        "description": request.form.get("description", "").strip(),
        "features": request.form.get("features", "").strip(),
        "tariffs": request.form.get("tariffs", "").strip(),
        "price": to_number_or_none(request.form.get("price")),
        "old_price": to_number_or_none(request.form.get("old_price")),
        "price_basic": to_number_or_none(request.form.get("price_basic")),
        "price_vip": to_number_or_none(request.form.get("price_vip")),
        "price_pro": to_number_or_none(request.form.get("price_pro")),
        "rental_price": to_number_or_none(request.form.get("rental_price")),
        "rental_price_basic": to_number_or_none(request.form.get("rental_price_basic")),
        "rental_price_vip": to_number_or_none(request.form.get("rental_price_vip")),
        "rental_price_pro": to_number_or_none(request.form.get("rental_price_pro")),
        "rent_available": 1 if request.form.get("rent_available") else 0,
        "badge": request.form.get("badge", "").strip(),
        "demo_url": request.form.get("demo_url", "").strip(),
        "sort_order": to_int(request.form.get("sort_order"), 100),
        "is_active": 1 if request.form.get("is_active") else 0,
        "image_path": (existing or {}).get("image_path", ""),
        "file_path": (existing or {}).get("file_path", ""),
        "file_original_name": (existing or {}).get("file_original_name", ""),
    }
    image = save_upload("image", IMAGE_DIR, IMAGE_EXTENSIONS, "product-image")
    if image:
        payload["image_path"] = image[0]
    file_upload = save_upload("product_file", FILE_DIR, FILE_EXTENSIONS, "product-file")
    if file_upload:
        payload["file_path"] = file_upload[0]
        payload["file_original_name"] = file_upload[1]
    if record_id:
        update_record("products", record_id, payload)
        flash("Товар обновлён.", "success")
    else:
        insert_record("products", payload)
        flash("Товар добавлен в маркет.", "success")
    return redirect(url_for("admin_panel", page="products"))


@app.route("/admin/product/delete", methods=["POST"])
def admin_product_delete() -> Response:
    require_admin()
    verify_csrf()
    delete_record("products", to_int(request.form.get("id"), 0))
    flash("Товар удалён.", "success")
    return redirect(url_for("admin_panel", page="products"))




def remove_uploaded_file(relative_path: str) -> None:
    if not relative_path:
        return
    try:
        full_path = (BASE_DIR / relative_path).resolve()
        if str(full_path).startswith(str(UPLOAD_DIR.resolve())) and full_path.exists():
            full_path.unlink()
    except OSError:
        pass

@app.route("/admin/product/clear-file", methods=["POST"])
def admin_product_clear_file() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    kind = request.form.get("kind")
    product = find_record("products", record_id) or {}
    if kind == "image":
        remove_uploaded_file(str(product.get("image_path", "")))
        update_record("products", record_id, {"image_path": ""})
        flash("Фото товара удалено. На карточку вернулась старая эмодзи-иконка.", "success")
    elif kind == "file":
        remove_uploaded_file(str(product.get("file_path", "")))
        update_record("products", record_id, {"file_path": "", "file_original_name": ""})
        flash("Файл товара отвязан.", "success")
    return redirect(url_for("admin_panel", page="products", edit=record_id))


@app.route("/admin/package/save", methods=["POST"])
def admin_package_save() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    payload = {
        "title": request.form.get("title", "").strip(),
        "description": request.form.get("description", "").strip(),
        "features": request.form.get("features", "").strip(),
        "price": to_number_or_none(request.form.get("price")),
        "badge": request.form.get("badge", "").strip(),
        "demo_url": request.form.get("demo_url", "").strip(),
        "sort_order": to_int(request.form.get("sort_order"), 100),
        "is_active": 1 if request.form.get("is_active") else 0,
    }
    if record_id:
        update_record("packages", record_id, payload)
        flash("Пакет обновлён.", "success")
    else:
        insert_record("packages", payload)
        flash("Пакет добавлен.", "success")
    return redirect(url_for("admin_panel", page="packages"))


@app.route("/admin/package/delete", methods=["POST"])
def admin_package_delete() -> Response:
    require_admin()
    verify_csrf()
    delete_record("packages", to_int(request.form.get("id"), 0))
    flash("Пакет удалён.", "success")
    return redirect(url_for("admin_panel", page="packages"))


@app.route("/admin/testimonial/save", methods=["POST"])
def admin_testimonial_save() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    payload = {
        "author": request.form.get("author", "").strip(),
        "role": request.form.get("role", "").strip(),
        "text": request.form.get("text", "").strip(),
        "rating": max(1, min(5, to_int(request.form.get("rating"), 5))),
        "sort_order": to_int(request.form.get("sort_order"), 100),
        "is_active": 1 if request.form.get("is_active") else 0,
    }
    if record_id:
        update_record("testimonials", record_id, payload)
        flash("Отзыв обновлён.", "success")
    else:
        insert_record("testimonials", payload)
        flash("Отзыв добавлен.", "success")
    return redirect(url_for("admin_panel", page="testimonials"))


@app.route("/admin/testimonial/delete", methods=["POST"])
def admin_testimonial_delete() -> Response:
    require_admin()
    verify_csrf()
    delete_record("testimonials", to_int(request.form.get("id"), 0))
    flash("Отзыв удалён.", "success")
    return redirect(url_for("admin_panel", page="testimonials"))


@app.route("/admin/faq/save", methods=["POST"])
def admin_faq_save() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    payload = {
        "question": request.form.get("question", "").strip(),
        "answer": request.form.get("answer", "").strip(),
        "sort_order": to_int(request.form.get("sort_order"), 100),
        "is_active": 1 if request.form.get("is_active") else 0,
    }
    if record_id:
        update_record("faq", record_id, payload)
        flash("FAQ обновлён.", "success")
    else:
        insert_record("faq", payload)
        flash("FAQ добавлен.", "success")
    return redirect(url_for("admin_panel", page="faq"))


@app.route("/admin/faq/delete", methods=["POST"])
def admin_faq_delete() -> Response:
    require_admin()
    verify_csrf()
    delete_record("faq", to_int(request.form.get("id"), 0))
    flash("FAQ удалён.", "success")
    return redirect(url_for("admin_panel", page="faq"))


@app.route("/admin/user/save", methods=["POST"])
def admin_user_save() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    fields = {
        "username": request.form.get("username", "").strip(),
        "email": request.form.get("email", "").strip(),
        "contact": request.form.get("contact", "").strip(),
        "balance": to_float(request.form.get("balance"), 0.0),
        "role": request.form.get("role", "user").strip() or "user",
        "is_active": 1 if request.form.get("is_active") else 0,
    }
    conflict = user_identity_conflict(fields["username"], fields["email"], exclude_id=record_id)
    if conflict:
        flash(conflict, "error")
        return redirect(url_for("admin_panel", page="users", edit=record_id) if record_id else url_for("admin_panel", page="users"))
    password = request.form.get("password", "")
    if password:
        fields["password_hash"] = generate_password_hash(password)
    if record_id:
        update_record("users", record_id, fields)
        flash("Пользователь обновлён.", "success")
    else:
        if not password:
            flash("Для нового пользователя укажите пароль.", "error")
            return redirect(url_for("admin_panel", page="users"))
        fields["password_hash"] = generate_password_hash(password)
        insert_record("users", fields)
        flash("Пользователь добавлен.", "success")
    return redirect(url_for("admin_panel", page="users"))


@app.route("/admin/user/delete", methods=["POST"])
def admin_user_delete() -> Response:
    require_admin()
    verify_csrf()
    delete_record("users", to_int(request.form.get("id"), 0))
    flash("Пользователь удалён.", "success")
    return redirect(url_for("admin_panel", page="users"))


@app.route("/admin/settings/save", methods=["POST"])
def admin_settings_save() -> Response:
    require_admin()
    verify_csrf()
    update_settings({
        "site_name": request.form.get("site_name", "DevBots").strip(),
        "site_badge": request.form.get("site_badge", "").strip(),
        "hero_title_1": request.form.get("hero_title_1", "").strip(),
        "hero_title_2": request.form.get("hero_title_2", "").strip(),
        "hero_subtitle": request.form.get("hero_subtitle", "").strip(),
        "email": request.form.get("email", "").strip(),
        "telegram": request.form.get("telegram", "").strip(),
        "whatsapp": request.form.get("whatsapp", "").strip(),
        "currency": request.form.get("currency", "₽").strip() or "₽",
        "demo_balance": to_float(request.form.get("demo_balance"), 100000),
        "calc_project_bot_name": request.form.get("calc_project_bot_name", "Telegram бот").strip() or "Telegram бот",
        "calc_project_website_name": request.form.get("calc_project_website_name", "Сайт").strip() or "Сайт",
        "calc_project_webapp_name": request.form.get("calc_project_webapp_name", "Web приложение").strip() or "Web приложение",
        "calc_project_design_name": request.form.get("calc_project_design_name", "Дизайн").strip() or "Дизайн",
        "calc_feature_admin_name": request.form.get("calc_feature_admin_name", "Админ-панель").strip() or "Админ-панель",
        "calc_feature_payment_name": request.form.get("calc_feature_payment_name", "Интеграция платежей").strip() or "Интеграция платежей",
        "calc_feature_api_name": request.form.get("calc_feature_api_name", "API интеграции").strip() or "API интеграции",
        "calc_feature_auth_name": request.form.get("calc_feature_auth_name", "Система авторизации").strip() or "Система авторизации",
        "calc_feature_push_name": request.form.get("calc_feature_push_name", "Push уведомления").strip() or "Push уведомления",
        "calc_feature_analytics_name": request.form.get("calc_feature_analytics_name", "Аналитика").strip() or "Аналитика",
        "calc_feature_database_name": request.form.get("calc_feature_database_name", "База данных").strip() or "База данных",
        "calc_feature_responsive_name": request.form.get("calc_feature_responsive_name", "Адаптивный дизайн").strip() or "Адаптивный дизайн",
        "calc_project_bot": to_float(request.form.get("calc_project_bot"), 10000),
        "calc_project_website": to_float(request.form.get("calc_project_website"), 25000),
        "calc_project_webapp": to_float(request.form.get("calc_project_webapp"), 50000),
        "calc_project_design": to_float(request.form.get("calc_project_design"), 15000),
        "calc_feature_admin": to_float(request.form.get("calc_feature_admin"), 15000),
        "calc_feature_payment": to_float(request.form.get("calc_feature_payment"), 10000),
        "calc_feature_api": to_float(request.form.get("calc_feature_api"), 12000),
        "calc_feature_auth": to_float(request.form.get("calc_feature_auth"), 8000),
        "calc_feature_push": to_float(request.form.get("calc_feature_push"), 5000),
        "calc_feature_analytics": to_float(request.form.get("calc_feature_analytics"), 7000),
        "calc_feature_database": to_float(request.form.get("calc_feature_database"), 6000),
        "calc_feature_responsive": to_float(request.form.get("calc_feature_responsive"), 8000),
    })
    flash("Настройки сайта сохранены.", "success")
    return redirect(url_for("admin_panel", page="settings"))


@app.route("/admin/access/save", methods=["POST"])
def admin_access_save() -> Response:
    require_admin()
    verify_csrf()
    username = request.form.get("admin_username", "admin").strip() or "admin"
    password = request.form.get("admin_password", "")
    fields: dict[str, Any] = {"admin_username": username}
    if password:
        if len(password) < 8:
            flash("Пароль должен быть не короче 8 символов.", "error")
            return redirect(url_for("admin_panel", page="settings"))
        fields["admin_password_hash"] = generate_password_hash(password)
    update_settings(fields)
    flash("Доступ администратора обновлён.", "success")
    return redirect(url_for("admin_panel", page="settings"))


@app.route("/admin/vacancy/save", methods=["POST"])
def admin_vacancy_save() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    existing = find_record("vacancies", record_id) if record_id else {}
    payload = {
        "title": request.form.get("title", "").strip(),
        "city": request.form.get("city", "").strip(),
        "employment": request.form.get("employment", "").strip(),
        "salary": request.form.get("salary", "").strip(),
        "description": request.form.get("description", "").strip(),
        "advantages": request.form.get("advantages", "").strip(),
        "requirements": request.form.get("requirements", "").strip(),
        "contact": request.form.get("contact", "").strip(),
        "sort_order": to_int(request.form.get("sort_order"), 100),
        "is_active": 1 if request.form.get("is_active") else 0,
        "image_path": (existing or {}).get("image_path", ""),
    }
    image = save_upload("image", VACANCY_IMAGE_DIR, IMAGE_EXTENSIONS, "vacancy-image")
    if image:
        payload["image_path"] = image[0]
    if not payload["title"] or not payload["description"]:
        flash("Заполните название и описание вакансии.", "error")
        return redirect(url_for("admin_panel", page="vacancies", edit=record_id) if record_id else url_for("admin_panel", page="vacancies"))
    if record_id:
        update_record("vacancies", record_id, payload)
        flash("Вакансия обновлена.", "success")
    else:
        insert_record("vacancies", payload)
        flash("Вакансия добавлена на сайт.", "success")
    return redirect(url_for("admin_panel", page="vacancies"))


@app.route("/admin/vacancy/delete", methods=["POST"])
def admin_vacancy_delete() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    vacancy = find_record("vacancies", record_id) or {}
    remove_uploaded_file(str(vacancy.get("image_path", "")))
    delete_record("vacancies", record_id)
    flash("Вакансия удалена.", "success")
    return redirect(url_for("admin_panel", page="vacancies"))


@app.route("/admin/vacancy/clear-image", methods=["POST"])
def admin_vacancy_clear_image() -> Response:
    require_admin()
    verify_csrf()
    record_id = to_int(request.form.get("id"), 0)
    vacancy = find_record("vacancies", record_id) or {}
    remove_uploaded_file(str(vacancy.get("image_path", "")))
    update_record("vacancies", record_id, {"image_path": ""})
    flash("Фото вакансии удалено.", "success")
    return redirect(url_for("admin_panel", page="vacancies", edit=record_id))


ensure_data_file()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
