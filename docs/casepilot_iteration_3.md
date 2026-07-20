# CasePilot — итерация 3

Дата проверки: 2026-07-19. Платформа: Ouroboros 6.61.4.

## Результат

Реализован полный контролируемый демонстрационный цикл:

1. план создаётся и записывается со статусом `proposed`;
2. сотрудник подтверждает его, запрашивает единственную редакцию или выбирает
   ручную обработку;
3. только `approved`-план текущей версии допускается к исполнению;
4. четыре mock-действия выполняются строго последовательно;
5. результаты и audit trail сохраняются локально;
6. итог требует отдельного финального решения сотрудника.

Реальное закрытие счёта, изменение банковского продукта и отправка сообщения
клиенту не выполняются.

## Runtime-состояние

Файлы:

- `data/runtime/plans.json` — обёртки планов;
- `data/runtime/approvals.json` — решения сотрудников;
- `data/runtime/executions.json` — исполнения и результаты шагов;
- `data/runtime/audit_log.jsonl` — append-only события без секретов.

Для них добавлены:

- `schemas/runtime_plans.schema.json`;
- `schemas/runtime_approvals.schema.json`;
- `schemas/runtime_executions.schema.json`.

Статусы плана: `proposed`, `change_requested`, `approved`, `executing`,
`completed`, `failed`, `manual_review`.

Отдельные статусы исполнения: `executing`, `completed`, `failed`,
`waiting_for_information`, `replan_required`, `manual_review`.

Запись JSON выполняется через временный файл и атомарный `os.replace`.
Validation и historical datasets не изменяются.

## Протокол решения

Skill `review_resolution_plan` принимает `case_id`, `plan_id`, `plan_version`,
`decision`, `employee_id` и `comment`. Для MVP разрешён только
`EMP-DEMO-001`.

- `approve_plan` переводит текущий `proposed`-план в `approved`;
- первый `request_change` версии 1 переводит её в `change_requested`;
- `build_resolution_plan` с `revision_context` может после этого создать
  версию 2 с `supersedes_plan_version: 1`;
- повторный `request_change` версии 1 до создания версии 2 также считается
  превышением лимита;
- любой `request_change` версии 2 переводит кейс в `manual_review`;
- версия 3 никогда не создаётся;
- `manual_review` останавливает автоматическое исполнение;
- решение по устаревшей версии отклоняется.

Approve и manual review полностью детерминированы. LLM допускается только для
создания первоначального плана и единственной версии 2.

## Контракты mock-Skills

Разрешённый action allowlist:

| Каноническое действие | Обязательные входы | Основной результат |
|---|---|---|
| `check_account_state` | `case_id`, `account_id` | остатки, сумма холдов, ограничения, статус |
| `check_pending_operations` | `case_id`, `card_id`, `account_id` | операции, hold, reversal, timestamp, `result_code` |
| `request_expertise` | точный `required_inputs` из каталога | детерминированный catalog-bound `result_code` |
| `check_account_closure_eligibility` | `case_id`, `account_id`, `previous_results` | `eligible`, blockers, пояснение |

Ouroboros 6.61.4 ограничивает техническое имя зарегистрированного tool
24 символами. Поэтому последний Skill зарегистрирован с внутренним alias
`closure_eligibility`; каталог Skill и каноническое действие плана остаются
`check_account_closure_eligibility`.

Для `VAL-DC-001` экспертиза `card_transaction_status_check` стабильно возвращает
`active_hold_confirmed`, идентификаторы `SYN-AUTH-901`/`SYN-OP-901`,
`reversal_pending` и ожидаемый срок освобождения.

## Оркестрация

`execute_approved_plan`:

1. проверяет существование и актуальность версии;
2. требует статус `approved`;
3. повторно валидирует plan JSON Schema;
4. проверяет action allowlist и точные `required_inputs`;
5. сортирует шаги по `order` и запрещает пропуски;
6. выполняет шаги последовательно;
7. сохраняет статус и результат каждого шага;
8. проверяет машинный `result_code` экспертизы;
9. применяет `failure_action`;
10. возвращает детерминированный черновик и требует финального подтверждения.

Поведение ошибок:

- `continue` — следующий шаг;
- `request_information` — `waiting_for_information`;
- `replan` — `replan_required`, без автоматического перестроения;
- `manual_review` или отклонение expertise `result_code` — возврат человеку.

Неизвестное действие или несовпадение input-контракта отклоняет план до
исполнения.

## Финальный Chat E2E

Task `d93a8603` в чистом Chat-контексте завершился маркером
`CASEPILOT_CHAT_E2E_OK`.

План `PLAN-VAL-DC-001-001`, версия 1:

1. `check_account_state` → `account_state_retrieved`;
2. `check_pending_operations` → `pending_reversal_confirmed`;
3. `request_expertise` → `active_hold_confirmed`;
4. `check_account_closure_eligibility` → `closure_not_eligible`.

Итог:

- `execution_status`: `completed`;
- `remaining_blockers`: `active_authorization_hold`;
- `closure_eligibility.eligible`: `false`;
- `recommended_next_action`: `wait_for_reversal`;
- `requires_final_employee_approval`: `true`.

Это ожидаемый результат: mock-проверки не имеют права искусственно снимать
реальный или синтетический hold. «Completed» означает завершение утверждённых
проверок, а не закрытие кейса.

## Audit trail демонстрационного запуска

1. `plan_created` — версия 1, `proposed`;
2. `plan_reviewed` — `approve_plan`, outcome `approved`;
3. `execution_started`;
4. `step_1` started/completed — `account_state_retrieved`;
5. `step_2` started/completed — `pending_reversal_confirmed`;
6. `step_3` started/completed — `active_hold_confirmed`;
7. `step_4` started/completed — `closure_not_eligible`;
8. `execution_completed` — `closure_eligible=false`,
   `requires_final_employee_approval=true`.

Полный машинный журнал находится в `data/runtime/audit_log.jsonl`.

## Проверки

Успешно пройдены:

- Python compile;
- исходные dataset-контракты;
- JSON Schema артефакта;
- официальный deterministic Skill preflight Ouroboros для семи затронутых
  Skills;
- штатная owner-attested review без платного LLM-review;
- регистрация и live-load всех extension Skills;
- локальный основной сценарий;
- финальный Chat E2E;
- выполнение неподтверждённого плана запрещено;
- устаревшую версию подтвердить нельзя;
- `manual_review` не исполняется;
- неизвестная экспертиза отклоняется;
- отсутствие обязательного expertise input отклоняется;
- повторный change request версии 1 останавливается;
- change request версии 2 переводит кейс в `manual_review`;
- версия 3 не создаётся.

## LLM-вызовы и стоимость

Детерминированные unit/preflight/review проверки не использовали LLM и стоили
`$0`.

За эту итерацию выполнены два ограниченных Chat-прогона:

- диагностический: 16 provider calls, `$0.1137`;
- финальный после усиления input-контрактов: 15 provider calls, `$0.0968`.

Итого итерации: 31 provider call, `$0.2105`.

Общий счётчик Ouroboros после тестов: 152 calls, `$3.2487` из лимита `$30`;
остаётся `$26.7513`. В provider calls входят основная модель Chat, safety checks
и один planning-вызов на каждый успешный прогон. Owner-attested Skill review
стоил `$0`.

## Созданные и изменённые файлы

Созданы:

- `casepilot/__init__.py`;
- `casepilot/runtime.py`;
- четыре runtime-файла;
- три runtime-схемы;
- шесть новых каталогов Skills;
- `tests/test_casepilot_runtime.py`;
- `tests/preflight_ouroboros_casepilot.py`;
- `tests/run_casepilot_demo.py`;
- этот отчёт.

Изменены:

- `README.md`;
- `tests/fixtures/VAL-DC-001_resolution_plan.json`;
- `schemas/resolution_plan.schema.json`;
- bundled schema и файлы `skills/build_resolution_plan`;
- нативный `tests/preflight_ouroboros_casepilot.py`.

Historical и validation datasets не изменены. API-ключ не записывался в
проект, runtime, audit или отчёт.

## Ограничения и следующий выбор

- Runtime рассчитан на локальный однопользовательский demo-процесс; межпроцессной
  блокировки и базы данных пока нет.
- Итог `eligible=false` требует ожидания reversal или ручного решения; автоматического
  фонового повторения нет.
- Финальное подтверждение закрытия ещё не реализовано.
- Не определён отдельный протокол подтверждения либо отклонения черновика
  клиентского ответа.

Перед следующей итерацией нужно согласовать контракт второго подтверждения:
разрешает ли оно только mock-переход состояния либо также формирует отдельные
команды `approve_case_closure` и `approve_client_response`, и как вести себя,
если blockers всё ещё существуют.
