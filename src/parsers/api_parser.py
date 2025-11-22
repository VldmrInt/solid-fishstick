"""
Парсер магазина Ozon через API Composer
"""

import json
import time
import logging
import random
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict

from src.config.settings import Settings
from src.utils.selenium_manager import SeleniumManager

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
        self.products: List[ProductInfo] = []

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

        try:
            # Создаем WebDriver
            self.selenium_manager.create_driver(headless=True)
            logger.info("WebDriver инициализирован")

            page_num = 1
            empty_pages_count = 0
            max_empty_pages = 3

            while page_num <= max_pages:
                logger.info(f"Парсинг страницы {page_num}/{max_pages}...")

                try:
                    page_products = self._parse_page(page_num)

                    if not page_products:
                        empty_pages_count += 1
                        logger.warning(f"Страница {page_num} пустая ({empty_pages_count}/{max_empty_pages})")

                        if empty_pages_count >= max_empty_pages:
                            logger.info("Достигнуто максимальное количество пустых страниц, завершаем")
                            break
                    else:
                        empty_pages_count = 0  # Сбрасываем счетчик
                        self.products.extend(page_products)
                        logger.info(f"Страница {page_num}: найдено {len(page_products)} товаров")

                    # Задержка между страницами
                    delay = random.uniform(Settings.REQUEST_DELAY_MIN, Settings.REQUEST_DELAY_MAX)
                    time.sleep(delay)

                    page_num += 1

                except Exception as e:
                    logger.error(f"Ошибка парсинга страницы {page_num}: {e}")
                    break

            logger.info(f"Парсинг завершен. Всего собрано товаров: {len(self.products)}")
            return self.products

        finally:
            self.selenium_manager.close()

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

        # Загружаем страницу
        if not self.selenium_manager.navigate_to_url(api_url, wait_for_load=True):
            logger.error(f"Не удалось загрузить страницу {page_num}")
            return []

        # Извлекаем JSON
        json_content = self.selenium_manager.extract_json_from_page()
        if not json_content:
            logger.error(f"Не удалось извлечь JSON со страницы {page_num}")
            return []

        # Парсим JSON
        try:
            data = json.loads(json_content)
            return self._extract_products_from_json(data)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга JSON: {e}")
            return []

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

        # Формируем полный API URL
        api_url = f"{Settings.OZON_API_BASE}?url={seller_path}&__rr=1"

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

            # Цены
            current_price = ''
            original_price = ''

            price_info = item.get('price', {})
            if isinstance(price_info, dict):
                current_price = str(price_info.get('price', price_info.get('current', '')))
                original_price = str(price_info.get('originalPrice', price_info.get('original', '')))
            elif isinstance(price_info, (str, int, float)):
                current_price = str(price_info)

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
