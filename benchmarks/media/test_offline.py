import unittest
import tempfile
from pathlib import Path
from PIL import Image
from engines.creative.planner import inspect, rank, storyboard, digest
from engines.media.render import edges_for, render


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.brief=dict(audience='young adults',occasion='evergreen',goal='awareness',industry='retail',emotion='excited',platform='reels')
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'source.png'; Image.new('RGB',(60,40),'red').save(self.path)
        self.asset=dict(path=str(self.path),rights_confirmed=True,**inspect(self.path))
        self.board=storyboard(self.brief,'rhythm',[self.asset]*3,['One','Two','Three'])

    def test_image(self):
        self.assertEqual((self.asset['width'],self.asset['height']),(60,40))
        self.assertEqual(self.asset['palette'][0],[255,0,0])
        self.assertEqual(self.asset['semantic_status'],'unverified')

    def test_ranking(self):
        self.assertEqual(rank(self.brief)[0]['id'],'rhythm')
        with self.assertRaises(ValueError): rank({})

    def test_rights(self):
        with self.assertRaises(ValueError): storyboard(self.brief,'rhythm',[dict(self.asset,rights_confirmed=False)]*3,['a']*3)

    def test_bad_caption(self):
        with self.assertRaises(ValueError): storyboard(self.brief,'rhythm',[self.asset]*3,['a\nb']*3)

    def test_approval(self):
        approved=digest(self.board); self.board['scenes'][0]['caption']='Changed'
        with self.assertRaisesRegex(ValueError,'approval mismatch'): render(self.board,approved,'unused.wav','9:16','unused.mp4')

    def test_timing(self):
        self.assertEqual(edges_for(self.board,[i/2 for i in range(13)]),[0,48,96,144])
        with self.assertRaises(ValueError): edges_for(self.board,[0,1])
        with self.assertRaises(ValueError): edges_for(self.board,[i/100 for i in range(13)])

    def test_tamper(self):
        from unittest.mock import patch
        approved=digest(self.board); Image.new('RGB',(60,40),'blue').save(self.path)
        with patch('engines.media.render.beat_times',return_value=[i/2 for i in range(13)]):
            with self.assertRaisesRegex(ValueError,'unapproved asset'): render(self.board,approved,'unused.wav','9:16',Path(self.tmp.name)/'out.mp4')


if __name__=='__main__': unittest.main()
