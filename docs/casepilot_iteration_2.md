# CasePilot: итерация 2 — build_resolution_plan

## Результат

Реализован и установлен в Ouroboros 6.61.4 read-only Skill
`build_resolution_plan`. Финальный end-to-end тест `VAL-DC-001` через штатный
Chat завершён со статусом `ok`: 4 orchestration rounds, 4 tool calls, 0 tool
errors. План не выполнялся.

Полный технический результат:
Стабилизированный контрактный пример:
[`tests/fixtures/VAL-DC-001_resolution_plan.json`](../tests/fixtures/VAL-DC-001_resolution_plan.json).

## 1. Созданные и изменённые файлы

Созданы:

- `skills/build_resolution_plan/SKILL.md`;
- `skills/build_resolution_plan/plugin.py`;
- `skills/build_resolution_plan/planner.py`;
- `skills/build_resolution_plan/resolution_plan.schema.json`;
- `skills/build_resolution_plan/casepilot_project_dir.txt`;
- `schemas/resolution_plan.schema.json`;
- первоначальный платный Chat-runner позднее удалён как устаревший;
- `tests/fixtures/VAL-DC-001_resolution_plan.json`;
- этот отчёт.

Изменены:

- `skills/find_similar_cases/scripts/find_similar_cases.py`;
- `skills/find_similar_cases/SKILL.md` (версия 0.3.1);
- `README.md`.

`find_similar_cases` теперь возвращает полный `historical_case` и принимает как
сам validation-case, так и штатный envelope `load_case` с полем `case`.

## 2. Контракт входа

Structured tool принимает нативные аргументы:

```json
{
  "case": {},
  "similar_cases": [],
  "expertise_catalog": []
}
```

`case` не может содержать скрытые поля решения; `similar_cases` содержит не
более трёх результатов с полными историческими кейсами; каталог должен быть
непустым. Skill не загружает эти данные повторно.

## 3. Schema результата

Используется JSON Schema Draft 2020-12. Она запрещает дополнительные поля,
первоначально требовала 2–6 шагов; позднее верхняя граница увеличена до 20.
Схема фиксирует enum-значения, `status: pending`,
`requires_employee_approval: true`, максимум две экспертизы и диапазоны score.
Копия Schema упакована внутрь isolated extension и идентична канонической
`schemas/resolution_plan.schema.json`.

## 4. Системный prompt

Полный prompt находится в `skills/build_resolution_plan/planner.py` в
`SYSTEM_PROMPT`. Он задаёт роль read-only планировщика, разрешает использовать
исторические решения только как стратегии, запрещает выдумывать данные и
выполнять план, ограничивает число шагов и экспертиз, задаёт правила
similarity/confidence и требует чистый JSON.

## 5. Программные проверки

После ответа модели проверяются:

- JSON Schema;
- совпадение `case_id`;
- ссылки только на переданные historical case IDs и неизменность их score;
- ссылки только на экспертизы каталога;
- допустимые required inputs экспертизы;
- уникальные и последовательные `step_id`/`order`;
- точное соответствие expertise-шагов и `required_expertises`;
- максимум две экспертизы;
- правила confidence для порогов 0.45 и 0.65;
- обязательное подтверждение сотрудником.

При первой ошибке допускается один repair-запрос с перечнем ошибок. После
второго невалидного ответа возвращается контролируемая ошибка.

## 6–8. Модель, запросы и стоимость

- Planner model: `z-ai/glm-5.2`.
- Reasoning effort: `medium`.
- Temperature: `0.1`.
- Модельных запросов внутри финального запуска Skill: **2** (первичный +
  repair).
- Полный успешный Chat-тест: **$0.0650** по разнице общего ledger Ouroboros
  (`$2.9732 → $3.0382`).
- `task_done` отдельно атрибутировал orchestration-задаче `$0.044976`;
  разница включает safety-проверки и два внутренних planner-вызова.

До финального теста интеграционная диагностика потребовала дополнительных
запусков: первоначальный script-вариант завершился по round limit
(`$0.141441`), тест с недоступной внешней Schema — `$0.197463`, а успешная
проверка bundled Schema с некорректно переданным envelope поиска — `$0.059453`.
Эти суммы не входят в `$0.0650` финального корректного теста.

## 9–10. Итоговый JSON и валидация

Полный неизменённый JSON сохранён в
`tests/fixtures/VAL-DC-001_resolution_plan.json`.

Повторная независимая локальная проверка:

```json
{
  "validation": "passed",
  "errors": [],
  "top_match": "HIST-DC-002",
  "top_score": 0.8247,
  "steps": 4,
  "expertises": 1,
  "approval": true
}
```

## 11. Читаемое представление

Кейс `VAL-DC-001`: закрытие блокирует активный authorization hold по отменённой
аренде; reversal остаётся в обработке. Признаки: код
`ACTIVE_AUTHORIZATION_HOLD`, `SYN-AUTH-901=reversal_pending`,
`SYN-OP-901=processing`, совпадающие ledger/available balance.

Основной пример — `HIST-DC-002` со score `0.8247`. План:

1. Запросить `card_transaction_status_check`.
2. По результату завершить reversal вручную либо дождаться автоосвобождения.
3. Повторить closure check.
4. Подготовить черновик сообщения клиенту.

Уверенность высокая (`0.82`). План требует подтверждения сотрудника; ни один
шаг не выполнен.

## 12. Ограничения

- Текущий similarity — детерминированный лексико-правиловый алгоритм на трёх
  исторических примерах, без семантического поиска.
- Planner делает прямые OpenRouter-запросы внутри extension; детальная стоимость
  этих вызовов не выделяется отдельной строкой task ledger.
- Chat orchestration чувствителен к форме envelope между script Skills; для
  `load_case → find_similar_cases` добавлена явная совместимость.
- В плане есть будущий `case_action`, но исполняющего Skill и банковской
  интеграции нет.
- Сгенерированная русская формулировка требует редакторской полировки
  (“активной авторизационного холда”), хотя структура и смысл валидны.

## 13. Что согласовать дальше

- Формат решения сотрудника: approve / request changes / manual review.
- Где хранить версию, автора, timestamp и audit trail подтверждения.
- Какие шаги разрешено выполнять автоматически и какие требуют отдельного
  подтверждения.
- Контракты будущих check/expertise/action Skills и идемпотентность.
- Поведение при изменении данных между построением и подтверждением плана.
- Нужен ли обязательный revalidation/replan перед исполнением.

До согласования этих пунктов подтверждение и исполнение плана не реализуются.
