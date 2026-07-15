from __future__ import annotations

import json
import hashlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from data_quality import profile  # noqa: E402
from redact_scan import run_scan  # noqa: E402
from safe_curator import make_plan  # noqa: E402
from workflow_core import EventLog, load_json, validate_workflow  # noqa: E402


def run_cli(*args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode != expect:
        raise AssertionError(
            f"expected exit {expect}, got {result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result


class WorkflowDefinitionTests(unittest.TestCase):
    def test_all_public_workflows_validate(self) -> None:
        for path in sorted((ROOT / "workflows").glob("*.json")):
            with self.subTest(path=path.name):
                self.assertEqual(validate_workflow(load_json(path)), [])

    def test_no_mutation_phase_in_public_workflows(self) -> None:
        for path in sorted((ROOT / "workflows").glob("*.json")):
            workflow = load_json(path)
            self.assertNotIn("mutation", {phase["type"] for phase in workflow["phases"]})


class EventLogTests(unittest.TestCase):
    def test_hash_chain_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            log = EventLog(path)
            log.append("run_created", {"run_id": "run_test", "inputs": {}})
            log.append("phase_started", {"phase": "p1"})
            self.assertEqual(len(log.read()), 2)
            text = path.read_text(encoding="utf-8").replace("run_test", "run_fake")
            path.write_text(text, encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "哈希"):
                log.read()

    def test_parallel_process_appends_remain_a_valid_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.jsonl"
            code = (
                "from pathlib import Path; "
                "from workflow_core import EventLog; "
                f"EventLog(Path({str(path)!r})).append('phase_started', {{'phase':'p'}})"
            )
            processes = [
                subprocess.Popen(
                    [sys.executable, "-c", code],
                    env={"PYTHONPATH": str(SCRIPTS)},
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(20)
            ]
            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, (stdout, stderr))
            events = EventLog(path).read()
            self.assertEqual(len(events), 20)
            self.assertEqual(len({event["event_id"] for event in events}), 20)

    def test_event_log_refuses_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            outside = base / "outside.jsonl"
            link = base / "events.jsonl"
            link.symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError, "符号链接"):
                EventLog(link).append("phase_started", {"phase": "p"})


class LoopCtlTests(unittest.TestCase):
    def test_first_phase_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            request = base / "request.md"
            sources = base / "sources.csv"
            request.write_text("研究问题：比较两个公开选项。\n用途：内部决策。\n", encoding="utf-8")
            sources.write_text("source,owner,allowed_use,rights_status\npublic-doc,publisher,research,approved\n", encoding="utf-8")
            workspace = base / "run"
            run_cli(
                sys.executable,
                str(SCRIPTS / "loopctl.py"),
                "init",
                str(ROOT / "workflows" / "research-to-brief.json"),
                "--workspace",
                str(workspace),
                "--input",
                f"research_request={request}",
                "--input",
                f"source_manifest={sources}",
            )
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "start", "preflight", "--workspace", str(workspace))
            scope = workspace / "10_work" / "scope.json"
            rights = workspace / "10_work" / "rights.csv"
            evidence = workspace / "10_work" / "preflight-check.json"
            scope.write_text("{}\n", encoding="utf-8")
            rights.write_text("source,status\npublic-doc,approved\n", encoding="utf-8")
            evidence.write_text('{"passed": true}\n', encoding="utf-8")
            for name, path in (("scope_contract", scope), ("rights_ledger", rights)):
                run_cli(
                    sys.executable,
                    str(SCRIPTS / "loopctl.py"),
                    "record",
                    "preflight",
                    name,
                    str(path),
                    "--workspace",
                    str(workspace),
                )
            for check in ("required_fields", "rights_fail_closed", "untrusted_content_is_data"):
                run_cli(
                    sys.executable,
                    str(SCRIPTS / "loopctl.py"),
                    "verify",
                    "preflight",
                    check,
                    "--by",
                    "human",
                    "--result",
                    "pass",
                    "--evidence",
                    str(evidence),
                    "--reviewer",
                    "reviewer-a",
                    "--producer",
                    "producer-a",
                    "--workspace",
                    str(workspace),
                )
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "complete", "preflight", "--workspace", str(workspace))
            status = run_cli(
                sys.executable,
                str(SCRIPTS / "loopctl.py"),
                "status",
                "--workspace",
                str(workspace),
                "--json",
            )
            state = json.loads(status.stdout)
            self.assertEqual(state["phases"]["preflight"]["status"], "completed")
            self.assertIn("research_plan", state["ready"])
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "doctor", "--workspace", str(workspace))

    def test_input_change_invalidates_old_artifacts_and_resets_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workflow = base / "workflow.json"
            workflow.write_text(
                json.dumps(
                    {
                        "id": "generation-test", "version": "1.0.0", "title": "test",
                        "audiences": ["test"], "job_stories": ["test"],
                        "inputs": [{"name": "source", "required": True, "rights_required": False, "formats": ["txt"]}],
                        "phases": [{
                            "id": "work", "title": "work", "type": "assistive", "risk": "low",
                            "depends_on": [], "inputs": ["input:source"],
                            "outputs": [{"name": "result", "required": True}],
                            "checks": [{"name": "review", "required": True}],
                            "completion": "reviewed", "abandon_when": [],
                            "retry": {"max_attempts": 2, "change_required": "change", "fallback": "stop"}
                        }],
                        "deliverables": ["result.txt"]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            source1 = base / "source1.txt"
            source2 = base / "source2.txt"
            source1.write_text("one", encoding="utf-8")
            source2.write_text("two", encoding="utf-8")
            workspace = base / "run"
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "init", str(workflow), "--workspace", str(workspace), "--input", f"source={source1}")
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "start", "work", "--workspace", str(workspace))
            artifact = workspace / "10_work" / "result.txt"
            evidence = workspace / "10_work" / "review.txt"
            artifact.write_text("old", encoding="utf-8")
            evidence.write_text("reviewed", encoding="utf-8")
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "record", "work", "result", str(artifact), "--workspace", str(workspace))
            run_cli(
                sys.executable, str(SCRIPTS / "loopctl.py"), "verify", "work", "review",
                "--by", "human", "--result", "pass", "--evidence", str(evidence),
                "--reviewer", "reviewer", "--producer", "producer", "--workspace", str(workspace),
            )
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "complete", "work", "--workspace", str(workspace))
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "change-input", "source", str(source2), "--workspace", str(workspace))
            status = run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "status", "--workspace", str(workspace), "--json")
            state = json.loads(status.stdout)
            self.assertEqual(state["generation"], 2)
            self.assertEqual(state["phases"]["work"]["status"], "invalidated")
            self.assertEqual(state["phases"]["work"]["attempts"], 0)
            self.assertEqual(state["phases"]["work"]["artifacts"], [])

    def test_human_check_rejects_empty_evidence_and_same_reviewer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workflow = base / "workflow.json"
            workflow.write_text(
                json.dumps({
                    "id": "human-test", "version": "1", "title": "test", "audiences": ["test"], "job_stories": ["test"],
                    "inputs": [{"name": "source", "required": True, "rights_required": False, "formats": ["txt"]}],
                    "phases": [{"id": "p", "title": "p", "type": "assistive", "risk": "low", "depends_on": [],
                        "inputs": ["input:source"], "outputs": [], "checks": [{"name": "review", "required": True}],
                        "completion": "done", "abandon_when": [], "retry": {"max_attempts": 1, "change_required": "none", "fallback": "stop"}}],
                    "deliverables": ["review"]
                }), encoding="utf-8"
            )
            source = base / "source.txt"
            source.write_text("source", encoding="utf-8")
            workspace = base / "run"
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "init", str(workflow), "--workspace", str(workspace), "--input", f"source={source}")
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "start", "p", "--workspace", str(workspace))
            run_cli(
                sys.executable, str(SCRIPTS / "loopctl.py"), "verify", "p", "review",
                "--by", "human", "--result", "pass", "--reviewer", "same", "--producer", "same",
                "--workspace", str(workspace), expect=2,
            )

    def test_automatic_verifier_computes_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            workflow = base / "workflow.json"
            workflow.write_text(json.dumps({
                "id": "auto-test", "version": "1", "title": "test", "audiences": ["test"], "job_stories": ["test"],
                "inputs": [],
                "phases": [{"id": "release", "title": "release", "type": "deterministic", "risk": "high",
                    "depends_on": [], "inputs": [], "outputs": [{"name": "result", "required": True}],
                    "checks": [{"name": "redaction_scan", "required": True}], "completion": "safe",
                    "abandon_when": [], "retry": {"max_attempts": 1, "change_required": "rebuild", "fallback": "stop"}}],
                "deliverables": ["result.md"]
            }), encoding="utf-8")
            workspace = base / "run"
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "init", str(workflow), "--workspace", str(workspace))
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "start", "release", "--workspace", str(workspace))
            artifact = workspace / "20_output" / "result.md"
            artifact.write_text("# Public synthetic result\n", encoding="utf-8")
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "record", "release", "result", str(artifact), "--taint", "publishable", "--workspace", str(workspace))
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "verify", "release", "redaction_scan", "--by", "auto", "--workspace", str(workspace))
            run_cli(sys.executable, str(SCRIPTS / "loopctl.py"), "complete", "release", "--workspace", str(workspace))


class SafetyToolTests(unittest.TestCase):
    def test_redaction_scan_does_not_echo_secret(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            secret = "sk-" + ("example" * 3) + "1234"
            (root / "note.txt").write_text(f"token={secret}\n", encoding="utf-8")
            report = run_scan(root, [])
            self.assertFalse(report["safe_to_publish"])
            self.assertGreater(report["summary"]["findings"], 0)
            self.assertNotIn(secret, json.dumps(report))

    def test_unknown_binary_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "image.png").write_bytes(b"not-a-real-image")
            report = run_scan(root, [])
            self.assertFalse(report["safe_to_publish"])
            self.assertEqual(report["summary"]["unknown"], 1)

    def test_missing_root_and_unknown_zip_member_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            missing = run_scan(base / "missing", [])
            self.assertFalse(missing["safe_to_publish"])
            archive = base / "unknown.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("image.bin", b"binary")
            report = run_scan(archive, [])
            self.assertFalse(report["safe_to_publish"])
            self.assertGreater(report["summary"]["unknown"], 0)

    def test_safe_curator_only_plans_and_copies(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            candidate = root / ".DS_Store"
            candidate.write_text("metadata", encoding="utf-8")
            keep = root / "keep.md"
            keep.write_text("keep", encoding="utf-8")
            plan = make_plan(root, False, 1024)
            self.assertEqual(plan["summary"]["cleanup_candidates"], 1)
            plan_path = Path(temp) / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            archive = Path(temp) / "candidates.zip"
            run_cli(
                sys.executable,
                str(SCRIPTS / "safe_curator.py"),
                "bundle",
                str(plan_path),
                "--output",
                str(archive),
                "--reason",
                "finder_metadata",
            )
            self.assertTrue(candidate.exists())
            self.assertTrue(keep.exists())
            with zipfile.ZipFile(archive) as bundle:
                self.assertIn("MANIFEST.private.json", bundle.namelist())

    def test_data_quality_keeps_duplicate_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            csv_path = Path(temp) / "items.csv"
            csv_path.write_text("platform,id,name\nx,1,A\nx,1,A copy\nx,2,B\n", encoding="utf-8")
            report = profile(csv_path, ["platform", "id"])
            self.assertEqual(report["rows"], 3)
            self.assertEqual(len(report["duplicate_candidates"]), 1)
            self.assertEqual(report["duplicate_candidates"][0]["rows"], [2, 3])

    def test_data_quality_reports_malformed_and_empty_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            csv_path = Path(temp) / "items.csv"
            csv_path.write_text("platform,id,name\nx,,A\ny\nz,3,C,extra\n", encoding="utf-8")
            report = profile(csv_path, ["platform", "id"])
            reasons = {item["reason"] for item in report["invalid_rows"]}
            self.assertIn("empty_stable_key_component", reasons)
            self.assertIn("missing_columns", reasons)
            self.assertIn("extra_columns", reasons)

    def test_action_manifest_is_plan_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            change = base / "change.json"
            fingerprints = base / "fingerprints.json"
            manifest = base / "manifest.json"
            change.write_text('{"field": {"from": "draft", "to": "ready"}}', encoding="utf-8")
            fingerprints.write_text('{"input": "abc123"}', encoding="utf-8")
            run_cli(
                sys.executable,
                str(SCRIPTS / "action_manifest.py"),
                "create",
                "--tenant", "tenant-a",
                "--profile", "profile-a",
                "--actor", "human-owner",
                "--action", "update-preview",
                "--target", "record-1",
                "--change", str(change),
                "--fingerprints", str(fingerprints),
                "--quantity", "1",
                "--cost-cap", "0",
                "--currency", "CNY",
                "--output", str(manifest),
            )
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "plan_only")
            run_cli(sys.executable, str(SCRIPTS / "action_manifest.py"), "validate", str(manifest))
            data["target"] = "record-2"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            run_cli(sys.executable, str(SCRIPTS / "action_manifest.py"), "validate", str(manifest), expect=1)

    def test_release_gate_scans_final_manifest_and_rejects_duplicate_destinations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source.md"
            source.write_text("# Public synthetic content\n", encoding="utf-8")
            source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            manifest = base / "allow.json"
            manifest.write_text(json.dumps({"items": [{
                "source": str(source), "destination": "docs/source.md", "taint": "publishable",
                "rights_status": "approved", "source_category": "synthetic", "source_sha256": source_hash
            }]}), encoding="utf-8")
            output = base / "release"
            run_cli(sys.executable, str(SCRIPTS / "release_gate.py"), str(manifest), "--output", str(output))
            self.assertTrue(run_scan(output, [])["safe_to_publish"])
            duplicate_manifest = base / "duplicates.json"
            duplicate_manifest.write_text(json.dumps({"items": [
                {"source": str(source), "source_sha256": source_hash, "destination": "same.md", "taint": "publishable", "rights_status": "approved"},
                {"source": str(source), "source_sha256": source_hash, "destination": "SAME.md", "taint": "publishable", "rights_status": "approved"}
            ]}), encoding="utf-8")
            run_cli(
                sys.executable, str(SCRIPTS / "release_gate.py"), str(duplicate_manifest),
                "--output", str(base / "duplicate-release"), expect=2,
            )


if __name__ == "__main__":
    unittest.main()
