import xml.etree.ElementTree as ET
from collections import Counter
import glob
import os

def find_duplicate_skus(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # собираем все sku
    skus = [item.find("sku").text for item in root.findall("item")]

    total = len(skus)  # сколько всего артикулов
    counter = Counter(skus)
    duplicates = {sku: count for sku, count in counter.items() if count > 1}

    print(f"\nФайл: {os.path.basename(xml_file)}")
    print(f"Проверено артикулов: {total}")

    if duplicates:
        print("Найдены дубли артикулов:")
        for sku, count in duplicates.items():
            print(f"  Артикул {sku} встречается {count} раз(а)")
    else:
        print("Дублей артикулов не найдено.")

if __name__ == "__main__":
    # ищем все xml-файлы, начинающиеся на seller_
    for xml_file in glob.glob("seller_*.xml"):
        find_duplicate_skus(xml_file)
