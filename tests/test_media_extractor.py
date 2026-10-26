import base64
import json
import unittest
from urllib.parse import unquote
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


def _batch_response(url):
    """Shape of Google's batchexecute reply: a header, a blank line, then a JSON list."""
    inner = json.dumps(["garturlres", url, 1])
    rows = [["wrb.fr", "Fbv4je", inner, None, None, None, "generic"], ["di", 12], ["af.httprm", 12, "-1", 5]]
    return SimpleNamespace(text=")]}'\n\n" + json.dumps(rows) + "\n", status_code=200)


SIGNED_PAGE = _page('<c-wiz><div jscontroller="x" data-n-a-sg="SIG123" data-n-a-ts="1761470000"></div></c-wiz>')


class ResolveGoogleNewsTests(unittest.TestCase):
    def setUp(self):
        me.resolve_google_news_url.cache_clear()

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

    def test_new_style_link_is_decoded_via_google(self):
        real = "https://www.hrw.org/news/2026/10/26/mali-report"
        url = GN.format("AU_newstyle_token")
        with mock.patch.object(me.requests, "get", return_value=SIGNED_PAGE), \
                mock.patch.object(me.requests, "post", return_value=_batch_response(real)) as post:
            self.assertEqual(me.resolve_google_news_url(url), real)
        sent = unquote(post.call_args.kwargs["data"])
        for expected in ("AU_newstyle_token", "SIG123", "1761470000", "garturlreq"):
            self.assertIn(expected, sent)

    def test_unparseable_response_still_found_by_fallback_pattern(self):
        real = "https://cpj.org/2026/10/some-story/"
        garbled = SimpleNamespace(text='garbage \\"garturlres\\",\\"' + real + '\\",1', status_code=200)
        with mock.patch.object(me.requests, "get", return_value=SIGNED_PAGE), \
                mock.patch.object(me.requests, "post", return_value=garbled):
            self.assertEqual(me.resolve_google_news_url(GN.format("AU_garbled_token")), real)

    def test_missing_signature_keeps_original_and_skips_post(self):
        url = GN.format("AU_nosig_token")
        with mock.patch.object(me.requests, "get", return_value=_page("<html>consent page</html>")), \
                mock.patch.object(me.requests, "post") as post:
            self.assertEqual(me.resolve_google_news_url(url), url)
        post.assert_not_called()

    def test_decoded_google_url_is_rejected(self):
        url = GN.format("AU_googleurl_token")
        with mock.patch.object(me.requests, "get", return_value=SIGNED_PAGE), \
                mock.patch.object(me.requests, "post", return_value=_batch_response(FONTS)):
            self.assertEqual(me.resolve_google_news_url(url), url)

    def test_post_error_keeps_original(self):
        url = GN.format("AU_posterror_token")
        with mock.patch.object(me.requests, "get", return_value=SIGNED_PAGE), \
                mock.patch.object(me.requests, "post", side_effect=RuntimeError("429")):
            self.assertEqual(me.resolve_google_news_url(url), url)

    def test_result_is_cached_per_link(self):
        real = "https://www.hrw.org/news/2026/10/26/mali-report"
        url = GN.format("AU_cached_token")
        with mock.patch.object(me.requests, "get", return_value=SIGNED_PAGE) as get, \
                mock.patch.object(me.requests, "post", return_value=_batch_response(real)):
            me.resolve_google_news_url(url)
            calls_after_first = get.call_count
            self.assertEqual(me.resolve_google_news_url(url), real)
        self.assertEqual(get.call_count, calls_after_first)

    def test_network_error_returns_original(self):
        url = GN.format("AU_eeeeeeee")
        with mock.patch.object(me.requests, "get", side_effect=RuntimeError("down")):
            self.assertEqual(me.resolve_google_news_url(url), url)


if __name__ == "__main__":
    unittest.main()


class PageImageTests(unittest.TestCase):
    BASE = "https://www.example.org/news/2026/story"

    def test_relative_og_image_made_absolute(self):
        html = '<meta property="og:image" content="/media/2026/photo.jpg">'
        self.assertEqual(me.extract_image_from_html(html, self.BASE), "https://www.example.org/media/2026/photo.jpg")

    def test_protocol_relative_and_entities(self):
        html = '<meta name="twitter:image" content="//cdn.example.org/p.jpg?a=1&amp;b=2">'
        self.assertEqual(me.extract_image_from_html(html, self.BASE), "https://cdn.example.org/p.jpg?a=1&b=2")

    def test_content_before_property_order(self):
        html = '<meta content="https://img.example.org/a.jpg" property="og:image">'
        self.assertEqual(me.extract_image_from_html(html, self.BASE), "https://img.example.org/a.jpg")

    def test_generic_logo_skipped_for_json_ld_photo(self):
        html = ('<meta property="og:image" content="https://www.example.org/static/site-logo.png">'
                '<script type="application/ld+json">{"@type":"NewsArticle","image":{"url":"https://img.example.org/real.jpg"}}</script>')
        self.assertEqual(me.extract_image_from_html(html, self.BASE), "https://img.example.org/real.jpg")

    def test_json_ld_list_and_graph(self):
        html = ('<script type="application/ld+json">{"@graph":[{"@type":"WebPage"},'
                '{"@type":"NewsArticle","image":["https://img.example.org/one.jpg","https://img.example.org/two.jpg"]}]}</script>')
        self.assertEqual(me.extract_image_from_html(html, self.BASE), "https://img.example.org/one.jpg")

    def test_bad_json_ld_ignored_and_nothing_found(self):
        self.assertEqual(me.extract_image_from_html('<script type="application/ld+json">{oops</script>', self.BASE), "")
        self.assertEqual(me.extract_image_from_html("", self.BASE), "")

    def test_placeholders_rejected(self):
        for u in ("https://x.org/img/placeholder.jpg", "https://x.org/default-share.png", "https://x.org/a/no-image.png"):
            self.assertFalse(me.is_valid_news_image(u), u)
        self.assertTrue(me.is_valid_news_image("https://x.org/uploads/2026/10/protest-crowd.jpg"))


class DownloadImageTests(unittest.TestCase):
    @staticmethod
    def _png(size):
        import io, random
        from PIL import Image
        random.seed(1)
        img = Image.new("RGB", size)
        img.putdata([(random.randrange(256), random.randrange(256), random.randrange(256)) for _ in range(size[0] * size[1])])
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def _get(self, size, status=200):
        return SimpleNamespace(status_code=status, content=self._png(size))

    def test_normal_photo_accepted_and_referer_sent(self):
        from services import card_design as d
        with mock.patch.object(d.requests, "get", return_value=self._get((600, 400))) as get:
            self.assertIsNotNone(d.download_image("https://cdn.example.org/a/photo.jpg"))
        self.assertEqual(get.call_args.kwargs["headers"]["Referer"], "https://cdn.example.org/")

    def test_wide_banner_and_tall_strip_rejected(self):
        from services import card_design as d
        for size in ((1600, 300), (250, 900)):
            with mock.patch.object(d.requests, "get", return_value=self._get(size)):
                self.assertIsNone(d.download_image("https://cdn.example.org/x.png"), size)

    def test_error_status_rejected(self):
        from services import card_design as d
        with mock.patch.object(d.requests, "get", return_value=self._get((600, 400), status=403)):
            self.assertIsNone(d.download_image("https://cdn.example.org/x.png"))
