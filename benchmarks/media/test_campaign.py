import copy
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from engines.creative.campaign import campaign_board, inspect_shot, recommend
from engines.creative.wave2 import approve, sha, verify


class CampaignTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.brief = dict(audience='young adults', occasion='launch', goal='awareness', industry='retail', emotion='excited', platform='reels')
        self.shots = []
        for i, role in enumerate(('hero', 'detail', 'context')):
            path = self.root/f'{role}.png'
            im = Image.new('RGB', (800, 600), (40+i*60, 60, 90))
            ImageDraw.Draw(im).rectangle((100, 100, 300+i*100, 400), fill='white')
            im.save(path)
            self.shots.append(inspect_shot(path, 'fixture-sku', role, 'original test fixture', rights_confirmed=True))

    def test_rank_and_sequence(self):
        ranked = recommend(self.brief, self.shots, '9:16')
        self.assertEqual(len(ranked), 4)
        self.assertEqual(ranked[0]['concept'], 'rhythm')
        self.assertEqual(ranked[0]['roles'], ('detail', 'hero', 'context'))
        self.assertEqual(ranked, recommend(self.brief, list(reversed(self.shots)), '9:16'))

    def test_missing_role(self):
        shots = copy.deepcopy(self.shots)
        shots[2]['role'] = 'hero'
        with self.assertRaisesRegex(ValueError, 'missing'):
            recommend(self.brief, shots, '1:1')

    def test_duplicate_reencoded_pixels(self):
        other = self.root/'same.bmp'
        with Image.open(self.shots[0]['path']) as im:
            im.save(other.with_suffix('.png'), compress_level=0)
        duplicate = inspect_shot(other.with_suffix('.png'), 'fixture-sku', 'context', 'duplicate', rights_confirmed=True)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            recommend(self.brief, [self.shots[0], self.shots[1], duplicate], '1:1')

    def test_identity_scope(self):
        shots = copy.deepcopy(self.shots)
        shots[2]['product_id'] = 'different'
        with self.assertRaisesRegex(ValueError, 'mixed products'):
            recommend(self.brief, shots, '1:1')
        self.assertEqual(len(recommend(self.brief, shots, '1:1', collection=True)), 4)

    def test_rights_required(self):
        with self.assertRaisesRegex(ValueError, 'rights'):
            inspect_shot(self.shots[0]['path'], 'sku', 'hero', 'source', rights_confirmed=False)

    def test_audio_rights_required(self):
        selected = recommend(self.brief, self.shots, '9:16')[0]
        with self.assertRaisesRegex(ValueError, 'audio rights'):
            campaign_board(self.brief, selected, '9:16', sha(b'audio'))

    def test_signed_metadata_and_changed_source(self):
        selected = recommend(self.brief, self.shots, '9:16')[0]
        board = campaign_board(self.brief, selected, '9:16', sha(b'audio'), audio_rights_confirmed=True)
        key = b'k'*32
        approval = approve(board, 'reviewer', key)
        verify(board, approval, key)
        board['scenes'][0]['product_id'] = 'altered'
        with self.assertRaisesRegex(ValueError, 'approval'):
            verify(board, approval, key)
        Image.new('RGB', (800, 600), 'red').save(self.shots[0]['path'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            campaign_board(self.brief, selected, '9:16', sha(b'audio'), audio_rights_confirmed=True)


if __name__ == '__main__':
    unittest.main()
