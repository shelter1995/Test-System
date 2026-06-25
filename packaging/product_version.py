from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
MAX_FILE_VERSION_COMPONENT = 65535


@dataclass(frozen=True)
class ProductVersion:
    text: str
    major: int
    minor: int
    patch: int

    @property
    def file_version(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}.0"


def read_product_version(path: str | Path) -> ProductVersion:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or set(payload) != {"version"}:
        raise ValueError("version.json must contain only the version key")

    text = payload["version"]
    if not isinstance(text, str) or VERSION_PATTERN.fullmatch(text) is None:
        raise ValueError("version must use MAJOR.MINOR.PATCH")

    major, minor, patch = (int(component) for component in text.split("."))
    if any(
        component > MAX_FILE_VERSION_COMPONENT
        for component in (major, minor, patch)
    ):
        raise ValueError("version components must be between 0 and 65535")
    return ProductVersion(text=text, major=major, minor=minor, patch=patch)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read the Test-System product version")
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--field",
        choices=("major", "minor", "patch", "file-version"),
    )
    args = parser.parse_args()

    try:
        version = read_product_version(args.path)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.error(str(exc))
    values = {
        None: version.text,
        "major": version.major,
        "minor": version.minor,
        "patch": version.patch,
        "file-version": version.file_version,
    }
    print(values[args.field])


if __name__ == "__main__":
    main()
