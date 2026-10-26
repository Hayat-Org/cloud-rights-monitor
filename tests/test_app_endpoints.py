import os
import tempfile
import unittest

try:
    from fastapi.testclient import TestClient
    import app as app_module
    from services import card_design as d
    HAVE_APP = True
except Exception:  # fastapi / feedparser / supabase not installed
    HAVE_APP = False


@unittest.skipUnless(HAVE_APP, "app dependencies not installed")
class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app_module.app)
        self._orig_dir, self._orig_secret = d.MEDIA_DIR, app_module.CRON_SECRET
        d.MEDIA_DIR = app_module.MEDIA_DIR = tempfile.mkdtemp()

    def tearDown(self):
        d.MEDIA_DIR = app_module.MEDIA_DIR = self._orig_dir
        app_module.CRON_SECRET = self._orig_secret

    def test_health(self):
        body = self.client.get("/").json()
        self.assertEqual(body["status"], "Online")
        self.assertIn("commit", body)

    def test_media_serves_saved_card_and_blocks_traversal(self):
        folder = os.path.join(d.MEDIA_DIR, "stories")
        os.makedirs(folder)
        with open(os.path.join(folder, "story_x.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff")
        self.assertEqual(self.client.get("/media/stories/story_x.jpg").status_code, 200)
        self.assertEqual(self.client.get("/media/stories/missing.jpg").status_code, 404)
        self.assertEqual(self.client.get("/media/secrets/story_x.jpg").status_code, 404)

    def test_preview_disabled_without_secret(self):
        app_module.CRON_SECRET = ""
        self.assertEqual(self.client.get("/preview/feed").status_code, 404)

    def test_diagnostics_disabled_without_secret(self):
        app_module.CRON_SECRET = ""
        self.assertEqual(self.client.get("/diagnostics").status_code, 404)

    def test_secret_required_when_configured(self):
        app_module.CRON_SECRET = "s3cret"
        self.assertEqual(self.client.get("/publish-queue").status_code, 401)
        self.assertEqual(self.client.get("/publish-queue", headers={"X-Cron-Secret": "wrong"}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
