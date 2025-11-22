import re
import html
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

# Расширенное регулярное выражение для product-ссылок
RE_PRODUCT_ID = re.compile(
    r'/product/[^\"\'>]*-(\d+)|ozon\.ru/product/[^\"\'>]*-(\d+)', re.IGNORECASE
)
RE_PRICE = re.compile(r'[\d\u00A0\u2009\u202F]+(?:\u2009| )?₽')
RE_SKU = re.compile(r'\"sku\"\s*:\s*(\d+)')
RE_SELLER_ID = re.compile(r'seller_(\d+)')

def clean_text(s: str) -> str:
    if not s:
        return ''
    s = s.strip()
    s = re.sub(r'[\u00A0\u2009\u202F]+', ' ', s)
    s = re.sub(r'\s+', ' ', s)
    return s

def parse_html_with_bs4(raw_html: str):
    soup = BeautifulSoup(raw_html, 'html.parser')
    items = {}

    # Поиск по ссылкам
    for a in soup.find_all('a', href=True):
        href = a['href']
        m = RE_PRODUCT_ID.search(href)
        pid = m.group(1) if m and m.group(1) else (m.group(2) if m and m.group(2) else None)
        if not pid:
            continue

        name = clean_text(a.text)
        if not name:
            img = a.find('img')
            if img and 'alt' in img.attrs:
                name = clean_text(img['alt'])

        # Поиск цен в родителях и соседях
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

        # Поиск SKU
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
            'prices': prices[:2]
        }

    # Поиск по карточкам товаров (div с типичными классами)
    for card in soup.find_all('div', class_=re.compile(r'card|tile|product', re.I)):
        # Ищем ссылку на товар
        a = card.find('a', href=True)
        if a:
            m = RE_PRODUCT_ID.search(a['href'])
            pid = m.group(1) if m and m.group(1) else (m.group(2) if m and m.group(2) else None)
            if pid and pid not in items:
                name = clean_text(card.get_text(separator=' ', strip=True))
                prices = [clean_text(p) for p in RE_PRICE.findall(card.get_text())]
                prices = list(dict.fromkeys(prices))[:2]
                sku = ''
                items[pid] = {
                    'name': name,
                    'sku': sku,
                    'prices': prices
                }

    logging.info(f"BeautifulSoup: найдено товаров: {len(items)}")
    return items

def parse_html_fallback(raw_html: str):
    items = {}
    for m in RE_PRODUCT_ID.finditer(raw_html):
        pid = m.group(1) if m.group(1) else (m.group(2) if m.group(2) else None)
        if not pid:
            continue
        start, end = m.start(), m.end()
        window = raw_html[max(0, start - 4000): end + 4000]  # расширено окно

        # Название: ищем alt, title, aria-label, и текст между тегами
        name_match = (
            re.search(r'alt=\"([^\"]{5,300}?)(\"|>)', window) or
            re.search(r'title=\"([^\"]{5,300}?)(\"|>)', window) or
            re.search(r'aria-label=\"([^\"]{5,300}?)(\"|>)', window) or
            re.search(r'>([^<]{10,400}?)<', window)
        )
        name = clean_text(name_match.group(1)) if name_match else ''

        # Цены: ищем все варианты
        prices = [clean_text(p) for p in RE_PRICE.findall(window)]
        seen = set()
        prices = [p for p in prices if p and p not in seen and not seen.add(p)][:2]

        # SKU
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
    merged_items = {}  # pid -> {'name':, 'sku':, 'prices':[], 'sources':[]}
    html_files = list(directory.glob('*.html')) + list(directory.glob('*.htm'))
    html_files = sorted(html_files)
    
    for file_path in html_files:
        logging.info(f"Parsing file: {file_path.name}")
        try:
            raw_html = file_path.read_text(encoding='utf-8', errors='ignore')
            if HAS_BS4:
                parsed = parse_html_with_bs4(raw_html)
            else:
                parsed = parse_html_fallback(raw_html)
            
            for pid, data in parsed.items():
                entry = merged_items.setdefault(pid, {'name': '', 'sku': '', 'prices': [], 'sources': []})
                # Update name if empty
                if data['name'] and not entry['name']:
                    entry['name'] = data['name']
                # Update sku if empty
                if data['sku'] and not entry['sku']:
                    entry['sku'] = data['sku']
                # Append unique prices
                for price in data['prices']:
                    if price and price not in entry['prices']:
                        entry['prices'].append(price)
                # Add source
                if file_path.name not in entry['sources']:
                    entry['sources'].append(file_path.name)
        except Exception as e:
            logging.error(f"Error parsing file {file_path.name}: {str(e)}", exc_info=True)
    
    return merged_items, html_files

def indent_xml(elem, level=0):
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
    root = ET.Element('items')
    skipped = []
    written = 0
    
    for pid, data in sorted(merged_items.items(), key=lambda x: int(x[0])):
        prices = data['prices'][:2]  # Only consider first two prices
        price1 = prices[0] if len(prices) >= 1 else ''
        price2 = prices[1] if len(prices) >= 2 else ''
        name = data['name']
        sku = data['sku'] or pid  # Fallback to pid
        
        missing = []
        if not price1: missing.append('price1')
        if not price2: missing.append('price2')
        if not name: missing.append('name')
        if not sku: missing.append('sku')  # Though sku has fallback, but if empty originally
        
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
    
    # Indent the XML for pretty printing
    indent_xml(root)
    
    try:
        # Write XML
        tree = ET.ElementTree(root)
        tree.write(xml_path, encoding='utf-8', xml_declaration=True)
        logging.info(f"XML written to {xml_path}")
    except Exception as e:
        logging.error(f"Error writing XML: {str(e)}", exc_info=True)
    
    try:
        # Write log as JSONL
        with log_path.open('w', encoding='utf-8') as f:
            for entry in skipped:
                json.dump(entry, f, ensure_ascii=False)
                f.write('\n')
        logging.info(f"Parse log written to {log_path}")
    except Exception as e:
        logging.error(f"Error writing parse log: {str(e)}", exc_info=True)
    
    return written, len(skipped)

def get_seller_id(script_dir: Path):
    config_path = script_dir / 'config.json'
    if not config_path.exists():
        logging.error("config.json not found")
        raise FileNotFoundError("config.json not found")
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        seller_url = config.get('seller_url', '')
        m = RE_SELLER_ID.search(seller_url)
        if m:
            return f"seller_{m.group(1)}"
        logging.error("Seller ID not found in config.json")
        raise ValueError("Seller ID not found in config.json")
    except Exception as e:
        logging.error(f"Error reading config.json: {str(e)}", exc_info=True)
        raise

def main():
    logging.basicConfig(filename='parser.log', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info("Starting parser script")
    
    script_dir = Path.cwd()
    try:
        seller_id = get_seller_id(script_dir)
        logging.info(f"Seller ID: {seller_id}")
        
        merged, files = parse_all_html_files(script_dir)
        if not files:
            logging.warning(f"No HTML files found in {script_dir}")
            print(f"No HTML files found in {script_dir}")
            return
        
        xml_file = script_dir / f'{seller_id}_output.xml'
        log_file = script_dir / 'parse_log.jsonl'
        
        # Archive old XML if exists
        archive_dir = script_dir / 'archive'
        os.makedirs(archive_dir, exist_ok=True)
        if xml_file.exists():
            now = datetime.datetime.now()
            archive_name = now.strftime("%d-%m-%y_%H") + f"_{seller_id}.xml"  # Using - for filename safety
            archive_path = archive_dir / archive_name
            shutil.move(xml_file, archive_path)
            logging.info(f"Archived old XML to {archive_path}")
            print(f"Archived old XML to {archive_path}")
        
        written, skipped = write_xml_and_log(merged, xml_file, log_file)
        
        logging.info(f"Processed {len(files)} HTML files.")
        logging.info(f"Written {written} items to {xml_file}")
        logging.info(f"Skipped {skipped} items, logged to {log_file}")
        if not HAS_BS4:
            logging.warning("BeautifulSoup not installed, used fallback parsing.")
        
        print(f"Processed {len(files)} HTML files.")
        print(f"Written {written} items to {xml_file}")
        print(f"Skipped {skipped} items, logged to {log_file}")
        if not HAS_BS4:
            print("Note: BeautifulSoup not installed, used fallback parsing.")
    
    except Exception as e:
        logging.error(f"Main execution error: {str(e)}", exc_info=True)
        print(f"Error: {str(e)}")
    
    logging.info("Parser script completed")

if __name__ == '__main__':
    main()