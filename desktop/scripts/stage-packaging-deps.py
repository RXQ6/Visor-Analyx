"""Copy only pinned wheel RECORD files; never copy a developer site-packages."""
from __future__ import annotations

import base64
import csv
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
from pathlib import Path


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def stage(source: Path, target: Path, lock: Path) -> dict[str, str]:
    pins = dict(line.strip().split("==") for line in lock.read_text().splitlines()
                if line.strip() and not line.startswith("#"))
    pins = {normalize(name): version for name, version in pins.items()}
    distributions = {normalize(dist.metadata["Name"]): dist
                     for dist in importlib.metadata.distributions(path=[str(source)])}
    if set(pins) != set(distributions):
        raise ValueError("Private Python dependencies do not match the packaging lock")
    for name, version in pins.items():
        dist = distributions[name]
        if dist.version != version or dist.files is None:
            raise ValueError(f"Pinned Python dependency missing or mismatched: {name}")
        # Read RECORD directly: newer importlib.metadata silently filters missing
        # files from dist.files, which would hide an incomplete installation.
        for recorded_path, recorded_hash, _size in csv.reader(dist.read_text("RECORD").splitlines()):
            relative = Path(recorded_path)
            # Wheels may record console wrappers outside site-packages. Never
            # copy them: stdio uses the fixed Node entrypoint, no shell wrappers.
            if relative.is_absolute() or ".." in relative.parts:
                continue
            if "__pycache__" in relative.parts or relative.suffix == ".pyc":
                continue
            origin = source / relative
            if not origin.is_file() or origin.is_symlink():
                raise ValueError(f"Wheel file unavailable: {name}")
            data = origin.read_bytes()
            if recorded_hash:
                algorithm, expected = recorded_hash.split("=", 1)
                digest = base64.urlsafe_b64encode(hashlib.new(algorithm, data).digest()).rstrip(b"=").decode()
                if digest != expected:
                    raise ValueError(f"Wheel file integrity mismatch: {name}")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, destination)
    return pins


if __name__ == "__main__":
    source, target, lock = map(Path, sys.argv[1:])
    print(json.dumps(stage(source.resolve(), target.resolve(), lock.resolve()), sort_keys=True))
