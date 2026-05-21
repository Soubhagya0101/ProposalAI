const ids = {
  leadsFound: "leads_found",
  messagesReady: "messages_ready",
  messagesSent: "messages_sent",
  replies: "replies",
  hotCount: "hot_leads_count",
  freeUsers: "free_users",
  payingUsers: "paying_users",
};

const rateIds = [
  ["leadReplyRate", "leadReplyBar", "lead_reply_rate"],
  ["replyRate", "replyRateBar", "reply_rate"],
  ["openRate", "openRateBar", "open_rate"],
  ["freeToPaidRate", "freeToPaidBar", "free_to_paid_rate"],
  ["leadToPaidRate", "leadToPaidBar", "lead_to_paid_rate"],
];

async function refreshDashboard() {
  const secret = new URLSearchParams(window.location.search).get("secret") || "";
  const query = secret ? `?secret=${encodeURIComponent(secret)}` : "";
  const response = await fetch(`/api/summary${query}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Dashboard API returned ${response.status}`);
  }
  render(await response.json());
}

function render(data) {
  const metrics = data.metrics || {};
  Object.entries(ids).forEach(([elementId, metricKey]) => {
    setText(elementId, formatNumber(metrics[metricKey]));
  });
  setText("emailsToday", `${formatNumber(metrics.emails_sent_today)} / ${formatNumber(metrics.email_daily_limit || 40)}`);
  setText("followupsScheduled", formatNumber(metrics.followups_scheduled));
  const followupBar = document.getElementById("followupsBar");
  if (followupBar) followupBar.style.width = `${Math.min(Number(metrics.followups_scheduled || 0) * 10, 100)}%`;

  rateIds.forEach(([textId, barId, key]) => {
    const raw = metrics[key];
    const value = raw === null || raw === undefined ? null : Number(raw || 0);
    setText(textId, value === null ? "N/A" : `${value.toFixed(1)}%`);
    const bar = document.getElementById(barId);
    if (bar) bar.style.width = `${Math.min(value || 0, 100)}%`;
  });

  renderActivity(data.recent_activity || []);
  renderHotLeads(data.hot_leads || []);
  renderFollowups(data.next_followups || []);
  renderScheduledRuns(data.next_scheduled_runs || []);

  const source = data.source || {};
  setText("source", `${source.created ? "Using sample store" : "Reading"}: ${source.path || "unknown"}`);
  setText("lastUpdated", `Updated ${formatTime(source.loaded_at)}`);
}

function renderScheduledRuns(items) {
  const list = document.getElementById("scheduledRuns");
  if (!list) return;
  list.innerHTML = "";
  if (!items.length) {
    list.append(emptyItem("No scheduled runs configured."));
    return;
  }
  items.forEach((run) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="row">
        <span class="title">${escapeHtml(run.name || "Run")}</span>
      </div>
      <span class="time">${escapeHtml(run.time || "")}</span>
    `;
    list.append(li);
  });
}

function renderActivity(items) {
  const list = document.getElementById("activity");
  if (!list) return;
  list.innerHTML = "";
  if (!items.length) {
    list.append(emptyItem("No activity yet."));
    return;
  }
  items.forEach((item) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="row">
        <span class="title">${escapeHtml(item.title || "Activity")}</span>
        <span class="time">${escapeHtml(formatTime(item.time))}</span>
      </div>
      <span class="detail">${escapeHtml(item.detail || item.type || "")}</span>
    `;
    list.append(li);
  });
}

function renderHotLeads(items) {
  const list = document.getElementById("hotLeads");
  if (!list) return;
  list.innerHTML = "";
  if (!items.length) {
    list.append(emptyItem("No hot leads flagged yet."));
    return;
  }
  items.forEach((lead) => {
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="row">
        <span class="title">${escapeHtml(lead.company || "Unknown company")}</span>
        <span class="pill">${formatNumber(lead.score)} score</span>
      </div>
      <span class="detail">${escapeHtml(lead.name || "Unknown lead")}</span>
      <span class="meta">${escapeHtml([lead.stage, lead.value].filter(Boolean).join(" · "))}</span>
    `;
    list.append(li);
  });
}

function renderFollowups(items) {
  const list = document.getElementById("followups");
  if (!list) return;
  list.innerHTML = "";
  if (!items.length) {
    list.append(emptyItem("No follow-ups scheduled."));
    return;
  }
  items.forEach((followup) => {
    const priority = String(followup.priority || "normal").toLowerCase();
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="row">
        <span class="title">${escapeHtml(followup.lead || "Follow-up")}</span>
        <span class="pill ${priority === "high" ? "priority-high" : ""}">${escapeHtml(priority)}</span>
      </div>
      <span class="detail">${escapeHtml(followup.action || "Follow up")}</span>
      <span class="time">${escapeHtml(formatTime(followup.due))}</span>
    `;
    list.append(li);
  });
}

function emptyItem(message) {
  const li = document.createElement("li");
  li.className = "empty";
  li.textContent = message;
  return li;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function formatTime(value) {
  if (!value) return "unscheduled";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.getElementById("refresh")?.addEventListener("click", () => {
  refreshDashboard().catch((error) => setText("source", error.message));
});

refreshDashboard().catch((error) => setText("source", error.message));
setInterval(() => refreshDashboard().catch((error) => setText("source", error.message)), 10000);
