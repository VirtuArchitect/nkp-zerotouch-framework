#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZT_ROOT = ROOT / ".zt"


def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_key(value):
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip("-") or "unknown"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def config_context(config_path):
    try:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "zt_config.py"), "context", "--config", str(config_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def latest_file(pattern):
    matches = [path for path in ROOT.glob(pattern) if path.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda item: item.stat().st_mtime)


def latest_lab_evidence(env_name):
    records = []
    for path in (ZT_ROOT / "lab-evidence").glob("*/lab-evidence.json") if (ZT_ROOT / "lab-evidence").exists() else []:
        data = read_json(path)
        if data and data.get("environment") == env_name:
            records.append((path, data))
    if not records:
        return None, None
    return max(records, key=lambda item: item[0].stat().st_mtime)


def latest_external_validation(area, env_name):
    records = []
    for path in (ZT_ROOT / "external-validations").glob("*.json") if (ZT_ROOT / "external-validations").exists() else []:
        data = read_json(path)
        if not data:
            continue
        scope = safe_key(data.get("environment", ""))
        if data.get("area") == area and scope in {"", "global", safe_key(env_name)}:
            records.append((path, data))
    if not records:
        return None, None
    return max(records, key=lambda item: item[0].stat().st_mtime)


def deployment_jobs(env_name):
    jobs = []
    for path in (ZT_ROOT / "jobs").glob("*/job.json") if (ZT_ROOT / "jobs").exists() else []:
        data = read_json(path)
        if data and data.get("environment") == env_name and data.get("action") in {"registry", "deploy", "upgrade"}:
            jobs.append({"path": str(path), "id": data.get("id", path.parent.name), "action": data.get("action"), "status": data.get("status"), "createdAt": data.get("createdAt", "")})
    return sorted(jobs, key=lambda item: item.get("createdAt", ""), reverse=True)


def latest_run(env_name):
    records = []
    for path in (ZT_ROOT / "runs").glob("*/summary.json") if (ZT_ROOT / "runs").exists() else []:
        data = read_json(path)
        if data and data.get("environment") == env_name:
            records.append((path, data))
    if not records:
        return None, None
    return max(records, key=lambda item: item[0].stat().st_mtime)


def evidence_packs(env_name):
    packs = []
    for path in (ZT_ROOT / "evidence").glob("*/evidence-manifest.json") if (ZT_ROOT / "evidence").exists() else []:
        data = read_json(path)
        if data and data.get("environment") == env_name:
            packs.append({"path": str(path), "createdAt": data.get("createdAt", ""), "files": len(data.get("files", [])) if isinstance(data.get("files"), list) else 0})
    return sorted(packs, key=lambda item: item.get("createdAt", ""), reverse=True)


def backup_manifests(env_name):
    backups = []
    for path in (ZT_ROOT / "environments" / safe_key(env_name) / "backup").glob("*/backup-manifest.json") if (ZT_ROOT / "environments" / safe_key(env_name) / "backup").exists() else []:
        data = read_json(path) or {}
        backups.append({"path": str(path), "createdAt": data.get("createdAt", "")})
    return sorted(backups, key=lambda item: item.get("createdAt", ""), reverse=True)


def signal(name, passed, detail, evidence_ref=""):
    return {
        "name": name,
        "status": "pass" if passed else "partial",
        "detail": detail,
        "evidenceRef": evidence_ref,
    }


def build_evidence(config_path):
    ctx = config_context(config_path)
    env_name = str(ctx.get("environmentName") or config_path.stem)
    cluster_name = str(ctx.get("clusterName") or "")
    env_type = str(ctx.get("environmentType") or "unknown")
    state_root = ZT_ROOT / "environments" / safe_key(env_name)
    preflight = ZT_ROOT / "preflight" / f"{safe_key(env_name)}.json"
    verification = state_root / "reports" / "verification-evidence.json"
    plan_review = state_root / "review" / "deploy-plan-review.json"
    lab_path, lab_data = latest_lab_evidence(env_name)
    prism_validation_path, prism_validation = latest_external_validation("prism-authorization", env_name)
    deployment_validation_path, deployment_validation = latest_external_validation("deployment-uat", env_name)
    run_path, run_data = latest_run(env_name)
    jobs = deployment_jobs(env_name)
    packs = evidence_packs(env_name)
    backups = backup_manifests(env_name)

    preflight_data = read_json(preflight) or {}
    preflight_summary = preflight_data.get("summary", {}) if isinstance(preflight_data, dict) else {}
    preflight_passed = preflight.exists() and int(preflight_summary.get("failures", 0) or 0) == 0
    reviewed = read_json(plan_review) or {}
    review_passed = reviewed.get("status") == "approved"
    lab_passed = bool(lab_data and lab_data.get("status") == "pass")
    prism_passed = bool(prism_validation and prism_validation.get("status") == "pass")
    deployment_passed = bool(deployment_validation and deployment_validation.get("status") == "pass")
    job_proof = any(job.get("status") in {"succeeded", "completed", "pending_approval", "approved"} for job in jobs)
    verification_passed = verification.exists()
    run_passed = bool(run_data)
    backup_passed = bool(backups)
    evidence_pack_passed = bool(packs)

    signals = [
        signal("Preflight evidence", preflight_passed, "preflight exists with no recorded failures" if preflight_passed else "preflight evidence missing or has failures", str(preflight) if preflight.exists() else ""),
        signal("Plan review", review_passed, reviewed.get("reviewedAt", "approved review missing") if reviewed else "approved deploy plan review missing", str(plan_review) if plan_review.exists() else ""),
        signal("Prism lab evidence", lab_passed, "latest lab evidence authenticated all targets" if lab_passed else "passing lab evidence missing", str(lab_path or "")),
        signal("Prism external validation", prism_passed, "passing prism-authorization record found" if prism_passed else "passing prism-authorization record missing", str(prism_validation_path or "")),
        signal("Deployment job or approval", job_proof, f"{len(jobs)} apply-class job/change candidate(s)" if jobs else "no apply-class job/change evidence found", jobs[0]["path"] if jobs else ""),
        signal("Verification evidence", verification_passed, "verification evidence file found" if verification_passed else "verification evidence missing", str(verification) if verification.exists() else ""),
        signal("Run summary", run_passed, "latest run summary found" if run_passed else "run summary missing", str(run_path or "")),
        signal("Backup manifest", backup_passed, f"{len(backups)} backup manifest(s)" if backups else "backup manifest missing", backups[0]["path"] if backups else ""),
        signal("Evidence pack", evidence_pack_passed, f"{len(packs)} evidence pack(s)" if packs else "evidence pack missing", packs[0]["path"] if packs else ""),
        signal("Deployment UAT validation", deployment_passed, "passing deployment-uat external validation found" if deployment_passed else "deployment-uat external validation not yet passed", str(deployment_validation_path or "")),
    ]
    passed = sum(1 for item in signals if item["status"] == "pass")
    required = ["Preflight evidence", "Plan review", "Prism lab evidence", "Deployment job or approval", "Verification evidence"]
    required_passed = all(item["status"] == "pass" for item in signals if item["name"] in required)
    status = "pass" if required_passed else ("partial" if passed else "missing")
    return {
        "capturedAt": utc_now(),
        "environment": env_name,
        "type": env_type,
        "cluster": cluster_name,
        "config": str(config_path),
        "status": status,
        "maturity": "controlled-uat" if status in {"pass", "partial"} else "not-ready",
        "productionValidated": False,
        "summary": {
            "signals": len(signals),
            "passedSignals": passed,
            "requiredSignals": len(required),
            "requiredSignalsPassed": sum(1 for item in signals if item["name"] in required and item["status"] == "pass"),
        },
        "signals": signals,
        "deploymentJobs": jobs,
        "evidencePacks": packs,
        "backups": backups,
        "redaction": {
            "secretValuesRecorded": False,
            "rawKubeconfigExcluded": True,
            "responseBodiesExcluded": True,
        },
        "boundary": "Deployment evidence is controlled-UAT readiness metadata until a passing deployment-uat validation record and post-deployment verification exist.",
    }


def write_summary(path, evidence):
    lines = [
        "# Deployment Evidence Summary",
        "",
        f"Environment: `{evidence['environment']}`",
        f"Status: `{evidence['status']}`",
        f"Maturity: `{evidence['maturity']}`",
        "",
        "| Signal | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for item in evidence["signals"]:
        lines.append(f"| {item['name']} | {item['status']} | {item['detail']} |")
    lines.extend([
        "",
        "This record excludes secret values, raw kubeconfig, and response bodies.",
        "It is UAT readiness evidence, not production validation.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_external_validation(evidence, evidence_path):
    record_id = f"ev-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{os.urandom(3).hex()}"
    status = "pass" if evidence["status"] == "pass" else "warn"
    record = {
        "id": record_id,
        "area": "deployment-uat",
        "environment": evidence["environment"],
        "status": status,
        "summary": f"Deployment evidence phase recorded {evidence['summary']['passedSignals']} of {evidence['summary']['signals']} UAT signals.",
        "evidenceRef": str(evidence_path),
        "validatedAt": evidence["capturedAt"],
        "recordedAt": utc_now(),
        "recordedBy": "deployment-evidence-phase",
    }
    path = ZT_ROOT / "external-validations" / f"{record_id}.json"
    write_json(path, record)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Capture redacted deployment UAT evidence from local ZeroTouch state.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--write-external-validation", action="store_true")
    args = parser.parse_args(argv)

    evidence = build_evidence(Path(args.config))
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    evidence_dir = ZT_ROOT / "deployment-evidence" / f"{safe_key(evidence['environment'])}-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "deployment-evidence.json"
    summary_path = evidence_dir / "README.md"
    write_json(evidence_path, evidence)
    write_summary(summary_path, evidence)

    external_paths = []
    if args.write_external_validation:
        external_paths.append(create_external_validation(evidence, evidence_path))

    print(json.dumps({
        "status": evidence["status"],
        "environment": evidence["environment"],
        "evidencePath": str(evidence_path),
        "summaryPath": str(summary_path),
        "externalValidationRecords": [str(path) for path in external_paths],
    }, indent=2))
    return 0 if evidence["status"] in {"pass", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
