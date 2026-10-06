"""Check the pinned runtime without installing or accessing the network."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys


def main():
    if sys.version_info < (3, 10):
        return 1
    for line in Path(__file__).with_name("requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, expected = line.split("==", 1)
        name = name.split("[", 1)[0]
        try:
            if version(name) != expected:
                return 1
        except PackageNotFoundError:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
