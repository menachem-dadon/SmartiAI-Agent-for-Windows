"""Regenerate the language-neutral and TypeScript desktop API artifacts."""
from pathlib import Path
import sys

repository_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repository_root))
from smarti.control_plane_contract import write_generated_contracts


if __name__ == "__main__":
    for output in write_generated_contracts(repository_root):
        print(output)
