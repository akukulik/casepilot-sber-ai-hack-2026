# CasePilot

[![CasePilot CI](https://github.com/akukulik/casepilot-sber-ai-hack-2026/actions/workflows/ci.yml/badge.svg)](https://github.com/akukulik/casepilot-sber-ai-hack-2026/actions/workflows/ci.yml)
[![Deploy GitHub Pages](https://github.com/akukulik/casepilot-sber-ai-hack-2026/actions/workflows/pages.yml/badge.svg)](https://github.com/akukulik/casepilot-sber-ai-hack-2026/actions/workflows/pages.yml)

CasePilot — MVP агентного помощника оператора по сложным отложенным кейсам
дебетовых карт для Sber AI Hack 2026. Агент на базе Ouroboros находит
переиспользуемую стратегию, строит проверяемый план, ждёт решения сотрудника,
выполняет только синтетические mock-проверки и формирует итоговую рекомендацию.

> Все клиенты, продукты, операции и ограничения в репозитории синтетические.
> Проект не подключён к банковским системам и не выполняет реальные операции.

## Демо для жюри

Публичная веб-форма:
[CasePilot на GitHub Pages](https://akukulik.github.io/casepilot-sber-ai-hack-2026/).

QR-код публичного репозитория:

<img src="assets/casepilot-repository-qr.png" alt="QR-код репозитория CasePilot" width="220">

На GitHub Pages включён безопасный статический demo mode с пятью синтетическими
кейсами: четыре полных сценария и одна контролируемая остановка из-за
недостающих данных. Демо не обращается к OpenRouter и не расходует API-бюджет.
Полноценный агентный режим с Ouroboros, LLM и всеми runtime-проверками
запускается локально по инструкции ниже.

## Что демонстрирует MVP

1. Оператор открывает validation-кейс и запускает CasePilot по `case_id`.
2. Retrieval фильтрует сценарии по теме/подтеме, применяет BM25 и business
   rerank, затем передаёт модели до трёх лучших стратегий.
3. `z-ai/glm-5.2` через OpenRouter формирует план из 2–20 шагов.
4. Сотрудник подтверждает план или переводит кейс в ручную работу.
5. Подтверждённый план последовательно выполняется в mock-контуре.
6. CasePilot показывает компактную рекомендацию, основания, ограничения,
   действия сотрудника и готовый ответ клиенту.

Реальное изменение кейса, закрытие счёта и отправка ответа запрещены.

## Состав проекта

```text
casepilot/       runtime, review и детерминированное mock-исполнение
data/            канонические синтетические данные и каталоги сценариев
data/runtime/    локальное состояние; создаётся при запуске и не попадает в Git
frontend/        dependency-free рабочее место оператора
schemas/         JSON Schema Draft 2020-12
skills/          исходники пользовательских Ouroboros Skills
scripts/         установка Skills, очистка runtime и единый тестовый запуск
tests/           контрактные, retrieval, runtime, API и preflight-проверки
docs/            архитектура, workflow, демо и технические отчёты
```

Датасет содержит 32 historical-кейса, 20 validation-кейсов, 20 экспертиз,
3 базовых сценария и 17 расширенных сценариев `approved_for_mvp`. Отдельный
контур scenario evolution создаёт drafts из подтверждённых ручных решений.

## Требования

- macOS 12+;
- официальный стабильный Ouroboros 6.61.4;
- Python 3.10+;
- OpenRouter API key, сохранённый штатно в Ouroboros;
- интернет только для LLM-вызовов.

Ouroboros и API-ключ не входят в репозиторий. Оценка выбранного релиза:
[`docs/ouroboros_installation_assessment.md`](docs/ouroboros_installation_assessment.md).

## Локальная установка

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Проверить проект:

```bash
python scripts/run_tests.py
```

Воспроизводимость дополнительно проверена чистым клонированием, созданием новой
`.venv` и установкой только из `requirements-dev.txt`. Отчёт:
[`docs/clean_install_report.md`](docs/clean_install_report.md).

Очистить накопленное демонстрационное состояние:

```bash
python scripts/reset_runtime.py
```

## Установка Skills в Ouroboros

Сначала один раз запустите Ouroboros, завершите onboarding и настройте
OpenRouter через Settings. Ключ не нужно передавать этому репозиторию.

```bash
python scripts/install_skills.py
```

Скрипт копирует каждый пакет из `skills/` в
`~/Ouroboros/data/skills/external/` и создаёт локальные locator-файлы только
в установленной копии. После установки в интерфейсе Ouroboros необходимо
повторить review, grants и enablement для изменившихся content hashes.

Затем проверить установленные Skills штатным preflight:

```bash
python scripts/run_tests.py --include-ouroboros
```

Другой профиль:

```bash
python scripts/install_skills.py --ouroboros-home /path/to/Ouroboros
```

## Запуск интерфейса

```bash
python server.py
```

Откройте [http://127.0.0.1:8080](http://127.0.0.1:8080). Сервер связывается с
локальным Ouroboros API; API-ключ остаётся в защищённых настройках Ouroboros и
не передаётся браузеру.

Рекомендуемый демо-сценарий описан в
[`docs/demo_script.md`](docs/demo_script.md).

## Основные Skills

- `load_case` — загружает validation-кейс;
- `find_case_scenarios` — ищет стратегии, а не отдельные кейсы;
- `take_case` — операторская точка входа по `case_id`;
- `build_resolution_plan` — LLM-планирование со строгой схемой;
- `review_resolution_plan` — approve, одна редакция или manual review;
- `execute_approved_plan` — последовательное mock-исполнение allowlist;
- `build-resolution-recommendation` — evidence-bound итог;
- `record-scenario-outcome` — записывает проверенный результат ручной работы;
- `analyze-scenario-gaps` — создаёт draft из повторяющихся ручных решений;
- `validate-scenario-draft` — независимо проверяет evidence и offline replay;
- `review-scenario-draft` — публикует только после решения эксперта;
- check/expertise/case-action Skills — синтетические исполнители шагов.

`find_similar_cases` сохранён как legacy-компонент и не является основным
retrieval-маршрутом.

## Safety и секреты

- API-ключи запрещено хранить в коде, данных, runtime, документации и Git.
- `.env`, настройки Ouroboros, runtime, imports, artifacts и логи исключены.
- Сервер по умолчанию слушает только `127.0.0.1`.
- Неизвестное действие останавливает исполнение.
- Validation-данные неизменяемы; состояние пишется только в `data/runtime/`.
- Финальное решение всегда принимает сотрудник.

См. [`SECURITY.md`](SECURITY.md).

## Текущее состояние и ограничения

Технический end-to-end MVP готов. Редактирование плана и автоматическое
продолжение после остановок осознанно исключены из хакатонного scope. Перед
финальной подачей остаётся добавить append-only сохранение финального решения
сотрудника по рекомендации для последующей аналитики. Полный список:

- [`docs/ISSUES.md`](docs/ISSUES.md);
- [`docs/TO_BE.md`](docs/TO_BE.md);
- [`docs/casepilot_mvp_architecture.md`](docs/casepilot_mvp_architecture.md).

## Лицензия

Исходный код CasePilot распространяется по лицензии MIT. Ouroboros является
отдельным проектом со своей лицензией и не включён в этот репозиторий.
