import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("public_web_builder", Path(__file__).with_name("build_site.py"))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PublicSiteArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.output = self.root / "site"
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        for name in ("index.html", "login.html", "assets/js/config.js", "assets/js/module.mjs", "assets/videos/demo.mp4"):
            self.write(name, b"public content")
        self.write("backend/.env", b"PRIVATE_BUILD_SECRET_CANARY", tracked=False)

    def write(self, name, content, tracked=True):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        if tracked:
            subprocess.run(["git", "add", "--", name], cwd=self.repo, check=True)

    def test_only_public_inputs_with_canonical_api_and_media(self):
        result = builder.prepare_site(self.repo, self.output)
        self.assertNotIn("backend/.env", result["files"])
        self.assertIn("assets/js/module.mjs", result["files"])
        self.assertIn("assets/videos/demo.mp4", result["files"])
        self.assertIn(builder.API_ORIGIN, (self.output / "assets/js/config.js").read_text())
        self.assertEqual((self.repo / "assets/js/config.js").read_bytes(), b"public content")

    def test_rejects_tracked_sensitive_asset_before_writing(self):
        self.write("assets/credentials.json", b"{}")
        with self.assertRaises(builder.guard.UnsafeBuildInput):
            builder.prepare_site(self.repo, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_secret_material_under_ordinary_asset_name(self):
        self.write("assets/config.json", b"PRIVATE_BUILD_SECRET_CANARY")
        with self.assertRaises(builder.guard.UnsafeBuildInput):
            builder.prepare_site(self.repo, self.output)
        self.assertFalse(self.output.exists())

    def test_rejects_symlink_source(self):
        path = self.repo / "assets/js/module.mjs"
        path.unlink()
        path.symlink_to(self.repo / "backend/.env")
        with self.assertRaises(builder.guard.UnsafeBuildInput):
            builder.prepare_site(self.repo, self.output)

    def test_rejects_source_tree_output(self):
        with self.assertRaises(builder.guard.UnsafeBuildInput):
            builder.prepare_site(self.repo, self.repo / "dist")

    def test_refuses_nonempty_output(self):
        self.output.mkdir()
        (self.output / "unrelated.txt").write_text("keep")
        with self.assertRaises(builder.guard.UnsafeBuildInput):
            builder.prepare_site(self.repo, self.output)


if __name__ == "__main__":
    unittest.main()
