/* Trace Explorer runs entirely in the browser. Files are never uploaded. */

const state = { runs: [], selectedRun: null, selectedTask: null, filter: "all", attemptFilter: "all", search: "" };
const $ = (selector) => document.querySelector(selector);

const descriptions = {
  workflow: "Fixed workflow: proposal, full test verification, and retry when needed.",
  single_agent: "Autonomous agent: model decisions interleaved with tool calls and submissions.",
  mas_sequential: "Sequential MAS: researcher, fixer, and checker hand work between roles.",
};

function text(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function parseLines(raw, sourceName) {
  const events = [];
  const bad = [];
  raw.split(/\r?\n/).forEach((line, index) => {
    if (!line.trim()) return;
    try { events.push({ ...JSON.parse(line), _line: index + 1 }); }
    catch { bad.push(index + 1); }
  });
  if (!events.length) return null;
  const runId = events.find((event) => event.run_id)?.run_id || sourceName;
  const solver = events.find((event) => event.solver)?.solver || "unknown";
  const tasks = new Map();
  events.forEach((event, originalIndex) => {
    const taskId = event.task_id || "unassigned";
    if (!tasks.has(taskId)) tasks.set(taskId, []);
    tasks.get(taskId).push({ ...event, _index: originalIndex });
  });
  const taskRows = [...tasks.entries()].map(([id, taskEvents]) => makeTask(id, taskEvents));
  taskRows.sort((a, b) => a.id.localeCompare(b.id));
  return { id: runId, solver, sourceName, events, tasks: taskRows, invalidLines: bad };
}

function makeTask(id, events) {
  let phase = 1;
  const outcomes = new Map();
  events.forEach((event) => {
    event._attemptPhase = phase;
    if (event.event === "attempt") {
      outcomes.set(phase, Boolean(event.result?.passed_all));
      phase += 1;
    }
  });
  const end = [...events].reverse().find((event) => event.event === "task_end");
  const attempts = events.filter((event) => event.event === "attempt");
  const accepted = attempts.filter((event) => event.result?.passed_all).length;
  const resultStatus = end?.result?.status;
  const solved = resultStatus === "solved" || accepted > 0;
  const status = solved ? "solved" : (resultStatus || "incomplete");
  const calls = events.filter((event) => event.event === "llm_call").length;
  const toolCalls = events.filter((event) => event.event === "tool_call").length;
  const usage = end?.usage || sumUsage(events);
  return { id, events, attempts, accepted, status, solved, calls, toolCalls, usage, outcomes };
}

function sumUsage(events) {
  return events.filter((event) => event.event === "llm_call").reduce((acc, event) => {
    const usage = event.usage || {};
    acc.input += Number(usage.input || 0); acc.output += Number(usage.output || 0);
    acc.reasoning += Number(usage.reasoning || 0); return acc;
  }, { input: 0, output: 0, reasoning: 0 });
}

function runStats(run) {
  const solved = run.tasks.filter((task) => task.solved).length;
  const totalCalls = run.tasks.reduce((sum, task) => sum + task.calls, 0);
  const totalTools = run.tasks.reduce((sum, task) => sum + task.toolCalls, 0);
  return { solved, total: run.tasks.length, totalCalls, totalTools };
}

function formatNumber(value) { return new Intl.NumberFormat().format(Number(value || 0)); }
function truncate(value, limit = 4800) {
  const valueText = text(value, "");
  return valueText.length > limit ? `${valueText.slice(0, limit)}\n\n… truncated in viewer (${formatNumber(valueText.length)} characters total)` : valueText;
}
function pretty(value) { return truncate(typeof value === "string" ? value : JSON.stringify(value, null, 2)); }
function shortPath(file) { return file.webkitRelativePath || file.name; }

function eventKind(event) {
  if (event.event === "llm_call") return "model";
  if (event.event === "attempt") return event.result?.passed_all ? "success" : "warning";
  if (event.event === "reminder") return "warning";
  if (event.event === "crash" || event.result?.error || event.result?.timed_out || event.result?.error) return "error";
  if (event.event === "task_end") return event.result?.status === "solved" ? "success" : "warning";
  if (event.event === "tool_call") {
    if (["trace", "get_test", "run_program"].includes(event.tool)) return "inspect";
    if (["run_tests"].includes(event.tool)) return "execute";
    if (event.tool === "submit") return event.result?.accepted ? "success" : "warning";
    return "execute";
  }
  return "slate";
}

function eventTitle(event) {
  if (event.event === "llm_call") return `${roleName(event.agent)} model response`;
  if (event.event === "tool_call") return `${event.tool || "tool"} call`;
  if (event.event === "attempt") return `Submission attempt ${event.result?.index ?? ""}`.trim();
  if (event.event === "task_start") return "Task started";
  if (event.event === "task_end") return "Task finished";
  return String(event.event || "Event").replaceAll("_", " ");
}

function roleName(role) {
  return ({ researcher: "Researcher", fixer: "Fixer", checker: "Checker", single_agent: "Agent", workflow: "Workflow" })[role] || text(role, "System");
}

function eventSummary(event) {
  if (event.event === "llm_call") {
    const content = event.result?.content;
    const calls = event.result?.tool_calls || [];
    if (content) return shortModelText(content);
    return calls.length ? `Requests ${calls.map((call) => call.name).join(", ")}.` : "No text response.";
  }
  if (event.event === "tool_call") {
    if (event.result?.error) return event.result.error;
    if (event.tool === "submit") return event.result?.accepted ? "Accepted: all tests passed." : `Rejected: ${summaryText(event.result?.summary)}.`;
    if (event.tool === "run_tests") return event.result?.passed_all ? "All selected tests passed." : `Test result: ${summaryText(event.result?.summary)}.`;
    if (event.tool === "trace") return `${event.result?.n_hits ?? 0} trace hits${event.result?.timed_out ? "; timed out" : ""}.`;
    if (event.tool === "get_test") return `Opened test ${text(event.result?.name)}.`;
    if (event.tool === "run_program") return event.result?.timed_out ? "Program timed out." : `Program exited with code ${text(event.result?.exit_code)}.`;
  }
  if (event.event === "attempt") return event.result?.passed_all ? "Candidate passed every test." : text(event.result?.summary, "Candidate did not pass all tests.");
  if (event.event === "task_end") return `Status: ${text(event.result?.status)}.`;
  return text(event.result?.error || event.error, "Lifecycle event.");
}

function shortModelText(content) {
  const beforeCode = String(content).split(/```/)[0].trim();
  if (beforeCode) return truncate(beforeCode, 280);
  return "Proposed a code change or response.";
}

function summaryText(summary) {
  if (!summary || typeof summary !== "object") return "no result summary";
  return Object.entries(summary).map(([name, count]) => `${count} ${name}`).join(", ");
}

function eventDetails(event) {
  const wrapper = document.createElement("div");
  if (event.event === "llm_call") {
    wrapper.append(details("Show response payload", pretty(event.result || {})));
    const messages = event.args?.messages;
    if (messages) wrapper.append(details(`Show prompt context (${messages.length} messages)`, pretty(messages)));
  } else {
    if (event.args !== undefined) wrapper.append(details("Show arguments", pretty(event.args)));
    if (event.result !== undefined) wrapper.append(details("Show result", pretty(event.result)));
  }
  wrapper.append(details("Show raw event", pretty(stripInternal(event))));
  return wrapper;
}

function stripInternal(event) { const { _index, _line, ...raw } = event; return raw; }
function details(label, payload) { const node = document.createElement("details"); const summary = document.createElement("summary"); summary.textContent = label; const pre = document.createElement("pre"); pre.textContent = payload; node.append(summary, pre); return node; }

function renderRuns() {
  const list = $("#run-list"); list.replaceChildren(); $("#run-count").textContent = state.runs.length;
  state.runs.forEach((run) => {
    const stats = runStats(run); const button = document.createElement("button");
    button.className = `run-button ${state.selectedRun === run ? "selected" : ""}`;
    button.type = "button"; button.innerHTML = `<span class="run-name">${escapeHtml(run.id)}</span><span class="run-stats">${escapeHtml(run.solver)} · ${stats.solved}/${stats.total} solved</span>`;
    button.addEventListener("click", () => selectRun(run)); list.append(button);
  });
}

function selectRun(run) {
  state.selectedRun = run; state.selectedTask = run.tasks[0] || null; state.filter = "all"; state.attemptFilter = "all"; state.search = "";
  $("#task-search").value = ""; document.querySelectorAll(".filter").forEach((button) => button.classList.toggle("active", button.dataset.filter === "all"));
  document.querySelectorAll(".attempt-filter").forEach((button) => button.classList.toggle("active", button.dataset.attemptFilter === "all"));
  renderRuns(); renderViewer();
}

function renderViewer() {
  const run = state.selectedRun; if (!run) return;
  $("#empty-state").hidden = true; $("#viewer").hidden = false;
  const stats = runStats(run); $("#selected-title").textContent = run.id;
  $("#method-description").textContent = descriptions[run.solver] || `Trace format for solver “${run.solver}”.`;
  $("#run-summary").textContent = `${run.sourceName} · ${run.solver}`;
  $("#run-metrics").innerHTML = metric(stats.total, "tasks") + metric(stats.solved, "solved") + metric(stats.totalCalls, "model calls") + metric(stats.totalTools, "tool calls");
  renderTasks();
}

function metric(value, label) { return `<div class="metric"><b>${formatNumber(value)}</b><span>${label}</span></div>`; }
function matchesFilter(task) { return (state.filter === "all" || (state.filter === "solved" ? task.solved : !task.solved)) && task.id.toLowerCase().includes(state.search); }

function renderTasks() {
  const list = $("#task-list"); list.replaceChildren(); const tasks = state.selectedRun.tasks.filter(matchesFilter);
  if (!tasks.includes(state.selectedTask)) state.selectedTask = tasks[0] || null;
  if (!tasks.length) list.innerHTML = `<p class="empty-lane">No matching tasks.</p>`;
  tasks.forEach((task) => {
    const button = document.createElement("button"); button.type = "button";
    button.className = `task-button ${task.solved ? "solved" : "failed"} ${state.selectedTask === task ? "selected" : ""}`;
    button.innerHTML = `<strong>${escapeHtml(task.id)}</strong><small>${task.solved ? "Solved" : escapeHtml(task.status)} · ${task.attempts.length} attempt${task.attempts.length === 1 ? "" : "s"}</small>`;
    button.addEventListener("click", () => { state.selectedTask = task; renderTasks(); }); list.append(button);
  });
  renderTaskDetail();
}

function renderTaskDetail() {
  const root = $("#task-detail"); const task = state.selectedTask; if (!task) { root.innerHTML = `<p class="empty-lane">Choose a task to inspect its trace.</p>`; return; }
  root.replaceChildren(); root.classList.toggle("task-solved", task.solved); root.classList.toggle("task-failed", !task.solved); const head = document.createElement("header"); head.className = "task-heading";
  head.innerHTML = `<div class="sidebar-heading"><div><p class="eyebrow">Task trace</p><h3>${escapeHtml(task.id)}</h3></div><span class="status ${task.solved ? "solved" : "failed"}">${task.solved ? "Solved" : escapeHtml(task.status)}</span></div><p class="task-details">${task.calls} model call${task.calls === 1 ? "" : "s"} · ${task.toolCalls} tool call${task.toolCalls === 1 ? "" : "s"} · ${task.attempts.length} submission attempt${task.attempts.length === 1 ? "" : "s"} · ${formatNumber(task.usage.input)} input / ${formatNumber(task.usage.output)} output tokens</p>`;
  root.append(head);
  if (state.selectedRun.solver === "mas_sequential") root.append(renderMas(task)); else root.append(renderTimeline(task));
}

function renderTimeline(task) {
  const flow = document.createElement("div"); flow.className = "flow";
  const turns = makeTurns(visibleEvents(task));
  if (!turns.length) flow.innerHTML = `<p class="empty-lane">No events match this attempt filter.</p>`;
  turns.forEach((turn, index) => flow.append(turnCard(turn, index + 1))); return flow;
}

function renderMas(task) {
  const flow = document.createElement("div"); flow.className = "mas-feed";
  const blocks = makeMasBlocks(visibleEvents(task));
  if (!blocks.length) flow.innerHTML = `<p class="empty-lane">No events match this attempt filter.</p>`;
  blocks.forEach((block, blockIndex) => {
    const section = document.createElement("section"); section.className = `role-section role-${block.role}`;
    section.innerHTML = `<header class="role-header"><span>${roleName(block.role)}</span><small>${rolePipelineLabel(block.role)}</small></header>`;
    const turns = makeTurns(block.events); const list = document.createElement("div"); list.className = "role-events";
    turns.forEach((turn, index) => list.append(turnCard(turn, index + 1, true)));
    section.append(list); flow.append(section);
    if (blockIndex < blocks.length - 1) flow.append(handoff(block, blocks[blockIndex + 1]));
  });
  return flow;
}

function visibleEvents(task) {
  if (state.attemptFilter === "all") return task.events;
  const expected = state.attemptFilter === "successful";
  return task.events.filter((event) => task.outcomes.get(event._attemptPhase) === expected);
}

function narrativeEvents(events) {
  return events.filter((event) => !["task_start", "task_end"].includes(event.event));
}

function makeTurns(events) {
  const turns = [];
  let current = null;
  narrativeEvents(events).forEach((event) => {
    if (event.event === "llm_call") {
      current = { lead: event, events: [event] };
      turns.push(current);
    } else if (current) {
      current.events.push(event);
    } else {
      current = { lead: null, events: [event] };
      turns.push(current);
    }
  });
  return turns;
}

function makeMasBlocks(events) {
  const blocks = [];
  narrativeEvents(events).forEach((event) => {
    const role = ["researcher", "fixer", "checker"].includes(event.agent) ? event.agent : "checker";
    const previous = blocks.at(-1);
    if (!previous || previous.role !== role) blocks.push({ role, events: [event] });
    else previous.events.push(event);
  });
  return blocks;
}

function turnCard(turn, index, inRoleFeed = false) {
  const card = document.createElement("section");
  const lead = turn.lead;
  const attempt = turn.events.find((event) => event.event === "attempt");
  const kind = attempt ? (attempt.result?.passed_all ? "success" : "warning") : (lead ? "model" : eventKind(turn.events[0]));
  const title = inRoleFeed ? (lead ? "Model message" : "Verification") : (lead ? `${roleName(lead.agent)} decision` : "Verification result");
  const summary = lead ? eventSummary(lead) : eventSummary(turn.events[0]);
  card.className = `phase-card kind-${kind} ${inRoleFeed ? "in-role-feed" : ""}`;
  card.innerHTML = `<header class="phase-header"><span class="phase-number">${index}</span><div><p class="phase-kicker">${title}</p><h4>${escapeHtml(summary)}</h4></div></header>`;
  card.append(compactDetails(turn.events, "Inspect this decision"));
  return card;
}

function handoff(from, to) {
  const node = document.createElement("p"); node.className = "flow-arrow";
  const labels = { "researcher-fixer": "Diagnosis handed to Fixer", "fixer-checker": "Candidate sent to Checker", "checker-researcher": "Checker feedback returned to Researcher" };
  node.textContent = labels[`${from.role}-${to.role}`] || `${roleName(from.role)} → ${roleName(to.role)}`;
  return node;
}

function rolePipelineLabel(role) {
  return ({ researcher: "Investigate", fixer: "Propose patch", checker: "Verify" })[role] || "Process";
}

function compactDetails(events, label) {
  const node = document.createElement("details"); node.className = "phase-details";
  const summary = document.createElement("summary"); summary.textContent = `${label} (${events.length} event${events.length === 1 ? "" : "s"})`;
  const list = document.createElement("div"); list.className = "event-mini-list";
  events.forEach((event) => {
    const item = document.createElement("section"); item.className = `event-mini kind-${eventKind(event)}`;
    item.innerHTML = `<strong>${escapeHtml(eventTitle(event))}</strong><span>${escapeHtml(eventSummary(event))}</span>`;
    item.append(eventDetails(event)); list.append(item);
  });
  node.append(summary, list); return node;
}

function eventCard(event, index) {
  const node = $("#event-template").content.firstElementChild.cloneNode(true); const kind = eventKind(event);
  node.classList.add(`kind-${kind}`); node.querySelector(".event-index").textContent = `#${index}`;
  node.querySelector(".event-title").textContent = eventTitle(event); node.querySelector(".event-meta").textContent = event.step ? `Step ${event.step}` : text(event.ts?.slice(11, 19), "");
  node.querySelector(".event-summary").textContent = eventSummary(event); node.querySelector(".event-expand").append(eventDetails(event)); return node;
}

async function importFolder(files) {
  const candidates = [...files].filter((file) => file.name === "trace.jsonl");
  if (!candidates.length) { $("#run-summary").textContent = "No trace.jsonl files were found in that folder."; return; }
  const parsed = (await Promise.all(candidates.map(async (file) => parseLines(await file.text(), shortPath(file))))).filter(Boolean);
  state.runs = parsed.sort((a, b) => a.id.localeCompare(b.id)); renderRuns(); if (parsed.length) selectRun(parsed[0]);
}

function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#039;", '"': "&quot;" })[character]); }

$("#folder-input").addEventListener("change", (event) => {
  importFolder(event.target.files);
  event.target.value = "";
});
document.querySelectorAll(".filter").forEach((button) => button.addEventListener("click", () => { state.filter = button.dataset.filter; document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item === button)); renderTasks(); }));
document.querySelectorAll(".attempt-filter").forEach((button) => button.addEventListener("click", () => { state.attemptFilter = button.dataset.attemptFilter; document.querySelectorAll(".attempt-filter").forEach((item) => item.classList.toggle("active", item === button)); renderTaskDetail(); }));
$("#task-search").addEventListener("input", (event) => { state.search = event.target.value.trim().toLowerCase(); renderTasks(); });

const appShell = document.querySelector(".app-shell");
const sidebarToggle = $("#sidebar-toggle");
function setSidebarCollapsed(collapsed) {
  appShell.classList.toggle("sidebar-collapsed", collapsed);
  sidebarToggle.title = collapsed ? "Show runs panel" : "Hide runs panel";
  sidebarToggle.querySelector(".sr-only").textContent = sidebarToggle.title;
  sidebarToggle.querySelector("span[aria-hidden]").textContent = collapsed ? "→☰" : "☰→";
  sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
}
sidebarToggle.addEventListener("click", () => setSidebarCollapsed(!appShell.classList.contains("sidebar-collapsed")));
const resizeHandle = $("#resize-handle");
resizeHandle.addEventListener("pointerdown", (event) => {
  if (appShell.classList.contains("sidebar-collapsed")) setSidebarCollapsed(false);
  resizeHandle.setPointerCapture(event.pointerId);
  const move = (moveEvent) => {
    const width = Math.max(220, Math.min(moveEvent.clientX, window.innerWidth - 520));
    appShell.style.setProperty("--sidebar-width", `${width}px`);
  };
  const stop = () => { resizeHandle.removeEventListener("pointermove", move); resizeHandle.removeEventListener("pointerup", stop); };
  resizeHandle.addEventListener("pointermove", move); resizeHandle.addEventListener("pointerup", stop);
});
