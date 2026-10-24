"""CLI runner for database seeding and sample asset generation.

Usage:
    python3 -m app.seeds [--reset] [--no-files]
"""

import argparse
import sys
from pathlib import Path

# Ensure backend directory is in sys.path when executed directly
backend_dir = Path(__file__).resolve().parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.seed import ensure_seeded


def main():
    parser = argparse.ArgumentParser(description="Seed the RFP Response Assistant database and sample assets.")
    parser.add_argument("--reset", action="store_true", help="Drop existing tables and re-seed from scratch.")
    parser.add_argument("--no-files", action="store_true", help="Skip generating sample RFP documents.")
    args = parser.parse_args()

    print(f"[*] Starting database seed (reset={args.reset}, generate_files={not args.no_files})...")
    ensure_seeded(reset=args.reset, generate_files=not args.no_files)
    print("[SUCCESS] Database and sample assets seeded successfully.")


if __name__ == "__main__":
    main()
