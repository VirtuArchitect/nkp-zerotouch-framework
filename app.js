const metrics = [
  ["Ready to Deploy", "3", "environments clear deploy gate"],
  ["Blocked", "1", "environments need operator action"],
  ["Pending Approval", "3", "apply jobs awaiting review"],
  ["Drift Detected", "4", "environments with drift signals"],
];

const environments = [
  {
    name: "lab-airgapped",
    file: "air-gapped.example.yaml",
    type: "air-gapped",
    lifecycle: "Generated",
    lifecycleClass: "ok",
    readiness: "7/10",
    readinessPct: 70,
    gate: "ready",
    gateClass: "ok",
    gateDetail: "deploy gate clear",
    drift: "attention",
    driftClass: "warn",
    driftDetail: "verification report missing",
    evidence: "approved",
    evidenceClass: "ok",
    evidenceDetail: "report missing",
    action: "Resolve drift",
    detail: "verification report missing",
  },
  {
    name: "lab-connected",
    file: "connected.example.yaml",
    type: "connected",
    lifecycle: "Verified",
    lifecycleClass: "ok",
    readiness: "6/10",
    readinessPct: 60,
    gate: "ready",
    gateClass: "ok",
    gateDetail: "deploy gate clear",
    drift: "attention",
    driftClass: "warn",
    driftDetail: "generate has not run",
    evidence: "approved",
    evidenceClass: "ok",
    evidenceDetail: "report available",
    action: "Prepare workspace",
    detail: "Stage NKP inputs and create local state.",
  },
  {
    name: "lab-connected",
    file: "lab-new.yaml",
    type: "connected",
    lifecycle: "Verified",
    lifecycleClass: "ok",
    readiness: "6/10",
    readinessPct: 60,
    gate: "ready",
    gateClass: "ok",
    gateDetail: "deploy gate clear",
    drift: "attention",
    driftClass: "warn",
    driftDetail: "generate has not run",
    evidence: "approved",
    evidenceClass: "ok",
    evidenceDetail: "report available",
    action: "Prepare workspace",
    detail: "Stage NKP inputs and create local state.",
  },
  {
    name: "lab-proxied",
    file: "proxied.example.yaml",
    type: "proxied",
    lifecycle: "Draft",
    lifecycleClass: "warn",
    readiness: "5/10",
    readinessPct: 50,
    gate: "blocked",
    gateClass: "warn",
    gateDetail: "plan review is not generated",
    drift: "attention",
    driftClass: "warn",
    driftDetail: "generate has not run; verification report missing",
    evidence: "not generated",
    evidenceClass: "warn",
    evidenceDetail: "report missing",
    action: "Prepare workspace",
    detail: "Stage NKP inputs and create local state.",
  },
];

const nextActions = [
  environments[0],
  environments[1],
  environments[2],
  environments[3],
];

const jobs = [
  ["job-20260629-apply-003", "deploy", "pending_approval", "jgoulden", "1 of 2"],
  ["job-20260629-registry-002", "registry", "pending_approval", "operator", "0 of 1"],
  ["job-20260629-generate-001", "generate", "completed", "jgoulden", "not required"],
];

const runs = [
  ["20260629-102047", "summary.md"],
  ["20260629-082052", "summary.md"],
  ["20260629-081805", "summary.md"],
];

const pipeline = [
  ["validate", "Schema and bundle checks", "ok", 100],
  ["prepare", "Local state and staged tools", "ok", 100],
  ["generate", "Plans, scripts, and dry-run", "warn", 65],
  ["registry", "Air-gapped bundle plan", "warn", 45],
  ["deploy", "Approval-gated NKP create", "warn", 20],
  ["verify", "Kubeconfig and reports", "warn", 10],
];

const artifacts = [
  ["cluster-values.yaml", "config", "lab-connected", "generated"],
  ["deploy-plan.md", "plan", "lab-connected", "review"],
  ["registry-plan.md", "plan", "lab-airgapped", "generated"],
  ["verification-summary.md", "report", "lab-airgapped", "missing"],
  ["environment.json", "state", "lab-connected", "ready"],
  ["deploy.log", "log", "lab-connected", "pending"],
];

const genericSections = {
  setup: ["Setup Wizard", "Create a deployment profile from connected, proxied, or air-gapped templates.", [["Source template", "connected.example.yaml"], ["Identity checks", "duplicate names blocked"], ["Next step", "prepare workspace"]]],
  preflight: ["Preflight", "Readiness matrix across bundle, network, credentials, and provider checks.", [["Bundle", "NKP v2.17.1 discovered"], ["Prism Central", "placeholder endpoint warning"], ["Registry", "required for air-gapped"]]],
  drift: ["Drift", "Generated plan and verification evidence signals.", [["lab-airgapped", "verification report missing"], ["lab-connected", "generate has not run"], ["lab-proxied", "plan review is not generated"]]],
  production: ["Production Gate", "Deployment gate checks before live apply is requested.", [["Placeholder endpoint block", "enabled"], ["Plan review", "required"], ["Backup evidence", "recommended"]]],
  health: ["Health", "Runner, tool, credential, and integration checks.", [["Runner", "Docker / Local Shell"], ["Credentials", "environment variables checked"], ["Optional tools", "podman warning"]]],
  plan: ["Plan Review", "Artifact review with hash evidence before apply approval.", [["deploy-plan.md", "awaiting approval"], ["registry-plan.md", "generated"], ["Change record", "linked to pending job"]]],
  kubeconfig: ["Kubeconfig", "Kubeconfig presence and verification output.", [["lab-connected", "not yet captured"], ["lab-airgapped", "report missing"], ["Access", "local artifact only"]]],
  backups: ["Backups", "Local backup snapshots before destructive workflows.", [["Latest backup", "not captured in demo"], ["Scope", "state, generated, reports"], ["Restore path", ".zt/environments/<name>/backup"]]],
  restore: ["Restore", "Restore workflow for local ZeroTouch state.", [["Mode", "operator selected backup"], ["Safety", "review before overwrite"], ["Audit", "restore event captured"]]],
  sources: ["Sources", "NKP bundle paths, source metadata, and checksums.", [["Standard bundle", "/mnt/c/Share/nkp-bundle_v2.17.1"], ["Air-gapped bundle", "/mnt/c/Share/nkp-air-gapped-bundle_v2.17.1"], ["Git source", "VirtuArchitect/nkp-zerotouch-framework"]]],
  inventory: ["Inventory", "AHV inventory and future bare-metal provider notes.", [["Provider", "nutanix-ahv"], ["Prism Element", "pe-cluster"], ["Image", "nkp-node-image"]]],
  network: ["Network", "Management, workload, API VIP, DNS, NTP, and proxy fields.", [["API VIP", "10.10.10.50 duplicate warning"], ["Pod CIDR", "192.168.0.0/16"], ["Service CIDR", "10.96.0.0/12"]]],
  locks: ["Locks", "Operational locks around apply-class jobs.", [["deploy", "approval lock pending"], ["destroy", "requires confirm flag"], ["registry", "air-gapped only"]]],
  actions: ["Safe Actions", "Dashboard-safe operations that do not perform live apply.", [["validate", "safe"], ["prepare", "safe"], ["generate", "safe"], ["verify", "safe"]]],
  changes: ["Change Records", "Apply requests are captured as change records.", [["CHG-003", "deploy pending approval"], ["CHG-002", "registry pending approval"], ["CHG-001", "generate completed"]]],
  approval: ["Approval Policy", "Approval thresholds for apply-class workflows.", [["deploy", "2 approvals"], ["registry", "1 approval"], ["destroy", "2 approvals and confirm flag"]]],
  channels: ["Release Channels", "Environment channel metadata and readiness.", [["lab", "connected/proxied/air-gapped"], ["pilot", "extra approval"], ["production", "stricter gate"]]],
  audit: ["Audit Trail", "Append-only local event stream.", [["08:35", "admin login accepted"], ["08:20", "PowerShell smoke completed"], ["08:18", "Bash smoke completed"]]],
  settings: ["Providers", "Default provider intent and local settings.", [["Provider", "nutanix-ahv"], ["Auth", "Local RBAC"], ["Persistence", "local .zt state"]]],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function renderMetrics() {
  $("#summaryGrid").innerHTML = metrics.map(([label, value, foot]) => `
    <a class="metric" href="#${label.toLowerCase().replaceAll(" ", "-")}" data-command="metric">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-foot">${foot}</div>
    </a>
  `).join("");
}

function renderNextActions() {
  $("#nextActions").innerHTML = nextActions.map((env) => `
    <div class="next-action">
      <div>
        <strong>${env.name}</strong>
        <div class="env-file">${env.file} · ${env.detail}</div>
      </div>
      <button class="button-link" type="button" data-command="action">${env.action}</button>
    </div>
  `).join("");
}

function renderEnvironments() {
  $("#environmentRows").innerHTML = environments.map((env) => `
    <tr>
      <td><div class="env-name">${env.name}</div><div class="env-file">${env.file}</div></td>
      <td><span class="badge ${env.type}">${env.type}</span><div class="env-file">channel lab</div></td>
      <td><span class="chip ${env.lifecycleClass}">${env.lifecycle}</span><div class="env-file">readiness ${env.readiness}</div><div class="progress-track"><div class="progress-bar" style="width:${env.readinessPct}%"></div></div></td>
      <td><span class="chip ${env.gateClass}">${env.gate}</span><div class="env-file">${env.gateDetail}</div></td>
      <td><span class="chip ${env.driftClass}">${env.drift}</span><div class="env-file">${env.driftDetail}</div></td>
      <td><span class="chip ${env.evidenceClass}">${env.evidence}</span><div class="env-file">${env.evidenceDetail}</div></td>
      <td><button class="button-link" type="button" data-command="action">${env.action}</button><div class="env-file">${env.detail}</div></td>
      <td><div class="manage-actions"><button class="button-link" type="button" data-command="open">Open</button><button class="button-link" type="button" data-command="edit">Edit</button></div></td>
    </tr>
  `).join("");
}

function renderRuns() {
  const rows = runs.map(([name, file]) => `<li><code>${name}</code><span class="muted">${file}</span></li>`).join("");
  $("#recentRuns").innerHTML = rows;
  $("#runsList").innerHTML = rows;
}

function renderJobs() {
  $("#jobRows").innerHTML = jobs.map(([id, action, status, requester, approval]) => `
    <tr><td><code>${id}</code></td><td>${action}</td><td><span class="chip ${status === "completed" ? "ok" : "warn"}">${status}</span></td><td>${requester}</td><td>${approval}</td></tr>
  `).join("");
}

function renderPipeline() {
  $("#pipelineSteps").innerHTML = pipeline.map(([name, detail, state, pct]) => `
    <div class="pipeline-step">
      <strong>${name}</strong>
      <span class="chip ${state}">${state === "ok" ? "pass" : "attention"}</span>
      <div class="env-file">${detail}</div>
      <div class="progress-track"><div class="progress-bar" style="width:${pct}%"></div></div>
    </div>
  `).join("");
}

function renderArtifacts() {
  $("#artifactRows").innerHTML = artifacts.map(([name, type, env, status]) => `
    <tr><td><code>${name}</code></td><td>${type}</td><td>${env}</td><td><span class="chip ${status === "missing" ? "warn" : "ok"}">${status}</span></td></tr>
  `).join("");
}

function renderGeneric(sectionKey) {
  const [title, copy, cards] = genericSections[sectionKey] || genericSections.settings;
  $("#genericTitle").textContent = title;
  $("#genericCopy").textContent = copy;
  $("#genericCards").innerHTML = cards.map(([heading, body]) => `
    <article class="settings-card"><h3>${heading}</h3><p>${body}</p></article>
  `).join("");
}

function setView(viewName) {
  const dedicated = ["environments", "jobs", "runs", "pipeline", "cli", "artifacts"];
  const targetView = dedicated.includes(viewName) ? viewName : "generic";
  $$(".view").forEach((view) => view.classList.toggle("active", view.dataset.view === targetView));
  $$("[data-view-link]").forEach((item) => item.classList.toggle("active", item.dataset.viewLink === viewName));
  if (targetView === "generic") renderGeneric(viewName);
  window.location.hash = viewName;
}

function toast(message) {
  const el = document.createElement("div");
  el.className = "copy-toast";
  el.textContent = message;
  document.body.append(el);
  setTimeout(() => el.remove(), 1600);
}

document.addEventListener("click", (event) => {
  const viewLink = event.target.closest("[data-view-link]");
  if (viewLink) setView(viewLink.dataset.viewLink);

  const command = event.target.closest("[data-command]")?.dataset.command;
  if (command === "demo-login") toast("Static demo session stays signed in");
  if (command === "action") toast("Demo action selected; live apply remains CLI-gated");
  if (command === "open") toast("Environment detail preview");
  if (command === "edit") toast("Edit workflow preview");
  if (command === "metric") toast("Metric drill-down preview");
});

renderMetrics();
renderNextActions();
renderEnvironments();
renderRuns();
renderJobs();
renderPipeline();
renderArtifacts();
renderGeneric("settings");

const initial = window.location.hash.replace("#", "");
if (initial) setView(initial);
