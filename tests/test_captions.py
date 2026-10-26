import unittest

from services import captions as c


class CaptionTests(unittest.TestCase):
    def test_threads_within_limit_and_has_credit_and_link(self):
        out = c.build_threads_caption("x" * 900, link="https://hrw.org/a", source="Human Rights Watch")
        self.assertLessEqual(len(out), 500)
        self.assertIn("Source: Human Rights Watch", out)
        self.assertTrue(out.endswith("https://hrw.org/a"))

    def test_threads_strips_hashtags(self):
        self.assertNotIn("#", c.build_threads_caption("Hello #world #rights"))

    def test_instagram_moves_hashtags_to_end_deduped(self):
        out = c.build_instagram_caption("Story #A text #a more #B", source="UN News")
        body, tag_line = out.rsplit("\n\n", 1)
        self.assertEqual(tag_line.split(), ["#A", "#B"])
        self.assertIn("Source: UN News", body)

    def test_instagram_default_hashtags_and_limit(self):
        out = c.build_instagram_caption("y" * 5000)
        self.assertLessEqual(len(out), 2200)
        self.assertIn("#HumanRights", out)

    def test_fallback_drafts_shape(self):
        d = c.fallback_drafts("Title", "Snippet text")
        self.assertEqual(set(d), {"threads", "instagram"})
        self.assertIn("#HumanRights", d["instagram"])


if __name__ == "__main__":
    unittest.main()
