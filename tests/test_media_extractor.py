import base64
import unittest
from types import SimpleNamespace
from unittest import mock

from services import media_extractor as me

GN = "https://news.google.com/rss/articles/{}?oc=5"
FONTS = "https://fonts.googleapis.com/css?family=Google+Sans:400,500,700"


def _page(body, url="https://news.google.com/rss/articles/x", status=200):
    return SimpleNamespace(text=body, url=url, status_code=status)


class ValidUrlTests(unittest.TestCase):
    def test_google_owned_hosts_rejected(self):
        for u in (FONTS, "https://www.gstatic.com/a/b", "https://lh3.googleusercontent.com/x/y",
                  "https://support.google.com/news/answer/1", "https://www.youtube.com/watch?v=1"):
            self.assertFalse(me.is_valid_article_url(u), u)

    def test_publisher_article_accepted(self):
        self.assertTrue(me.is_valid_article_url("https://www.hrw.org/news/2026/10/26/some-report"))


class ResolveGoogleNewsTests(unittest.TestCase):
    def test_non_google_url_untouched(self):
        self.assertEqual(me.resolve_google_news_url("https://www.hrw.org/a"), "https://www.hrw.org/a")

    def test_fonts_url_is_never_returned_and_original_is_kept(self):
        """Regression: every Google News item used to resolve to the same fonts URL."""
        url = GN.format("AU_unresolvable_token_1")
        page = _page(f'<link href="{FONTS}"><script src="https://www.gstatic.com/x/y.js"></script>')
        with mock.patch.object(me.requests, "get", return_value=page):
            self.assertEqual(me.resolve_google_news_url(url), url)

    def test_different_articles_stay_distinct(self):
        page = _page(f'<link href="{FONTS}">')
        with mock.patch.object(me.requests, "get", return_value=page):
            a = me.resolve_google_news_url(GN.format("AU_aaaaaaaa"))
            b = me.resolve_google_news_url(GN.format("AU_bbbbbbbb"))
        self.assertNotEqual(a, b)

    def test_real_publisher_link_in_page_is_used(self):
        real = "https://www.amnesty.org/en/latest/news/2026/10/a-real-story"
        page = _page(f'<link href="{FONTS}"><a href="{real}">read</a>')
        with mock.patch.object(me.requests, "get", return_value=page):
            self.assertEqual(me.resolve_google_news_url(GN.format("AU_cccccccc")), real)

    def test_http_redirect_to_publisher_is_used(self):
        real = "https://cpj.org/2026/10/journalist-detained/"
        with mock.patch.object(me.requests, "get", return_value=_page("", url=real)):
            self.assertEqual(me.resolve_google_news_url(GN.format("AU_dddddddd")), real)

    def test_old_style_token_decoded_without_network(self):
        real = "https://www.example.org/news/2026/some-article"
        token = base64.urlsafe_b64encode(b"\x08\x13\x22" + bytes([len(real)]) + real.encode() + b"\xd2\x01\x00").decode().rstrip("=")
        with mock.patch.object(me.requests, "get", side_effect=AssertionError("no network expected")):
            self.assertEqual(me.resolve_google_news_url(GN.format(token)), real)

    def test_network_error_returns_original(self):
        url = GN.format("AU_eeeeeeee")
        with mock.patch.object(me.requests, "get", side_effect=RuntimeError("down")):
            self.assertEqual(me.resolve_google_news_url(url), url)


if __name__ == "__main__":
    unittest.main()
