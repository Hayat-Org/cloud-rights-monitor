import unittest

from PIL import Image, ImageDraw

from services import card_design as d
from services import card_glyphs as gl


class GlyphTests(unittest.TestCase):
    def test_every_category_has_its_own_glyph(self):
        labels = [c[0] for c in d.CATEGORIES]
        self.assertEqual(set(labels), set(gl.GLYPH_FOR_CATEGORY))
        self.assertEqual(len({gl.glyph_for(l) for l in labels}), len(labels), "glyphs must be distinct")

    def test_unknown_category_falls_back_to_globe(self):
        self.assertIs(gl.glyph_for(d.DEFAULT_CATEGORY[0]), gl.globe)
        self.assertIs(gl.glyph_for("SOMETHING NEW"), gl.globe)

    def test_each_glyph_draws_and_stays_inside_its_square(self):
        r, cx, cy, margin = 100, 250, 250, 14   # margin allows for the stroke width
        for fn in list(gl.GLYPH_FOR_CATEGORY.values()) + [gl.globe]:
            layer = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
            fn(ImageDraw.Draw(layer), cx, cy, r, (255, 255, 255, 255))
            box = layer.getchannel("A").getbbox()
            self.assertIsNotNone(box, fn.__name__)
            self.assertGreaterEqual(box[0], cx - r - margin, fn.__name__)
            self.assertGreaterEqual(box[1], cy - r - margin, fn.__name__)
            self.assertLessEqual(box[2], cx + r + margin, fn.__name__)
            self.assertLessEqual(box[3], cy + r + margin, fn.__name__)


if __name__ == "__main__":
    unittest.main()
