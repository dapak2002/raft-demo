const traceEl = document.getElementById("trace");
const traceStatusEl = document.getElementById("trace-status");
const errorPanel = document.getElementById("error-panel");
const errorTitle = document.getElementById("error-title");
const errorText = document.getElementById("error-text");
const ordersBody = document.getElementById("orders-body");
const statusBadge = document.getElementById("status-badge");
const rawJson = document.getElementById("raw-json");
const queryInput = document.getElementById("query");
const submitBtn = document.getElementById("submit");

const NODE_LABELS = {
  fetch: "Fetch orders",
  parse_record: "Parse records",
  merge_parse: "Merge parsed data",
  plan: "Build filter plan",
  review_plan: "Review plan",
  validate_plan: "Validate plan",
  execute: "Apply filters",
  respond: "Complete",
};

let lastNode = null;
let parseGroupEl = null;
let parseGroupCount = 0;
let parseGroupCompleted = 0;
let parseGroupStep = null;

function setBadge(status) {
  statusBadge.className = `badge badge-${status}`;
  statusBadge.textContent = status;
}

function resetUi() {
  lastNode = null;
  parseGroupEl = null;
  parseGroupCount = 0;
  parseGroupCompleted = 0;
  parseGroupStep = null;
  traceEl.innerHTML = "";
  traceStatusEl.textContent = "Running…";
  errorPanel.classList.add("hidden");
  errorTitle.textContent = "Couldn't complete your query";
  errorText.textContent = "";
  ordersBody.innerHTML =
    '<tr class="empty-row"><td colspan="6">Running query…</td></tr>';
  rawJson.textContent = "{}";
  setBadge("running");
}

function finalizeCurrentSteps() {
  traceEl.querySelectorAll(".trace-step.current").forEach((item) => {
    item.classList.remove("current");
    item.classList.add("done");
  });
}

function formatNodeLabel(node, visit, patch = {}) {
  const base = patch.label || NODE_LABELS[node] || node.replaceAll("_", " ");
  if (visit > 1) {
    return `${base} (#${visit})`;
  }
  return base;
}

function formatStepIndex(step) {
  return step == null ? "…" : String(step);
}

function buildStepDetails(patch) {
  const details = [];
  if (patch.error) {
    return "";
  }
  if (patch.raw_count != null) details.push(`${patch.raw_count} raw`);
  if (patch.parsed_count != null) {
    const label =
      patch.node === "merge_parse"
        ? `${patch.parsed_count} orders merged`
        : `${patch.parsed_count} parsed`;
    details.push(label);
  }
  if (patch.order_count != null) details.push(`${patch.order_count} matched`);
  if (patch.plan_attempts != null) {
    details.push(`review attempt ${patch.plan_attempts}`);
  }
  if (patch.plan_feedback) {
    details.push(patch.plan_feedback);
  }
  return details.join(" · ");
}

function describeError(raw) {
  const message = raw || "Something went wrong. Try again.";
  const lower = message.toLowerCase();

  if (
    lower.includes("order data service") ||
    lower.includes("failed to reach")
  ) {
    return {
      title: "Order data service unavailable",
      body: message,
    };
  }

  return {
    title: "Couldn't complete your query",
    body: message,
  };
}

function showError(raw) {
  const info = describeError(raw);
  errorTitle.textContent = info.title;
  errorText.textContent = info.body;
  errorPanel.classList.remove("hidden");
}

function createTraceStepElement(patch = {}) {
  const li = document.createElement("li");
  li.className = "trace-step current";
  if (patch.status === "error" || patch.error) {
    li.classList.add("trace-error");
  }
  li.innerHTML = `
    <span class="trace-index"></span>
    <div class="trace-body">
      <div class="trace-title-row">
        <span class="trace-node"></span>
      </div>
      <div class="trace-detail"></div>
    </div>
  `;
  return li;
}

function findStep(node, visit) {
  return traceEl.querySelector(
    `.trace-step[data-node="${node}"][data-visit="${visit || 1}"]`,
  );
}

function setStepMeta(li, patch) {
  li.dataset.node = patch.node;
  li.dataset.visit = String(patch.visit || 1);
}

function renderParseGroup({ running = false } = {}) {
  if (!parseGroupEl) return;

  const label = `Parse records ×${parseGroupCount}`;
  const recordLabel = parseGroupCount === 1 ? "record" : "records";

  parseGroupEl.querySelector(".trace-index").textContent = formatStepIndex(
    parseGroupStep,
  );
  parseGroupEl.querySelector(".trace-node").textContent = label;

  let detailText;
  if (running && parseGroupCompleted < parseGroupCount) {
    detailText = `${parseGroupCompleted}/${parseGroupCount} ${recordLabel} parsed`;
  } else {
    detailText = `${parseGroupCount} ${recordLabel} parsed in parallel`;
  }

  const detailEl = parseGroupEl.querySelector(".trace-detail");
  if (detailEl) {
    detailEl.textContent = detailText;
  }

  parseGroupEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
  traceStatusEl.textContent = running
    ? `Running: ${label}`
    : `Last completed: ${label}`;
  lastNode = "parse_record";
}

function beginParseRecord(patch) {
  if (!parseGroupEl) {
    finalizeCurrentSteps();
    parseGroupEl = createTraceStepElement(patch);
    parseGroupEl.classList.add("trace-group");
    setStepMeta(parseGroupEl, { node: "parse_record", visit: 1 });
    parseGroupStep = patch.step ?? 2;
    parseGroupCount = 0;
    parseGroupCompleted = 0;
    traceEl.appendChild(parseGroupEl);
  }

  parseGroupCount += 1;
  renderParseGroup({ running: true });
}

function completeParseRecord(patch) {
  if (!parseGroupEl) {
    beginParseRecord(patch);
  }

  parseGroupCompleted += 1;

  if (patch.error) {
    parseGroupEl.classList.add("trace-error");
  }

  if (parseGroupCompleted >= parseGroupCount) {
    parseGroupEl.classList.remove("current");
    parseGroupEl.classList.add("done");
    renderParseGroup({ running: false });
    parseGroupEl = null;
    parseGroupCount = 0;
    parseGroupCompleted = 0;
    parseGroupStep = null;
    return;
  }

  renderParseGroup({ running: true });
}

function beginStep(patch) {
  if (patch.node === "parse_record") {
    beginParseRecord(patch);
    return;
  }

  parseGroupEl = null;
  parseGroupCount = 0;
  parseGroupCompleted = 0;
  parseGroupStep = null;

  finalizeCurrentSteps();

  const node = patch.node;
  const visit = patch.visit || 1;
  const isRevisit = visit > 1;

  const li = createTraceStepElement(patch);
  setStepMeta(li, patch);
  const label = formatNodeLabel(node, visit, patch);
  const tags = isRevisit ? ['<span class="trace-tag">revisit</span>'] : [];

  li.querySelector(".trace-index").textContent = formatStepIndex(patch.step);
  li.querySelector(".trace-node").textContent = label;
  li.querySelector(".trace-title-row").insertAdjacentHTML(
    "beforeend",
    tags.join(""),
  );
  li.querySelector(".trace-detail").textContent = "Running…";

  traceEl.appendChild(li);
  li.scrollIntoView({ block: "nearest", behavior: "smooth" });

  lastNode = node;
  traceStatusEl.textContent = `Running: ${label}`;
}

function completeStep(patch) {
  if (patch.node === "parse_record") {
    completeParseRecord(patch);
    return;
  }

  parseGroupEl = null;
  parseGroupCount = 0;
  parseGroupCompleted = 0;
  parseGroupStep = null;

  const node = patch.node;
  const visit = patch.visit || 1;
  const isRevisit = visit > 1;
  const isErrorStep = patch.status === "error" || Boolean(patch.error);
  const label = formatNodeLabel(node, visit, patch);
  const detailText = buildStepDetails(patch);

  let li = findStep(node, visit);
  if (!li) {
    beginStep(patch);
    li = findStep(node, visit);
  }

  li.classList.remove("current");
  li.classList.add("done");
  if (isErrorStep) {
    li.classList.add("trace-error");
  }

  li.querySelector(".trace-index").textContent = formatStepIndex(patch.step);
  li.querySelector(".trace-node").textContent = label;

  const titleRow = li.querySelector(".trace-title-row");
  titleRow.querySelectorAll(".trace-tag").forEach((tag) => tag.remove());
  const tags = isRevisit ? ['<span class="trace-tag">revisit</span>'] : [];
  if (isErrorStep) {
    tags.push('<span class="trace-tag trace-tag-error">stopped</span>');
  }
  titleRow.insertAdjacentHTML("beforeend", tags.join(""));

  const detailEl = li.querySelector(".trace-detail");
  if (detailText) {
    if (detailEl) {
      detailEl.textContent = detailText;
    } else {
      li.querySelector(".trace-body").insertAdjacentHTML(
        "beforeend",
        `<div class="trace-detail">${escapeHtml(detailText)}</div>`,
      );
    }
  } else if (detailEl) {
    detailEl.remove();
  }

  li.scrollIntoView({ block: "nearest", behavior: "smooth" });

  lastNode = node;
  traceStatusEl.textContent = isErrorStep
    ? `Stopped at ${label}`
    : `Last completed: ${label}`;
}

function renderOrders(orders, { failed = false } = {}) {
  ordersBody.innerHTML = "";
  if (failed) {
    ordersBody.innerHTML =
      '<tr class="empty-row"><td colspan="6">Orders could not be loaded.</td></tr>';
    return;
  }
  if (!orders || orders.length === 0) {
    ordersBody.innerHTML =
      '<tr class="empty-row"><td colspan="6">No matching orders.</td></tr>';
    return;
  }

  for (const order of orders) {
    const row = document.createElement("tr");
    const items = Array.isArray(order.items) ? order.items.join(", ") : "";
    row.innerHTML = `
      <td>${escapeHtml(order.orderId ?? "")}</td>
      <td>${escapeHtml(order.buyer ?? "")}</td>
      <td>${escapeHtml(order.city ?? "")}</td>
      <td>${escapeHtml(order.state ?? "")}</td>
      <td>${formatTotal(order.total)}</td>
      <td>${escapeHtml(items)}</td>
    `;
    ordersBody.appendChild(row);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function formatTotal(value) {
  if (value == null || value === "") return "";
  const num = Number(value);
  return Number.isFinite(num) ? `$${num.toFixed(2)}` : escapeHtml(value);
}

function finish(result) {
  rawJson.textContent = JSON.stringify(result, null, 2);
  finalizeCurrentSteps();

  if (result.status === "error") {
    setBadge("error");
    showError(result.error);
    renderOrders([], { failed: true });
    traceStatusEl.textContent =
      traceEl.children.length > 0
        ? "Query stopped before completion"
        : "Query couldn't be started";
    return;
  }

  renderOrders(result.orders || []);
  setBadge("ok");
  traceStatusEl.textContent = `Finished — ${traceEl.children.length} step(s)`;
}

async function runQuery() {
  const query = queryInput.value.trim();
  if (!query) return;

  submitBtn.disabled = true;
  resetUi();

  try {
    const response = await fetch("/api/query/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || "Request failed");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() || "";

      for (const chunk of chunks) {
        const line = chunk.split("\n").find((row) => row.startsWith("data: "));
        if (!line) continue;
        const payload = JSON.parse(line.slice(6));

        if (payload.event === "node_start") {
          beginStep(payload);
        } else if (payload.event === "node") {
          completeStep(payload);
        } else if (payload.event === "error") {
          showError(payload.message || "Stream error");
        } else if (payload.event === "done") {
          finish(payload.result || {});
        }
      }
    }
  } catch (err) {
    setBadge("error");
    showError(err.message || String(err));
    ordersBody.innerHTML =
      '<tr class="empty-row"><td colspan="6">Orders could not be loaded.</td></tr>';
    traceStatusEl.textContent = "Query couldn't be completed";
  } finally {
    submitBtn.disabled = false;
  }
}

function resizeQueryInput() {
  queryInput.style.height = "auto";
  const maxHeight = parseFloat(getComputedStyle(queryInput).maxHeight);
  const scrollHeight = queryInput.scrollHeight;
  const nextHeight = Number.isFinite(maxHeight)
    ? Math.min(scrollHeight, maxHeight)
    : scrollHeight;
  queryInput.style.height = `${nextHeight}px`;
  queryInput.style.overflowY = scrollHeight > nextHeight ? "auto" : "hidden";
}

submitBtn.addEventListener("click", runQuery);
queryInput.addEventListener("input", resizeQueryInput);
queryInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    runQuery();
  }
});
resizeQueryInput();
