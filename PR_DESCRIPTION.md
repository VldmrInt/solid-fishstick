# Fix: Совместимость с undetected-chromedriver

## Проблема

После основного рефакторинга проекта возникла ошибка при запуске парсера:

```
selenium.common.exceptions.InvalidArgumentException:
Message: invalid argument: cannot parse capability: goog:chromeOptions
from invalid argument: unrecognized chrome option: excludeSwitches
```

## Причина

`undetected-chromedriver` сам управляет опциями `excludeSwitches` и `useAutomationExtension` для обхода детекции автоматизации. Добавление этих опций вручную вызывало конфликт.

## Решение

### Коммит 1: `f4610ce` - Устранение дублирования

- Объединены два вызова `add_experimental_option('excludeSwitches', ...)` в один массив
- До: опция устанавливалась дважды на строках 107 и 115
- После: единый массив `["enable-automation", "enable-logging"]`

### Коммит 2: `b0a8cf0` - Совместимость с UC

- Добавлен параметр `use_uc` в метод `_create_chrome_options()`
- Экспериментальные опции теперь применяются **только для обычного ChromeDriver**
- При использовании `undetected-chromedriver` эти опции пропускаются
- UC управляет анти-детект опциями автоматически

## Изменения в коде

**Файл**: `src/utils/selenium_manager.py`

```python
def create_driver(self, headless: bool = True) -> webdriver.Chrome:
    options = self._create_chrome_options(headless, use_uc=HAS_UC)  # Передаем флаг UC
    ...

def _create_chrome_options(self, headless: bool, use_uc: bool = False) -> ChromeOptions:
    options = ChromeOptions()

    # Базовые опции (для всех)
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    ...

    # Экспериментальные опции ТОЛЬКО для обычного ChromeDriver
    if not use_uc:
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_experimental_option('useAutomationExtension', False)

    return options
```

## Результат

✅ Парсер корректно работает с `undetected-chromedriver`
✅ Сохранена обратная совместимость с обычным ChromeDriver
✅ Все анти-детект техники работают без конфликтов

## Тестирование

Проверено на:
- Python 3.13
- Chrome 142
- undetected-chromedriver 3.5.4+
- selenium-stealth 1.0.6

## Готово к мержу

Критический фикс для работы парсера. Рекомендуется немедленный мерж.
