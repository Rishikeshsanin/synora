import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageChops
from engines.creative.wave2 import approve, concepts, sha, verify
from engines.media.wave2 import HD, layout, render_hd, snapshot_image, snapshot_audio


class Wave2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d=Path(self.tmp.name)
        self.key=b'a'*32
        self.p=self.d/'asset.png'
        Image.new('RGB',(120,60),'red').save(self.p)
        self.brief=dict(audience='young adults',occasion='launch',goal='awareness',industry='retail',emotion='excited',platform='reels')
        self.board=dict(version='m2-offline-v2',ratio='9:16',fps=24,brief=self.brief,concept='rhythm',audio_sha256=sha(b'original'),audio_rights_confirmed=True,scenes=[dict(id=f'scene-{i+1}',beats=4,rights_confirmed=True,asset_sha256=sha(self.p.read_bytes()),caption='A closer look') for i in range(3)])

    def test_rank(self):
        ranked=concepts(self.brief)
        self.assertEqual(ranked[0]['id'],'rhythm')
        self.assertEqual(len(ranked),4)
        self.assertTrue(ranked[0]['reasons'])

    def test_signed_approval(self):
        a=approve(self.board,'reviewer',self.key,now=100)
        verify(self.board,a,self.key,now=101)
        for field,value in [('ratio','1:1'),('audio_sha256','f'*64)]:
            b=copy.deepcopy(self.board)
            b[field]=value
            with self.assertRaises(ValueError):
                verify(b,a,self.key,now=101)
        b=copy.deepcopy(self.board)
        b['scenes'][0]['caption']='Meet the product'
        with self.assertRaises(ValueError):
            verify(b,a,self.key,now=101)
        with self.assertRaises(ValueError):
            verify(self.board,a,b'b'*32,now=101)
        a['payload']['reviewer']='imposter'
        with self.assertRaises(ValueError):
            verify(self.board,a,self.key,now=101)

    def test_expiry(self):
        a=approve(self.board,'reviewer',self.key,now=100,ttl=5)
        for t in (99,105):
            with self.assertRaises(ValueError):
                verify(self.board,a,self.key,now=t)

    def test_claim(self):
        self.board['scenes'][0]['caption']='Cures every illness'
        with self.assertRaisesRegex(ValueError,'unsubstantiated'):
            approve(self.board,'reviewer',self.key)
        self.board['scenes'][0]['evidence']=dict(source_id='fact',text='Different',reviewed=True,sha256=sha(b'Different'))
        with self.assertRaisesRegex(ValueError,'evidence mismatch'):
            approve(self.board,'reviewer',self.key)

    def test_source_mismatch(self):
        self.board['scenes'][0].update(caption='AUREL DEMO',evidence=dict(source_id='fact',text='AUREL DEMO',reviewed=True,sha256=sha(b'AUREL DEMO')))
        a=approve(self.board,'reviewer',self.key)
        fact=self.d/'fact.txt'
        fact.write_text('not approved')
        with self.assertRaisesRegex(ValueError,'claim source mismatch'):
            render_hd(self.board,a,self.key,[self.p]*3,'unused',self.d/'out.mp4',evidence_paths={'fact':fact})
        self.assertFalse((self.d/'out.mp4').exists())

    def test_image_tamper(self):
        expected=sha(self.p.read_bytes())
        Image.new('RGB',(120,60),'blue').save(self.p)
        with self.assertRaisesRegex(ValueError,'asset hash mismatch'):
            snapshot_image(self.p,expected)

    def test_audio_tamper(self):
        p=self.d/'audio.wav'
        p.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'audio hash mismatch'):
            snapshot_audio(p,self.board['audio_sha256'])

    def test_fidelity_all_ratios(self):
        source=snapshot_image(self.p,sha(self.p.read_bytes()))
        for size in HD.values():
            for progress in (0,.5,1):
                frame,(x,y,w,h)=layout(source,'A closer look',size,progress)
                self.assertLessEqual(abs(w/h-2),.01)
                self.assertGreaterEqual(x,0)
                self.assertGreaterEqual(y,0)
                self.assertLessEqual(x+w,size[0])
                self.assertLessEqual(y+h,size[1])
                self.assertIsNone(ImageChops.difference(frame.crop((x,y,x+w,y+h)),source.resize((w,h),Image.Resampling.LANCZOS)).getbbox())

    def test_legacy_rejected_by_v2(self):
        with self.assertRaises(ValueError):
            verify(self.board,'unsigned',b'short')


if __name__=='__main__':
    unittest.main()
