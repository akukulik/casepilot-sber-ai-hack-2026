# Отчёт о демонстрационной валидации CasePilot

Дата: 2026-07-19. Модель планирования:
`z-ai/glm-5.2`, `reasoning_effort=medium`.

## Validation-набор

- `VAL-DC-001`: активный hold и незавершённый reversal.
- `VAL-DC-002`: технический минус `-199 RUB`, mock-корректировка одобрена.
- `VAL-DC-003`: ограничение с неоднозначным юридическим основанием.
- `VAL-DC-004`: ограничение без обязательного `restriction_reference`.

Существующих трёх historical cases достаточно: каждый новый сценарий имеет
релевантный аналог. Историческая база не изменялась.

## Результаты четырёх E2E

| Кейс | Основной аналог | План | Экспертиза/result code | Итог | Eligibility | Следующее действие | Calls | Стоимость |
|---|---|---:|---|---|---|---|---:|---:|
| VAL-DC-001 | HIST-DC-002, 0.8247 | 4 шага | card_transaction_status_check / active_hold_confirmed | completed | false; active_authorization_hold | wait_for_reversal | 14 | $0.1200 |
| VAL-DC-002 | HIST-DC-001, 0.8148 | 3 шага | account_balance_analysis / zero_balance_confirmed | completed | true; blockers=[] | approve_case_closure | 13 | $0.1240 |
| VAL-DC-003 | HIST-DC-003, 0.8388 | 4 запланировано, 3 выполнено | account_restriction_check / manual_legal_review_required | manual_review | false | perform_manual_review | 15 | $0.1101 |
| VAL-DC-004 | HIST-DC-003, 0.7810 | 3 запланировано, 2 начато | account_restriction_check не вызвана: missing restriction_reference | waiting_for_information | не проверена | request_missing_information | 15 | $0.0992 |

Во всех четырёх случаях решение `approve_plan` записал `EMP-DEMO-001`.
Реальное закрытие и отправка клиенту не выполнялись. Полный audit trail:
`data/runtime/audit_log.jsonl`.

Calls и стоимость рассчитаны по разнице Ouroboros ledger перед и после каждого
сценария. Это все учтённые provider/LLM-вызовы агентного прогона, включая
служебные supervised-вызовы Ouroboros, а не только один запрос планировщика.
Суммарно: 57 calls и `$0.4533`.

## Стабильность GLM 5.2

Каждый из четырёх планов построен с первого запроса:
`model_requests=1`, `validation=passed`. Repair не потребовался. Все действия
планов входят в разрешённые четыре mock-Skills, а экспертизы — в каталог.

В Chat-презентации последнего кейса модель косметически написала
`remaining_blockers=[]`. Источник истины — runtime: eligibility не была
проверена, потому что исполнение остановилось на отсутствующем
`restriction_reference`. Контракт ранней остановки усилен верхнеуровневыми
полями eligibility, missing fields и next action; executor перезагружен.
Повторный платный E2E не запускался.

## Бюджет

`$30` берётся из локального файла настроек Ouroboros, поле `TOTAL_BUDGET`.
Ouroboros
передаёт его supervisor и показывает как `budget_limit` в `/api/state`.
Это локальный safety ledger приложения, а не подтверждённый лимит
OpenRouter-ключа и не общая квота проекта `$300`.

Лимит не изменялся. После тестов ledger:
`spent_usd=$3.7020`, `spent_calls=209`, локальный остаток `$26.2980`.
Провайдерский баланс/лимит нужно проверять отдельно в OpenRouter; приложение
не доказывает, что он равен `$30` или `$300`.

## Итог

Для видео выбран `VAL-DC-002`: сильный аналог, одна экспертиза, три понятных
шага, устранение блокера и обязательное финальное решение сотрудника.
Остаётся перед записью один раз визуально проверить компактность Chat-ответа
на чистом демо-чате. Новые архитектурные компоненты для этого не нужны.
