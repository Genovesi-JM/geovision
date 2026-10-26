import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

from starlette.testclient import TestClient


class PublicSiteRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'public').mkdir()
        (root / 'public' / 'index.html').write_text('Public homepage')
        (root / 'public' / 'login.html').write_text('Sign in')
        shutil.copyfile(Path(__file__).with_name('site.py'), root / 'site.py')
        spec = importlib.util.spec_from_file_location('qa_static_site', root / 'site.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.app = module.app

    def test_www_moves_signin_to_callback_origin_and_keeps_destination(self):
        with TestClient(self.app, base_url='https://www.geovisionops.com') as client:
            response = client.get('/login.html?return=%2Fdashboard.html%3Fview%3Dmap', follow_redirects=False)
            self.assertEqual(response.status_code, 308)
            self.assertEqual(response.headers['location'], 'https://geovisionops.com/login.html?return=%2Fdashboard.html%3Fview%3Dmap')
            self.assertIn('max-age=', response.headers['strict-transport-security'])

    def test_apex_and_azure_health_remain_available_without_redirect(self):
        for origin in ('https://geovisionops.com', 'https://preview.azurecontainerapps.io'):
            with self.subTest(origin=origin), TestClient(self.app, base_url=origin) as client:
                self.assertEqual(client.get('/').text, 'Public homepage')
                self.assertEqual(client.get('/_site/health').json()['status'], 'ok')
                self.assertEqual(client.get('/backend/.env').status_code, 404)


if __name__ == '__main__':
    unittest.main()
