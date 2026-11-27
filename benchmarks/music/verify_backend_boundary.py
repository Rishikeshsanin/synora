"""Optional cross-agent smoke, requires Agent 2 adapter + its Pydantic deps.

Run from repository root: PYTHONPATH=apps/api:. python -m benchmarks.music.verify_backend_boundary
No database, network, real music or paid resources.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import pydantic
from synora.models import MusicSpec
from synora.provider import to_engine_spec, validate_fixture, fixture_capabilities
from engines.music import (
    MusicSpec as EngineSpec, FixtureProvider, GenerationContext, MusicError, fixture_capabilities as engine_caps,
)


def main():
    print("Pydantic", pydantic.__version__)
    for mode, lyrics, lang in (
        ("instrumental", None, None), ("vocals", "original lyrics", "en"),
        ("vocals", "వెన్నెల దారి", "te"), ("vocals", "नई सुबह", "hi"),
    ):
        spec = MusicSpec(prompt="test", mode=mode, genres=["pop"], moods=[],
                         instruments=["piano"], duration_seconds=15, bpm=100,
                         lyrics=lyrics, language=lang)
        with TemporaryDirectory() as temp:
            path = Path(temp)
            progress = []
            out = FixtureProvider().generate(to_engine_spec(spec),
                                             GenerationContext(path, progress=progress.append))
            data, duration, provenance = validate_fixture(out, path, 15)
            assert duration == 15 and len(data) == 480044 and provenance["simulated"]
            assert progress[-1] == 100
            out.artifact.write_bytes(data + b"x")
            try:
                validate_fixture(out, path, 15)
            except MusicError:
                pass
            else:
                raise AssertionError("tampering accepted")
            print(mode, lang, "PASS, duration", duration, "bytes", len(data), "tamper rejected")
    for key in ("simulated", "vocals", "lyrics", "exact_bpm", "genres", "moods", "instruments"):
        assert fixture_capabilities()[key] == engine_caps()[key]
    print("shared capability flags PASS")
    baseline = dict(prompt="test", mode="vocals", genres=[], moods=[], instruments=[],
                    duration_seconds=15, bpm=100, lyrics=" original ", language=" en ")
    for fields, valid in (({"instruments": ["x"] * 12}, True),
                          ({"instruments": ["x"] * 13}, False),
                          ({"language": "x" * 32}, True), ({"language": "x" * 33}, False),
                          ({"lyrics": ""}, False), ({"lyrics": "  "}, False),
                          ({"genres": ["x" * 64]}, True), ({"genres": ["x" * 65]}, False),
                          ({"mode": "instrumental", "lyrics": "lyrics"}, False)):
        for model in (MusicSpec, EngineSpec):
            try:
                model(**(baseline | fields))
            except ValueError:
                assert not valid, (model.__name__, fields)
            else:
                assert valid, (model.__name__, fields)
    print("API/engine acceptance parity: 9 boundary cases PASS")


if __name__ == "__main__":
    main()
