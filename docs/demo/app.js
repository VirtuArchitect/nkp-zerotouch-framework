const environments = [
  {
    name: "lab-connected",
    mode: "connected",
    provider: "nutanix-ahv",
    version: "v2.17.1",
    status: "Ready",
    readiness: 92,
    approvals: "1 of 1",
    note: "Plan reviewed, backup current",
    command: "./scripts/zt.sh deploy --config configs/environments/connected.example.yaml --apply",
  },
  {
    name: "pilot-proxied",
    mode: "proxied",
    provider: "proxied-ahv",
    version: "v2.17.1",
    status: "Review",
    readiness: 78,
    approvals: "1 of 2",
    note: "Proxy and plan hash review pending",
    command: "./scripts/zt.sh generate --config configs/environments/proxied.example.yaml",
  },
  {
    name: "factory-airgap",
    mode: "air-gapped",
    provider: "air-gapped-ahv",
    version: "v2.17.1",
    status: "Blocked",
    readiness: 63,
    approvals: "0 of 2",
    note: "Registry proof and kubeconfig evidence missing",
    command: "./scripts/zt.sh registry --config configs/environments/air-gapped.example.yaml --apply",
  },
];

const phases = [
  ["validate", "Schema, bundle, and endpoint preflight", "done", 100],
  ["prepare", "Workspace, binaries, metadata, and state", "done", 100],
  ["generate", "Cluster YAML, deploy script, and dry-run", "done", 100],
  ["registry", "Air-gapped bundle push plan", "running", 58],
  ["deploy", "Guarded NKP create cluster execution", "pending", 0],
  ["verify", "Kubeconfig, nodes, pods, and reports", "pending", 0],
];

const governance = [
  ["Plan review", "Approved with current artifact hashes", "pass"],
  ["Release channel", "pilot requires two approvals", "warn"],
  ["Placeholder endpoints", "Apply blocks example.com targets", "pass"],
  ["Backup evidence", "Latest backup captured 11 minutes ago", "pass"],
  ["Drift detection", "Generated plan differs from edited YAML", "warn"],
];

const artifacts = [
  ["deploy-plan.md", "plan", "2 minutes ago"],
  ["registry-plan.md", "plan", "7 minutes ago"],
  ["verification-summary.md", "report", "11 minutes ago"],
  ["component-health.json", "report", "11 minutes ago"],
  ["environment.json", "state", "14 minutes ago"],
  ["staged-tools.json", "state", "14 minutes ago"],
];

let selectedEnvironment = environments[0];
let mode = "connected";
let phaseCursor = 3;

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function renderEnvironments() {
  const query = $("#environmentSearch").value.trim().toLowerCase();
  $("#environmentList").innerHTML = environments
    .filter((env) => `${env.name} ${env.mode} ${env.provider}`.toLowerCase().includes(query))
    .map((env) => `
      <button class="environment-row ${env.name === selectedEnvironment.name ? "active" : ""}" type="button" data-env="${env.name}">
        <span class="environment-title">
          <strong>${env.name}</strong>
          <span class="muted">${env.provider} / ${env.version}</span>
        </span>
        <span class="tag">${env.mode}</span>
        <span class="status-pill ${statusClass(env.status)}">${env.status}</span>
      </button>
    `)
    .join("");
}

function statusClass(status) {
  if (status === "Blocked") return "fail";
  if (status === "Review") return "warn";
  return "";
}

function renderSelectedEnvironment() {
  $("#selectedName").textContent = selectedEnvironment.name;
  $("#selectedMode").textContent = selectedEnvironment.mode;
  $("#selectedProvider").textContent = selectedEnvironment.provider;
  $("#selectedVersion").textContent = selectedEnvironment.version;
  $("#selectedApprovals").textContent = selectedEnvironment.approvals;
  $("#selectedStatus").textContent = selectedEnvironment.status;
  $("#selectedStatus").className = `status-pill ${statusClass(selectedEnvironment.status)}`;
  $("#readinessValue").textContent = selectedEnvironment.readiness;
  $("#readinessRing").style.setProperty("--score", selectedEnvironment.readiness);
  $("#readinessLabel").textContent = selectedEnvironment.note;
  $("#commandPreview").textContent = selectedEnvironment.command;
}

function renderYaml() {
  const registryBlock = mode === "air-gapped"
    ? `registry:\n  endpoint: registry.corp.example/nkp\n  namespace: ${$("#registryNamespace").value}\n  pushConcurrency: 4\n`
    : `registry:\n  namespace: ${$("#registryNamespace").value}\n`;
  const proxyBlock = mode === "proxied"
    ? `  proxy:\n    httpProxy: http://proxy.corp.example:8080\n    httpsProxy: http://proxy.corp.example:8443\n`
    : "";
  $("#yamlPreview").textContent = `environment:
  name: ${$("#clusterName").value}
  type: ${mode}
${proxyBlock}nkp:
  version: v2.17.1
  bundleType: ${mode === "air-gapped" ? "air-gapped" : "standard"}
nutanix:
  prismCentralEndpoint: ${$("#prismEndpoint").value}
  clusterName: pe-cluster-01
cluster:
  name: ${$("#clusterName").value}
  kubernetesVersion: ${$("#kubernetesVersion").value}
  controlPlaneReplicas: ${$("#controlPlane").value}
  workerReplicas: ${$("#workers").value}
${registryBlock}`;
}

function renderPhases() {
  $("#phaseTrack").innerHTML = phases
    .map(([name, detail, state, pct], index) => {
      const computedState = index < phaseCursor ? "done" : index === phaseCursor ? "running" : "pending";
      const computedPct = index < phaseCursor ? 100 : index === phaseCursor ? pct : 0;
      return `
        <div class="phase-item">
          <span class="phase-icon ${computedState}"><i data-lucide="${phaseIcon(computedState)}"></i></span>
          <span>
            <strong>${name}</strong>
            <span class="muted">${detail}</span>
          </span>
          <span class="progress" aria-label="${computedPct}% complete"><span style="width:${computedPct}%"></span></span>
        </div>
      `;
    })
    .join("");
}

function phaseIcon(state) {
  if (state === "done") return "check";
  if (state === "running") return "loader-2";
  return "circle";
}

function renderGovernance() {
  $("#governanceChecks").innerHTML = governance
    .map(([title, detail, state]) => `
      <div class="check-row">
        <span class="phase-icon ${state === "pass" ? "done" : "running"}"><i data-lucide="${state === "pass" ? "check" : "triangle-alert"}"></i></span>
        <span><strong>${title}</strong><span class="muted">${detail}</span></span>
        <span class="tag">${state === "pass" ? "pass" : "review"}</span>
      </div>
    `)
    .join("");
  $("#auditList").innerHTML = [
    ["09:42 UTC", "registry apply requested by operator"],
    ["09:35 UTC", "plan review approved for lab-connected"],
    ["09:22 UTC", "generate completed with fresh artifact hashes"],
    ["09:18 UTC", "backup captured before apply request"],
  ].map(([time, event]) => `<div class="audit-row"><strong>${time}</strong><span>${event}</span></div>`).join("");
}

function renderArtifacts() {
  const filter = $("#artifactFilter").value;
  $("#artifactTable").innerHTML = artifacts
    .filter((artifact) => filter === "all" || artifact[1] === filter)
    .map(([name, type, updated]) => `
      <div class="artifact-row">
        <strong>${name}</strong>
        <span class="tag">${type}</span>
        <span class="muted">${updated}</span>
      </div>
    `)
    .join("");
}

function setView(viewName) {
  $$(".view").forEach((view) => view.classList.toggle("active", view.dataset.view === viewName));
  $$("[data-view-link]").forEach((item) => item.classList.toggle("active", item.dataset.viewLink === viewName));
}

function toast(message) {
  const el = document.createElement("div");
  el.className = "copy-toast";
  el.textContent = message;
  document.body.append(el);
  setTimeout(() => el.remove(), 1600);
}

document.addEventListener("click", async (event) => {
  const viewLink = event.target.closest("[data-view-link]");
  if (viewLink) setView(viewLink.dataset.viewLink);

  const envButton = event.target.closest("[data-env]");
  if (envButton) {
    selectedEnvironment = environments.find((env) => env.name === envButton.dataset.env);
    renderEnvironments();
    renderSelectedEnvironment();
  }

  const segment = event.target.closest("[data-mode]");
  if (segment) {
    mode = segment.dataset.mode;
    $$(".segment").forEach((item) => item.classList.toggle("active", item.dataset.mode === mode));
    renderYaml();
  }

  const command = event.target.closest("[data-command]")?.dataset.command;
  if (command === "copy") {
    await navigator.clipboard?.writeText($("#commandPreview").textContent);
    toast("Command copied");
  }
  if (command === "refresh") {
    phaseCursor = 3;
    renderPhases();
    createIcons();
    toast("Demo state refreshed");
  }
  if (command === "run-next") {
    phaseCursor = Math.min(phaseCursor + 1, phases.length);
    renderPhases();
    createIcons();
  }
  if (command === "validate-form") {
    toast("Schema validation passed");
  }
  if (command === "approve") {
    governance[1][2] = "pass";
    governance[1][1] = "second approval recorded";
    renderGovernance();
    createIcons();
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "environmentSearch") renderEnvironments();
  if (["clusterName", "prismEndpoint", "kubernetesVersion", "controlPlane", "workers", "registryNamespace"].includes(event.target.id)) {
    renderYaml();
  }
});

$("#artifactFilter").addEventListener("change", renderArtifacts);

function createIcons() {
  if (window.lucide) window.lucide.createIcons();
}

renderEnvironments();
renderSelectedEnvironment();
renderYaml();
renderPhases();
renderGovernance();
renderArtifacts();
createIcons();
