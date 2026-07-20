# Управляемая эволюция сценариев CasePilot

## Назначение

Контур обнаруживает повторяющиеся успешные ручные решения и предлагает новый
сценарий. Он не использует Ouroboros `/evolve`, не работает в фоне и не
публикует знания без человека.

```text
validated manual outcomes
        ↓
analyze_scenario_gaps
        ↓
draft
        ↓
validate_scenario_draft
        ↓
ready_for_expert_review
        ↓ EMP-DEMO-001
review_scenario_draft
        ↓
published runtime scenario
```

## Источники evidence

`data/scenario_learning_events.json` содержит полностью синтетический
демонстрационный кластер из трёх ручных решений. В production такие события
должны создаваться только после завершения кейса и проверки результата:

- решение было ручным или план CasePilot был исправлен;
- кейс успешно завершён;
- результат подтверждён экспертом;
- сохранены фактические действия, экспертизы и обязательные входы.

Сам факт нажатия «Решить самостоятельно» недостаточен для обучения.
`record_scenario_outcome` записывает runtime-событие только после отдельного
подтверждения результата `EMP-DEMO-001`.

## Создание draft

`analyze_scenario_gaps` группирует события по теме, подтеме и
`problem_signature`. Минимальный кластер — три события. Повторный запуск
идемпотентен: активный draft не дублируется.

Draft сохраняется в `data/runtime/scenario_drafts.json`. Канонические datasets
и рабочий каталог не изменяются.

## Независимая валидация

`validate_scenario_draft` проверяет:

- минимум три expert-validated evidence-события;
- 2–20 последовательных шагов;
- только разрешённые mock-actions;
- только экспертизы из `expertise_catalog.json`;
- конфликт с существующим каталогом;
- offline replay каждого evidence-события;
- pass rate не ниже 0.8.

Успех означает только `ready_for_expert_review`.

## Решение эксперта

`review_scenario_draft` принимает `approve` или `reject`. В MVP разрешён
`EMP-DEMO-001`. После approve новая версия попадает в
`data/runtime/published_scenarios.json`, после чего
`find_case_scenarios` включает её в retrieval.

Публикация записывается в отдельный append-only
`scenario_evolution_audit.jsonl`. Исходный `scenario_catalog.json` не
перезаписывается.

## Границы MVP

- нет scheduler или фонового цикла;
- нет LLM-генерации draft: структура синтезируется детерминированно из
  подтверждённых действий;
- нет автоматического approve;
- нет реальных банковских кейсов;
- нет production rollout, A/B evaluation и rollback;
- UI экспертного review пока не реализован.

Детерминированное создание выбрано намеренно: оно доказывает жизненный цикл
без дополнительных расходов и не позволяет модели выдумывать действия.
LLM-редактор формулировок можно добавить позднее, не меняя governance.
