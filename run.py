#!/usr/bin/env python3
"""
Ozon Product Parser - Main Entry Point
Парсинг товаров магазина на Ozon через API Composer
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

from src.config.settings import Settings
from src.parsers.api_parser import OzonAPIParser
from src.parsers.html_parser import OzonHTMLParser
from src.utils.exporter import DataExporter
from src.utils.logger import setup_logger

logger = setup_logger('ozon_parser')


def main():
    """Главная функция программы"""
    parser = argparse.ArgumentParser(
        description='Ozon Product Parser - парсинг товаров магазина'
    )
    parser.add_argument(
        '--url',
        type=str,
        help='URL магазина Ozon (если не указан, берется из config.json)'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=100,
        help='Максимальное количество страниц для парсинга (по умолчанию: 100)'
    )
    parser.add_argument(
        '--method',
        type=str,
        choices=['api', 'html'],
        default='html',
        help='Метод парсинга: api (через API endpoints) или html (прямой HTML, рекомендуется) (по умолчанию: html)'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        default=True,
        help='Запускать браузер в headless режиме (по умолчанию: True)'
    )
    parser.add_argument(
        '--no-headless',
        dest='headless',
        action='store_false',
        help='Открыть видимое окно браузера (помогает обойти защиту)'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['excel', 'xml', 'json', 'all'],
        default='all',
        help='Формат экспорта: excel, xml, json или all (по умолчанию: all)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Имя выходного файла без расширения (по умолчанию: seller_{ID}_{timestamp})'
    )

    args = parser.parse_args()

    logger.info("=" * 70)
    logger.info("Запуск Ozon Product Parser")
    logger.info("=" * 70)

    try:
        # Получение URL продавца
        if args.url:
            seller_url = args.url
            logger.info(f"Используется URL из аргументов: {seller_url}")
        else:
            config = Settings.load_config()
            seller_url = config.get('seller_url')
            if not seller_url:
                logger.error("URL продавца не найден ни в аргументах, ни в config.json")
                sys.exit(1)
            logger.info(f"Используется URL из config.json: {seller_url}")

        # Получение ID продавца
        seller_id = Settings.get_seller_id(seller_url)
        if not seller_id:
            logger.warning("Не удалось извлечь ID продавца из URL")
            seller_id = "unknown"

        # Инициализация парсера в зависимости от выбранного метода
        logger.info(f"Инициализация парсера для продавца ID: {seller_id}")
        logger.info(f"Метод парсинга: {args.method.upper()}")

        if args.method == 'html':
            logger.info(f"Режим браузера: {'headless' if args.headless else 'с видимым окном'}")
            parser = OzonHTMLParser(seller_url, headless=args.headless)
        else:  # api
            parser = OzonAPIParser(seller_url)

        # Парсинг товаров
        logger.info(f"Начало парсинга (максимум {args.max_pages} страниц)...")
        products = parser.parse_all_pages(max_pages=args.max_pages)

        if not products:
            logger.warning("Не найдено ни одного товара!")
            logger.info("Возможные причины:")
            logger.info("  - Неверный URL магазина")
            logger.info("  - Блокировка запросов (попробуйте позже)")
            logger.info("  - Магазин не имеет товаров")
            sys.exit(1)

        logger.info(f"Успешно спарсено товаров: {len(products)}")

        # Подготовка имени файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if args.output:
            base_filename = args.output
        else:
            base_filename = f"seller_{seller_id}_{timestamp}"

        # Создание директории для результатов
        results_dir = Settings.OUTPUT_DIR
        results_dir.mkdir(exist_ok=True)

        # Экспорт данных
        success_count = 0
        formats_to_export = []

        if args.format == 'all':
            formats_to_export = ['excel', 'xml', 'json']
        else:
            formats_to_export = [args.format]

        logger.info(f"Экспорт данных в форматы: {', '.join(formats_to_export)}")

        for fmt in formats_to_export:
            if fmt == 'excel':
                excel_file = results_dir / f"{base_filename}.xlsx"
                logger.info(f"Экспорт в Excel: {excel_file}")
                if DataExporter.export_to_excel(products, excel_file):
                    success_count += 1
                    logger.info(f"✓ Excel файл успешно сохранен: {excel_file}")
                else:
                    logger.error(f"✗ Ошибка экспорта в Excel")

            elif fmt == 'xml':
                xml_file = results_dir / f"{base_filename}.xml"
                logger.info(f"Экспорт в XML: {xml_file}")
                if DataExporter.export_to_xml(products, xml_file):
                    success_count += 1
                    logger.info(f"✓ XML файл успешно сохранен: {xml_file}")
                else:
                    logger.error(f"✗ Ошибка экспорта в XML")

            elif fmt == 'json':
                json_file = results_dir / f"{base_filename}.json"
                logger.info(f"Экспорт в JSON: {json_file}")
                if DataExporter.export_to_json(products, json_file):
                    success_count += 1
                    logger.info(f"✓ JSON файл успешно сохранен: {json_file}")
                else:
                    logger.error(f"✗ Ошибка экспорта в JSON")

        # Итоговая статистика
        logger.info("=" * 70)
        logger.info(f"Парсинг завершен успешно!")
        logger.info(f"Товаров спарсено: {len(products)}")
        logger.info(f"Файлов создано: {success_count}/{len(formats_to_export)}")
        logger.info(f"Результаты сохранены в: {results_dir}")
        logger.info("=" * 70)

        # Вывод примера товаров в консоль
        if products:
            logger.info("\nПример первых 3 товаров:")
            for i, product in enumerate(products[:3], 1):
                logger.info(f"\n{i}. {product.name}")
                logger.info(f"   SKU: {product.sku}")
                logger.info(f"   Цена: {product.current_price}")
                if product.brand:
                    logger.info(f"   Бренд: {product.brand}")
                if product.rating:
                    logger.info(f"   Рейтинг: {product.rating} ({product.reviews_count} отзывов)")

        return 0

    except KeyboardInterrupt:
        logger.warning("\n\nПарсинг прерван пользователем (Ctrl+C)")
        return 130

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
