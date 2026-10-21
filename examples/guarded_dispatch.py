"""Example dispatch gate. This intentionally does not launch any worker."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
result = subprocess.run([sys.executable, str(root / 'gaming_guard.py'), 'check'], timeout=25)
if result.returncode != 0:
    print('Deferred: gaming mode, cooldown, or detector unavailable.')
    raise SystemExit(0)
print('Dispatch permitted: integrate your approved worker launch here.')
