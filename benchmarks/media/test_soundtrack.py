import io
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

from engines.media.soundtrack import bind_soundtrack, prepare, project_cache, project_key


class SoundtrackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.rate = 22050
        self.rights = dict(source=True, derivative=True, advertising_sync=True)
        self.provenance = dict(kind='synthetic-fixture', source_id='original test tone')
        t = np.arange(self.rate*6)/self.rate
        self.samples = .7*np.sin(2*np.pi*220*t)
        self.path = self.root/'source.wav'
        sf.write(self.path, self.samples, self.rate, subtype='PCM_24')

    def test_real_normalization_and_selection(self):
        data, receipt = prepare(self.path, self.provenance, self.rights, self.rate, 4*self.rate)
        y, rate = sf.read(io.BytesIO(data))
        self.assertEqual((len(y), rate), (4*self.rate, self.rate))
        self.assertEqual((y[0], y[-1]), (0, 0))
        self.assertLessEqual(receipt['after']['dbtp'], -2)
        self.assertLessEqual(receipt['after']['lufs'], -15.8)
        self.assertFalse(receipt['inference_verified'])
        self.assertEqual(receipt['start_frame'], self.rate)
        self.assertEqual(receipt['provenance']['kind'], 'synthetic-fixture')

    def test_rights_and_provenance(self):
        with self.assertRaisesRegex(ValueError, 'rights'):
            prepare(self.path, self.provenance, dict(self.rights, advertising_sync=False), 0, 4*self.rate)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            prepare(self.path, dict(kind='genuine', source_id='not proven'), self.rights, 0, 4*self.rate)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            prepare(self.path, dict(kind='generated-unverified', source_id='x'), self.rights, 0, 4*self.rate)

    def test_selection_bounds(self):
        for start, count in ((-1, 4*self.rate), (0, 1), (4*self.rate, 4*self.rate), (True, 4*self.rate)):
            with self.assertRaises(ValueError):
                prepare(self.path, self.provenance, self.rights, start, count)

    def test_nonfinite_float_rejected(self):
        self.samples[100] = np.nan
        sf.write(self.path, self.samples, self.rate, subtype='FLOAT')
        with self.assertRaisesRegex(ValueError, 'non-finite'):
            prepare(self.path, self.provenance, self.rights, 0, 4*self.rate)

    def test_silence_rejected(self):
        sf.write(self.path, np.zeros(6*self.rate), self.rate)
        with self.assertRaisesRegex(ValueError, 'silent'):
            prepare(self.path, self.provenance, self.rights, 0, 4*self.rate)

    def test_project_isolation(self):
        key = b'x'*32
        root = self.root/'private'
        a = project_cache(root, key, 'project-A')
        b = project_cache(root, key, 'project-B')
        self.assertNotEqual(a, b)
        self.assertNotEqual(project_key(key, 'project-A'), project_key(key, 'project-B'))
        (a/'clip.mp4').write_bytes(b'a')
        self.assertFalse((b/'clip.mp4').exists())
        self.assertEqual(a, project_cache(root, key, 'project-A'))
        self.assertNotEqual(a, project_cache(root, b'y'*32, 'project-A'))

    def test_private_root(self):
        root = self.root/'public'
        root.mkdir(mode=0o755)
        if os.name == 'posix':
            with self.assertRaisesRegex(ValueError, 'private'):
                project_cache(root, b'x'*32, 'project-A')
            real = self.root/'real'
            real.mkdir(mode=0o700)
            alias = self.root/'alias'
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'private'):
                project_cache(alias, b'x'*32, 'project-A')

    def test_long_stereo_intake(self):
        for seconds, rate, subtype in ((15, 44100, 'FLOAT'), (60, 48000, 'PCM_24')):
            t = np.arange(rate*seconds)/rate
            y = .18*np.sin(2*np.pi*220*t)*np.exp(-8*(t % .5))
            y += .48*np.sin(2*np.pi*880*t)*np.exp(-100*(t % .5))
            sf.write(self.path, np.column_stack((y, y*.8)), rate, subtype=subtype)
            data, receipt = prepare(self.path, self.provenance, self.rights, 0, len(y))
            info = sf.info(io.BytesIO(data))
            self.assertEqual((info.frames, info.samplerate, info.channels, info.subtype), (seconds*rate, rate, 2, 'PCM_16'))
            self.assertLessEqual(receipt['after']['dbtp'], -2.)
            self.assertLessEqual(receipt['after']['lufs'], -15.8)

    def test_binding_preserves_input(self):
        _, receipt = prepare(self.path, self.provenance, self.rights, 0, 4*self.rate)
        board = {'audio_sha256': 'old'}
        bound = bind_soundtrack(board, receipt, 'project-A')
        self.assertEqual(board['audio_sha256'], 'old')
        self.assertEqual(bound['audio_sha256'], receipt['audio_sha256'])
        self.assertEqual(bound['project_id'], 'project-A')
        receipt['rights']['source'] = False
        self.assertTrue(bound['soundtrack']['rights']['source'])


if __name__ == '__main__':
    unittest.main()
