"""Repository paths, resolved relative to this file so they work on any OS and any checkout name."""
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CODE_DIR.parent
DATASET_DIR = REPO_ROOT / "dataset"
DEFAULT_OUTPUT = REPO_ROOT / "output.csv"
