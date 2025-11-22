"""
Парсер магазина Ozon через API Composer
"""

import json
import time
import logging
import random
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from urllib.parse import quote

from src.config.settings import Settings
from src.utils.selenium_manager import SeleniumManager

try:
    from src.utils.playwright_manager import PlaywrightManager, HAS_PLAYWRIGHT
except ImportError:
    HAS_PLAYWRIGHT = False
    PlaywrightManager = None

logger = logging.getLogger(__name__)


@dataclass
class ProductInfo:
    """Информация о товаре"""
    sku: str
    name: str
    current_price: str
    original_price: str
    link: str
    image_url: str = ''
    rating: str = ''
    reviews_count: str = ''
    seller_name: str = ''
    seller_inn: str = ''
    category: str = ''
    brand: str = ''
    success: bool = True
    error: str = ''

    def to_dict(self) -> dict:
        """Преобразует в словарь"""
        return asdict(self)


class OzonAPIParser:
    """
    Парсер магазина через Ozon API Composer.

    Использует официальный API Ozon для получения структурированных данных
    вместо парсинга HTML.
    """

    def __init__(self, seller_url: str):
        """
        Args:
            seller_url: URL магазина
                       (напр. https://www.ozon.ru/seller/magazin-123456/?miniapp=seller_123456)
        """
        self.seller_url = seller_url
        self.seller_id = Settings.get_seller_id(seller_url)
        self.selenium_manager = SeleniumManager()
        self.playwright_manager = PlaywrightManager() if HAS_PLAYWRIGHT else None
        self.products: List[ProductInfo] = []
        self.use_playwright = False  # Флаг использования Playwright

        # API endpoint management
        self.current_api_endpoint = Settings.OZON_API_BASE_MOBILE
        self.tried_endpoints = []  # Список уже попробованных endpoints
        self.api_endpoint_failures = 0  # Счетчик ошибок текущего endpoint

        if not self.seller_id:
            logger.warning(f"Не удалось извлечь ID продавца из URL: {seller_url}")

    def parse_all_pages(self, max_pages: int = 100) -> List[ProductInfo]:
        """
        Парсит все страницы магазина.

        Args:
            max_pages: Максимальное количество страниц для парсинга

        Returns:
            Список товаров
        """
        logger.info(f"Начало парсинга магазина: {self.seller_url}")
        logger.info(f"ID продавца: {self.seller_id}")

        # Информация о доступных API endpoints
        logger.info("📡 Доступные API endpoints:")
        logger.info(f"   1. Mobile API (приоритет):  {Settings.OZON_API_BASE_MOBILE}")
        logger.info(f"   2. Desktop API (fallback):  {Settings.OZON_API_BASE_DESKTOP}")
        logger.info(f"   Начинаем с: Mobile API")

        try:
            # Для мобильного API приоритетнее использовать Playwright
            if HAS_PLAYWRIGHT and self.playwright_manager:
                try:
                    logger.info("Инициализация Playwright (приоритет для mobile API)...")
                    self.playwright_manager.create_browser(headless=True)
                    logger.info("Playwright инициализирован")
                    self.use_playwright = True
                except Exception as e:
                    logger.warning(f"Не удалось инициализировать Playwright: {e}")
                    # Fallback на Selenium
                    logger.info("Переключаемся на Selenium как fallback...")
                    self.selenium_manager.create_driver(headless=True)
                    logger.info("WebDriver (Selenium) инициализирован")
                    self.use_playwright = False
            else:
                # Playwright недоступен, используем Selenium
                logger.info("Playwright недоступен, используем Selenium...")
                self.selenium_manager.create_driver(headless=True)
                logger.info("WebDriver (Selenium) инициализирован")
                self.use_playwright = False

            page_num = 1
            empty_pages_count = 0
            max_empty_pages = 3
            blocked_count = 0
            max_blocked = 1  # Переключаемся на Playwright сразу при первой блокировке

            while page_num <= max_pages:
                logger.info(f"Парсинг страницы {page_num}/{max_pages}...")

                try:
                    page_products = self._parse_page(page_num)

                    if not page_products:
                        empty_pages_count += 1
                        logger.warning(f"Страница {page_num} пустая ({empty_pages_count}/{max_empty_pages})")

                        # Пробуем переключить API endpoint если еще не пробовали все варианты
                        if self._should_try_alternative_endpoint():
                            if self._switch_to_alternative_endpoint():
                                logger.info(f"🔄 Повторяем страницу {page_num} с новым endpoint")
                                empty_pages_count = 0  # Сбрасываем счетчик
                                continue  # Пробуем эту же страницу снова

                        # Проверяем, не заблокировали ли нас
                        if self._check_if_blocked():
                            logger.warning(f"Обнаружена блокировка!")

                            # Немедленно переключаемся на Playwright
                            if not self.use_playwright and HAS_PLAYWRIGHT and self.playwright_manager:
                                logger.info("🎭 Переключаемся на Playwright из-за блокировки Selenium...")
                                self.selenium_manager.close()
                                try:
                                    self.playwright_manager.create_browser(headless=True)
                                    self.use_playwright = True
                                    empty_pages_count = 0  # Сбрасываем счетчик пустых страниц
                                    logger.info("✅ Playwright успешно инициализирован, повторяем страницу")
                                    continue  # Пробуем текущую страницу снова с Playwright
                                except Exception as pw_error:
                                    logger.error(f"Не удалось инициализировать Playwright: {pw_error}")
                                    break
                            elif self.use_playwright:
                                # Уже на Playwright и всё равно блокировка - увеличиваем задержку
                                logger.warning("⚠️ Блокировка даже на Playwright, увеличиваем задержку...")
                                time.sleep(20)  # Дополнительная задержка

                        if empty_pages_count >= max_empty_pages:
                            logger.info("Достигнуто максимальное количество пустых страниц, завершаем")
                            break
                    else:
                        empty_pages_count = 0  # Сбрасываем счетчик
                        blocked_count = 0  # Сбрасываем счетчик блокировок
                        self.products.extend(page_products)
                        logger.info(f"Страница {page_num}: найдено {len(page_products)} товаров")

                    # Задержка между страницами
                    delay = random.uniform(Settings.REQUEST_DELAY_MIN, Settings.REQUEST_DELAY_MAX)
                    logger.debug(f"Задержка перед следующей страницей: {delay:.1f} сек")
                    time.sleep(delay)

                    page_num += 1

                except Exception as e:
                    logger.error(f"Ошибка парсинга страницы {page_num}: {e}")

                    # Еще одна попытка переключиться на Playwright при ошибке
                    if not self.use_playwright and HAS_PLAYWRIGHT and self.playwright_manager:
                        logger.info("Пытаемся переключиться на Playwright после ошибки...")
                        try:
                            self.selenium_manager.close()
                            self.playwright_manager.create_browser(headless=True)
                            self.use_playwright = True
                            continue  # Пробуем текущую страницу снова
                        except:
                            break
                    else:
                        break

            logger.info(f"Парсинг завершен. Всего собрано товаров: {len(self.products)}")
            return self.products

        finally:
            self.selenium_manager.close()
            if self.playwright_manager:
                self.playwright_manager.close()

    def _parse_page(self, page_num: int) -> List[ProductInfo]:
        """
        Парсит одну страницу магазина через API.

        Args:
            page_num: Номер страницы

        Returns:
            Список товаров на странице
        """
        # Формируем URL для API
        api_url = self._build_api_url(page_num)

        # Выбираем менеджер в зависимости от флага
        manager = self.playwright_manager if self.use_playwright else self.selenium_manager

        # Загружаем страницу
        if not manager.navigate_to_url(api_url, wait_for_load=True):
            logger.error(f"Не удалось загрузить страницу {page_num}")
            self.api_endpoint_failures += 1

            # Если несколько ошибок подряд - возможно проблема с endpoint
            if self.api_endpoint_failures >= 2:
                logger.warning(f"⚠️ Множественные ошибки с текущим API endpoint ({self.api_endpoint_failures} подряд)")

            return []

        # Извлекаем JSON
        json_content = manager.extract_json_from_page()
        if not json_content:
            logger.error(f"Не удалось извлечь JSON со страницы {page_num}")
            return []

        # Парсим JSON
        try:
            data = json.loads(json_content)

            # Сохраняем пример JSON для отладки (только первая страница)
            if page_num == 1:
                debug_file = Settings.PROJECT_ROOT / f'debug_page_{page_num}.json'
                try:
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Пример JSON сохранен в {debug_file} для отладки")
                except Exception as e:
                    logger.debug(f"Не удалось сохранить debug JSON: {e}")

            return self._extract_products_from_json(data)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return []

    def _check_if_blocked(self) -> bool:
        """
        Проверяет, заблокирован ли доступ.

        Returns:
            True если обнаружена блокировка
        """
        manager = self.playwright_manager if self.use_playwright else self.selenium_manager
        return manager.is_page_blocked()

    def _should_try_alternative_endpoint(self) -> bool:
        """
        Проверяет, стоит ли попробовать альтернативный API endpoint.

        Returns:
            True если есть непроверенные альтернативные endpoints
        """
        all_endpoints = [Settings.OZON_API_BASE_MOBILE, Settings.OZON_API_BASE_DESKTOP]
        untried = [ep for ep in all_endpoints if ep not in self.tried_endpoints]
        return len(untried) > 0

    def _switch_to_alternative_endpoint(self) -> bool:
        """
        Переключается на альтернативный API endpoint.

        Returns:
            True если переключение успешно, False если нет альтернатив
        """
        all_endpoints = [Settings.OZON_API_BASE_MOBILE, Settings.OZON_API_BASE_DESKTOP]

        # Помечаем текущий endpoint как попробованный
        if self.current_api_endpoint not in self.tried_endpoints:
            self.tried_endpoints.append(self.current_api_endpoint)

        # Ищем непроверенный endpoint
        for endpoint in all_endpoints:
            if endpoint not in self.tried_endpoints:
                old_endpoint = self.current_api_endpoint
                self.current_api_endpoint = endpoint
                self.api_endpoint_failures = 0

                endpoint_name = "Mobile API" if endpoint == Settings.OZON_API_BASE_MOBILE else "Desktop API"
                old_name = "Mobile API" if old_endpoint == Settings.OZON_API_BASE_MOBILE else "Desktop API"

                logger.warning(f"🔄 Переключаемся с {old_name} на {endpoint_name}")
                logger.info(f"   Старый: {old_endpoint}")
                logger.info(f"   Новый:  {endpoint}")

                return True

        logger.error("❌ Все доступные API endpoints уже проверены")
        return False

    def _build_api_url(self, page_num: int) -> str:
        """
        Формирует URL для API Composer.

        Args:
            page_num: Номер страницы

        Returns:
            Полный URL API
        """
        # Убираем https://www.ozon.ru из seller_url
        seller_path = self.seller_url.replace(Settings.OZON_BASE_URL, '')

        # Добавляем page параметр если нужно
        if page_num > 1:
            if '?' in seller_path:
                seller_path += f'&page={page_num}'
            else:
                seller_path += f'?page={page_num}'

        # Формируем полный API URL с URL-encoding параметра url
        # Используем текущий активный endpoint
        encoded_path = quote(seller_path, safe='')
        api_url = f"{self.current_api_endpoint}?url={encoded_path}&__rr=1"

        endpoint_name = "Mobile" if self.current_api_endpoint == Settings.OZON_API_BASE_MOBILE else "Desktop"
        logger.debug(f"Seller path: {seller_path}")
        logger.debug(f"API endpoint: {endpoint_name}")
        logger.debug(f"API URL: {api_url}")
        return api_url

    def _extract_products_from_json(self, data: dict) -> List[ProductInfo]:
        """
        Извлекает товары из JSON ответа API.

        Args:
            data: Распарсенный JSON

        Returns:
            Список товаров
        """
        products = []
        widget_states = data.get('widgetStates', {})

        # Ищем виджеты с товарами
        # Возможные ключи: searchResultsV2, webCurrentSeller, webSearchResult, productTile
        for key, value in widget_states.items():
            if any(pattern in key.lower() for pattern in ['searchresult', 'seller', 'product', 'tile']):
                try:
                    # value может быть строкой (JSON) или уже dict
                    widget_data = json.loads(value) if isinstance(value, str) else value

                    # Извлекаем товары из виджета
                    items = self._extract_items_from_widget(widget_data)
                    products.extend(items)

                except Exception as e:
                    logger.debug(f"Пропуск виджета {key}: {e}")
                    continue

        logger.debug(f"Извлечено товаров из JSON: {len(products)}")
        return products

    def _extract_items_from_widget(self, widget_data: dict) -> List[ProductInfo]:
        """
        Извлекает товары из виджета.

        Args:
            widget_data: Данные виджета

        Returns:
            Список товаров
        """
        products = []

        # Ищем массив items в различных местах структуры
        items = widget_data.get('items', [])

        # Если items пустой, пробуем другие варианты
        if not items:
            # Иногда товары в products
            items = widget_data.get('products', [])

        # Иногда items внутри вложенных объектов
        if not items and 'state' in widget_data:
            items = widget_data['state'].get('items', [])

        for item in items:
            product = self._parse_product_item(item)
            if product:
                products.append(product)

        return products

    def _parse_product_item(self, item: dict) -> Optional[ProductInfo]:
        """
        Парсит один товар из JSON item.

        Args:
            item: Данные товара

        Returns:
            ProductInfo или None если ошибка
        """
        try:
            # SKU/артикул
            sku = str(item.get('sku', item.get('id', '')))
            if not sku:
                return None

            # Название
            name = item.get('name', item.get('title', ''))

            # Ссылка
            link = item.get('link', item.get('url', ''))
            if link and not link.startswith('http'):
                link = Settings.OZON_BASE_URL + link

            # Цены - более глубокий парсинг
            current_price = ''
            original_price = ''

            # Вариант 1: объект price
            price_info = item.get('price', {})
            if isinstance(price_info, dict):
                # НОВАЯ СТРУКТУРА: price.price[0].text
                price_array = price_info.get('price')
                if isinstance(price_array, list) and len(price_array) > 0:
                    # Извлекаем текст цены из первого элемента массива
                    price_obj = price_array[0]
                    if isinstance(price_obj, dict):
                        current_price = price_obj.get('text', '')

                    # Старая цена может быть во втором элементе или отдельном поле
                    if len(price_array) > 1:
                        old_price_obj = price_array[1]
                        if isinstance(old_price_obj, dict):
                            original_price = old_price_obj.get('text', '')

                # Если не нашли через массив, пробуем старые варианты
                if not current_price:
                    # Пробуем разные поля для текущей цены
                    current_price = (
                        price_info.get('text') or
                        price_info.get('current') or
                        price_info.get('finalPrice') or
                        price_info.get('displayPrice') or
                        ''
                    )

                # Пробуем разные поля для старой цены
                if not original_price:
                    original_price = (
                        price_info.get('originalPrice') or
                        price_info.get('original') or
                        price_info.get('ozonCardPrice') or
                        ''
                    )

                # Конвертируем в строку если это число
                if isinstance(current_price, (int, float)):
                    current_price = f"{current_price} ₽"
                if isinstance(original_price, (int, float)):
                    original_price = f"{original_price} ₽"

            elif isinstance(price_info, (str, int, float)):
                current_price = str(price_info)
                if isinstance(price_info, (int, float)):
                    current_price = f"{current_price} ₽"

            # Вариант 2: прямые поля в item
            if not current_price:
                current_price = item.get('finalPrice', item.get('displayPrice', ''))
                if isinstance(current_price, (int, float)):
                    current_price = f"{current_price} ₽"

            # Логируем если цена не найдена
            if not current_price:
                logger.debug(f"Цена не найдена для товара {sku}. Доступные ключи: {list(item.keys())[:10]}")

            current_price = str(current_price)
            original_price = str(original_price)

            # Изображение
            image_url = item.get('image', item.get('coverImage', item.get('img', '')))
            if isinstance(image_url, dict):
                image_url = image_url.get('src', '')

            # Рейтинг и отзывы
            rating = str(item.get('rating', ''))
            reviews_count = str(item.get('reviewsCount', item.get('reviews', '')))

            # Бренд и категория
            brand = item.get('brand', '')
            category = item.get('category', '')

            # Продавец
            seller_name = ''
            seller_inn = ''
            seller_info = item.get('seller', {})
            if isinstance(seller_info, dict):
                seller_name = seller_info.get('name', '')
                seller_inn = seller_info.get('inn', '')

            product = ProductInfo(
                sku=sku,
                name=name,
                current_price=current_price,
                original_price=original_price,
                link=link,
                image_url=image_url,
                rating=rating,
                reviews_count=reviews_count,
                seller_name=seller_name,
                seller_inn=seller_inn,
                brand=brand,
                category=category,
                success=True,
                error=''
            )

            return product

        except Exception as e:
            logger.error(f"Ошибка парсинга товара: {e}")
            return None

    def get_products(self) -> List[ProductInfo]:
        """Возвращает список спарсенных товаров"""
        return self.products

    def get_products_count(self) -> int:
        """Возвращает количество спарсенных товаров"""
        return len(self.products)
