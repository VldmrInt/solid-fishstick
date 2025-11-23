"""
Парсер магазина Ozon через прямой HTML парсинг
Использует undetected-chromedriver для обхода защиты
"""

import re
import json
import time
import random
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

try:
    from undetected_chromedriver import Chrome, ChromeOptions
    HAS_UC = True
except ImportError:
    HAS_UC = False
    Chrome = None
    ChromeOptions = None

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

from src.config.settings import Settings

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


class OzonHTMLParser:
    """
    Парсер магазина через прямой HTML парсинг.

    Использует undetected-chromedriver для загрузки страниц
    и BeautifulSoup для извлечения данных.
    """

    # Регулярные выражения
    RE_PRODUCT_ID = re.compile(r'/product/[^\"\'>]*-(\d+)', re.IGNORECASE)
    RE_PRICE = re.compile(r'[\d\u00A0\u2009\u202F]+(?:\u2009| )?₽')
    RE_SKU = re.compile(r'\"sku\"\s*:\s*(\d+)')

    def __init__(self, seller_url: str, headless: bool = True):
        """
        Args:
            seller_url: URL магазина
            headless: Запускать в headless режиме
        """
        if not HAS_UC:
            raise ImportError(
                "undetected-chromedriver не установлен. "
                "Установите: pip install undetected-chromedriver"
            )

        self.seller_url = seller_url
        self.seller_id = Settings.get_seller_id(seller_url)
        self.headless = headless
        self.driver: Optional[Chrome] = None
        self.products: List[ProductInfo] = []

        if not self.seller_id:
            logger.warning(f"Не удалось извлечь ID продавца из URL: {seller_url}")

    def _create_driver(self) -> Chrome:
        """Создает undetected Chrome driver"""
        options = ChromeOptions()

        if self.headless:
            options.add_argument("--headless=new")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2
        })
        options.add_argument("--disable-blink-features=AutomationControlled")

        driver = Chrome(options=options, version_main=Settings.CHROME_VERSION)
        logger.info(f"Создан undetected-chromedriver (headless={self.headless})")
        return driver

    def parse_all_pages(self, max_pages: int = 100) -> List[ProductInfo]:
        """
        Парсит магазин с бесконечной лентой через скролл.

        Ozon использует бесконечную ленту товаров, поэтому парсим
        только первую страницу со скроллом до конца.

        Args:
            max_pages: Игнорируется (оставлен для совместимости)

        Returns:
            Список товаров
        """
        logger.info(f"Начало HTML парсинга магазина: {self.seller_url}")
        logger.info(f"ID продавца: {self.seller_id}")
        logger.info(f"Режим: {'headless' if self.headless else 'с видимым окном'}")
        logger.info("ℹ️  Ozon использует бесконечную ленту - парсим одну страницу со скроллом")

        try:
            self.driver = self._create_driver()

            # Парсим только первую страницу с бесконечным скроллом
            logger.info(f"📄 Загрузка страницы магазина...")
            page_products = self._parse_page(1)

            if page_products:
                self.products.extend(page_products)
                logger.info(f"✅ Найдено товаров: {len(page_products)}")
            else:
                logger.warning("Товары не найдены")

            logger.info(f"HTML парсинг завершен. Всего собрано товаров: {len(self.products)}")
            return self.products

        finally:
            if self.driver:
                self.driver.quit()
                logger.info("WebDriver закрыт")

    def _parse_page(self, page_num: int) -> List[ProductInfo]:
        """
        Парсит одну страницу.

        Args:
            page_num: Номер страницы

        Returns:
            Список товаров на странице
        """
        # Формируем URL
        current_url = f"{self.seller_url}&page={page_num}" if page_num > 1 else self.seller_url

        # Загружаем страницу
        self.driver.get(current_url)
        logger.debug(f"Открыта страница: {current_url}")

        # Ждем загрузки
        time.sleep(5)

        # Проверяем на экран проверки CloudFlare
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Пожалуйста, дождитесь окончания проверки')]")
                )
            )
            logger.info("🔒 Обнаружен экран проверки CloudFlare, ждем...")
            WebDriverWait(self.driver, 60).until_not(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Пожалуйста, дождитесь окончания проверки')]")
                )
            )
            logger.info("✅ Проверка CloudFlare завершена")
        except TimeoutException:
            logger.debug("Экран проверки не обнаружен, продолжаем")

        # Проверяем на пустую страницу
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'ничего не нашлось')]")
                )
            )
            logger.info(f"Страница {page_num} пустая (нет товаров)")
            return []
        except TimeoutException:
            pass  # Страница с товарами

        # Скроллим страницу для загрузки всех товаров
        self._scroll_page()

        # Получаем HTML
        page_source = self.driver.page_source

        # Сохраняем HTML первой страницы для отладки
        if page_num == 1:
            debug_file = Settings.PROJECT_ROOT / f'debug_html_page_{page_num}.html'
            try:
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(page_source)
                logger.info(f"💾 HTML первой страницы сохранен в {debug_file} для отладки")
            except Exception as e:
                logger.warning(f"Не удалось сохранить debug HTML: {e}")

        # Парсим HTML
        if HAS_BS4:
            products = self._parse_html_with_bs4(page_source)
        else:
            products = self._parse_html_fallback(page_source)

        return products

    def _scroll_page(self):
        """
        Скроллит бесконечную ленту Ozon до конца.

        Продолжает скролл пока появляются новые товары.
        Останавливается если товары не появляются 10 секунд.
        """
        logger.info("🔄 Начинаем бесконечный скролл для загрузки всех товаров...")

        last_product_count = 0
        last_change_time = time.time()
        max_wait_seconds = 10  # Ждем 10 секунд без новых товаров
        scroll_attempts = 0
        max_scroll_attempts = 1000  # Увеличен лимит для больших магазинов

        logger.info("   Начальный подсчет товаров на странице...")

        while scroll_attempts < max_scroll_attempts:
            # Скроллим вниз
            scroll_step = random.randint(800, 1200)
            self.driver.execute_script(f"window.scrollBy(0, {scroll_step});")

            # Небольшая пауза для загрузки контента
            time.sleep(0.8)

            # Считаем текущее количество товаров на странице
            # Используем специфичные селекторы для Ozon
            current_product_count = self.driver.execute_script("""
                // Считаем ссылки на товары Ozon
                const productLinks = document.querySelectorAll('a[href*="/product/"]');

                // Фильтруем уникальные товары по SKU в URL
                const uniqueProducts = new Set();
                productLinks.forEach(link => {
                    const match = link.href.match(/\\/product\\/[^\\/-]+-(\\d+)/);
                    if (match && match[1]) {
                        uniqueProducts.add(match[1]);
                    }
                });

                return uniqueProducts.size;
            """)

            # Проверяем появились ли новые товары
            current_time = time.time()
            elapsed_since_change = current_time - last_change_time

            if current_product_count > last_product_count:
                logger.info(f"   Загружено товаров: {current_product_count} (+{current_product_count - last_product_count})")
                last_product_count = current_product_count
                last_change_time = current_time  # Обновляем время последнего изменения
            else:
                # Если товары не появляются больше max_wait_seconds секунд
                if elapsed_since_change >= max_wait_seconds:
                    logger.info(f"✅ Скролл завершен: {max_wait_seconds} секунд без новых товаров")
                    logger.info(f"   Всего загружено уникальных товаров: {current_product_count}")
                    break

            scroll_attempts += 1

            # Логируем каждые 20 попыток для отслеживания прогресса
            if scroll_attempts % 20 == 0:
                logger.info(f"   Скролл #{scroll_attempts}: товаров {current_product_count}, времени без изменений: {elapsed_since_change:.1f}с")

        if scroll_attempts >= max_scroll_attempts:
            logger.warning(f"⚠️ Достигнут лимит попыток скролла ({max_scroll_attempts})")

        logger.info(f"Скролл завершен за {scroll_attempts} попыток, найдено {last_product_count} товаров")

    def _parse_html_with_bs4(self, html: str) -> List[ProductInfo]:
        """Парсит HTML с помощью BeautifulSoup"""
        soup = BeautifulSoup(html, 'html.parser')
        items = {}

        # Исключаем блок "Возможно, вам понравится"
        recommendations_blocks = soup.find_all('div', class_=lambda x: x and 'im8_24' in x)
        for block in recommendations_blocks:
            # Проверяем, есть ли текст "Возможно, вам понравится"
            if block.find(string=lambda text: text and 'Возможно, вам понравится' in text):
                logger.info("🚫 Исключаем блок 'Возможно, вам понравится'")
                block.decompose()  # Удаляем блок из DOM

        # Поиск по ссылкам на товары
        for a in soup.find_all('a', href=True):
            href = a['href']
            m = self.RE_PRODUCT_ID.search(href)
            if not m:
                continue

            pid = m.group(1)

            # Проверяем, не находится ли ссылка в блоке рекомендаций
            # (дополнительная защита если блок не удалился)
            parent_text = ''
            check_parent = a.parent
            for _ in range(5):
                if check_parent:
                    parent_text = check_parent.get_text(separator=' ', strip=True)
                    if 'Возможно, вам понравится' in parent_text:
                        # Пропускаем этот товар
                        break
                    check_parent = check_parent.parent
            else:
                # Товар не в блоке рекомендаций, парсим его

                # Название товара
                name = self._clean_text(a.text)
                if not name:
                    img = a.find('img')
                    if img and 'alt' in img.attrs:
                        name = self._clean_text(img['alt'])

                # Поиск цен в родителях
                prices = []
                container = a.parent
                for _ in range(4):
                    if container:
                        text = container.get_text(separator=' ', strip=True)
                        found_prices = self.RE_PRICE.findall(text)
                        for p in found_prices:
                            cleaned_p = self._clean_text(p)
                            if cleaned_p and cleaned_p not in prices:
                                prices.append(cleaned_p)
                        container = container.parent

                # Полная ссылка на товар
                full_link = f"https://www.ozon.ru{href}" if not href.startswith('http') else href

                items[pid] = {
                    'name': name,
                    'sku': pid,
                    'prices': prices[:2],
                    'link': full_link
                }

        # Конвертируем в ProductInfo
        products = []
        for pid, data in items.items():
            prices = data['prices']
            product = ProductInfo(
                sku=data['sku'],
                name=data['name'],
                current_price=prices[0] if len(prices) > 0 else '',
                original_price=prices[1] if len(prices) > 1 else '',
                link=data['link']
            )
            products.append(product)

        logger.debug(f"BeautifulSoup: найдено {len(products)} товаров (исключая рекомендации)")
        return products

    def _parse_html_fallback(self, html: str) -> List[ProductInfo]:
        """Парсит HTML с помощью регулярных выражений (fallback)"""

        # Удаляем блок "Возможно, вам понравится" из HTML
        # Ищем начало блока
        recommendation_start = html.find('Возможно, вам понравится')
        if recommendation_start != -1:
            logger.info("🚫 Исключаем блок 'Возможно, вам понравится' (fallback)")
            # Ищем начало блока (за 500 символов до текста)
            block_start = max(0, recommendation_start - 500)
            # Ищем конец блока (примерно 10000 символов после текста, чтобы захватить все товары)
            block_end = min(len(html), recommendation_start + 10000)
            # Вырезаем блок
            html = html[:block_start] + html[block_end:]

        items = {}

        for m in self.RE_PRODUCT_ID.finditer(html):
            pid = m.group(1)
            start, end = m.start(), m.end()
            window = html[max(0, start - 2000): end + 2000]

            # Название
            name_match = (
                re.search(r'alt=\"([^\"]{5,300}?)\"', window) or
                re.search(r'title=\"([^\"]{5,300}?)\"', window)
            )
            name = self._clean_text(name_match.group(1)) if name_match else ''

            # Цены
            prices = [self._clean_text(p) for p in self.RE_PRICE.findall(window)]
            seen = set()
            prices = [p for p in prices if p and p not in seen and not seen.add(p)][:2]

            # Ссылка
            link = f"https://www.ozon.ru/product/-{pid}/"

            items[pid] = {
                'name': name,
                'sku': pid,
                'prices': prices,
                'link': link
            }

        # Конвертируем в ProductInfo
        products = []
        for pid, data in items.items():
            prices = data['prices']
            product = ProductInfo(
                sku=data['sku'],
                name=data['name'],
                current_price=prices[0] if len(prices) > 0 else '',
                original_price=prices[1] if len(prices) > 1 else '',
                link=data['link']
            )
            products.append(product)

        logger.debug(f"Fallback: найдено {len(products)} товаров (исключая рекомендации)")
        return products

    @staticmethod
    def _clean_text(s: str) -> str:
        """Очищает текст от лишних символов"""
        if not s:
            return ''
        s = s.strip()
        s = re.sub(r'[\u00A0\u2009\u202F]+', ' ', s)
        s = re.sub(r'\s+', ' ', s)
        return s

    def get_products(self) -> List[ProductInfo]:
        """Возвращает список спарсенных товаров"""
        return self.products

    def get_products_count(self) -> int:
        """Возвращает количество спарсенных товаров"""
        return len(self.products)
