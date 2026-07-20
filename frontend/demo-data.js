window.CASEPILOT_DEMO_DATA = {
  cases: [
    {
      case_id: "VAL-DC-002",
      client_id: "SYN-CL-9002",
      case_topic: "Дебетовые карты",
      case_subtopic: "Закрытие счёта",
      created_at: "2026-07-18T14:20:00+03:00",
      priority: "normal",
      case_description: "Закрытие счёта отклонено из-за технического минуса после комиссии, начисленной уже после блокировки дебетовой карты. Корректировка комиссии одобрена операционным подразделением, но требуется контрольная проверка.",
      conversation_transcript: [
        {
          speaker: "client",
          timestamp: "2026-07-18T14:20:00+03:00",
          text: "Я заблокировал карту и вывел деньги, но вижу минус 199 рублей и не могу закрыть счёт.",
        },
        {
          speaker: "employee",
          timestamp: "2026-07-18T14:24:00+03:00",
          text: "Комиссия начислена после блокировки. В системе уже есть одобрение технической корректировки, проверим итоговый остаток.",
        },
        {
          speaker: "system",
          timestamp: "2026-07-18T14:25:00+03:00",
          text: "Автозакрытие отклонено: ACCOUNT_BALANCE_NOT_ZERO.",
        },
      ],
      client_context: {
        segment: "Массовый",
        region: "Москва",
      },
      products: [
        {
          product_id: "SYN-CARD-9002",
          product_type: "debit_card",
          status: "blocked_by_client",
          currency: "RUB",
          balance: 0,
          available_balance: 0,
          linked_account_id: "SYN-ACC-9002",
        },
        {
          product_id: "SYN-ACC-9002",
          product_type: "current_account",
          status: "closure_requested",
          currency: "RUB",
          balance: -199,
          available_balance: 0,
        },
      ],
      synthetic_system_data: {
        closure_check_code: "ACCOUNT_BALANCE_NOT_ZERO",
        ledger_balance: -199,
        available_balance: 0,
        restriction_flags: [],
      },
    },
  ],
  analysis: {
    case_id: "VAL-DC-002",
    run_id: "RUN-DEMO-0001",
    plan_id: "PLAN-DEMO-0001",
    plan_version: 1,
    scenario_title: "Закрытие счёта после технической корректировки",
    scenario: {
      scenario_id: "SCN-DC-CLOSE-NEGATIVE-BALANCE",
      similarity_score: 0.82,
    },
    plan: {
      confidence: {
        level: "high",
        score: 0.82,
        reason: "Совпали причина блокировки и одобренная техническая корректировка.",
      },
      proposed_plan: [
        {
          step_id: "step_1",
          order: 1,
          action_type: "check",
          action: "check_account_state",
          description: "Проверить текущий остаток и статус счёта.",
        },
        {
          step_id: "step_2",
          order: 2,
          action_type: "expertise",
          action: "request_expertise",
          description: "Подтвердить технический характер комиссии и корректировку.",
        },
        {
          step_id: "step_3",
          order: 3,
          action_type: "check",
          action: "check_account_closure_eligibility",
          description: "Повторно проверить возможность закрытия счёта.",
        },
      ],
    },
  },
  execution: {
    execution_id: "EXE-DEMO-0001",
    execution_status: "completed",
    status_label: "Проверки по плану завершены",
    case_id: "VAL-DC-002",
    plan_version: 1,
    remaining_blockers: [],
    missing_fields: [],
    steps: [
      {
        step_id: "step_1",
        order: 1,
        title: "Проверить текущий остаток и статус счёта.",
        action_label: "Проверка",
        status: "completed",
        result: { summary: "Подтверждён технический остаток −199 ₽." },
      },
      {
        step_id: "step_2",
        order: 2,
        title: "Подтвердить технический характер комиссии и корректировку.",
        action_label: "Экспертиза",
        status: "completed",
        result: { summary: "Корректировка одобрена, контрольный остаток — 0 ₽." },
      },
      {
        step_id: "step_3",
        order: 3,
        title: "Повторно проверить возможность закрытия счёта.",
        action_label: "Проверка",
        status: "completed",
        result: { summary: "Препятствий для закрытия не обнаружено." },
      },
    ],
    resolution_recommendation: {
      title: "Счёт можно закрыть после подтверждения сотрудника",
      summary: "Техническая комиссия скорректирована, остаток равен нулю, активных ограничений нет.",
      confidence: { level: "high", score: 0.91 },
      employee_actions: [
        "Проверить реквизиты счёта.",
        "Подтвердить закрытие в штатной системе.",
      ],
      key_findings: [
        { finding: "Технический отрицательный остаток устранён." },
        { finding: "Контрольная проверка не выявила блокеров." },
      ],
      remaining_risks: [
        "Демо не выполняет реальную банковскую операцию.",
      ],
    },
    client_response_draft: "Проверка завершена: техническая комиссия скорректирована. Счёт готов к закрытию после финального подтверждения сотрудника.",
  },
};
