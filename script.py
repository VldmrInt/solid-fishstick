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

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()
file_handler = logging.FileHandler('parser.log')
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Загрузка конфига
try:
    with open('config.json', 'r') as f:
        config = json.load(f)
    seller_url = config['seller_url']
except FileNotFoundError:
    logger.error("Файл config.json не найден.")
    raise
except KeyError:
    logger.error("В config.json отсутствует 'seller_url'.")
    raise

# Глобальные locks для синхронизации
driver_lock = threading.Lock()
file_lock = threading.Lock()

# Архивация старых HTML-файлов перед запуском (принудительная)
archive_dir = 'archive'
if not os.path.exists(archive_dir):
    os.makedirs(archive_dir)
    logger.info(f"Создана папка {archive_dir}.")

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
archive_subdir = os.path.join(archive_dir, timestamp)
os.makedirs(archive_subdir)
logger.info(f"Создана подпапка {archive_subdir} для старых файлов.")

# Перемещаем все существующие HTML-файлы
old_files = [f for f in os.listdir('.') if f.startswith('page_source_page_') and f.endswith('.html')]
if old_files:
    for old_file in old_files:
        shutil.move(old_file, os.path.join(archive_subdir, old_file))
    logger.info(f"Перемещено {len(old_files)} старых файлов в {archive_subdir}.")
else:
    logger.info("Старых HTML-файлов не найдено.")

# Функция для парсинга одной страницы
def parse_page(page_number, results):
    try:
        options = ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-gpu")
        options.add_argument("--log-level=3")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36")
        options.add_experimental_option("prefs", {"profile.default_content_setting_values.notifications": 2})
        options.add_argument("--disable-blink-features=AutomationControlled")

        with driver_lock:
            driver = Chrome(options=options, version_main=139)

        current_url = f"{seller_url}&page={page_number}" if page_number > 1 else seller_url
        driver.get(current_url)
        logger.info(f"[Поток {threading.current_thread().name}] Открыта страница {page_number}: {current_url}")
        
        time.sleep(10)
        
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Пожалуйста, дождитесь окончания проверки браузера')]"))
            )
            logger.info(f"[Поток {threading.current_thread().name}] Обнаружен экран проверки, ждем...")
            WebDriverWait(driver, 60).until_not(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Пожалуйста, дождитесь окончания проверки браузера')]"))
            )
            logger.info(f"[Поток {threading.current_thread().name}] Проверка завершена.")
        except TimeoutException:
            logger.info(f"[Поток {threading.current_thread().name}] Нет экрана проверки, продолжаем.")

        is_empty = False
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'ничего не нашлось')]"))
            )
            logger.info(f"[Поток {threading.current_thread().name}] Страница {page_number} пустая.")
            is_empty = True
        except TimeoutException:
            logger.info(f"[Поток {threading.current_thread().name}] Страница {page_number} с товарами.")

        if not is_empty:
            last_height = driver.execute_script("return document.body.scrollHeight")
            no_change_count = 0
            max_no_change = 5
            max_attempts = 50
            scroll_attempts = 0
            while scroll_attempts < max_attempts:
                scroll_step = random.randint(500, 1500)
                driver.execute_script(f"window.scrollBy(0, {scroll_step});")
                time.sleep(random.uniform(2, 4))
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    no_change_count += 1
                    if no_change_count >= max_no_change:
                        break
                else:
                    no_change_count = 0
                last_height = new_height
                scroll_attempts += 1
            logger.info(f"[Поток {threading.current_thread().name}] Скролл завершен для страницы {page_number}.")

        source = driver.page_source
        
        base_filename = f'page_source_page_{page_number}.html'
        filename = base_filename
        
        with file_lock:
            if os.path.exists(filename):
                file_timestamp = int(time.time())
                filename = f'page_source_page_{page_number}_{file_timestamp}.html'
                logger.warning(f"[Поток {threading.current_thread().name}] Файл {base_filename} существует, сохраняю как {filename}.")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(source)
            logger.info(f"[Поток {threading.current_thread().name}] HTML сохранён в {filename}.")

        # Новый блок: логируем количество товаров на странице через парсер
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

# Основной цикл с многопоточностью
page_number = 1
group_size = 20
results = {}

while True:
    threads = []
    group_pages = [page_number + i for i in range(group_size)]
    
    for pg in group_pages:
        t = threading.Thread(target=parse_page, args=(pg, results), name=f"Thread-Page-{pg}")
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    group_empty = all(results.get(pg, {'is_empty': True})['is_empty'] for pg in group_pages)
    if group_empty:
        logger.info("Вся группа пустая. Завершаем.")
        break
    
    if results.get(group_pages[-1], {'is_empty': False})['is_empty']:
        prev_empty = all(results.get(pg, {'is_empty': True})['is_empty'] for pg in group_pages[:-1])
        if prev_empty:
            logger.info("Предыдущие страницы пустые. Завершаем.")
            break
        else:
            logger.info("Последняя пустая, но предыдущие имеют товары. Продолжаем.")
    else:
        logger.info("Группа обработана. Переходим к следующей.")

    page_number += group_size

# Запуск второго скрипта
logger.info("Парсинг завершен. Ожидание 10 секунд перед запуском parse_ozon_grok.py...")
time.sleep(10)
logger.info("Запуск parse_ozon_grok.py...")
subprocess.call(['python', 'parse_ozon_grok.py'])