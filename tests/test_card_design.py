import unittest

from PIL import Image, ImageDraw

from services import card_design as d


class CategoryTests(unittest.TestCase):
    def test_press_freedom_detected(self):
        label, _ = d.detect_category("Journalist detained as censorship grows", "")
        self.assertIn(label, {"PRESS FREEDOM", "POLITICAL PRISONERS"})

    def test_default_when_no_keywords(self):
        label, _ = d.detect_category("Quarterly update", "")
        self.assertEqual(label, d.DEFAULT_CATEGORY[0])

    def test_title_outweighs_snippet(self):
        label, _ = d.detect_category("War crimes probe opens", "a court of law hears a trial")
        self.assertEqual(label, "WAR CRIMES")


class TextHelpersTests(unittest.TestCase):
    def test_clean_headline_strips_outlet_suffix(self):
        self.assertEqual(d.clean_headline("Rights abuses rise - Amnesty International"), "Rights abuses rise")

    def test_clean_headline_keeps_inner_dash_titles(self):
        self.assertEqual(d.clean_headline("Hope - and fear"), "Hope - and fear")

    def test_clean_headline_empty(self):
        self.assertEqual(d.clean_headline(""), "Human rights update")

    def test_source_label_known_and_unknown(self):
        self.assertEqual(d.source_label("https://www.hrw.org/news/2026/x"), "Human Rights Watch")
        self.assertEqual(d.source_label("https://news.un.org/en/story/1"), "UN News")
        self.assertEqual(d.source_label("https://example.com/a"), "")

    def test_fit_text_respects_height_and_lines(self):
        draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        text = "word " * 60
        font, lines = d.fit_text(draw, text.strip(), 900, 6, 80, 30, max_height=500)
        self.assertLessEqual(len(lines), 6)
        self.assertLessEqual(len(lines) * int(font.size * d.LINE_SPACING), 500)
        for line in lines:
            self.assertLessEqual(draw.textlength(line, font=font), 900 + 1)

    def test_fit_text_truncates_with_ellipsis_when_impossible(self):
        draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        _, lines = d.fit_text(draw, "supercalifragilistic " * 200, 400, 2, 40, 30, max_height=90)
        self.assertTrue(lines[-1].endswith("…"))


class ImageHelpersTests(unittest.TestCase):
    def test_cover_crop_exact_size(self):
        for size in [(2000, 500), (500, 2000), (1080, 1080)]:
            out = d.cover_crop(Image.new("RGB", size, "red"), 1080, 1350)
            self.assertEqual(out.size, (1080, 1350))

    def test_download_rejects_non_http(self):
        self.assertIsNone(d.download_image(""))
        self.assertIsNone(d.download_image("ftp://x/y.jpg"))

    def test_save_card_writes_jpeg_and_url(self):
        import os, tempfile
        d.MEDIA_DIR = tempfile.mkdtemp()
        path, url = d.save_card(Image.new("RGB", (100, 100), "blue"), "feed", "t")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(url.endswith(os.path.basename(path)))
        self.assertIn("/media/feed/", url)


if __name__ == "__main__":
    unittest.main()
