"""
Ozon XML Duplicate Checker
Утилита для проверки дубликатов SKU в XML-файлах с результатами парсинга.
"""

import xml.etree.ElementTree as ET
from collections import Counter
import glob
import os
import sys


def find_duplicate_skus(xml_file):
    """
    Проверяет XML-файл на наличие дубликатов SKU.

    Args:
        xml_file: Путь к XML-файлу

    Returns:
        Кортеж (total, duplicates):
        - total: Общее количество артикулов
        - duplicates: Словарь {sku: count} с дубликатами
    """
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()

        # Собираем все SKU
        skus = []
        for item in root.findall("item"):
            sku_elem = item.find("sku")
            if sku_elem is not None and sku_elem.text:
                skus.append(sku_elem.text)

        total = len(skus)
        counter = Counter(skus)
        duplicates = {sku: count for sku, count in counter.items() if count > 1}

        return total, duplicates

    except ET.ParseError as e:
        print(f"Ошибка парсинга XML-файла {xml_file}: {e}")
        return 0, {}
    except Exception as e:
        print(f"Ошибка обработки файла {xml_file}: {e}")
        return 0, {}


def print_results(xml_file, total, duplicates):
    """
    Выводит результаты проверки на дубликаты.

    Args:
        xml_file: Путь к XML-файлу
        total: Общее количество артикулов
        duplicates: Словарь с дубликатами
    """
    print(f"\n{'=' * 60}")
    print(f"Файл: {os.path.basename(xml_file)}")
    print(f"{'=' * 60}")
    print(f"Проверено артикулов: {total}")

    if duplicates:
        print(f"\n⚠️  Найдены дубли артикулов:")
        for sku, count in sorted(duplicates.items()):
            print(f"  • Артикул {sku} встречается {count} раз(а)")
        print(f"\nВсего уникальных дублей: {len(duplicates)}")
        print(f"Всего дублирующихся записей: {sum(duplicates.values())}")
    else:
        print("\n✓ Дублей артикулов не найдено.")


def main():
    """Главная функция программы"""
    print("Ozon XML Duplicate Checker")
    print("=" * 60)

    # Ищем все XML-файлы, начинающиеся на seller_
    xml_files = glob.glob("seller_*.xml")

    if not xml_files:
        print("\nXML-файлы формата 'seller_*.xml' не найдены в текущей директории.")
        print("Убедитесь, что вы запускаете скрипт из директории с XML-файлами.")
        sys.exit(1)

    print(f"\nНайдено файлов для проверки: {len(xml_files)}")

    # Обрабатываем каждый файл
    total_duplicates = 0
    for xml_file in sorted(xml_files):
        total, duplicates = find_duplicate_skus(xml_file)
        print_results(xml_file, total, duplicates)
        total_duplicates += len(duplicates)

    # Итоговая статистика
    print(f"\n{'=' * 60}")
    print(f"Итого обработано файлов: {len(xml_files)}")
    print(f"Итого найдено уникальных дублей: {total_duplicates}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
