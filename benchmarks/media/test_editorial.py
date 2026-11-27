import copy
import unittest
from PIL import Image, ImageChops
from engines.creative.wave2 import approve, verify
from engines.media.editorial import editorial_layout
from engines.media.wave2 import HD
from benchmarks.media import test_wave2


class EditorialTests(unittest.TestCase):
    def test_compositions_preserve_source(self):
        source = Image.new('RGB', (600, 400), '#dcad82')
        for size in HD.values():
            boxes = []
            for scene in range(3):
                for progress in (0, .5, 1):
                    frame, (x,y,w,h) = editorial_layout(source, 'Explore the collection', size, progress, scene)
                    self.assertGreaterEqual(x, 0)
                    self.assertGreaterEqual(y, 0)
                    self.assertLessEqual(x+w, size[0])
                    self.assertLessEqual(y+h, size[1])
                    self.assertIsNone(ImageChops.difference(frame.crop((x,y,x+w,y+h)), source.resize((w,h), Image.Resampling.LANCZOS)).getbbox())
                    self.assertAlmostEqual(w/h, 1.5, places=2)
                boxes.append((x,y,w,h))
            self.assertNotEqual(boxes[0], boxes[1])

    def test_presentation_bound_to_approval(self):
        fixture = test_wave2.Wave2Tests()
        fixture.setUp()
        try:
            board = copy.deepcopy(fixture.board)
            board['presentation'] = 'editorial-v1'
            approval = approve(board, 'reviewer', fixture.key)
            verify(board, approval, fixture.key)
            board['presentation'] = 'classic'
            with self.assertRaises(ValueError):
                verify(board, approval, fixture.key)
            board['presentation'] = 'unknown'
            with self.assertRaisesRegex(ValueError, 'unsupported presentation'):
                approve(board, 'reviewer', fixture.key)
        finally:
            fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
