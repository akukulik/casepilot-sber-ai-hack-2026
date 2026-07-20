function demoCase({
  caseId,
  clientId,
  subtopic,
  description,
  createdAt,
  priority = "normal",
  balance = 0,
  accountStatus = "active",
  restrictionFlags = [],
  conversation,
  systemData = {},
}) {
  const accountId = `SYN-ACC-${caseId.slice(-3)}`;
  return {
    case_id: caseId,
    client_id: clientId,
    case_topic: "Дебетовые карты",
    case_subtopic: subtopic,
    created_at: createdAt,
    priority,
    case_description: description,
    conversation_transcript: conversation,
    client_context: {
      segment: priority === "high" ? "Премиальный" : "Массовый",
      region: "Москва",
    },
    products: [
      {
        product_id: `SYN-CARD-${caseId.slice(-3)}`,
        product_type: "debit_card",
        status: "active",
        currency: "RUB",
        balance,
        available_balance: Math.max(balance, 0),
        linked_account_id: accountId,
      },
      {
        product_id: accountId,
        product_type: "current_account",
        status: accountStatus,
        currency: "RUB",
        balance,
        available_balance: Math.max(balance, 0),
      },
    ],
    synthetic_system_data: {
      ledger_balance: balance,
      available_balance: Math.max(balance, 0),
      restriction_flags: restrictionFlags,
      ...systemData,
    },
  };
}

function demoAnalysis(caseId, scenarioId, scenarioTitle, score, steps) {
  return {
    case_id: caseId,
    run_id: `RUN-DEMO-${caseId}`,
    plan_id: `PLAN-DEMO-${caseId}`,
    plan_version: 1,
    scenario_title: scenarioTitle,
    scenario: {
      scenario_id: scenarioId,
      similarity_score: score,
    },
    plan: {
      confidence: {
        level: score >= 0.8 ? "high" : "medium",
        score,
        reason: "Совпали тема, причина обращения и ключевые системные признаки.",
      },
      proposed_plan: steps.map((step, index) => ({
        step_id: `step_${index + 1}`,
        order: index + 1,
        action_type: step.type,
        action: step.action,
        description: step.title,
      })),
    },
  };
}

function demoExecution(caseId, status, steps, result = {}) {
  const labels = {
    completed: "Проверки по плану завершены",
    waiting_for_information: "Нужны дополнительные данные",
    manual_review: "Требуется ручная проверка",
  };
  return {
    execution_id: `EXE-DEMO-${caseId}`,
    execution_status: status,
    status_label: labels[status] || "Выполнение остановлено",
    case_id: caseId,
    plan_version: 1,
    remaining_blockers: result.remainingBlockers || [],
    missing_fields: result.missingFields || [],
    stop_reason: result.stopReason || null,
    steps: steps.map((step, index) => ({
      step_id: `step_${index + 1}`,
      order: index + 1,
      title: step.title,
      action_label: step.type === "expertise" ? "Экспертиза" : "Проверка",
      status: step.status || "completed",
      ...(step.summary ? { result: { summary: step.summary } } : {}),
      ...(step.error ? { error_message: step.error } : {}),
      ...(step.missingFields ? { missing_fields: step.missingFields } : {}),
    })),
    resolution_recommendation: result.recommendation || null,
    client_response_draft: result.clientResponse || "",
    recommendation: result.fallbackRecommendation || "",
  };
}

function recommendation(title, summary, score, employeeActions, findings, risks) {
  return {
    title,
    summary,
    confidence: { level: score >= 0.8 ? "high" : "medium", score },
    employee_actions: employeeActions,
    key_findings: findings.map((finding) => ({ finding })),
    remaining_risks: risks,
  };
}

const cases = [
  demoCase({
    caseId: "VAL-DC-002",
    clientId: "SYN-CL-9002",
    subtopic: "Закрытие счёта",
    createdAt: "2026-07-18T14:20:00+03:00",
    balance: -199,
    accountStatus: "closure_requested",
    description: "Закрытие счёта отклонено из-за технического минуса после комиссии. Корректировка одобрена, но требуется контрольная проверка.",
    systemData: { closure_check_code: "ACCOUNT_BALANCE_NOT_ZERO" },
    conversation: [
      { speaker: "client", timestamp: "2026-07-18T14:20:00+03:00", text: "После блокировки карты появился минус 199 рублей, и я не могу закрыть счёт." },
      { speaker: "employee", timestamp: "2026-07-18T14:24:00+03:00", text: "Проверим техническую корректировку и итоговый остаток." },
      { speaker: "system", timestamp: "2026-07-18T14:25:00+03:00", text: "Автозакрытие отклонено: ACCOUNT_BALANCE_NOT_ZERO." },
    ],
  }),
  demoCase({
    caseId: "VAL-DC-013",
    clientId: "SYN-CL-9013",
    subtopic: "Неуспешный реверс",
    createdAt: "2026-07-18T12:05:00+03:00",
    balance: 4760,
    description: "После оплаты на АЗС предавторизация 8 000 ₽ не снялась, хотя итоговая покупка 3 240 ₽ уже проведена.",
    systemData: { active_hold: 8000, posted_amount: 3240, reversal_status: "delayed" },
    conversation: [
      { speaker: "client", timestamp: "2026-07-18T12:05:00+03:00", text: "Покупка прошла, но ещё восемь тысяч заблокированы." },
      { speaker: "employee", timestamp: "2026-07-18T12:09:00+03:00", text: "Проверим связку предавторизации, покупки и реверса." },
      { speaker: "system", timestamp: "2026-07-18T12:10:00+03:00", text: "REVERSAL_DELAYED: authorization hold remains active." },
    ],
  }),
  demoCase({
    caseId: "VAL-DC-016",
    clientId: "SYN-CL-9016",
    subtopic: "Регулярный платёж",
    createdAt: "2026-07-17T16:40:00+03:00",
    priority: "high",
    balance: 31800,
    description: "Клиент отменил подписку на фитнес-приложение, но merchant token продолжает разрешать регулярные списания.",
    systemData: { recurring_token_status: "active", customer_cancellation_confirmed: true },
    conversation: [
      { speaker: "client", timestamp: "2026-07-17T16:40:00+03:00", text: "Подписка отменена, но вчера снова списались деньги." },
      { speaker: "employee", timestamp: "2026-07-17T16:44:00+03:00", text: "Проверим тип операции и активный токен регулярного платежа." },
      { speaker: "system", timestamp: "2026-07-17T16:45:00+03:00", text: "RECURRING_TOKEN_ACTIVE." },
    ],
  }),
  demoCase({
    caseId: "VAL-DC-018",
    clientId: "SYN-CL-9018",
    subtopic: "Возврат по карточной операции",
    createdAt: "2026-07-17T10:15:00+03:00",
    balance: 7200,
    description: "Клиент ожидает возврат 11 480 ₽ за отменённый заказ. Merchant прислал подтверждение, но зачисления ещё нет.",
    systemData: { refund_amount: 11480, refund_message_status: "matched", posting_status: "pending" },
    conversation: [
      { speaker: "client", timestamp: "2026-07-17T10:15:00+03:00", text: "Магазин подтвердил возврат, но деньги не пришли." },
      { speaker: "employee", timestamp: "2026-07-17T10:18:00+03:00", text: "Сопоставим сообщение merchant с карточной операцией." },
      { speaker: "system", timestamp: "2026-07-17T10:19:00+03:00", text: "REFUND_MESSAGE_MATCHED; posting pending." },
    ],
  }),
  demoCase({
    caseId: "VAL-DC-004",
    clientId: "SYN-CL-9004",
    subtopic: "Закрытие счёта",
    createdAt: "2026-07-16T09:30:00+03:00",
    priority: "critical",
    balance: 0,
    accountStatus: "restricted",
    restrictionFlags: ["legal_restriction"],
    description: "Закрытие счёта отклонено из-за ограничения, но в выгрузке отсутствует номер документа-основания.",
    systemData: { closure_check_code: "ACCOUNT_RESTRICTED", restriction_reference: null },
    conversation: [
      { speaker: "client", timestamp: "2026-07-16T09:30:00+03:00", text: "Баланс нулевой. Почему счёт всё ещё нельзя закрыть?" },
      { speaker: "employee", timestamp: "2026-07-16T09:34:00+03:00", text: "Вижу ограничение, проверю документ-основание." },
      { speaker: "system", timestamp: "2026-07-16T09:35:00+03:00", text: "ACCOUNT_RESTRICTED; restriction_reference is missing." },
    ],
  }),
];

const flowDefinitions = {
  "VAL-DC-002": {
    scenarioId: "SCN-DC-CLOSE-NEGATIVE-BALANCE",
    scenarioTitle: "Закрытие счёта после технической корректировки",
    score: 0.82,
    steps: [
      { type: "check", action: "check_account_state", title: "Проверить текущий остаток и статус счёта.", summary: "Подтверждён технический остаток −199 ₽." },
      { type: "expertise", action: "request_expertise", title: "Подтвердить технический характер комиссии и корректировку.", summary: "Корректировка одобрена, контрольный остаток — 0 ₽." },
      { type: "check", action: "check_account_closure_eligibility", title: "Повторно проверить возможность закрытия счёта.", summary: "Препятствий для закрытия не обнаружено." },
    ],
    result: {
      recommendation: recommendation(
        "Счёт можно закрыть после подтверждения сотрудника",
        "Техническая комиссия скорректирована, остаток равен нулю.",
        0.91,
        ["Проверить реквизиты счёта.", "Подтвердить закрытие в штатной системе."],
        ["Технический отрицательный остаток устранён.", "Активных ограничений нет."],
        ["Демо не выполняет реальную банковскую операцию."],
      ),
      clientResponse: "Техническая комиссия скорректирована. Счёт готов к закрытию после подтверждения сотрудника.",
    },
  },
  "VAL-DC-013": {
    scenarioId: "SCN-DC-DELAYED-REVERSAL",
    scenarioTitle: "Снятие зависшей предавторизации после финального списания",
    score: 0.87,
    steps: [
      { type: "check", action: "check_pending_operations", title: "Сопоставить предавторизацию и финальную покупку.", summary: "Покупка 3 240 ₽ связана с hold 8 000 ₽." },
      { type: "expertise", action: "request_expertise", title: "Проверить статус реверса в карточном процессинге.", summary: "Реверс найден и подтверждён процессингом." },
      { type: "check", action: "case_actions", title: "Снять устаревший hold в mock-контуре.", summary: "Hold снят, доступный остаток восстановлен на 4 760 ₽." },
    ],
    result: {
      recommendation: recommendation(
        "Блокировка суммы устранена",
        "Предавторизация связана с завершённой покупкой, реверс подтверждён.",
        0.93,
        ["Проверить обновлённый доступный остаток.", "Завершить обращение."],
        ["Найдено корректное сопоставление authorization → posted.", "Hold снят в mock-контуре."],
        ["Реальный процессинг в демо не изменяется."],
      ),
      clientResponse: "Проверка завершена: временная блокировка снята, доступный остаток восстановлен.",
    },
  },
  "VAL-DC-016": {
    scenarioId: "SCN-DC-RECURRING-TOKEN",
    scenarioTitle: "Остановка повторных списаний по merchant token",
    score: 0.84,
    steps: [
      { type: "check", action: "check_pending_operations", title: "Подтвердить регулярный тип спорного списания.", summary: "Операция классифицирована как recurring payment." },
      { type: "expertise", action: "request_expertise", title: "Проверить подтверждение отмены подписки.", summary: "Отмена подписки подтверждена до повторного списания." },
      { type: "check", action: "case_actions", title: "Заблокировать merchant token в mock-контуре.", summary: "Merchant token переведён в blocked." },
      { type: "check", action: "check_account_state", title: "Проверить отсутствие новых разрешённых списаний.", summary: "Новых авторизаций по токену нет." },
    ],
    result: {
      recommendation: recommendation(
        "Регулярные списания остановлены",
        "Merchant token заблокирован после подтверждённой отмены подписки.",
        0.89,
        ["Проверить сумму спорной операции.", "Передать клиенту подтверждение блокировки токена."],
        ["Отмена подписки подтверждена.", "Повторные авторизации остановлены."],
        ["Возврат предыдущего списания рассматривается отдельно."],
      ),
      clientResponse: "Будущие регулярные списания по этой подписке заблокированы. Спорную операцию проверяем отдельно.",
    },
  },
  "VAL-DC-018": {
    scenarioId: "SCN-DC-REFUND-TRACE",
    scenarioTitle: "Розыск подтверждённого возврата",
    score: 0.79,
    steps: [
      { type: "check", action: "check_pending_operations", title: "Найти исходную покупку и сообщение о возврате.", summary: "Исходная покупка и refund message сопоставлены." },
      { type: "expertise", action: "request_expertise", title: "Проверить статус зачисления возврата.", summary: "Возврат находится в очереди на posting." },
      { type: "check", action: "case_actions", title: "Создать mock-контроль зачисления.", summary: "Контроль зачисления зарегистрирован со сроком один рабочий день." },
    ],
    result: {
      recommendation: recommendation(
        "Возврат найден и поставлен на контроль",
        "Сообщение merchant сопоставлено с исходной покупкой; posting ожидается.",
        0.86,
        ["Проконтролировать зачисление на следующий рабочий день.", "Не создавать дублирующий спор."],
        ["Сумма возврата — 11 480 ₽.", "Refund message успешно сопоставлен."],
        ["Зачисление ещё не отражено на балансе."],
      ),
      clientResponse: "Возврат найден и ожидает зачисления. Мы поставили операцию на контроль.",
    },
  },
  "VAL-DC-004": {
    scenarioId: "SCN-DC-CLOSE-RESTRICTION",
    scenarioTitle: "Проверка ограничения перед закрытием счёта",
    score: 0.78,
    steps: [
      { type: "check", action: "check_account_state", title: "Подтвердить нулевой остаток и активное ограничение.", summary: "Баланс 0 ₽, ограничение активно." },
      {
        type: "expertise",
        action: "request_expertise",
        title: "Проверить документ-основание ограничения.",
        status: "failed",
        error: "Для экспертизы отсутствует обязательный номер документа.",
        missingFields: ["Номер документа-основания ограничения"],
      },
      { type: "check", action: "check_account_closure_eligibility", title: "Проверить возможность закрытия после экспертизы.", status: "pending" },
    ],
    result: {
      status: "waiting_for_information",
      missingFields: ["Номер документа-основания ограничения"],
      remainingBlockers: ["Активное ограничение по счёту"],
      stopReason: "Исполнение безопасно остановлено до получения обязательного реквизита.",
      fallbackRecommendation: "Запросить номер документа-основания и продолжить проверку в банковском workflow.",
    },
  },
};

const flows = Object.fromEntries(
  Object.entries(flowDefinitions).map(([caseId, definition]) => {
    const status = definition.result.status || "completed";
    return [
      caseId,
      {
        analysis: demoAnalysis(
          caseId,
          definition.scenarioId,
          definition.scenarioTitle,
          definition.score,
          definition.steps,
        ),
        execution: demoExecution(caseId, status, definition.steps, definition.result),
      },
    ];
  }),
);

window.CASEPILOT_DEMO_DATA = { cases, flows };
