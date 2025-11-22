"""
Ozon Product Scraper
Автоматический скрипт для сбора HTML-страниц магазина на Ozon.
Использует многопоточность для параллельной загрузки страниц.
"""

import json
import logging
import time
import random
import os
import shutil
from datetime import datetime
from undetected_chromedriver import Chrome, ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
import threading
import subprocess

# ==================== КОНСТАНТЫ ====================
CONFIG_FILE = 'config.json'
LOG_FILE = 'parser.log'
ARCHIVE_DIR = 'archive'
HTML_FILE_TEMPLATE = 'page_source_page_{}.html'

# Параметры Chrome
CHROME_VERSION = 139
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'

# Таймауты (в секундах)
INITIAL_WAIT = 10
VERIFICATION_TIMEOUT = 60
EMPTY_PAGE_CHECK_TIMEOUT = 5
SCROLL_DELAY_MIN = 2
SCROLL_DELAY_MAX = 4
PARSER_DELAY = 10

# Параметры скроллинга
SCROLL_STEP_MIN = 500
SCROLL_STEP_MAX = 1500
MAX_SCROLL_ATTEMPTS = 50
MAX_NO_CHANGE_SCROLLS = 5

# Параметры многопоточности
GROUP_SIZE = 20

# ==================== НАСТРОЙКА ЛОГИРОВАНИЯ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
# Locks для синхронизации потоков
driver_lock = threading.Lock()
file_lock = threading.Lock()


# ==================== ФУНКЦИИ ====================
def load_config():
    """Загружает конфигурацию из config.json"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        seller_url = config['seller_url']
        logger.info(f"Конфигурация загружена успешно: {seller_url}")
        return seller_url
    except FileNotFoundError:
        logger.error(f"Файл {CONFIG_FILE} не найден.")
        raise
    except KeyError:
        logger.error(f"В {CONFIG_FILE} отсутствует обязательное поле 'seller_url'.")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга {CONFIG_FILE}: {e}")
        raise


def archive_old_html_files():
    """Архивирует старые HTML-файлы перед запуском нового парсинга"""
    if not os.path.exists(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR)
        logger.info(f"Создана папка {ARCHIVE_DIR}.")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    archive_subdir = os.path.join(ARCHIVE_DIR, timestamp)
    os.makedirs(archive_subdir)
    logger.info(f"Создана подпапка {archive_subdir} для архивации.")

    old_files = [f for f in os.listdir('.') if f.startswith('page_source_page_') and f.endswith('.html')]
    if old_files:
        for old_file in old_files:
            shutil.move(old_file, os.path.join(archive_subdir, old_file))
        logger.info(f"Перемещено {len(old_files)} старых файлов в {archive_subdir}.")
    else:
        logger.info("Старых HTML-файлов не найдено.")

def create_chrome_options():
    """Создает и настраивает опции для Chrome WebDriver"""
    options = ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
    options.add_argument("--disable-blink-features=AutomationControlled")
    return options


def parse_page(page_number, results, seller_url):
    """
    Парсит одну страницу каталога Ozon.

    Args:
        page_number: Номер страницы для парсинга
        results: Словарь для сохранения результатов
        seller_url: Базовый URL продавца
    """
    try:
        options = create_chrome_options()

        with driver_lock:
            driver = Chrome(options=options, version_main=CHROME_VERSION)

        current_url = f"{seller_url}&page={page_number}" if page_number > 1 else seller_url
        driver.get(current_url)
        logger.info(f"[Поток {threading.current_thread().name}] Открыта страница {page_number}: {current_url}")

        time.sleep(INITIAL_WAIT)

        # Проверка на экран верификации браузера
        try:
            WebDriverWait(driver, INITIAL_WAIT).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Пожалуйста, дождитесь окончания проверки браузера')]"))
            )
            logger.info(f"[Поток {threading.current_thread().name}] Обнаружен экран проверки, ждем...")
            WebDriverWait(driver, VERIFICATION_TIMEOUT).until_not(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Пожалуйста, дождитесь окончания проверки браузера')]"))
            )
            logger.info(f"[Поток {threading.current_thread().name}] Проверка завершена.")
        except TimeoutException:
            logger.info(f"[Поток {threading.current_thread().name}] Нет экрана проверки, продолжаем.")

        # Проверка, есть ли товары на странице
        is_empty = False
        try:
            WebDriverWait(driver, EMPTY_PAGE_CHECK_TIMEOUT).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'ничего не нашлось')]"))
            )
            logger.info(f"[Поток {threading.current_thread().name}] Страница {page_number} пустая.")
            is_empty = True
        except TimeoutException:
            logger.info(f"[Поток {threading.current_thread().name}] Страница {page_number} с товарами.")

        # Скроллинг страницы для подгрузки всех товаров
        if not is_empty:
            last_height = driver.execute_script("return document.body.scrollHeight")
            no_change_count = 0
            scroll_attempts = 0

            while scroll_attempts < MAX_SCROLL_ATTEMPTS:
                scroll_step = random.randint(SCROLL_STEP_MIN, SCROLL_STEP_MAX)
                driver.execute_script(f"window.scrollBy(0, {scroll_step});")
                time.sleep(random.uniform(SCROLL_DELAY_MIN, SCROLL_DELAY_MAX))

                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    no_change_count += 1
                    if no_change_count >= MAX_NO_CHANGE_SCROLLS:
                        break
                else:
                    no_change_count = 0
                last_height = new_height
                scroll_attempts += 1
            logger.info(f"[Поток {threading.current_thread().name}] Скролл завершен для страницы {page_number}.")

        # Сохранение HTML-кода страницы
        source = driver.page_source
        base_filename = HTML_FILE_TEMPLATE.format(page_number)
        filename = base_filename

        with file_lock:
            # Если файл уже существует, добавляем timestamp
            if os.path.exists(filename):
                file_timestamp = int(time.time())
                filename = f'page_source_page_{page_number}_{file_timestamp}.html'
                logger.warning(f"[Поток {threading.current_thread().name}] Файл {base_filename} существует, сохраняю как {filename}.")

            with open(filename, 'w', encoding='utf-8') as f:
                f.write(source)
            logger.info(f"[Поток {threading.current_thread().name}] HTML сохранён в {filename}.")

        # Подсчет найденных товаров (опционально)
        try:
            from parse_ozon_grok import parse_html_with_bs4, parse_html_fallback, HAS_BS4
            if HAS_BS4:
                items = parse_html_with_bs4(source)
            else:
                items = parse_html_fallback(source)
            logger.info(f"[Поток {threading.current_thread().name}] Найдено товаров на странице {page_number}: {len(items)}")
        except Exception as e:
            logger.warning(f"[Поток {threading.current_thread().name}] Не удалось посчитать товары: {str(e)}")

        results[page_number] = {
            'is_empty': is_empty,
            'filename': filename
        }

    except Exception as e:
        logger.error(f"[Поток {threading.current_thread().name}] Ошибка на странице {page_number}: {str(e)}")
        results[page_number] = {'is_empty': True, 'filename': None}
    finally:
        driver.quit()


def run_parser(seller_url):
    """
    Запускает многопоточный парсинг страниц каталога.

    Args:
        seller_url: Базовый URL продавца на Ozon
    """
    page_number = 1
    results = {}

    while True:
        threads = []
        group_pages = [page_number + i for i in range(GROUP_SIZE)]

        # Создаем и запускаем потоки для группы страниц
        for pg in group_pages:
            t = threading.Thread(
                target=parse_page,
                args=(pg, results, seller_url),
                name=f"Thread-Page-{pg}"
            )
            threads.append(t)
            t.start()

        # Ждем завершения всех потоков
        for t in threads:
            t.join()

        # Проверяем, пустая ли вся группа
        group_empty = all(results.get(pg, {'is_empty': True})['is_empty'] for pg in group_pages)
        if group_empty:
            logger.info("Вся группа пустая. Завершаем парсинг.")
            break

        # Проверяем последнюю страницу группы
        if results.get(group_pages[-1], {'is_empty': False})['is_empty']:
            prev_empty = all(results.get(pg, {'is_empty': True})['is_empty'] for pg in group_pages[:-1])
            if prev_empty:
                logger.info("Предыдущие страницы пустые. Завершаем парсинг.")
                break
            else:
                logger.info("Последняя пустая, но предыдущие имеют товары. Продолжаем.")
        else:
            logger.info("Группа обработана. Переходим к следующей.")

        page_number += GROUP_SIZE

    logger.info(f"Парсинг завершен. Обработано {len(results)} страниц.")


def run_html_parser():
    """Запускает скрипт parse_ozon_grok.py для обработки собранных HTML-файлов"""
    logger.info(f"Ожидание {PARSER_DELAY} секунд перед запуском parse_ozon_grok.py...")
    time.sleep(PARSER_DELAY)
    logger.info("Запуск parse_ozon_grok.py...")
    subprocess.call(['python', 'parse_ozon_grok.py'])


def main():
    """Главная функция программы"""
    logger.info("=" * 50)
    logger.info("Запуск Ozon Product Scraper")
    logger.info("=" * 50)

    # Загружаем конфигурацию
    seller_url = load_config()

    # Архивируем старые файлы
    archive_old_html_files()

    # Запускаем парсинг
    run_parser(seller_url)

    # Запускаем обработку HTML
    run_html_parser()

    logger.info("=" * 50)
    logger.info("Работа скрипта завершена")
    logger.info("=" * 50)


if __name__ == '__main__':
    main()