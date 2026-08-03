"""Private isolated worker for executing verified downstream scenarios."""

from __future__ import annotations

from pathlib import Path
import os
import signal
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.downstream_canary.model import CHECK_IDS  # noqa: E402
from tools.downstream_canary.scenarios import _run_scenarios_in_process  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 6:
        return 2
    workspace, package_root, dependency_root, fixture_path, resource_path = map(Path, argv[:5])
    try:
        status_descriptor = int(argv[5])
    except ValueError:
        return 2
    try:
        checks = _run_scenarios_in_process(
            workspace,
            package_root,
            dependency_root,
            fixture_path.read_bytes(),
            resource_path.read_bytes(),
        )
    except BaseException:
        status = b"F"
    else:
        status = b"P" if checks == CHECK_IDS else b"F"
    try:
        os.write(status_descriptor, status)
        os.close(status_descriptor)
    except OSError:
        return 9
    while True:
        signal.pause()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
