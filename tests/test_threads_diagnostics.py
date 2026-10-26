import unittest
from unittest import mock

from services import diagnostics as dg
from services import threads as th


class Resp:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class DiagnosticsTests(unittest.TestCase):
    def setUp(self):
        dg.pop_errors()

    def test_user_id_mismatch_is_reported(self):
        with mock.patch.object(dg, "THREADS_ACCESS_TOKEN", "tok"), mock.patch.object(dg, "THREADS_USER_ID", "111"), \
                mock.patch.object(dg.requests, "get", return_value=Resp({"id": "999", "username": "acct"})):
            problems = dg.check_threads()
        self.assertEqual(len(problems), 1)
        self.assertIn("does not match", problems[0])

    def test_expired_token_is_reported(self):
        err = {"error": {"type": "OAuthException", "code": 190, "message": "Session has expired"}}
        with mock.patch.object(dg, "THREADS_ACCESS_TOKEN", "tok"), mock.patch.object(dg, "THREADS_USER_ID", "1"), \
                mock.patch.object(dg.requests, "get", return_value=Resp(err)):
            self.assertIn("rejected", dg.check_threads()[0])

    def test_ok_when_ids_match(self):
        with mock.patch.object(dg, "THREADS_ACCESS_TOKEN", "tok"), mock.patch.object(dg, "THREADS_USER_ID", "42"), \
                mock.patch.object(dg.requests, "get", return_value=Resp({"id": "42", "username": "a"})):
            self.assertEqual(dg.check_threads(), [])

    def test_missing_credentials(self):
        with mock.patch.object(dg, "THREADS_ACCESS_TOKEN", ""):
            self.assertIn("no access token", dg.check_threads()[0])

    def test_record_error_redacts_token(self):
        with mock.patch.object(dg, "THREADS_ACCESS_TOKEN", "SECRET123"):
            dg.record_error("Threads", "bad token SECRET123 here")
        self.assertNotIn("SECRET123", dg.pop_errors()["Threads"])


class ThreadsPostTests(unittest.TestCase):
    def setUp(self):
        dg.pop_errors()
        p1 = mock.patch.object(th, "THREADS_USER_ID", "1")
        p2 = mock.patch.object(th, "THREADS_ACCESS_TOKEN", "tok")
        p3 = mock.patch.object(th.time, "sleep", lambda *_: None)
        for p in (p1, p2, p3):
            p.start()
            self.addCleanup(p.stop)

    def test_image_failure_falls_back_to_text_only(self):
        calls = []

        def post(url, headers=None, params=None, timeout=None):
            calls.append((url.rsplit("/", 1)[-1], params.get("media_type")))
            if url.endswith("/threads") and params["media_type"] == "IMAGE":
                return Resp({"error": {"message": "bad image"}})
            return Resp({"id": "c1"}) if url.endswith("/threads") else Resp({"id": "post1"})

        with mock.patch.object(th.requests, "post", side_effect=post), \
                mock.patch.object(th.requests, "get", return_value=Resp({"status": "FINISHED"})):
            self.assertTrue(th.post_to_threads("hello", "https://x/y.jpg"))
        self.assertIn(("threads", "IMAGE"), calls)
        self.assertIn(("threads", "TEXT"), calls)

    def test_failure_records_api_error(self):
        err = {"error": {"message": "token expired", "code": 190}}
        with mock.patch.object(th.requests, "post", return_value=Resp(err)):
            self.assertFalse(th.post_to_threads("hello"))
        self.assertIn("token expired", dg.pop_errors()["Threads"])

    def test_waits_for_in_progress_container(self):
        states = iter([{"status": "IN_PROGRESS"}, {"status": "IN_PROGRESS"}, {"status": "FINISHED"}])
        with mock.patch.object(th.requests, "get", side_effect=lambda *a, **k: Resp(next(states))):
            self.assertTrue(th._wait_until_ready("c1", {}))


if __name__ == "__main__":
    unittest.main()
