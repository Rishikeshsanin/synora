"""Actual offline renderer acceptance (no model, network or real user assets)."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf
from PIL import Image

from engines.creative.wave2 import approve, sha
from engines.media import wave2
from engines.media.soundtrack import bind_soundtrack, prepare, project_key, render_project


class SoundtrackIntegrationTests(unittest.TestCase):
    def test_real_project_render_and_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            rate = 22050
            # Original rhythmic synthetic audio; no vocals or inference.
            t = np.arange(rate*10)/rate
            y = .18*np.sin(2*np.pi*220*t)*np.exp(-8*(t % .5))
            y += .48*np.sin(2*np.pi*880*t)*np.exp(-100*(t % .5))
            source = root/'source.wav'
            sf.write(source, y, rate, subtype='PCM_24')
            preview, receipt = prepare(source, dict(kind='synthetic-fixture', source_id='original test beat'),
                                       dict(source=True, derivative=True, advertising_sync=True), 0, len(y))
            audio = root/'prepared.wav'
            audio.write_bytes(preview)
            images = []
            for i, color in enumerate(('red', 'green', 'blue')):
                path = root/f'{i}.png'
                Image.new('RGB', (120, 80), color).save(path)
                images.append(path)
            brief = dict(audience='adults', occasion='evergreen', goal='awareness', industry='retail', emotion='calm', platform='reels')
            base = dict(version='m2-offline-v2', presentation='classic', ratio='9:16', fps=24, brief=brief, concept='showcase',
                        scenes=[dict(id=f'scene-{i+1}', beats=4, rights_confirmed=True, asset_sha256=sha(p.read_bytes()), caption='A closer look') for i,p in enumerate(images)])
            master = b'k'*32
            cache = root/'private'
            a = bind_soundtrack(base, receipt, 'a')
            b = bind_soundtrack(base, receipt, 'b')
            sign_a = approve(a, 'fixture-reviewer', project_key(master, 'a'))
            sign_b = approve(b, 'fixture-reviewer', project_key(master, 'b'))
            # Real beat detection and FFmpeg; use preview resolution for regression cost.
            with patch.dict(wave2.HD, {'9:16': (360,640)}):
                def render(board, sign, project, name):
                    return render_project(board, sign, master, project, source, audio, images, root/name, cache)
                first = render(a, sign_a, 'a', 'a.mp4')
                self.assertEqual(len(first['rendered']), 3)
                self.assertEqual(first['frames'], first['timing']['frames'])
                self.assertLessEqual(first['final_audio']['dbtp'], -1.0)
                self.assertLessEqual(first['final_audio']['lufs'], -15.5)
                self.assertFalse(first['soundtrack']['inference_verified'])
                repeat = render(a, sign_a, 'a', 'a-repeat.mp4')
                self.assertEqual(len(repeat['hits']), 3)
                self.assertEqual(first['sha256'], repeat['sha256'])
                other = render(b, sign_b, 'b', 'b.mp4')
                self.assertEqual(len(other['hits']), 0)
                self.assertEqual(len(other['rendered']), 3)
                with self.assertRaisesRegex(ValueError, 'project mismatch'):
                    render(a, sign_a, 'b', 'wrong.mp4')
                tampered = copy.deepcopy(a)
                tampered['soundtrack']['provenance']['source_id'] = 'changed'
                with self.assertRaisesRegex(ValueError, 'approval'):
                    render(tampered, sign_a, 'a', 'tampered.mp4')
                original = audio.read_bytes()
                audio.write_bytes(original+b'bad')
                with self.assertRaisesRegex(ValueError, 'prepared soundtrack changed'):
                    render(a, sign_a, 'a', 'bad-preview.mp4')
                audio.write_bytes(original)
                source.write_bytes(source.read_bytes()+b'bad')
                with self.assertRaisesRegex(ValueError, 'original soundtrack changed'):
                    render(a, sign_a, 'a', 'bad-source.mp4')
            self.assertFalse((root/'wrong.mp4').exists())
            self.assertFalse((root/'tampered.mp4').exists())
            self.assertFalse((root/'bad-preview.mp4').exists())
            self.assertFalse((root/'bad-source.mp4').exists())


if __name__ == '__main__':
    unittest.main()
