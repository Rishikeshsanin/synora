import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from benchmarks.media import test_wave2
from engines.creative.wave2 import approve
from engines.media import incremental as inc


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.key = b'k'*32
        self.identity = 'a'*64
        self.source = self.root/'clip.mp4'
        self.source.write_bytes(b'fixture bytes, not a playable clip')
        self.cache = self.root/'cache'
        self.cache.mkdir(mode=0o700)
        self.target = self.root/'copy.mp4'

    def test_keys_change_with_render_inputs(self):
        scene = dict(asset_sha256='a'*64, caption='A closer look')
        base = inc.scene_key(scene, (1080,1920), 'editorial-v1', 0, 48, 'engine')
        for args in [(dict(scene, caption='Meet the product'), (1080,1920), 'editorial-v1', 0, 48, 'engine'),
                     (dict(scene, asset_sha256='b'*64), (1080,1920), 'editorial-v1', 0, 48, 'engine'),
                     (scene, (1080,1080), 'editorial-v1', 0, 48, 'engine'),
                     (scene, (1080,1920), 'classic', 0, 48, 'engine'),
                     (scene, (1080,1920), 'editorial-v1', 1, 48, 'engine'),
                     (scene, (1080,1920), 'editorial-v1', 0, 49, 'engine'),
                     (scene, (1080,1920), 'editorial-v1', 0, 48, 'other')]:
            self.assertNotEqual(base, inc.scene_key(*args))

    def test_authenticated_cache(self):
        inc._save(self.cache, self.identity, self.key, self.source)
        self.assertTrue(inc._load(self.cache, self.identity, self.key, self.target))
        self.assertEqual(self.source.read_bytes(), self.target.read_bytes())
        self.assertFalse(inc._load(self.cache, self.identity, b'x'*32, self.target))

    def test_corrupted_clip_and_manifest(self):
        inc._save(self.cache, self.identity, self.key, self.source)
        (self.cache/(self.identity+'.mp4')).write_bytes(b'changed')
        self.assertFalse(inc._load(self.cache, self.identity, self.key, self.target))
        inc._save(self.cache, self.identity, self.key, self.source)
        manifest = self.cache/(self.identity+'.json')
        record = json.loads(manifest.read_text())
        record['payload']['sha256'] = 'f'*64
        manifest.write_text(json.dumps(record))
        self.assertFalse(inc._load(self.cache, self.identity, self.key, self.target))
        manifest.write_text('not json')
        self.assertFalse(inc._load(self.cache, self.identity, self.key, self.target))

    def test_cache_limits(self):
        with patch.object(inc, 'MAX_CACHE', 1):
            inc._save(self.cache, self.identity, self.key, self.source)
            self.assertEqual(list(self.cache.iterdir()), [])
        with patch.object(inc, 'MAX_ENTRIES', 0):
            inc._save(self.cache, self.identity, self.key, self.source)
            self.assertEqual(list(self.cache.iterdir()), [])

    def test_approval_required_before_cache(self):
        fixture = test_wave2.Wave2Tests()
        fixture.setUp()
        try:
            board = copy.deepcopy(fixture.board)
            approval = approve(board, 'reviewer', fixture.key)
            board['scenes'][1]['caption'] = 'Meet the product'
            with patch.object(inc, '_load') as load:
                with self.assertRaisesRegex(ValueError, 'approval'):
                    inc.render_incremental(board, approval, fixture.key, [fixture.p]*3,
                                           'missing.wav', self.root/'out.mp4', self.cache)
                load.assert_not_called()
        finally:
            fixture.doCleanups()

    def test_source_evidence_required_before_cache(self):
        fixture = test_wave2.Wave2Tests()
        fixture.setUp()
        try:
            board = copy.deepcopy(fixture.board)
            board['scenes'][0].update(caption='AUREL DEMO', evidence=dict(source_id='fact', text='AUREL DEMO', sha256=inc.sha(b'AUREL DEMO'), reviewed=True))
            approval = approve(board, 'reviewer', fixture.key)
            with patch.object(inc, '_load') as load:
                with self.assertRaisesRegex(ValueError, 'claim source mismatch'):
                    inc.render_incremental(board, approval, fixture.key, [fixture.p]*3,
                                           'missing.wav', self.root/'out.mp4', self.cache)
                load.assert_not_called()
        finally:
            fixture.doCleanups()

    def test_actual_ffmpeg_uneven_timing_and_corruption_recovery(self):
        # Real encoding, mux and decode at small resolution; inject beat timestamps
        # to isolate uneven-duration behavior from the beat detection algorithm.
        fixture = test_wave2.Wave2Tests()
        fixture.setUp()
        try:
            board = copy.deepcopy(fixture.board)
            audio = self.root/'silence.wav'
            with wave.open(str(audio), 'wb') as f:
                f.setparams((1, 2, 22050, 0, 'NONE', 'not compressed'))
                f.writeframes(bytes(22050*2*6))
            board['audio_sha256'] = inc.sha(audio.read_bytes())
            approval = approve(board, 'reviewer', fixture.key)
            times = [0, .25, .5, .75, 25/24, 1.4, 1.7, 2, 53/24, 2.5, 2.8, 3.1, 80/24]
            with patch.object(inc, 'beat_times', return_value=times), patch.dict(inc.wave2.HD, {'9:16': (360,640)}):
                first = inc.render_incremental(board, approval, fixture.key, [fixture.p]*3, audio,
                                               self.root/'first.mp4', self.cache)
                self.assertEqual(first['frames'], 80)
                self.assertEqual(first['cut_frames'], [25,53])
                self.assertEqual(len(first['rendered']), 3)
                identity = inc.scene_key(board['scenes'][1], (360,640), 'classic', 1, 28, inc._engine_version())
                (self.cache/(identity+'.mp4')).write_bytes(b'tampered cache')
                second = inc.render_incremental(board, approval, fixture.key, [fixture.p]*3, audio,
                                                self.root/'second.mp4', self.cache)
                self.assertEqual(second['hits'], ['scene-1','scene-3'])
                self.assertEqual(second['rendered'], ['scene-2'])
                self.assertEqual(first['sha256'], second['sha256'])
        finally:
            fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
