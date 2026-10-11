"""Fail closed if a check changes original images or tracked source/baselines."""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "generated-artifacts"


def new_run_directory(parent=None):
    parent = Path(parent or OUTPUT_ROOT / "browser-checks").resolve()
    if not parent.is_relative_to(OUTPUT_ROOT) or parent == OUTPUT_ROOT:
        raise ValueError("Results must be inside generated-artifacts")
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="run-", dir=parent))


def fingerprint(root=ROOT):
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    paths = {root / name for name in tracked if name}
    # Protect original PNGs even when ignored/untracked. Generated captures
    # live outside this tree and must not enter the reference inventory.
    if (root / "screenshots").exists():
        paths.update((root / "screenshots").rglob("*.png"))
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        if path.is_file() else None
        for path in sorted(paths)
        if not path.is_relative_to(root / "generated-artifacts")
    }


class SourcePreservation:
    def __init__(self, directory, root=ROOT):
        self.directory = Path(directory)
        self.root = root
        self.changed = []

    def __enter__(self):
        self.before = fingerprint(self.root)
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "source-before.json").write_text(
            json.dumps(self.before, indent=2, ensure_ascii=False))
        return self

    def __exit__(self, *_exc):
        after = fingerprint(self.root)
        self.changed = sorted(name for name in self.before.keys() | after.keys()
                              if self.before.get(name) != after.get(name))
        (self.directory / "source-after.json").write_text(
            json.dumps(after, indent=2, ensure_ascii=False))
        (self.directory / "source-preservation.json").write_text(json.dumps({
            "unchanged": not self.changed,
            "files_checked": len(self.before),
            "changed": self.changed,
        }, indent=2, ensure_ascii=False))
        if self.changed:
            raise RuntimeError(f"Source/reference preservation failed: {self.changed}")
