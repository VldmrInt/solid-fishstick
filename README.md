# Ozon Product Parser

Мощный парсер товаров магазинов на Ozon с использованием официального API Composer и продвинутыми техниками обхода защиты от ботов.

## Описание

Проект представляет собой профессиональный инструмент для автоматического сбора информации о товарах из магазинов продавцов на Ozon. В отличие от традиционных HTML-скраперов, использует официальный API Composer от Ozon для получения структурированных данных в формате JSON, что обеспечивает высокую скорость и надежность парсинга.

### Ключевые особенности

- **API-based парсинг**: Использование официального Ozon API Composer вместо HTML-скрапинга
- **Обход анти-бот защиты**: Комбинация undetected-chromedriver + selenium-stealth
- **Модульная архитектура**: Чистый код с разделением ответственности (src/parsers, src/utils, src/config)
- **Множественные форматы экспорта**: Excel (с форматированием), XML, JSON
- **Богатая информация о товарах**: SKU, название, цены, рейтинг, отзывы, продавец, бренд, категория
- **Готовность к автоматизации**: Запуск через cron, подробное логирование, обработка ошибок
- **Анти-детект техники**: Скрытие automation-флагов, кастомизация WebGL, обнаружение блокировок

## Требования

- Python 3.8+
- Google Chrome (для Selenium)
- 2 GB RAM минимум

## Установка

### 1. Клонирование репозитория

```bash
git clone https://github.com/VldmrInt/solid-fishstick.git
cd solid-fishstick
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 3. Конфигурация

Создайте или отредактируйте `config.json`:

```json
{
  "seller_url": "https://www.ozon.ru/seller/your-shop-name-123456/?miniapp=seller_123456"
}
```

**Где найти URL магазина:**
1. Откройте магазин продавца на Ozon
2. Скопируйте полный URL из адресной строки
3. Убедитесь, что URL содержит `seller` и ID магазина

## Использование

### Базовый запуск

```bash
python run.py
```

Парсер автоматически:
- Загрузит конфигурацию из `config.json`
- Спарсит все страницы магазина (до 100 страниц по умолчанию)
- Экспортирует данные во все форматы (Excel, XML, JSON)
- Сохранит результаты в папку `output/`

### Продвинутое использование

#### Указать URL напрямую

```bash
python run.py --url "https://www.ozon.ru/seller/magazin-123456/?miniapp=seller_123456"
```

#### Ограничить количество страниц

```bash
python run.py --max-pages 50
```

#### Выбрать формат экспорта

```bash
# Только Excel
python run.py --format excel

# Только XML
python run.py --format xml

# Только JSON
python run.py --format json

# Все форматы (по умолчанию)
python run.py --format all
```

#### Указать имя выходного файла

```bash
python run.py --output my_products
# Создаст: my_products.xlsx, my_products.xml, my_products.json
```

#### Комбинированный пример

```bash
python run.py \
  --url "https://www.ozon.ru/seller/magazin-123456/" \
  --max-pages 30 \
  --format excel \
  --output products_$(date +%Y%m%d)
```

### Автоматизация через Cron

Пример настройки cron для ежедневного парсинга в 3:00 AM:

```bash
# Откройте crontab
crontab -e

# Добавьте строку (замените /path/to на реальный путь)
0 3 * * * cd /path/to/solid-fishstick && /usr/bin/python3 run.py >> /var/log/ozon_parser.log 2>&1
```

## Структура проекта

```
solid-fishstick/
├── run.py                      # Главный скрипт запуска
├── config.json                 # Конфигурация (URL магазина)
├── requirements.txt            # Зависимости Python
├── README.md                   # Документация
├── LICENSE                     # MIT License
│
├── src/                        # Исходный код
│   ├── config/                 # Конфигурация
│   │   ├── __init__.py
│   │   └── settings.py         # Централизованные настройки
│   │
│   ├── parsers/                # Парсеры
│   │   ├── __init__.py
│   │   └── api_parser.py       # API Composer парсер
│   │
│   └── utils/                  # Утилиты
│       ├── __init__.py
│       ├── selenium_manager.py # WebDriver с анти-детект
│       ├── exporter.py         # Экспорт данных
│       └── logger.py           # Настройка логирования
│
├── output/                     # Результаты парсинга
│   ├── seller_123456_20250122_030000.xlsx
│   ├── seller_123456_20250122_030000.xml
│   └── seller_123456_20250122_030000.json
│
├── archive/                    # Архив старых HTML-файлов
├── legacy/                     # Старые версии скриптов
│   ├── script.py               # Старый HTML-скрапер
│   ├── parse_ozon_grok.py      # Старый HTML-парсер
│   └── check_duplicates.py     # Проверка дубликатов
│
└── parser.log                  # Логи работы

```

## Технические детали

### API Composer

Парсер использует официальный API endpoint от Ozon:

```
https://www.ozon.ru/api/composer-api.bx/page/json/v2?url={PATH}&__rr=1
```

Этот API возвращает структурированные JSON-данные вместо HTML, что обеспечивает:
- Высокую скорость парсинга
- Надежность (не зависит от изменений HTML-разметки)
- Полную информацию о товарах

### Анти-бот техники

**1. Undetected ChromeDriver**
- Автоматическое обновление ChromeDriver
- Удаление следов автоматизации

**2. Selenium-Stealth**
- Маскировка WebDriver флагов
- Кастомизация WebGL renderer/vendor
- Подмена языков и платформы

**3. JavaScript патчи**
- Удаление `navigator.webdriver`
- Переопределение `permissions`, `plugins`
- Randomization User-Agent

**4. Обнаружение блокировок**
- Детекция Cloudflare
- Детекция DDoS-Guard
- Детекция капчи
- Проверка на пустые страницы

### Извлекаемые данные

Для каждого товара парсер извлекает:

| Поле | Описание | Пример |
|------|----------|--------|
| `sku` | Артикул товара | "123456789" |
| `name` | Название товара | "Футболка мужская хлопок" |
| `current_price` | Текущая цена | "1 990 ₽" |
| `original_price` | Старая цена (если есть) | "2 500 ₽" |
| `rating` | Рейтинг товара | "4.5" |
| `reviews_count` | Количество отзывов | "142" |
| `seller_name` | Название продавца | "Модная лавка" |
| `seller_inn` | ИНН продавца | "7712345678" |
| `brand` | Бренд товара | "Nike" |
| `category` | Категория | "Одежда" |
| `link` | Ссылка на товар | "https://www.ozon.ru/product/..." |
| `image_url` | URL изображения | "https://cdn1.ozon.ru/..." |

### Форматы экспорта

**Excel (.xlsx)**
- Форматированные заголовки (синий фон, белый текст, жирный шрифт)
- Автоматическая подстройка ширины столбцов
- Границы ячеек
- Выравнивание текста
- Готов для анализа в Excel/Google Sheets

**XML**
- Стандартный формат с метаданными
- Pretty-printed форматирование
- Количество товаров и timestamp
- Совместим с любыми XML-парсерами

**JSON**
- Современный формат для API интеграций
- Метаданные (count, exported_at)
- Структурированные данные
- Готов для загрузки в базы данных

## Логирование

Все операции логируются в файл `parser.log`:

```
2025-01-22 03:00:01 - ozon_parser - INFO - Запуск Ozon Product Parser
2025-01-22 03:00:02 - ozon_parser - INFO - Используется URL из config.json: https://www.ozon.ru/seller/...
2025-01-22 03:00:03 - ozon_parser - INFO - Инициализация парсера для продавца ID: 123456
2025-01-22 03:00:05 - ozon_parser - INFO - Парсинг страницы 1...
2025-01-22 03:00:08 - ozon_parser - INFO - Найдено товаров: 36
...
```

**Уровни логирования:**
- INFO: Основные операции
- WARNING: Предупреждения (блокировки, пропуски)
- ERROR: Ошибки парсинга
- DEBUG: Подробная отладка (опционально)

## Обработка ошибок

### Блокировки и капчи

Если Ozon заблокировал запрос:
```
WARNING - Страница заблокирована (Cloudflare/DDoS-Guard)
```

**Решения:**
1. Подождите 5-10 минут
2. Уменьшите частоту запросов (редактируйте `REQUEST_DELAY_MIN/MAX` в `src/config/settings.py`)
3. Используйте прокси (добавьте в `SeleniumManager`)

### Пустые результаты

Если парсер не нашел товары:
```
WARNING - Не найдено ни одного товара!
```

**Проверьте:**
- Правильность URL в `config.json`
- Доступность магазина на Ozon
- Наличие товаров в магазине

## Настройки (Advanced)

Отредактируйте `src/config/settings.py` для тонкой настройки:

```python
# Таймауты (секунды)
PAGE_LOAD_TIMEOUT = 30          # Загрузка страницы
API_REQUEST_TIMEOUT = 20        # API запрос
RETRY_DELAY = 5                 # Задержка между повторами

# Парсинг
MAX_RETRIES = 3                 # Максимум повторов при ошибке
REQUEST_DELAY_MIN = 2           # Минимальная задержка между запросами
REQUEST_DELAY_MAX = 5           # Максимальная задержка

# Многопоточность
MAX_WORKERS = 3                 # Количество потоков (не рекомендуется >3)

# Chrome
CHROME_VERSION = 142            # Версия Chrome
```

## Сравнение с Legacy версией

| Характеристика | Legacy (HTML) | Новая (API) |
|----------------|---------------|-------------|
| Скорость | ~10 сек/страница | ~2 сек/страница |
| Надежность | Средняя (зависит от HTML) | Высокая (структурированный JSON) |
| Данные | Базовые (цена, SKU, название) | Полные (+ рейтинг, отзывы, продавец, бренд) |
| Архитектура | Монолитная | Модульная |
| Экспорт | XML | Excel, XML, JSON |
| Анти-бот | Базовый (User-Agent) | Продвинутый (multi-layer) |
| Обслуживание | Сложное | Простое |

**Legacy файлы сохранены в папке `legacy/` для справки.**

## Устранение проблем

### Chrome/ChromeDriver ошибки

```
Error: This version of ChromeDriver only supports Chrome version X
```

**Решение:**
1. Обновите Chrome до последней версии
2. Измените `CHROME_VERSION` в `src/config/settings.py`

### Ошибка импорта openpyxl

```
ImportError: No module named 'openpyxl'
```

**Решение:**
```bash
pip install openpyxl
```

### Selenium ошибки в headless режиме

**Решение:** Измените `headless=False` в `src/utils/selenium_manager.py` для отладки:
```python
def create_driver(self, headless: bool = False):  # False для видимого режима
```

## Лицензия

MIT License - см. файл [LICENSE](LICENSE)

## Автор

**VldmrInt**

GitHub: [@VldmrInt](https://github.com/VldmrInt)

## Поддержка

При возникновении проблем:
1. Проверьте раздел "Устранение проблем"
2. Изучите файл `parser.log`
3. Создайте issue в [GitHub Issues](https://github.com/VldmrInt/solid-fishstick/issues)

## Благодарности

Проект вдохновлен [ozon-parser by NurjahonErgashevMe](https://github.com/NurjahonErgashevMe/ozon-parser) с адаптацией для парсинга по магазинам вместо категорий.

---

**⚠️ Disclaimer**: Данный инструмент предназначен для образовательных целей и автоматизации легитимного сбора публичных данных. Используйте в соответствии с условиями использования Ozon и применимым законодательством.
