const LIFECYCLE = {
  open: "開啟中",
  closed: "已關閉",
  future: "尚未開始",
};

const ACTIVITY = {
  active: "近期有活動",
  never: "從未使用",
  dormant_zero: "長期未用，目前為零",
  dormant_nonzero: "長期未用，仍有餘額",
  closed: "已關閉",
  future: "尚未開始",
};

const HISTORY = {
  explicit_zero: "明確從零開始",
  opening_pad: "以期初 Pad 匯入",
  late_pad: "帳內期間仍有 Pad",
  equity_seeded: "由 Equity 建立起始值",
  implicit_zero: "從 Open 隱含為零",
  unused: "尚無交易歷史",
  equity_role: "Equity 功能帳戶",
};

const HISTORY_NOTE = {
  explicit_zero: "首筆一般活動前，相關幣別已有零額 Balance assertion。",
  opening_pad: "起點以 Pad 帶入；若要向前追溯，可逐步用更早的真實交易取代。",
  late_pad: "一般活動開始後仍出現 Pad，代表帳內期間可能有缺口，宜優先查看。",
  equity_seeded: "第一筆一般活動直接由 Equity 建立餘額；起點在帳內，但外部歷史未獲證實。",
  implicit_zero: "Beancount 從 Open 隱含以零開始，但沒有外部零額 Balance 證明。",
  unused: "帳戶已 Open，但尚無一般 transaction posting。",
  equity_role: "此帳戶用來承接帳本模型或歷史邊界，不套用一般帳戶的起點判定。",
};

const PAD = {
  none: "沒有 Pad",
  initial_only: "僅期初 Pad",
  multiple_initial: "多筆期初 Pad",
  late: "後期 Pad",
  multiple: "多段 Pad",
};

const EQUITY_ROLE = {
  technical: "技術用途",
  modeled_asset: "合成資產模型",
  opening_history: "期初／歷史來源",
  untraceable: "無法追溯來源",
  dust: "零碎差額",
  revaluation: "重估",
  buffer: "Buffer",
  other: "其他",
};

const REASON = {
  closed_nonzero: "已關閉但仍有原生幣別餘額",
  never_used: "帳戶已開立但從未使用",
  dormant_zero: "長期未用且目前為零，可確認是否應關戶",
  dormant_nonzero: "長期未用但仍有餘額",
  buffer_nonzero: "預期歸零的 Buffer 目前仍有餘額",
  pad_gap: "Pad 不只出現在單一、乾淨的期初位置",
  equity_recent_usage: "歷史／不明來源 Equity 最近仍被使用",
};

const EVENT = {
  open: "Open",
  close: "Close",
  first_activity: "第一筆一般活動",
  last_zero: "最近一次歸零",
  last_activity: "最近一般活動",
};

const ACCOUNT_MAINTENANCE_STATE = new WeakMap();

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined && value !== null) node.textContent = String(value);
  return node;
}

function fallback(value, empty = "—") {
  return value === undefined || value === null || value === "" ? empty : String(value);
}

function accountUrl(account) {
  const prefix = window.location.pathname.split("/extension/")[0];
  return `${prefix}/account/${encodeURIComponent(account)}/`;
}

function addBadge(parent, label, review = false) {
  const badge = element("span", `am-badge${review ? " am-badge-review" : ""}`, label);
  parent.append(badge);
}

function addMetrics(parent, items) {
  const grid = element("div", "am-metrics");
  for (const [label, value] of items) {
    const metric = element("div", "am-metric");
    metric.append(
      element("div", "am-metric-label", label),
      element("div", "am-metric-value", fallback(value)),
    );
    grid.append(metric);
  }
  parent.append(grid);
}

function addSection(parent, title) {
  const section = element("section", "am-detail-section");
  section.append(element("h4", "", title));
  parent.append(section);
  return section;
}

function addKeyValues(parent, items) {
  const list = element("dl", "am-kv");
  for (const [label, value] of items) {
    const item = element("div");
    item.append(element("dt", "", label), element("dd", "", fallback(value)));
    list.append(item);
  }
  parent.append(list);
}

function addTable(parent, headers, rows) {
  const table = element("table", "am-table");
  const thead = element("thead");
  const heading = element("tr");
  for (const header of headers) heading.append(element("th", "", header));
  thead.append(heading);
  table.append(thead);

  const tbody = element("tbody");
  for (const values of rows) {
    const row = element("tr");
    for (const value of values) {
      const cell = element("td");
      if (value && typeof value === "object" && "text" in value) {
        cell.textContent = fallback(value.text);
        if (value.className) cell.className = value.className;
      } else {
        cell.textContent = fallback(value);
      }
      row.append(cell);
    }
    tbody.append(row);
  }
  table.append(tbody);
  parent.append(table);
}

function detailHeader(detail, title, subtitle, account) {
  const header = element("div", "am-detail-header");
  const heading = element("div");
  heading.append(element("h3", "", title));
  if (subtitle) heading.append(element("p", "am-detail-subtitle", subtitle));
  header.append(heading);
  if (account) {
    const link = element("a", "am-detail-link", "開啟帳戶頁");
    link.href = accountUrl(account);
    header.append(link);
  }
  detail.append(header);
}

function daysText(date, days) {
  if (!date) return "—";
  if (days === null || days === undefined) return date;
  return `${date} · ${days} 天前`;
}

function renderGroup(detail, row) {
  detailHeader(detail, row.path, "帳戶群組");
  const counts = row.counts;
  addMetrics(detail, [
    ["帳戶", counts.total],
    ["開啟中", counts.open],
    ["需要查看", counts.needs_review],
    ["可向前追溯", counts.backfill],
  ]);

  const state = addSection(detail, "群組狀態");
  addKeyValues(state, [
    ["已關閉", counts.closed],
    ["尚未開始", counts.future],
    ["目前非零", counts.nonzero],
    ["目前為零", counts.zero],
  ]);

  const reasons = Object.entries(row.reason_counts || {});
  if (reasons.length) {
    const section = addSection(detail, "需要查看的原因");
    const list = element("ul", "am-list");
    for (const [reason, count] of reasons) {
      list.append(element("li", "", `${REASON[reason] || reason} · ${count}`));
    }
    section.append(list);
  }

  if (row.direct_account) {
    const section = addSection(detail, "同名直接帳戶");
    const link = element("a", "", row.direct_account);
    link.href = accountUrl(row.direct_account);
    section.append(link);
  }
}

function renderAccount(detail, row) {
  const subtitle = [row.nickname, row.purpose].filter(Boolean).join(" · ");
  detailHeader(detail, row.account, subtitle, row.account);

  const badges = element("div", "am-badges");
  addBadge(badges, LIFECYCLE[row.lifecycle] || row.lifecycle);
  if (row.backfill_candidate) addBadge(badges, "可向前追溯");
  for (const reason of row.reasons) addBadge(badges, REASON[reason] || reason, true);
  detail.append(badges);

  addMetrics(detail, [
    ["目前原生餘額", row.inventory_text],
    ["活動狀態", ACTIVITY[row.activity_status] || row.activity_status],
    ["最近活動", daysText(row.last_activity, row.days_inactive)],
  ]);

  const state = addSection(detail, "帳戶狀態");
  addKeyValues(state, [
    ["類型", row.kind],
    ["Open", row.open_date],
    ["Close", row.close_date],
    ["一般 postings", row.activity_count],
    ["第一筆活動", row.first_activity],
    ["閒置天數", row.days_inactive],
  ]);

  const history = addSection(detail, "歷史起點與 Pad");
  addKeyValues(history, [
    ["歷史邊界", HISTORY[row.history_boundary] || row.history_boundary],
    ["Pad 狀態", PAD[row.pad_status] || row.pad_status],
    ["起始 Equity", row.equity_counterparts.join(" · ") || null],
    ["Equity 功能", row.equity_role ? EQUITY_ROLE[row.equity_role] || row.equity_role : null],
  ]);
  history.append(element("p", "am-detail-subtitle", HISTORY_NOTE[row.history_boundary] || ""));
  if (row.pads.length) {
    addTable(
      history,
      ["Pad 日期", "來源帳戶"],
      row.pads.map((pad) => [pad.date, pad.source_account]),
    );
  }

  if (row.is_buffer) {
    const buffer = addSection(detail, "Buffer 狀況");
    addKeyValues(buffer, [
      ["目前餘額", row.inventory_text],
      ["最近歸零", row.last_zero_date],
      ["本段非零自", row.nonzero_since],
      ["最近對手帳戶", row.recent_counterparts.join(" · ") || null],
    ]);
  }

  if (row.price_units.length) {
    const prices = addSection(detail, "投資標的價格");
    addTable(
      prices,
      ["Commodity", "最近 Price", "日數", "價格"],
      row.price_units.map((price) => [
        price.currency,
        price.date,
        price.days_since,
        price.number && price.quote ? `${price.number} ${price.quote}` : null,
      ]),
    );
  }

  const timelineEvents = [];
  for (const item of row.lifecycle_timeline) {
    timelineEvents.push({ date: item.date, event: EVENT[item.event] || item.event });
  }
  if (row.lifecycle === "future" && row.open_date) {
    timelineEvents.push({ date: row.open_date, event: "預定 Open" });
  }
  for (const [date, event] of [
    [row.first_activity, EVENT.first_activity],
    [row.last_zero_date, EVENT.last_zero],
    [row.last_activity, EVENT.last_activity],
  ]) {
    if (date) timelineEvents.push({ date, event });
  }
  timelineEvents.sort((left, right) => left.date.localeCompare(right.date));
  if (timelineEvents.length) {
    const timeline = addSection(detail, "時間線");
    const list = element("ol", "am-timeline");
    const seen = new Set();
    for (const item of timelineEvents) {
      const key = `${item.date}:${item.event}`;
      if (seen.has(key)) continue;
      seen.add(key);
      list.append(element("li", "", `${item.date} · ${item.event}`));
    }
    timeline.append(list);
  }

  const source = addSection(detail, "帳本來源");
  addKeyValues(source, [
    ["檔案", row.source_file],
    ["行號", row.source_line],
    ["Purpose", row.purpose],
    ["Nickname", row.nickname],
  ]);
}

function initAccountMaintenance(
  root = document.querySelector("[data-account-maintenance]"),
) {
  if (!root) return null;
  const existing = ACCOUNT_MAINTENANCE_STATE.get(root);
  if (existing) return existing;

  const dataElement = root.querySelector("#account-maintenance-data");
  const detail = root.querySelector("#account-maintenance-detail");
  if (!dataElement || !detail) return;

  let data;
  try {
    data = JSON.parse(dataElement.textContent);
  } catch (error) {
    detail.replaceChildren(element("p", "am-detail-placeholder", "無法讀取帳戶資料。"));
    return null;
  }

  root.dataset.initialized = "true";
  root.addEventListener("click", handleAccountMaintenanceClick);
  const controls = new Map();
  for (const control of root.querySelectorAll("[data-am-key]")) {
    controls.set(control.dataset.amKey, control);
  }

  let selectedKey = null;
  function select(key) {
    const row = data.node_data[key];
    const control = controls.get(key);
    if (!row || !control) return;
    for (const candidate of controls.values()) candidate.classList.remove("is-selected");
    control.classList.add("is-selected");
    selectedKey = key;
    detail.replaceChildren();
    if (row.type === "group") renderGroup(detail, row);
    else renderAccount(detail, row);
  }

  function isVisible(control) {
    return control && !control.closest("li[hidden]");
  }

  function firstVisibleControl() {
    const candidates = [
      ...root.querySelectorAll(".am-leaf > [data-am-key]"),
      ...root.querySelectorAll("summary[data-am-key]"),
    ];
    return candidates.find(isVisible) || null;
  }

  function applyFilter(mode) {
    for (const button of root.querySelectorAll("[data-am-filter]")) {
      button.setAttribute("aria-pressed", String(button.dataset.amFilter === mode));
    }

    for (const node of root.querySelectorAll("[data-am-node]")) {
      node.hidden = !node.dataset.amModes.split(/\s+/).includes(mode);
    }

    const empty = root.querySelector("[data-am-empty]");
    const hasVisible = [...root.querySelectorAll(".am-tree > [data-am-node]")].some(
      (node) => !node.hidden,
    );
    if (empty) empty.hidden = hasVisible;

    if (!isVisible(controls.get(selectedKey))) {
      const first = firstVisibleControl();
      if (first) select(first.dataset.amKey);
      else {
        selectedKey = null;
        detail.replaceChildren(element("p", "am-detail-placeholder", "這個篩選下沒有帳戶。"));
      }
    }
  }

  const state = {applyFilter, select};
  ACCOUNT_MAINTENANCE_STATE.set(root, state);

  if (data.default_key && controls.has(data.default_key)) select(data.default_key);
  else {
    const first = firstVisibleControl();
    if (first) select(first.dataset.amKey);
  }
  state.applyFilter(root.dataset.amDefaultView || "all");
  return state;
}

function handleAccountMaintenanceClick(event) {
  const target = event.target instanceof Element ? event.target : null;
  const root = target?.closest("[data-account-maintenance]");
  if (!root) return;

  const state = initAccountMaintenance(root);
  if (!state) return;

  const filter = target.closest("[data-am-filter]");
  if (filter && root.contains(filter)) {
    if (event.currentTarget !== document) event.stopPropagation();
    state.applyFilter(filter.dataset.amFilter || "all");
    return;
  }

  const control = target.closest("[data-am-key]");
  if (control && root.contains(control)) {
    if (event.currentTarget !== document) event.stopPropagation();
    state.select(control.dataset.amKey);
  }
}

export default {
  init() {
    document.addEventListener("click", handleAccountMaintenanceClick);
  },
  onExtensionPageLoad() {
    initAccountMaintenance();
  },
};
