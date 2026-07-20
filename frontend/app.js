const state = {
  cases: [],
  selectedId: null,
  analysis: null,
  pollingToken: 0,
  executionRetryUsed: false,
  demoMode: false,
  demoData: window.CASEPILOT_DEMO_DATA || null,
};

const elements = {
  list: document.querySelector("#case-list"),
  count: document.querySelector("#case-count"),
  content: document.querySelector("#case-content"),
  strategy: document.querySelector("#strategy"),
};

const priorities = {
  high: "Высокий",
  critical: "Критический",
  normal: "Обычный",
  low: "Низкий",
};
const speakers = { client: "Клиент", employee: "Оператор", system: "Система" };
const products = { debit_card: "Дебетовая карта", current_account: "Текущий счёт" };

const icons = {
  calendar: `<svg viewBox="0 0 24 24"><path d="M6 3v3m12-3v3M4 8h16v12H4z"/></svg>`,
  person: `<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3"/><path d="M5 20c.5-4 2.8-6 7-6s6.5 2 7 6"/></svg>`,
  pin: `<svg viewBox="0 0 24 24"><path d="M12 21s6-5.1 6-11a6 6 0 1 0-12 0c0 5.9 6 11 6 11Z"/><circle cx="12" cy="10" r="2"/></svg>`,
  segment: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6 2.1 2.1"/></svg>`,
  product: `<svg viewBox="0 0 24 24"><path d="M8 6h8v12H8zM5 9h3m8 0h3M5 15h3m8 0h3"/></svg>`,
  account: `<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/></svg>`,
  balance: `<svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/><path d="M7 5v4m5 1v4m5 1v4"/></svg>`,
  alert: `<svg viewBox="0 0 24 24"><path d="m12 3 9 17H3L12 3Z"/><path d="M12 9v5m0 3v.1"/></svg>`,
  chat: `<svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 0 1-8 8 9 9 0 0 1-3.5-.7L4 20l1.6-4A8 8 0 1 1 20 11Z"/></svg>`,
  chevron: `<svg class="chevron" viewBox="0 0 24 24"><path d="m8 10 4 4 4-4"/></svg>`,
  book: `<svg viewBox="0 0 24 24"><path d="M4 5a4 4 0 0 1 4-1l4 2v14l-4-2a4 4 0 0 0-4 1V5Zm16 0a4 4 0 0 0-4-1l-4 2v14l4-2a4 4 0 0 1 4 1V5Z"/></svg>`,
  check: `<svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6"/></svg>`,
  edit: `<svg viewBox="0 0 24 24"><path d="m4 20 4-1 11-11-3-3L5 16l-1 4Zm10-13 3 3"/></svg>`,
  manual: `<svg viewBox="0 0 24 24"><circle cx="12" cy="7" r="3"/><path d="M5 20c.5-4 2.8-6 7-6s6.5 2 7 6"/></svg>`,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function date(value, time = false) {
  const options = { day: "2-digit", month: "2-digit", year: "numeric" };
  if (time) Object.assign(options, { hour: "2-digit", minute: "2-digit" });
  return new Intl.DateTimeFormat("ru-RU", options).format(new Date(value));
}

function clock(value) {
  return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function money(value, currency = "RUB") {
  return new Intl.NumberFormat("ru-RU", { style: "currency", currency, maximumFractionDigits: 0 }).format(value ?? 0);
}

function account(item) {
  return item.products.find((product) => product.product_type === "current_account");
}

function renderQueue() {
  elements.count.textContent = state.cases.length;
  elements.list.innerHTML = state.cases.map((item) => `
    <button class="case-card ${item.case_id === state.selectedId ? "active" : ""}" data-case="${item.case_id}">
      <span class="case-top">
        <span class="case-priority ${item.priority}"><span class="priority-dot"></span>${priorities[item.priority]}</span>
        <span class="case-date">${date(item.created_at)}</span>
      </span>
      <span class="case-id">${escapeHtml(item.case_id)}</span>
      <span class="client-id">${escapeHtml(item.client_id)}</span>
    </button>
  `).join("");
  elements.list.querySelectorAll("[data-case]").forEach((button) => {
    button.addEventListener("click", () => selectCase(button.dataset.case));
  });
}

function attribute(icon, label, value) {
  return `
    <div class="attribute">
      <span class="attribute-icon">${icon}</span>
      <span class="attribute-label">${escapeHtml(label)}</span>
      <span class="attribute-value">${escapeHtml(value)}</span>
    </div>
  `;
}

function renderCase(item) {
  const caseAccount = account(item);
  const hasRestrictions = (item.synthetic_system_data.restriction_flags || []).length > 0;
  elements.content.innerHTML = `
    <div class="case-header">
      <div class="case-heading">
        <h2>${escapeHtml(item.case_id)}</h2>
        <span class="priority-pill ${item.priority}">${priorities[item.priority]}</span>
      </div>
      <div class="case-meta">
        <span class="meta-item">${icons.calendar}${date(item.created_at, true)}</span>
        <span class="meta-divider"></span>
        <span class="meta-item">${icons.person}${escapeHtml(item.client_id)}</span>
      </div>
    </div>

    <section class="content-section">
      <div class="section-heading"><span class="section-icon">▤</span><h3>Описание кейса</h3></div>
      <p class="case-description">${escapeHtml(item.case_description)}</p>
    </section>

    <section class="content-section">
      <h3>Ключевые атрибуты</h3>
      <div class="attributes" style="margin-top:18px">
        ${attribute(icons.person, "Клиент", item.client_id)}
        ${attribute(icons.account, "Счёт", caseAccount?.product_id || "—")}
        ${attribute(icons.pin, "Регион", item.client_context.region)}
        ${attribute(icons.balance, "Баланс", money(item.synthetic_system_data.ledger_balance))}
        ${attribute(icons.segment, "Сегмент", item.client_context.segment)}
        ${attribute(icons.alert, "Ограничения", hasRestrictions ? "Есть" : "Нет")}
        ${attribute(icons.product, "Продукт", "Дебетовая карта")}
      </div>
    </section>

    <section class="content-section">
      <h3>Банковские продукты</h3>
      <div class="products">
        ${item.products.map((product) => `
          <div class="product">
            <div class="product-left">
              <span class="product-icon">${icons.account}</span>
              <div><strong>${products[product.product_type] || product.product_type}</strong><small>${escapeHtml(product.product_id)}</small></div>
            </div>
            <span class="product-balance">${money(product.balance, product.currency)}</span>
          </div>
        `).join("")}
      </div>
    </section>

    <section class="content-section" style="border-bottom:0">
      <button class="transcript-toggle" id="transcript-toggle">
        ${icons.chat}
        <span class="transcript-copy"><strong>Общение с клиентом</strong><span>${item.conversation_transcript.length} сообщения</span></span>
        <span class="transcript-action">Показать</span>
        ${icons.chevron}
      </button>
      <div class="transcript-body" id="transcript-body">
        ${item.conversation_transcript.map((message) => `
          <div class="message">
            <div class="message-meta"><strong>${speakers[message.speaker]}</strong><time>${clock(message.timestamp)}</time></div>
            <p>${escapeHtml(message.text)}</p>
          </div>
        `).join("")}
      </div>
    </section>
  `;

  const toggle = document.querySelector("#transcript-toggle");
  const body = document.querySelector("#transcript-body");
  toggle.addEventListener("click", () => {
    const open = body.classList.toggle("open");
    toggle.classList.toggle("open", open);
    toggle.querySelector(".transcript-action").textContent = open ? "Скрыть" : "Показать";
  });
}

function renderStrategyStart(item) {
  elements.strategy.innerHTML = `
    <h2>Стратегия решения</h2>
    <div class="empty" style="height:calc(100% - 35px)">
      <div class="empty-icon">✦</div>
      <h2>Кейс готов к анализу</h2>
      <p>CasePilot подберёт сценарий и сформирует план.</p>
      <button class="run-button" id="run-analysis">Запустить CasePilot</button>
    </div>
  `;
  document.querySelector("#run-analysis").addEventListener("click", runAnalysis);
}

function scenarioName(result) {
  return result.scenario_title || result.scenario?.scenario_id || "Сценарий решения";
}

function selectedDemoFlow() {
  if (!state.demoData) return null;
  return state.demoData.flows?.[state.selectedId] || (
    state.demoData.analysis && state.demoData.execution
      ? {
          analysis: state.demoData.analysis,
          execution: state.demoData.execution,
        }
      : null
  );
}

function renderStrategy(result) {
  state.analysis = result;
  state.executionRetryUsed = false;
  const plan = result.plan;
  const confidence = plan.confidence || { score: 0 };
  elements.strategy.innerHTML = `
    <h2>Стратегия решения</h2>
    <p class="analysis-status">CasePilot проанализировал кейс</p>

    <section class="strategy-block">
      <div class="strategy-block-title">${icons.book}<h3>Выбранный сценарий</h3></div>
      <p class="scenario-title">${escapeHtml(scenarioName(result))}</p>
      <span class="confidence">Уверенность ${Math.round(confidence.score * 100)}%</span>
    </section>

    <h3 class="plan-title">План сценария</h3>
    <div class="steps">
      ${plan.proposed_plan.map((step) => `
        <article class="step">
          <span class="step-number">${step.order}</span>
          <div class="step-card">
            <p class="step-text">${escapeHtml(step.description)}</p>
            <span class="step-badge">${step.action_type === "expertise" ? "Экспертиза" : "Проверка"}</span>
          </div>
        </article>
      `).join("")}
    </div>

    <section class="decision">
      <h3>Требуется решение сотрудника</h3>
      <div class="decision-grid">
        <button class="decision-button primary" data-decision="approve">${icons.check}Подтвердить</button>
        <button class="decision-button manual" data-decision="manual">${icons.manual}Решить самостоятельно</button>
      </div>
    </section>
  `;

  elements.strategy.querySelectorAll("[data-decision]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (button.dataset.decision === "approve") {
        await approveAndExecute();
        return;
      }
      if (button.dataset.decision === "manual") {
        await takeCaseManual();
      }
    });
  });
}

const terminalExecutionStatuses = new Set([
  "completed",
  "failed",
  "waiting_for_information",
  "replan_required",
  "manual_review",
]);

function executionIsTerminal(execution) {
  return terminalExecutionStatuses.has(execution.execution_status)
    && execution.recommendation_status !== "generating";
}

function statusText(status) {
  return {
    pending: "Ожидает",
    executing: "Выполняется",
    completed: "Выполнен",
    failed: "Остановлен",
  }[status] || "Ожидает";
}

function stepMarker(step) {
  if (step.status === "completed") return "✓";
  if (step.status === "failed") return "!";
  if (step.status === "executing") return `<span class="spinner"></span>`;
  return step.order;
}

function terminalAction(execution) {
  if (execution.execution_status === "waiting_for_information") {
    return `<button class="terminal-button" id="add-case-information">Добавить информацию</button>`;
  }
  if (execution.execution_status === "replan_required") {
    return `<button class="terminal-button">Сформировать обновлённый план</button>`;
  }
  if (execution.execution_status === "manual_review") {
    return `<button class="terminal-button" id="open-manual-review">Перейти к ручному решению</button>`;
  }
  if (execution.execution_status === "failed" && !state.executionRetryUsed) {
    return `<button class="terminal-button" id="retry-execution">Повторить выполнение</button>`;
  }
  return "";
}

function renderExecution(execution) {
  const terminal = executionIsTerminal(execution);
  const title = execution.status_label || (
    terminal ? "Выполнение завершено" : "План выполняется"
  );
  const missing = execution.missing_fields || [];
  const blockers = execution.remaining_blockers || [];
  const resolution = execution.resolution_recommendation;
  elements.strategy.innerHTML = `
    <div class="execution-head">
      <div>
        <span class="execution-kicker">Выполнение плана</span>
        <h2>${escapeHtml(title)}</h2>
        <p>${escapeHtml(execution.case_id)} · План v${execution.plan_version}</p>
      </div>
      <span class="execution-state ${execution.execution_status}">
        ${execution.execution_status === "executing" ? `<span class="spinner"></span>` : ""}
        ${escapeHtml(title)}
      </span>
    </div>

    <div class="execution-steps">
      ${execution.steps.map((step) => `
        <article class="execution-step ${step.status} ${["executing", "failed"].includes(step.status) ? "expanded" : ""}">
          <span class="execution-marker">${stepMarker(step)}</span>
          <div class="execution-step-card">
            <div class="execution-step-top">
              <span class="execution-step-title">${escapeHtml(step.title)}</span>
              <span class="execution-step-status">${statusText(step.status)}</span>
            </div>
            <span class="execution-action">${escapeHtml(step.action_label)}</span>
            ${step.result?.summary ? `<p class="execution-result">${escapeHtml(step.result.summary)}</p>` : ""}
            ${step.error_message ? `<p class="execution-error">${escapeHtml(step.error_message)}</p>` : ""}
            ${step.missing_fields?.length ? `<p class="execution-missing">Не хватает данных: ${step.missing_fields.map(escapeHtml).join(", ")}</p>` : ""}
          </div>
        </article>
      `).join("")}
    </div>

    ${terminal ? `
      <section class="execution-summary ${execution.execution_status}">
        <h3>${escapeHtml(title)}</h3>
        ${missing.length ? `<p><strong>Не хватает данных:</strong> ${missing.map(escapeHtml).join(", ")}</p>` : ""}
        ${blockers.length ? `<p><strong>Оставшиеся препятствия:</strong> ${blockers.map(escapeHtml).join(", ")}</p>` : ""}
        ${execution.stop_reason ? `<p>${escapeHtml(execution.stop_reason)}</p>` : ""}
        ${resolution ? `
          <div class="recommendation">
            <span>Рекомендация CasePilot</span>
            <h3>${escapeHtml(resolution.title)}</h3>
            <p>${escapeHtml(resolution.summary)}</p>
            <small>Уверенность: ${escapeHtml(resolution.confidence.level)} · ${Math.round(resolution.confidence.score * 100)}%</small>
          </div>
          <div class="recommendation-details">
            <strong>Действия сотрудника</strong>
            <ul>${resolution.employee_actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
          </div>
          ${(resolution.key_findings.length || resolution.remaining_risks.length) ? `
            <details class="recommendation-more">
              <summary>Основания и ограничения</summary>
              ${resolution.key_findings.length ? `
                <div class="recommendation-details">
                  <strong>Что установлено</strong>
                  <ul>${resolution.key_findings.map((item) => `<li>${escapeHtml(item.finding)}</li>`).join("")}</ul>
                </div>
              ` : ""}
              ${resolution.remaining_risks.length ? `
                <div class="recommendation-details risks">
                  <strong>Риски и ограничения</strong>
                  <ul>${resolution.remaining_risks.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
                </div>
              ` : ""}
            </details>
          ` : ""}
        ` : `
          <div class="recommendation">
            <span>Рекомендация CasePilot</span>
            <p>${escapeHtml(execution.recommendation)}</p>
          </div>
        `}
        ${execution.client_response_draft ? `
          <div class="client-response">
            <span>Ответ клиенту</span>
            <p id="client-response-text">${escapeHtml(execution.client_response_draft)}</p>
            <textarea id="client-response-editor" hidden>${escapeHtml(execution.client_response_draft)}</textarea>
          </div>
        ` : ""}
        ${execution.execution_status === "completed" ? `
          <div class="result-actions">
            <button class="result-button secondary" id="edit-client-response" ${execution.client_response_draft ? "" : "disabled"}>${icons.edit}Редактировать ответ</button>
            <button class="result-button primary" id="close-case">${icons.check}Закрыть кейс</button>
          </div>
        ` : ""}
        ${terminalAction(execution)}
      </section>
    ` : ""}
  `;
  const retry = document.querySelector("#retry-execution");
  if (retry) {
    retry.addEventListener("click", retryExecution);
  }
  const editResponse = document.querySelector("#edit-client-response");
  const closeCase = document.querySelector("#close-case");
  const openManualReview = document.querySelector("#open-manual-review");
  const addCaseInformation = document.querySelector("#add-case-information");
  if (editResponse) {
    editResponse.addEventListener("click", toggleClientResponseEditor);
  }
  if (closeCase) {
    closeCase.addEventListener("click", closeCaseView);
  }
  if (openManualReview) {
    openManualReview.addEventListener("click", openManualReviewView);
  }
  if (addCaseInformation) {
    addCaseInformation.addEventListener("click", addCaseInformationView);
  }
  const active = elements.strategy.querySelector(".execution-step.expanded");
  active?.scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function closeCaseView() {
  collapseCasePilot(
    "Кейс закрыт",
    "Работа по кейсу завершена",
    "closed",
  );
}

async function takeCaseManual() {
  if (!state.analysis) return;
  const buttons = [...elements.strategy.querySelectorAll("[data-decision]")];
  const manual = elements.strategy.querySelector('[data-decision="manual"]');
  buttons.forEach((button) => { button.disabled = true; });
  if (manual) manual.textContent = "Сохраняем решение…";
  if (state.demoMode) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    collapseCasePilot(
      "Самостоятельное решение",
      "Демо: оператор продолжает работу по кейсу самостоятельно",
      "manual",
    );
    return;
  }
  try {
    const response = await fetch(
      `/api/plans/${encodeURIComponent(state.analysis.plan_id)}/manual-review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: state.selectedId,
          plan_version: state.analysis.plan_version,
          comment: "Оператор выбрал самостоятельное решение кейса.",
        }),
      },
    );
    const result = await response.json();
    if (!response.ok || result.status !== "manual_review") {
      throw new Error(result.message || "Решение не удалось сохранить");
    }
    collapseCasePilot(
      "Самостоятельное решение",
      "Оператор продолжает работу по кейсу самостоятельно",
      "manual",
    );
  } catch (error) {
    buttons.forEach((button) => { button.disabled = false; });
    if (manual) manual.innerHTML = `${icons.manual}Повторить`;
  }
}

function openManualReviewView() {
  collapseCasePilot(
    "Требуется ручная проверка",
    "Оператор продолжает решение кейса самостоятельно",
    "manual",
  );
}

function addCaseInformationView() {
  collapseCasePilot(
    "Добавление информации",
    "Оператор добавляет недостающие сведения вручную",
    "information",
  );
}

function collapseCasePilot(title, subtitle, kind) {
  const workspace = document.querySelector(".workspace");
  if (!workspace || elements.content.querySelector(".outcome-banner")) return;
  elements.content.scrollTo({ top: 0, behavior: "smooth" });
  elements.content.insertAdjacentHTML(
    "afterbegin",
    `<div class="outcome-banner ${kind}">${kind === "closed" ? icons.check : icons.manual}<span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(subtitle)}</small></span></div>`,
  );
  requestAnimationFrame(() => workspace.classList.add("case-closed"));
}

function toggleClientResponseEditor() {
  const text = document.querySelector("#client-response-text");
  const editor = document.querySelector("#client-response-editor");
  const button = document.querySelector("#edit-client-response");
  if (!text || !editor || !button) return;
  const editing = !editor.hidden;
  if (editing) {
    text.textContent = editor.value.trim();
    text.hidden = false;
    editor.hidden = true;
    button.innerHTML = `${icons.edit}Редактировать ответ`;
  } else {
    text.hidden = true;
    editor.hidden = false;
    editor.focus();
    button.innerHTML = `${icons.check}Сохранить ответ`;
  }
}

async function approveAndExecute() {
  if (!state.analysis) return;
  const buttons = [...elements.strategy.querySelectorAll("[data-decision]")];
  const approve = elements.strategy.querySelector('[data-decision="approve"]');
  buttons.forEach((button) => { button.disabled = true; });
  approve.textContent = "Подтверждаем план…";
  if (state.demoMode) {
    const demoFlow = selectedDemoFlow();
    if (!demoFlow) return;
    const steps = state.analysis.plan.proposed_plan.map((step) => ({
      step_id: step.step_id,
      order: step.order,
      title: step.description,
      action_label: step.action_type === "expertise" ? "Экспертиза" : "Проверка",
      status: "pending",
    }));
    for (let index = 0; index < steps.length; index += 1) {
      const finalStep = demoFlow.execution.steps[index];
      if (!finalStep || finalStep.status === "pending") break;
      steps[index].status = "executing";
      renderExecution({
        execution_status: "executing",
        status_label: "План выполняется",
        case_id: state.selectedId,
        plan_version: state.analysis.plan_version,
        steps,
      });
      await new Promise((resolve) => setTimeout(resolve, 700));
      steps[index] = { ...finalStep };
      if (finalStep.status === "failed") break;
    }
    renderExecution(structuredClone(demoFlow.execution));
    return;
  }
  try {
    const approvalResponse = await fetch(
      `/api/plans/${encodeURIComponent(state.analysis.plan_id)}/approve`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          case_id: state.selectedId,
          plan_version: state.analysis.plan_version,
        }),
      },
    );
    const approval = await approvalResponse.json();
    if (!approvalResponse.ok || approval.status !== "approved") {
      throw new Error(approval.message || "План не удалось подтвердить");
    }

    renderExecution({
      execution_status: "executing",
      status_label: "План выполняется",
      case_id: state.selectedId,
      plan_version: state.analysis.plan_version,
      steps: state.analysis.plan.proposed_plan.map((step) => ({
        step_id: step.step_id,
        order: step.order,
        title: step.description,
        action_label: step.action_type === "expertise" ? "Экспертиза" : "Проверка",
        status: "pending",
      })),
    });
    await launchExecution();
  } catch (error) {
    buttons.forEach((button) => { button.disabled = false; });
    if (approve) approve.innerHTML = `${icons.check}Повторить`;
  }
}

async function launchExecution() {
  const response = await fetch(
    `/api/plans/${encodeURIComponent(state.analysis.plan_id)}/execute`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_version: state.analysis.plan_version }),
    },
  );
  const execution = await response.json();
  if (!response.ok) {
    throw new Error(execution.message || "Выполнение не удалось запустить");
  }
  renderExecution(execution);
  if (!executionIsTerminal(execution)) {
    await pollExecution(execution.execution_id);
  }
}

async function pollExecution(executionId) {
  const token = ++state.pollingToken;
  while (token === state.pollingToken) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    if (token !== state.pollingToken) return;
    const response = await fetch(`/api/executions/${encodeURIComponent(executionId)}`);
    if (!response.ok) {
      throw new Error("Не удалось обновить состояние выполнения");
    }
    const execution = await response.json();
    renderExecution(execution);
    if (executionIsTerminal(execution)) return;
  }
}

async function retryExecution() {
  if (state.executionRetryUsed) return;
  state.executionRetryUsed = true;
  try {
    await launchExecution();
  } catch {}
}

async function runAnalysis() {
  const button = document.querySelector("#run-analysis");
  button.disabled = true;
  const startedAt = Date.now();
  let elapsed = 0;
  button.textContent = "CasePilot анализирует… 0 с";
  const timer = setInterval(() => {
    elapsed += 1;
    button.textContent = `CasePilot анализирует… ${elapsed} с`;
  }, 1000);
  try {
    if (state.demoMode) {
      const demoFlow = selectedDemoFlow();
      if (!demoFlow) throw new Error("Для кейса не настроен demo flow");
      await new Promise((resolve) => setTimeout(resolve, 1200));
      clearInterval(timer);
      renderStrategy(structuredClone(demoFlow.analysis));
      return;
    }
    const response = await fetch(`/api/cases/${encodeURIComponent(state.selectedId)}/analysis`, { method: "POST" });
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "Не удалось получить стратегию");
    if (result.metadata?.reason === "latest_plan_reused") {
      const targetDelay = 3000 + Math.floor(Math.random() * 2001);
      const remainingDelay = Math.max(0, targetDelay - (Date.now() - startedAt));
      if (remainingDelay) {
        await new Promise((resolve) => setTimeout(resolve, remainingDelay));
      }
    }
    clearInterval(timer);
    if (result.latest_execution) {
      state.analysis = result;
      renderExecution(result.latest_execution);
    } else {
      renderStrategy(result);
    }
  } catch (error) {
    clearInterval(timer);
    button.disabled = false;
    button.textContent = "Повторить";
  }
}

function selectCase(caseId) {
  const item = state.cases.find((candidate) => candidate.case_id === caseId);
  if (!item) return;
  state.selectedId = caseId;
  state.analysis = null;
  state.pollingToken += 1;
  state.executionRetryUsed = false;
  document.querySelector(".workspace")?.classList.remove("case-closed");
  renderQueue();
  renderCase(item);
  renderStrategyStart(item);
  elements.content.scrollTop = 0;
  elements.strategy.scrollTop = 0;
}

async function start() {
  const staticHost = location.hostname.endsWith("github.io") || location.protocol === "file:";
  if (staticHost && state.demoData) {
    state.demoMode = true;
    state.cases = state.demoData.cases;
    renderQueue();
    selectCase(state.cases[0].case_id);
    return;
  }
  try {
    const response = await fetch("/api/cases");
    if (!response.ok) throw new Error();
    state.cases = await response.json();
    renderQueue();
    selectCase(state.cases[3]?.case_id || state.cases[0].case_id);
  } catch {
    if (state.demoData) {
      state.demoMode = true;
      state.cases = state.demoData.cases;
      renderQueue();
      selectCase(state.cases[0].case_id);
      return;
    }
    elements.content.innerHTML = `<div class="loading">Запустите локальный server.py</div>`;
  }
}

start();
