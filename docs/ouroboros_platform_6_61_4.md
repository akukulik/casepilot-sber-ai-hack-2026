# Ouroboros 6.61.4: как устроены агенты и Skills

Дата проверки: 2026-07-19.

Источник: установленное приложение и исходники официального релиза 6.61.4 в
`~/Ouroboros/repo`, прежде всего `docs/CREATING_SKILLS.md`,
`ouroboros/skill_loader.py`, `ouroboros/contracts/plugin_api.py` и gateway API.

## Где находятся конфиг и данные

- Приложение: `/Applications/Ouroboros.app`.
- Управляемый код runtime: `~/Ouroboros/repo`.
- Настройки провайдеров, моделей, review и бюджета:
  `~/Ouroboros/data/settings.json`.
- Память: `~/Ouroboros/data/memory`.
- Пользовательские Skills: `~/Ouroboros/data/skills/external/<name>`.
- Review, enablement, grants и state Skill:
  `~/Ouroboros/data/state/skills/<name>`.

`settings.json` версии 6.61.4 является штатным локальным хранилищем мастера.
В нашем окружении права файла дополнительно ограничены до `600`. Секреты не
копируются в репозиторий CasePilot.

## Как подключается LLM

Onboarding сохраняет ключ провайдера и model slots в Settings. После запуска
Ouroboros применяет настройки к окружению своего процесса, загружает каталог
моделей и поднимает Supervisor. Основная модель CasePilot —
`z-ai/glm-5.2` с `reasoning_effort=medium` через OpenRouter.

Skill не должен содержать ключ. Extension может объявить
`env_from_settings: [OPENROUTER_API_KEY]`, пройти review и получить отдельный
owner grant, после чего читает только разрешённое значение через
`PluginAPI.get_settings`.

## Как создаются агенты

Основной агент запускается Supervisor после появления рабочего провайдера.
Обычный пользовательский запрос приходит из Chat по WebSocket и становится
задачей агента. Дополнительные специализированные агенты создаются механизмами
делегирования/A2A, но для данного PoC и первого CasePilot MVP они не нужны.
Режим `light` оставляет self-modification выключенным.

## Типы Skills

- `instruction`: только Markdown-инструкции, собственного executable surface нет;
- `script`: один или несколько подпроцессов из `scripts/`, запуск через
  `skill_exec`;
- `extension`: `plugin.py`, который через `PluginAPI` регистрирует agent-tools,
  HTTP routes, WebSocket handlers или widgets.

Минимальный пакет содержит каталог и `SKILL.md` либо `skill.json`. Для
extension также нужны `runtime: python3`, `entry: plugin.py` и сам `plugin.py`.

## Жизненный цикл

1. Поместить пакет в `data/skills/external/<name>`.
2. Выполнить deterministic `skill_preflight`.
3. Выполнить LLM review либо owner attestation для собственного Skill.
4. Выдать только запрошенные grants.
5. Включить Skill.
6. Запустить через `skill_exec` для script, agent-tool/route для extension.

Любое изменение runtime-файла меняет content hash и делает review/grants
устаревшими до повторной проверки.

## Реализованный PoC

Исходники лежат в `skills/openrouter_echo/`. Это extension с:

- tool `ask`, доступным агенту;
- route `POST /api/extensions/openrouter_echo/ask`;
- фиксированным endpoint OpenRouter;
- лимитом входа 4 000 символов, выхода 256 tokens и timeout 30 секунд;
- одним запросом без retry-loop;
- доступом только к `OPENROUTER_API_KEY`.

PoC прошёл deterministic preflight, owner attestation, grant, enable/load и
вернул `POC_OK` на полноценном вызове.

На проверку выполнено два модельных вызова: один Chat smoke test и один
PoC-вызов Skill. Ouroboros зафиксировал суммарный расход `$0.2035` при лимите
`$10`; циклы, фоновые задачи и автоматические повторы не запускались.
