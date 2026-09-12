"""Offline packaging contracts. Fixtures contain no real credentials."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('gateway_context_under_test', HERE / 'build_context.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='geovision-gateway-build-test-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / 'repo'
        self.repo.mkdir()
        self.output = self.base / 'context'
        self.tracked = ['admin.html', 'login.html', 'assets/js/auth.js', 'assets/css/style.css']
        self.put('admin.html', b'<!doctype html><html><head><script src="assets/js/auth.js"></script></head><body>Admin</body></html>')
        self.put('login.html', b'<html><HEAD lang="en"><script src="assets/js/auth.js"></script></HEAD><body>Login</body></html>')
        self.put('assets/js/auth.js', b'window.syntheticFixture = true;\n')
        self.put('assets/css/style.css', b'body { margin: 0; }\n')
        self.put('infra/azure/online_gateway/gateway.py', b'# synthetic gateway fixture\n')
        self.put('infra/azure/online_gateway/Dockerfile', (HERE / 'Dockerfile').read_bytes())
        blocker = patch.object(builder.subprocess, 'run', side_effect=AssertionError('Subprocess/network operations are forbidden by default'))
        blocker.start()
        self.addCleanup(blocker.stop)

    def put(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def build(self):
        with patch.object(builder, 'tracked_paths', return_value=self.tracked):
            return builder.prepare_context(self.repo, self.output)

    def test_source_only_manifest_matches_transformed_bytes(self):
        original = {name: (self.repo / name).read_bytes() for name in self.tracked}
        summary = self.build()
        manifest_bytes = (self.output / 'manifest.json').read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(set(manifest), {'files'})
        self.assertEqual(set(manifest['files']), set(self.tracked))
        self.assertEqual(summary['manifest_sha256'], hashlib.sha256(manifest_bytes).hexdigest())
        for name, digest in manifest['files'].items():
            content = (self.output / 'public' / name).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), digest)
            self.assertEqual((self.repo / name).read_bytes(), original[name])
        self.assertEqual(summary['gateway_sha256'], hashlib.sha256((self.output / 'gateway.py').read_bytes()).hexdigest())

    def test_runtime_config_precedes_existing_scripts_on_all_html(self):
        self.build()
        for page in ('admin.html', 'login.html'):
            content = (self.output / 'public' / page).read_bytes()
            self.assertEqual(content.count(builder.CONFIG_SCRIPT), 1)
            self.assertLess(content.index(builder.CONFIG_SCRIPT), content.index(b'<script src="assets/js/auth.js"'))

    def test_optional_contact_and_chat_scripts_disabled_only_in_artifact(self):
        for name in builder.NOOP_FILES:
            self.put(name, b'fetch("https://example.invalid/external-integration");')
            self.tracked.append(name)
        self.build()
        for name in builder.NOOP_FILES:
            self.assertEqual((self.output / 'public' / name).read_bytes(), builder.NOOP_CONTENT)
            self.assertIn(b'fetch', (self.repo / name).read_bytes())

    def test_untracked_private_files_and_infra_tests_never_enter_context(self):
        for name in ('.env', 'backend/.env', 'assets/untracked.json', 'infra/azure/online_gateway/test_gateway.py'):
            self.put(name, b'PRIVATE_BUILD_SECRET_CANARY')
        self.build()
        actual = {str(path.relative_to(self.output)) for path in self.output.rglob('*') if path.is_file()}
        self.assertEqual(actual, {'Dockerfile', '.dockerignore', 'gateway.py', 'manifest.json'} | {'public/' + name for name in self.tracked})
        self.assertNotIn(b'PRIVATE_BUILD_SECRET_CANARY', b''.join(path.read_bytes() for path in self.output.rglob('*') if path.is_file()))

    def test_sensitive_tracked_asset_names_fail_before_output_creation(self):
        for name in ('assets/.env', 'assets/credentials.json', 'assets/private/config.json', 'assets/db-backup.json', 'assets/passwords.json', 'assets/access-token.json'):
            with self.subTest(name=name):
                self.put(name, b'fixture')
                with patch.object(builder, 'tracked_paths', return_value=self.tracked + [name]), self.assertRaises(builder.UnsafeBuildInput):
                    builder.prepare_context(self.repo, self.output)
                self.assertFalse(self.output.exists())

    def test_private_key_content_fails_even_under_public_filename(self):
        for content in (b'-----BEGIN PRIVATE KEY-----\nfixture', b'-----BEGIN RSA PRIVATE KEY-----', b'PRIVATE_BUILD_SECRET_CANARY'):
            with self.subTest(content=content):
                self.put('assets/data.json', content)
                with patch.object(builder, 'tracked_paths', return_value=self.tracked + ['assets/data.json']), self.assertRaises(builder.UnsafeBuildInput):
                    builder.prepare_context(self.repo, self.output)
                self.assertFalse(self.output.exists())

    def test_symlink_file_is_rejected_even_if_target_is_inside_repo(self):
        (self.repo / 'assets' / 'linked.js').symlink_to(self.repo / 'assets' / 'js' / 'auth.js')
        self.tracked.append('assets/linked.js')
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()
        self.assertFalse(self.output.exists())

    def test_symlink_directory_escape_is_rejected(self):
        external = self.base / 'external'
        external.mkdir()
        (external / 'data.json').write_text('PRIVATE_BUILD_SECRET_CANARY')
        (self.repo / 'assets' / 'escaped').symlink_to(external, target_is_directory=True)
        self.tracked.append('assets/escaped/data.json')
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()
        self.assertFalse(self.output.exists())

    def test_traversal_absolute_backslash_and_control_names_are_rejected(self):
        for name in ('../outside.html', '/absolute.html', 'assets/../data.json', 'assets\\data.json', 'assets//data.json', 'assets/a\n.json', 'assets/a\x7f.json', 'assets/a%20b.png', 'assets/a?b.png', 'assets/a#b.png'):
            with self.subTest(name=name), self.assertRaises(builder.UnsafeBuildInput):
                builder.checked_relative(name)

    def test_existing_nonempty_output_is_never_overwritten(self):
        self.output.mkdir()
        canary = self.output / 'keep.txt'
        canary.write_text('user-owned')
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()
        self.assertEqual(canary.read_text(), 'user-owned')

    def test_output_cannot_be_source_root_or_any_descendant(self):
        for output in (self.repo, self.repo / 'build', self.repo / 'infra' / 'output'):
            with self.subTest(output=output), self.assertRaises(builder.UnsafeBuildInput):
                builder.prepare_context(self.repo, output)

    def test_output_symlink_is_rejected(self):
        directory = self.base / 'other'
        directory.mkdir()
        self.output.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()
        self.assertFalse(any(directory.iterdir()))

    def test_gateway_source_symlink_is_rejected(self):
        gateway = self.repo / 'infra/azure/online_gateway/gateway.py'
        gateway.unlink()
        gateway.symlink_to(self.repo / 'assets/js/auth.js')
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()

    def test_nested_html_video_and_non_allowlisted_suffixes_are_excluded(self):
        excluded = ('emails/reset-password.html', 'assets/videos/demo.mp4', 'assets/js/config.mjs', 'assets/archive.zip')
        for name in excluded:
            self.put(name, b'ignored fixture')
            self.tracked.append(name)
        self.build()
        manifest = json.loads((self.output / 'manifest.json').read_bytes())
        self.assertFalse(set(excluded) & set(manifest['files']))

    def test_existing_public_reset_password_page_is_not_a_password_export(self):
        self.put('reset-password.html', b'<html><head></head><body>Reset UI</body></html>')
        self.tracked.append('reset-password.html')
        self.build()
        self.assertTrue((self.output / 'public/reset-password.html').is_file())

    def test_malformed_html_missing_head_fails_closed(self):
        self.put('login.html', b'<html><body>No head</body></html>')
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()

    def test_script_before_head_is_rejected_instead_of_preceding_runtime_config(self):
        self.put('login.html', b'<script>early()</script><html><head></head></html>')
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()

    def test_unicode_spaces_and_parentheses_in_images_are_preserved(self):
        name = 'assets/img/Construção (mapa técnico).png'
        self.put(name, b'synthetic bitmap fixture')
        self.tracked.append(name)
        self.build()
        manifest = json.loads((self.output / 'manifest.json').read_bytes())
        self.assertEqual(manifest['files'][name], hashlib.sha256(b'synthetic bitmap fixture').hexdigest())

    def test_required_pages_must_be_indexed(self):
        self.tracked.remove('admin.html')
        with self.assertRaises(builder.UnsafeBuildInput):
            self.build()

    def test_duplicate_index_paths_are_deduplicated(self):
        self.tracked += ['login.html', 'admin.html']
        self.assertEqual(self.build()['files'], 4)

    def test_manifest_is_deterministic_for_index_order(self):
        first = self.build()
        self.output = self.base / 'second-context'
        self.tracked.reverse()
        self.assertEqual(self.build(), first)

    def test_file_and_total_size_limits_are_enforced(self):
        with patch.object(builder, 'MAX_FILE_BYTES', 5), self.assertRaises(builder.UnsafeBuildInput):
            self.build()
        with patch.object(builder, 'MAX_CONTEXT_BYTES', 5), self.assertRaises(builder.UnsafeBuildInput):
            self.build()
        self.assertFalse(self.output.exists())

    def test_git_inventory_uses_no_shell_and_only_static_pathspecs(self):
        response = types.SimpleNamespace(stdout=b'login.html\0assets/js/auth.js\0')
        with patch.object(builder.subprocess, 'run', return_value=response) as run:
            self.assertEqual(builder.tracked_paths(self.repo), ['login.html', 'assets/js/auth.js'])
        run.assert_called_once_with(['git', 'ls-files', '-z', '--', '*.html', 'assets/**'], cwd=self.repo, capture_output=True, check=True, timeout=30)

    def test_image_validation_requires_exact_repository_lowercase_digest(self):
        digest = 'sha256:' + 'a' * 64
        self.assertEqual(builder.validate_gateway_image(builder.GATEWAY_REPOSITORY + '@' + digest), digest)
        for image in (builder.GATEWAY_REPOSITORY + ':latest', builder.GATEWAY_REPOSITORY + '@sha256:' + 'A' * 64, builder.GATEWAY_REPOSITORY + '@sha256:abc', 'other.azurecr.io/geovision-online-gateway@' + digest, builder.GATEWAY_REPOSITORY + '@' + digest + '/x', None):
            with self.subTest(image=image), self.assertRaises(builder.UnsafeBuildInput):
                builder.validate_gateway_image(image)


class InfrastructureContractTests(unittest.TestCase):
    def test_additive_template_default_private_identity_pull_only_and_small_scale(self):
        source = (HERE / 'online.bicep').read_text()
        self.assertIn('param externalIngress bool = false', source)
        self.assertIn("lifecycle: 'None'", source)
        self.assertIn('secrets: []', source)
        self.assertIn('minReplicas: 0', source)
        self.assertIn('maxReplicas: 1', source)
        self.assertIn("cpu: json('0.25')", source)
        self.assertIn("memory: '0.5Gi'", source)
        self.assertIn("geovision-online-gateway", source)
        self.assertEqual(source.count("resource gateway 'Microsoft.App/containerApps"), 1)
        for forbidden in ('roleAssignments@', 'database-url', 'ACCOUNTS_DATABASE_URL', 'SECRET_KEY', 'Microsoft.Network/', 'apiExternalIngress'):
            self.assertNotIn(forbidden, source)

    def test_dockerfile_has_fixed_base_explicit_copies_no_backend_start(self):
        source = (HERE / 'Dockerfile').read_text()
        self.assertIn('geovision-backend@sha256:37e0280a688c9ae8915c4adec00c83b9ff2895f28c11a0a18d986f0f4dc1de00', source)
        self.assertIn('USER 10001:10001', source)
        self.assertIn('ENTRYPOINT ["python", "/gateway/gateway.py"]', source)
        self.assertIn('CMD []', source)
        self.assertIn('/_gateway/health', source)
        self.assertNotIn('COPY .', source)
        self.assertNotIn('start.py', source)
        self.assertNotIn('pip install', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
