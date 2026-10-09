"""Keep source installation inside the project's own supported virtualenv."""

import argparse
import importlib.metadata
import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    selected = Path(__file__).absolute().parents[1] / ".venv"
    if not (3, 12, 15) <= sys.version_info[:3] < (3, 13):
        raise RuntimeError(
            "Use a fresh Python 3.12.15+ environment; the existing environment has been preserved"
        )
    if (
        selected.is_symlink()
        or selected.is_junction()
        or selected.resolve().parent != selected.parent.resolve()
        or Path(sys.prefix).resolve() != selected.resolve()
        or Path(sys.base_prefix).resolve() == Path(sys.prefix).resolve()
    ):
        raise RuntimeError("Installation requires this project's own .venv; environment preserved")

    def lxml_present() -> bool:
        try:
            importlib.metadata.distribution("lxml")
        except importlib.metadata.PackageNotFoundError:
            return importlib.util.find_spec("lxml") is not None
        return True

    present = lxml_present()
    if present and not args.check_only:
        subprocess.run([sys.executable, "-m", "pip", "uninstall", "--yes", "lxml"], check=True)
        importlib.invalidate_caches()
        if lxml_present():
            raise RuntimeError("Legacy lxml is still visible; use a fresh project .venv")
    print(
        json.dumps(
            {
                "environment": str(selected),
                "check_only": args.check_only,
                "legacy_lxml_removed": present and not args.check_only,
                "legacy_lxml_present": lxml_present(),
            }
        )
    )


if __name__ == "__main__":
    main()
