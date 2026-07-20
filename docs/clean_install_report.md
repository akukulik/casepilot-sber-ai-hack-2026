# CasePilot: clean-install report

Дата проверки: 2026-07-20.

## Методика

Проверка выполнена не в рабочей папке, а в новом временном клоне:

1. `git clone --no-hardlinks`;
2. `python3 -m venv .venv`;
3. `.venv/bin/python -m pip install -r requirements-dev.txt`;
4. `.venv/bin/python scripts/run_tests.py`;
5. `node --check frontend/app.js`;
6. `node --check frontend/demo-data.js`.

Локальные настройки Ouroboros, API-ключ, runtime и кеши в clone не
переносились.

## Окружение проверки

- macOS на Apple Silicon;
- Python 3.13;
- изолированная `.venv`;
- зависимости только из `requirements-dev.txt`.

## Результат

- зависимости установлены без ручных исправлений;
- 9 из 9 тестовых программ CasePilot завершились успешно;
- JSON Schema и все синтетические наборы данных валидны;
- retrieval, runtime, scenario evolution, рекомендации и frontend API прошли;
- оба frontend JavaScript-файла прошли синтаксическую проверку;
- runtime в Git не требуется и создаётся локально.

## Граница проверки

Clean-install подтверждает воспроизводимость исходного кода CasePilot.
Установка самого Ouroboros и provider onboarding являются отдельными
локальными шагами: приложение и API-ключ намеренно не входят в репозиторий.
Native preflight выполняется после `scripts/install_skills.py` командой:

```bash
python scripts/run_tests.py --include-ouroboros
```
