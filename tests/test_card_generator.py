import tempfile
import unittest
from unittest import mock

from PIL import Image

from services import card_design as d
from services import card_generator as g


def _photo(*_a, **_k):
    return Image.new("RGB", (1600, 1000), (80, 100, 120))


class RenderTests(unittest.TestCase):
    def test_feed_card_size_with_photo(self):
        with mock.patch.object(d, "download_image", _photo):
            img = g.render_feed_card("Journalists detained", "", "http://x/y.jpg", "Amnesty International")
        self.assertEqual(img.size, g.FEED_SIZE)

    def test_story_card_size_with_photo(self):
        with mock.patch.object(d, "download_image", _photo):
            img = g.render_story_card("Journalists detained", "", "http://x/y.jpg")
        self.assertEqual(img.size, g.STORY_SIZE)

    def test_typographic_fallback_when_no_photo(self):
        with mock.patch.object(d, "download_image", lambda *a, **k: None):
            feed = g.render_feed_card("No photo available", "", None)
            story = g.render_story_card("No photo available", "", None)
        self.assertEqual(feed.size, g.FEED_SIZE)
        self.assertEqual(story.size, g.STORY_SIZE)

    def test_very_long_and_unicode_headlines_do_not_crash(self):
        long_title = "Ünïcödé headline – " + "very long words " * 40
        with mock.patch.object(d, "download_image", lambda *a, **k: None):
            self.assertEqual(g.render_feed_card(long_title).size, g.FEED_SIZE)
            self.assertEqual(g.render_story_card(long_title).size, g.STORY_SIZE)

    def test_story_text_stays_inside_safe_zone(self):
        # The footer block is the lowest element; it must end above the IG UI zone.
        self.assertLessEqual(g.STORY_SAFE_BOTTOM, g.STORY_SIZE[1] - 300)

    def test_generate_helpers_return_urls(self):
        d.MEDIA_DIR = tempfile.mkdtemp()
        with mock.patch.object(d, "download_image", lambda *a, **k: None):
            self.assertIn("/media/feed/", g.generate_feed_card("A title"))
            self.assertIn("/media/stories/", g.generate_story_card("A title"))

    def test_generate_helpers_never_raise(self):
        with mock.patch.object(g, "render_feed_card", side_effect=RuntimeError("boom")):
            self.assertIsNone(g.generate_feed_card("x"))


if __name__ == "__main__":
    unittest.main()
