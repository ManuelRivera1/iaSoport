"""Create a review-only source package. Model/runtime data are never included."""

import argparse
from pathlib import Path

from support_ai.distribution import application_package
from support_ai.guide import GuideWorkspace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/releases/SupportAI-portable.zip"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    workspace = GuideWorkspace(root)
    workspace.ensure()
    payload = application_package(root, workspace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(f"Paquete: {args.output.resolve()} ({len(payload):,} bytes, sin modelos ni caches)")


if __name__ == "__main__":
    main()
