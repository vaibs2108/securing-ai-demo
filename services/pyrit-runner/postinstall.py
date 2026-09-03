"""Post-install step for pyrit-runner's real custom jailbreak templates.

PyRIT's own template lookup is a plain filesystem path
(pyrit/datasets/jailbreak/templates/*.yaml — see this service's own
TEMPLATES_DIR default), not a plugin/entry_points mechanism, so
requirements.txt alone can install real PyRIT but can't place files inside
it. This one small real step does that — copying the real, version-
controlled templates in patches/ into the installed package right after
`pip install -r requirements.txt` runs.

Render build command: pip install -r requirements.txt && python postinstall.py
Local dev: same, or just `uv run python postinstall.py` after `uv sync`.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

PATCHES_DIR = Path(__file__).parent / "patches"


def main() -> None:
    spec = importlib.util.find_spec("pyrit")
    if spec is None or not spec.submodule_search_locations:
        print("pyrit not found — is PyRIT installed? (pip install -r requirements.txt first)", file=sys.stderr)
        sys.exit(1)

    pyrit_dir = Path(list(spec.submodule_search_locations)[0])
    dest_dir = pyrit_dir / "datasets" / "jailbreak" / "templates"
    if not dest_dir.exists():
        print(f"expected real templates dir not found: {dest_dir}", file=sys.stderr)
        sys.exit(1)

    for patch_file in PATCHES_DIR.glob("*.yaml"):
        dest = dest_dir / patch_file.name
        shutil.copy2(patch_file, dest)
        print(f"installed real custom template: {patch_file.name} -> {dest}")


if __name__ == "__main__":
    main()
