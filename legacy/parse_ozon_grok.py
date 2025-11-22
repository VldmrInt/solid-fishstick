"""
Ozon HTML Parser
Парсер HTML-файлов страниц Ozon для извлечения информации о товарах.
Поддерживает парсинг с BeautifulSoup и fallback-режим через регулярные выражения.
"""

import re
import json
from pathlib import Path
from xml.etree import ElementTree as ET
import datetime
import os
import shutil
import logging

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# ==================== КОНСТАНТЫ ====================
CONFIG_FILE = 'config.json'
LOG_FILE = 'parser.log'
OUTPUT_LOG_FILE = 'parse_log.jsonl'
ARCHIVE_DIR = 'archive'

# Регулярные выражения для парсинга
RE_PRODUCT_ID = re.compile(
    r'/product/[^\"\'>]*-(\d+)|ozon\.ru/product/[^\"\'>]*-(\d+)', re.IGNORECASE
)
RE_PRICE = re.compile(r'[\d\u00A0\u2009\u202F]+(?:\u2009| )?₽')
RE_SKU = re.compile(r'\"sku\"\s*:\s*(\d+)')
RE_SELLER_ID = re.compile(r'seller_(\d+)')

# Параметры парсинга
SEARCH_WINDOW_SIZE = 4000  # Размер окна поиска вокруг найденного товара
MAX_PRICES_PER_ITEM = 2    # Максимальное количество цен на товар

def clean_text(s: str) -> str:
    """
    Очищает текст от лишних пробелов и специальных символов.

    Args:
        s: Исходная строка

    Returns:
        Очищенная строка
    """
    if not s:
        return ''
    s = s.strip()
    s = re.sub(r'[\u00A0\u2009\u202F]+', ' ', s)  # Заменяем неразрывные пробелы
    s = re.sub(r'\s+', ' ', s)  # Заменяем множественные пробелы одним
    return s


def parse_html_with_bs4(raw_html: str):
    """
    Парсит HTML с использованием BeautifulSoup для извлечения информации о товарах.

    Args:
        raw_html: HTML-код страницы

    Returns:
        Словарь с информацией о товарах {product_id: {name, sku, prices}}
    """
    soup = BeautifulSoup(raw_html, 'html.parser')
    items = {}

    # Поиск товаров по ссылкам
    for a in soup.find_all('a', href=True):
        href = a['href']
        m = RE_PRODUCT_ID.search(href)
        pid = m.group(1) if m and m.group(1) else (m.group(2) if m and m.group(2) else None)
        if not pid:
            continue

        # Извлечение названия товара
        name = clean_text(a.text)
        if not name:
            img = a.find('img')
            if img and 'alt' in img.attrs:
                name = clean_text(img['alt'])

        # Поиск цен в родительских элементах
        prices = []
        container = a.parent
        for _ in range(4):
            if container:
                text = container.get_text(separator=' ', strip=True)
                found_prices = RE_PRICE.findall(text)
                for p in found_prices:
                    cleaned_p = clean_text(p)
                    if cleaned_p not in prices:
                        prices.append(cleaned_p)
                container = container.parent

        # Поиск SKU в JavaScript-коде
        sku = ''
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and pid in script.string:
                m_sku = RE_SKU.search(script.string)
                if m_sku:
                    sku = m_sku.group(1)
                    break

        items[pid] = {
            'name': name,
            'sku': sku,
            'prices': prices[:MAX_PRICES_PER_ITEM]
        }

    # Поиск по карточкам товаров (элементы с классами card/tile/product)
    for card in soup.find_all('div', class_=re.compile(r'card|tile|product', re.I)):
        a = card.find('a', href=True)
        if a:
            m = RE_PRODUCT_ID.search(a['href'])
            pid = m.group(1) if m and m.group(1) else (m.group(2) if m and m.group(2) else None)
            if pid and pid not in items:
                name = clean_text(card.get_text(separator=' ', strip=True))
                prices = [clean_text(p) for p in RE_PRICE.findall(card.get_text())]
                prices = list(dict.fromkeys(prices))[:MAX_PRICES_PER_ITEM]
                sku = ''
                items[pid] = {
                    'name': name,
                    'sku': sku,
                    'prices': prices
                }

    logging.info(f"BeautifulSoup: найдено товаров: {len(items)}")
    return items


def parse_html_fallback(raw_html: str):
    """
    Fallback-парсинг HTML через регулярные выражения (если BeautifulSoup недоступен).

    Args:
        raw_html: HTML-код страницы

    Returns:
        Словарь с информацией о товарах {product_id: {name, sku, prices}}
    """
    items = {}
    for m in RE_PRODUCT_ID.finditer(raw_html):
        pid = m.group(1) if m.group(1) else (m.group(2) if m.group(2) else None)
        if not pid:
            continue

        start, end = m.start(), m.end()
        window = raw_html[max(0, start - SEARCH_WINDOW_SIZE): end + SEARCH_WINDOW_SIZE]

        # Поиск названия товара в различных атрибутах
        name_match = (
            re.search(r'alt=\"([^\"]{5,300}?)(\"|>)', window) or
            re.search(r'title=\"([^\"]{5,300}?)(\"|>)', window) or
            re.search(r'aria-label=\"([^\"]{5,300}?)(\"|>)', window) or
            re.search(r'>([^<]{10,400}?)<', window)
        )
        name = clean_text(name_match.group(1)) if name_match else ''

        # Поиск цен
        prices = [clean_text(p) for p in RE_PRICE.findall(window)]
        seen = set()
        prices = [p for p in prices if p and p not in seen and not seen.add(p)][:MAX_PRICES_PER_ITEM]

        # Поиск SKU
        sku_match = RE_SKU.search(window)
        sku = sku_match.group(1) if sku_match else ''

        items[pid] = {
            'name': name,
            'sku': sku,
            'prices': prices
        }

    logging.info(f"Fallback: найдено товаров: {len(items)}")
    return items


def parse_all_html_files(directory: Path):
    """
    Парсит все HTML-файлы в указанной директории и объединяет результаты.

    Args:
        directory: Путь к директории с HTML-файлами

    Returns:
        Кортеж (merged_items, html_files):
        - merged_items: Словарь с объединенными данными о товарах
        - html_files: Список обработанных HTML-файлов
    """
    merged_items = {}
    html_files = list(directory.glob('*.html')) + list(directory.glob('*.htm'))
    html_files = sorted(html_files)

    for file_path in html_files:
        logging.info(f"Parsing file: {file_path.name}")
        try:
            raw_html = file_path.read_text(encoding='utf-8', errors='ignore')

            # Выбираем метод парсинга
            if HAS_BS4:
                parsed = parse_html_with_bs4(raw_html)
            else:
                parsed = parse_html_fallback(raw_html)

            # Объединяем результаты
            for pid, data in parsed.items():
                entry = merged_items.setdefault(pid, {'name': '', 'sku': '', 'prices': [], 'sources': []})

                # Обновляем название, если оно пустое
                if data['name'] and not entry['name']:
                    entry['name'] = data['name']

                # Обновляем SKU, если он пустой
                if data['sku'] and not entry['sku']:
                    entry['sku'] = data['sku']

                # Добавляем уникальные цены
                for price in data['prices']:
                    if price and price not in entry['prices']:
                        entry['prices'].append(price)

                # Добавляем источник
                if file_path.name not in entry['sources']:
                    entry['sources'].append(file_path.name)

        except Exception as e:
            logging.error(f"Error parsing file {file_path.name}: {str(e)}", exc_info=True)

    return merged_items, html_files

def indent_xml(elem, level=0):
    """
    Рекурсивно добавляет отступы в XML для красивого форматирования.

    Args:
        elem: XML-элемент
        level: Уровень вложенности
    """
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for sub_elem in elem:
            indent_xml(sub_elem, level + 1)
        if not sub_elem.tail or not sub_elem.tail.strip():
            sub_elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def write_xml_and_log(merged_items, xml_path: Path, log_path: Path):
    """
    Записывает данные о товарах в XML-файл и логирует пропущенные товары.

    Args:
        merged_items: Словарь с информацией о товарах
        xml_path: Путь для сохранения XML-файла
        log_path: Путь для сохранения лога пропущенных товаров

    Returns:
        Кортеж (written, skipped):
        - written: Количество записанных товаров
        - skipped: Количество пропущенных товаров
    """
    root = ET.Element('items')
    skipped = []
    written = 0

    for pid, data in sorted(merged_items.items(), key=lambda x: int(x[0])):
        prices = data['prices'][:MAX_PRICES_PER_ITEM]
        price1 = prices[0] if len(prices) >= 1 else ''
        price2 = prices[1] if len(prices) >= 2 else ''
        name = data['name']
        sku = data['sku'] or pid  # Используем product_id как fallback для SKU

        # Проверяем наличие обязательных полей
        missing = []
        if not price1: missing.append('price1')
        if not price2: missing.append('price2')
        if not name: missing.append('name')

        if missing:
            log_entry = {
                'sku': sku,
                'missing': missing,
                'found': {
                    'price1': price1,
                    'price2': price2,
                    'name': name,
                    'sku': sku
                },
                'sources': data['sources'],
                'note': 'skipped - missing fields'
            }
            skipped.append(log_entry)
        else:
            item_elem = ET.SubElement(root, 'item')
            ET.SubElement(item_elem, 'price1').text = price1
            ET.SubElement(item_elem, 'price2').text = price2
            ET.SubElement(item_elem, 'name').text = name
            ET.SubElement(item_elem, 'sku').text = sku
            written += 1
    
    # Форматируем XML для красивого вывода
    indent_xml(root)

    try:
        # Записываем XML
        tree = ET.ElementTree(root)
        tree.write(xml_path, encoding='utf-8', xml_declaration=True)
        logging.info(f"XML written to {xml_path}")
    except Exception as e:
        logging.error(f"Error writing XML: {str(e)}", exc_info=True)

    try:
        # Записываем лог в формате JSONL
        with log_path.open('w', encoding='utf-8') as f:
            for entry in skipped:
                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')
        logging.info(f"Parse log written to {log_path}")
    except Exception as e:
        logging.error(f"Error writing parse log: {str(e)}", exc_info=True)

    return written, len(skipped)


def get_seller_id(script_dir: Path):
    """
    Извлекает ID продавца из конфигурационного файла.

    Args:
        script_dir: Директория скрипта

    Returns:
        Строка формата "seller_{id}"

    Raises:
        FileNotFoundError: Если config.json не найден
        ValueError: Если seller_id не найден в URL
    """
    config_path = script_dir / CONFIG_FILE
    if not config_path.exists():
        logging.error(f"{CONFIG_FILE} not found")
        raise FileNotFoundError(f"{CONFIG_FILE} not found")

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        seller_url = config.get('seller_url', '')
        m = RE_SELLER_ID.search(seller_url)
        if m:
            return f"seller_{m.group(1)}"
        logging.error(f"Seller ID not found in {CONFIG_FILE}")
        raise ValueError(f"Seller ID not found in {CONFIG_FILE}")
    except Exception as e:
        logging.error(f"Error reading {CONFIG_FILE}: {str(e)}", exc_info=True)
        raise


def main():
    """Главная функция программы"""
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("=" * 50)
    logging.info("Starting Ozon HTML Parser")
    logging.info("=" * 50)

    script_dir = Path.cwd()
    try:
        # Получаем ID продавца
        seller_id = get_seller_id(script_dir)
        logging.info(f"Seller ID: {seller_id}")

        # Парсим все HTML-файлы
        merged, files = parse_all_html_files(script_dir)
        if not files:
            logging.warning(f"No HTML files found in {script_dir}")
            print(f"No HTML files found in {script_dir}")
            return

        # Подготавливаем пути для выходных файлов
        xml_file = script_dir / f'{seller_id}_output.xml'
        log_file = script_dir / OUTPUT_LOG_FILE

        # Архивируем старый XML-файл, если он существует
        archive_dir = script_dir / ARCHIVE_DIR
        os.makedirs(archive_dir, exist_ok=True)
        if xml_file.exists():
            now = datetime.datetime.now()
            archive_name = now.strftime("%d-%m-%y_%H") + f"_{seller_id}.xml"
            archive_path = archive_dir / archive_name
            shutil.move(str(xml_file), str(archive_path))
            logging.info(f"Archived old XML to {archive_path}")
            print(f"Archived old XML to {archive_path}")

        # Записываем результаты
        written, skipped = write_xml_and_log(merged, xml_file, log_file)

        # Выводим статистику
        logging.info(f"Processed {len(files)} HTML files.")
        logging.info(f"Written {written} items to {xml_file}")
        logging.info(f"Skipped {skipped} items, logged to {log_file}")
        if not HAS_BS4:
            logging.warning("BeautifulSoup not installed, used fallback parsing.")

        print(f"\nProcessed {len(files)} HTML files.")
        print(f"Written {written} items to {xml_file}")
        print(f"Skipped {skipped} items, logged to {log_file}")
        if not HAS_BS4:
            print("\nNote: BeautifulSoup not installed, used fallback parsing.")
            print("For better results, install BeautifulSoup: pip install beautifulsoup4")

    except Exception as e:
        logging.error(f"Main execution error: {str(e)}", exc_info=True)
        print(f"Error: {str(e)}")

    logging.info("=" * 50)
    logging.info("Parser script completed")
    logging.info("=" * 50)


if __name__ == '__main__':
    main()