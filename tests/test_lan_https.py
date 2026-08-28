from __future__ import annotations

import hashlib
import importlib.util
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "lan_https.py"
SPEC = importlib.util.spec_from_file_location("lan_https", TOOL)
assert SPEC and SPEC.loader
lan_https = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lan_https
SPEC.loader.exec_module(lan_https)


@unittest.skipUnless(shutil.which("openssl"), "OpenSSL is required")
class LanHttpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="chrome-lan-test.")
        self.base = Path(self.temporary.name)
        self.state = self.base / "state"
        self.site = self.base / "site"
        shutil.copytree(ROOT / "tests" / "fixtures" / "site", self.site)
        self._write_artifact_metadata()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_artifact_metadata(self) -> None:
        meta = self.site / "meta"
        meta.mkdir()
        publication = {
            "schemaVersion": 1,
            "repository": "devs-guide/chrome",
            "sourceRef": "test",
            "sourceSha": "0" * 40,
            "buildTime": "2026-01-01T00:00:00Z",
            "release": "test",
            "catalogVersion": "test",
            "artifactVersion": "1",
        }
        (meta / "publication.json").write_text(
            json.dumps(publication, sort_keys=True) + "\n", encoding="utf-8"
        )
        files = sorted(path for path in self.site.rglob("*") if path.is_file())
        (meta / "checksums.sha256").write_text(
            "".join(
                f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(self.site).as_posix()}\n"
                for path in files
            ),
            encoding="utf-8",
        )

    def run_cli(self, *arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(TOOL), *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def init(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "init", "--state-dir", str(self.state), "--root", str(self.site),
            "--ip", "127.0.0.1", *extra,
        )

    def test_initial_generation_and_matching_sans(self) -> None:
        self.init("--dns", "chrome.test")
        paths = lan_https.state_paths(self.state)
        self.assertTrue(paths.ca_key.is_file())
        self.assertTrue(paths.ca_der.is_file())
        self.assertTrue(paths.server_chain.is_file())
        self.assertEqual(
            lan_https.certificate_sans(paths.server_cert),
            (["127.0.0.1"], ["chrome.test"]),
        )
        self.assertEqual(paths.ca_key.stat().st_mode & 0o777, 0o600)
        self.assertEqual(paths.server_key.stat().st_mode & 0o777, 0o600)

    def test_init_is_idempotent_and_preserves_existing_ca(self) -> None:
        self.init()
        paths = lan_https.state_paths(self.state)
        ca_before = paths.ca_key.read_bytes()
        leaf_before = paths.server_cert.read_bytes()
        result = self.init()
        self.assertIn("preserved existing CA and matching leaf", result.stdout)
        self.assertEqual(paths.ca_key.read_bytes(), ca_before)
        self.assertEqual(paths.server_cert.read_bytes(), leaf_before)

    def test_renew_changes_leaf_and_retains_ca(self) -> None:
        self.init()
        paths = lan_https.state_paths(self.state)
        ca_before = paths.ca_key.read_bytes()
        leaf_before = paths.server_cert.read_bytes()
        self.run_cli(
            "renew", "--state-dir", str(self.state), "--root", str(self.site),
            "--ip", "127.0.0.1", "--dns", "touch.chrome.test",
        )
        self.assertEqual(paths.ca_key.read_bytes(), ca_before)
        self.assertNotEqual(paths.server_cert.read_bytes(), leaf_before)
        self.assertEqual(lan_https.certificate_sans(paths.server_cert)[1], ["touch.chrome.test"])

    def test_wrong_hostname_and_missing_ca_are_rejected(self) -> None:
        self.init()
        paths = lan_https.state_paths(self.state)
        good = subprocess.run(
            ["openssl", "verify", "-CAfile", str(paths.ca_cert), "-verify_ip", "127.0.0.1", str(paths.server_cert)],
            capture_output=True, check=False,
        )
        wrong = subprocess.run(
            ["openssl", "verify", "-CAfile", str(paths.ca_cert), "-verify_hostname", "wrong.test", str(paths.server_cert)],
            capture_output=True, check=False,
        )
        missing = subprocess.run(
            ["openssl", "verify", "-CAfile", str(self.base / "missing.pem"), str(paths.server_cert)],
            capture_output=True, check=False,
        )
        self.assertEqual(good.returncode, 0)
        self.assertNotEqual(wrong.returncode, 0)
        self.assertNotEqual(missing.returncode, 0)

    def test_doctor_verifies_tls_hostname_and_exact_bytes(self) -> None:
        self.init()
        result = self.run_cli(
            "doctor", "--state-dir", str(self.state), "--root", str(self.site),
            "--ip", "127.0.0.1", "--bind", "127.0.0.1", "--port", "0", "--json",
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["overallStatus"], "PASS")
        passed = {check["id"] for check in report["checks"] if check["status"] == "PASS"}
        self.assertIn("https-self-test", passed)
        self.assertFalse(report["data"]["deviceTrustVerified"])

    def test_missing_state_has_deterministic_diagnostic(self) -> None:
        result = self.run_cli("status", "--state-dir", str(self.state), "--json", expected=1)
        report = json.loads(result.stdout)
        self.assertFalse(report["caExists"])
        self.assertFalse(report["leafExists"])

    def test_san_mismatch_is_reported_with_renewal_guidance(self) -> None:
        self.init()
        result = self.run_cli(
            "doctor", "--state-dir", str(self.state), "--root", str(self.site),
            "--ip", "127.0.0.2", "--bind", "127.0.0.1", "--port", "0", "--json",
            expected=1,
        )
        report = json.loads(result.stdout)
        san = next(check for check in report["checks"] if check["id"] == "san-coverage")
        self.assertEqual(san["status"], "FAIL")
        self.assertIn("renew", san["remediation"])

    def test_clean_preserves_ca(self) -> None:
        self.init()
        paths = lan_https.state_paths(self.state)
        ca_before = paths.ca_key.read_bytes()
        self.run_cli("clean", "--state-dir", str(self.state), "--yes")
        self.assertEqual(paths.ca_key.read_bytes(), ca_before)
        self.assertFalse(paths.server_key.exists())

    def test_expired_certificate_time_is_diagnosed(self) -> None:
        self.init()
        paths = lan_https.state_paths(self.state)
        with self.assertRaisesRegex(lan_https.LanHttpsError, "expired"):
            lan_https.validity(
                paths.server_cert,
                now=dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=500),
            )

    def test_reset_requires_explicit_confirmation_without_changing_ca(self) -> None:
        self.init()
        paths = lan_https.state_paths(self.state)
        ca_before = paths.ca_key.read_bytes()
        result = self.run_cli(
            "reset-ca", "--state-dir", str(self.state), "--root", str(self.site),
            "--ip", "127.0.0.1", expected=1,
        )
        self.assertIn("RESET-LAN-CA", result.stderr)
        self.assertEqual(paths.ca_key.read_bytes(), ca_before)

    def test_repository_does_not_track_private_keys(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout.split(b"\0")
        suspicious = [path for path in tracked if path.endswith((b".key", b".key.pem"))]
        self.assertEqual(suspicious, [])


class InputValidationTests(unittest.TestCase):
    def test_unspecified_ip_is_not_a_certificate_identity(self) -> None:
        with self.assertRaises(lan_https.LanHttpsError):
            lan_https.validated_identities(["0.0.0.0"], [])

    def test_mount_rejects_traversal(self) -> None:
        with self.assertRaises(lan_https.LanHttpsError):
            lan_https.normalized_mount("/chrome/../secret")


if __name__ == "__main__":
    unittest.main()
