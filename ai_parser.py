import json
import os
import re
from typing import Any, Dict, List

# База типовых авторабот и запчастей в Казахстане (цены в тенге ₸)
# Поддерживает ключевые слова на русском и казахском языках
CATALOG_RULES: List[Dict[str, Any]] = [
    {
        "keywords": ["масло двс", "замена масла", "масла", "масло 5w", "масло 0w", "5w30", "5w-30", "5w40", "5w-40", "май ауыстыру", "қозғалтқыш майы"],
        "title": "Замена моторного масла (синтетика 5W-30) и масляного фильтра",
        "category": "mandatory",
        "price": 32500,
    },
    {
        "keywords": ["масло акпп", "акпп", "коробк", "вариатор", "беріліс қорабы"],
        "title": "Частичная замена масла в АКПП с фильтром",
        "category": "recommended",
        "price": 46000,
    },
    {
        "keywords": ["пыльник шрус", "шрус", "гранат", "шаңқап"],
        "title": "Замена пыльника наружного ШРУС + комплект смазки и хомутов",
        "category": "mandatory",
        "price": 18500,
    },
    {
        "keywords": ["передние колодк", "колодки перед", "передних колод", "колодки стерты", "колодок", "тежегіш қалып", "алдыңғы колодка"],
        "title": "Замена передних тормозных колодок (комплект + смазка направляющих)",
        "category": "mandatory",
        "price": 26500,
    },
    {
        "keywords": ["задние колодк", "колодки зад", "задних колод", "артқы колодка"],
        "title": "Замена задних тормозных колодок (комплект + работа)",
        "category": "mandatory",
        "price": 22000,
    },
    {
        "keywords": ["тормозные диск", "диски тормоз", "проточка диск", "тежегіш диск"],
        "title": "Замена передних тормозных дисков (пара)",
        "category": "mandatory",
        "price": 48000,
    },
    {
        "keywords": ["тормозная жидкост", "тормозной жидкост", "dot-4", "dot4", "тежегіш сұйықтық"],
        "title": "Аппаратная замена тормозной жидкости DOT-4",
        "category": "recommended",
        "price": 10500,
    },
    {
        "keywords": ["амортизатор", "стойка потек", "стойки аморт", "потекли стойк"],
        "title": "Замена передних амортизаторов (пара, KYB + работа)",
        "category": "mandatory",
        "price": 54000,
    },
    {
        "keywords": ["стойки стабилизатор", "стабилизатор", "линки", "яйца"],
        "title": "Замена стоек переднего стабилизатора (пара)",
        "category": "mandatory",
        "price": 13500,
    },
    {
        "keywords": ["шаров", "рычаг", "сайлентблок", "ходов", "стук в подвеск", "аспа"],
        "title": "Замена шаровых опор и сайлентблоков передних рычагов",
        "category": "mandatory",
        "price": 29000,
    },
    {
        "keywords": ["развал", "схожден", "геометр"],
        "title": "Регулировка 3D развал-схождения осей",
        "category": "recommended",
        "price": 8500,
    },
    {
        "keywords": ["грм", "ремень грм", "помпа", "ролик грм"],
        "title": "Замена комплекта ремня ГРМ (ремень, ролики, работа)",
        "category": "mandatory",
        "price": 58000,
    },
    {
        "keywords": ["свеч", "зажиган", "троит", "вибрац", "оталдыру шамы"],
        "title": "Замена комплекта свечей зажигания (4 шт., NGK/Denso)",
        "category": "mandatory",
        "price": 16500,
    },
    {
        "keywords": ["дроссел", "форсунк", "инжектор"],
        "title": "Чистка дроссельной заслонки с адаптацией",
        "category": "recommended",
        "price": 9500,
    },
    {
        "keywords": ["клапанн", "прокладк", "течь масла", "подтек", "подтёк"],
        "title": "Замена прокладки клапанной крышки и мойка узла",
        "category": "mandatory",
        "price": 23500,
    },
    {
        "keywords": ["салонный фильтр", "фильтр салон", "салон сүзгісі"],
        "title": "Замена салонного угольного фильтра",
        "category": "recommended",
        "price": 7500,
    },
    {
        "keywords": ["воздушный фильтр", "фильтр воздуш", "ауа сүзгісі"],
        "title": "Замена воздушного фильтра двигателя",
        "category": "recommended",
        "price": 6500,
    },
    {
        "keywords": ["антифриз", "тосол", "радиатор", "охлажден", "салқындатқыш"],
        "title": "Полная аппаратная замена антифриза G12+",
        "category": "recommended",
        "price": 18000,
    },
    {
        "keywords": ["диагностик", "чек горит", "check engine", "сканер", "қате"],
        "title": "Компьютерная диагностика электронных систем (OBD-II)",
        "category": "mandatory",
        "price": 6000,
    },
    {
        "keywords": ["аккумулятор", "акб", "генератор"],
        "title": "Диагностика АКБ и проверка зарядки генератора",
        "category": "recommended",
        "price": 4500,
    },
    {
        "keywords": ["подшипник", "ступиц", "гул"],
        "title": "Замена переднего ступичного подшипника",
        "category": "mandatory",
        "price": 24000,
    },
]

# Коэффициент корректировки цен по классу авто
PREMIUM_BRANDS = ["lexus", "лексус", "bmw", "бмв", "mercedes", "мерседес", "audi", "ауди", "land cruiser", "прадо", "prado"]
BUDGET_BRANDS = ["cobalt", "кобальт", "nexia", "нексия", "lada", "лада", "granta", "гранта", "accent", "акцент", "rio", "рио"]


def _detect_price_multiplier(text_lower: str) -> float:
    if any(b in text_lower for b in PREMIUM_BRANDS):
        return 1.25
    if any(b in text_lower for b in BUDGET_BRANDS):
        return 0.85
    return 1.0


def _round_kzt(amount: float) -> int:
    return int(round(amount / 500.0) * 500)


def fallback_parse_estimate(note: str) -> Dict[str, Any]:
    """Умный локальный парсер заметок мастера на русском и казахском (100% оффлайн-надёжность)."""
    text = (note or "").strip()
    text_lower = text.lower()
    multiplier = _detect_price_multiplier(text_lower)

    matched_items: List[Dict[str, Any]] = []
    used_titles = set()

    for rule in CATALOG_RULES:
        if any(kw in text_lower for kw in rule["keywords"]):
            if rule["title"] not in used_titles:
                used_titles.add(rule["title"])
                matched_items.append(
                    {
                        "title": rule["title"],
                        "category": rule["category"],
                        "price": _round_kzt(rule["price"] * multiplier),
                        "is_approved": True,
                    }
                )

    # Если упомянут фильтр масляный, но не было слова «масло»
    if "маслян" in text_lower and not any("масла" in i["title"].lower() for i in matched_items):
        matched_items.append(
            {
                "title": "Замена масляного фильтра и доливка моторного масла",
                "category": "mandatory",
                "price": _round_kzt(14000 * multiplier),
                "is_approved": True,
            }
        )

    # Если текст нестандартный и ни одно правило не совпало — формируем разумную базовую смету
    if not matched_items:
        matched_items = [
            {
                "title": "Комплексная диагностика по обращению клиента",
                "category": "mandatory",
                "price": 7500,
                "is_approved": True,
            },
            {
                "title": f"Работы по заявке: {text[:60]}" if text else "Плановый технический осмотр узлов",
                "category": "mandatory",
                "price": 18000,
                "is_approved": True,
            },
            {
                "title": "Проверка уровней технических жидкостей и давления в шинах",
                "category": "recommended",
                "price": 4500,
                "is_approved": True,
            },
        ]
    elif not any(i["category"] == "recommended" for i in matched_items):
        # Добавляем одну полезную рекомендацию для демонстрации интерактивного чекбокса у клиента
        matched_items.append(
            {
                "title": "Комплексная проверка ходовой части и всех жидкостей",
                "category": "recommended",
                "price": 6000,
                "is_approved": True,
            }
        )

    return {
        "source": "local_smart_parser",
        "items": matched_items,
    }


def parse_estimate_with_ai(note: str, car_model: str = "") -> Dict[str, Any]:
    """
    Пытается разобрать заметку мастера через Google Gemini API (gemini-2.5-flash).
    При отсутствии GEMINI_API_KEY, ошибке сети или некорректном ответе
    моментально переключается на локальный умный парсер.
    """
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    combined_text = f"{car_model}. {note}".strip(". ")

    if not api_key:
        return fallback_parse_estimate(combined_text)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        prompt = (
            "Ты — опытный мастер-приёмщик СТО в Казахстане (город Жезказган). "
            "Преобразуй сырую заметку механика в структурированную смету ремонта в тенге (KZT).\n"
            f"Автомобиль: {car_model or 'не указан'}\n"
            f"Заметка мастера: {note}\n\n"
            "Верни СТРОГО валидный JSON-массив объектов без markdown-обёрток. Формат каждого объекта:\n"
            '{"title": "Чёткое название работы и/или запчасти на русском", "category": "mandatory" или "recommended", "price": целое_число_в_тенге}\n'
            "Правила:\n"
            "- category='mandatory' для критичных дефектов безопасности и базового ТО.\n"
            "- category='recommended' для профилактических и дополнительных работ (салонный фильтр, развал, профилактика).\n"
            "- Цены реалистичные для независимых СТО Казахстана, кратные 500 тенге (от 4000 до 95000 ₸).\n"
            "- От 2 до 7 позиций."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw_text = (response.text or "").strip()

        # Извлекаем JSON даже если модель обернула его в ```json ... ```
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            return fallback_parse_estimate(combined_text)

        parsed = json.loads(match.group(0))
        cleaned_items: List[Dict[str, Any]] = []
        for entry in parsed:
            title = str(entry.get("title", "")).strip()
            category = str(entry.get("category", "mandatory")).strip().lower()
            if category not in ("mandatory", "recommended"):
                category = "mandatory"
            try:
                price = max(1000, _round_kzt(float(entry.get("price", 10000))))
            except (TypeError, ValueError):
                price = 10000
            if title:
                cleaned_items.append(
                    {
                        "title": title,
                        "category": category,
                        "price": price,
                        "is_approved": True,
                    }
                )

        if not cleaned_items:
            return fallback_parse_estimate(combined_text)

        return {
            "source": "gemini-2.5-flash",
            "items": cleaned_items,
        }
    except Exception:
        return fallback_parse_estimate(combined_text)
