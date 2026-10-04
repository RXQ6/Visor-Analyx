"""Packaging security: pinned RECORD allowlist and integrity failures."""
import base64
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "desktop/scripts/stage-packaging-deps.py"
spec = importlib.util.spec_from_file_location("packaged_dependencies", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackagedDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.target = self.root / "target"
        self.lock = self.root / "requirements.txt"
        self.lock.write_text("fixture==1.0\n")
        self.info = self.source / "fixture-1.0.dist-info"
        self.info.mkdir()
        (self.info / "METADATA").write_text("Metadata-Version: 2.1\nName: fixture\nVersion: 1.0\n")
        (self.source / "fixture.py").write_bytes(b"value = 1\n")
        digest = base64.urlsafe_b64encode(hashlib.sha256(b"value = 1\n").digest()).rstrip(b"=").decode()
        (self.info / "RECORD").write_text(f"fixture.py,sha256={digest},10\nfixture-1.0.dist-info/METADATA,,\nfixture-1.0.dist-info/RECORD,,\n")

    def test_unlisted_environment_file_and_external_wrapper_are_not_copied(self):
        (self.source / ".env").write_text("API_KEY=synthetic-test-only")
        with (self.info / "RECORD").open("a") as record:
            record.write("../Scripts/wrapper.exe,,\n")
        module.stage(self.source, self.target, self.lock)
        self.assertTrue((self.target / "fixture.py").is_file())
        self.assertFalse((self.target / ".env").exists())
        self.assertFalse((self.root / "Scripts").exists())

    def test_changed_wheel_payload_is_rejected(self):
        (self.source / "fixture.py").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "integrity"):
            module.stage(self.source, self.target, self.lock)

    def test_missing_recorded_file_is_rejected(self):
        (self.source / "fixture.py").unlink()
        with self.assertRaisesRegex(ValueError, "unavailable"):
            module.stage(self.source, self.target, self.lock)

    def test_unpinned_or_wrong_version_is_rejected(self):
        self.lock.write_text("fixture==2.0\n")
        with self.assertRaisesRegex(ValueError, "mismatched"):
            module.stage(self.source, self.target, self.lock)
        self.lock.write_text("other==1.0\n")
        with self.assertRaisesRegex(ValueError, "lock"):
            module.stage(self.source, self.target, self.lock)
