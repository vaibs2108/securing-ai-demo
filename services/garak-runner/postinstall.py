"""Post-install step for garak-runner's real custom probe.

garak's own plugin loader only ever discovers probes physically present
inside its *installed* package directory (garak/_plugins.py:
`importlib.import_module(f"garak.{category}.{module_name}")`, scanning
`os.listdir(_config.transient.package_dir / category)`) — there's no pip
entry_points or external-module mechanism for probes. requirements.txt
alone can install real garak, but it can't place a file inside it, so this
one small real step does that — copying the real, version-controlled probe
in patches/ into the installed package right after `pip install -r
requirements.txt` runs.

Render build command: pip install -r requirements.txt && python postinstall.py
Local dev: same, or just `uv run python postinstall.py` after `uv sync`.
"""

import importlib.util
import shutil
import sys
from pathlib import Path

PATCHES_DIR = Path(__file__).parent / "patches"


def main() -> None:
    spec = importlib.util.find_spec("garak.probes")
    if spec is None or not spec.submodule_search_locations:
        print("garak.probes not found — is garak installed? (pip install -r requirements.txt first)", file=sys.stderr)
        sys.exit(1)

    dest_dir = Path(list(spec.submodule_search_locations)[0])
    for patch_file in PATCHES_DIR.glob("*.py"):
        dest = dest_dir / patch_file.name
        shutil.copy2(patch_file, dest)
        print(f"installed real custom probe: {patch_file.name} -> {dest}")


if __name__ == "__main__":
    main()
