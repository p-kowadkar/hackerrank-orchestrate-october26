"""Re-render usage_report.md from run_manifest.md and usage_ledger.md (main.py does this on every run).

Run: python3 code/evaluation/usage_report.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from llm.manifest import main   # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
