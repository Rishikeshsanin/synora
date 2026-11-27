"""Compatibility entry point; backend-only smoke lives in benchmarks/music."""
from runpy import run_module

if __name__ == "__main__":
    run_module("benchmarks.music.verify_backend_boundary", run_name="__main__")
