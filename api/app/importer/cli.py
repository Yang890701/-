from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import create_engine

from .pipeline import ExcelImporter


def main() -> None:
    parser = argparse.ArgumentParser(description="Import the legacy Haoshi Excel workbooks.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="Repository root containing the four source .xlsx files.",
    )
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")

    engine = create_engine(args.database_url, future=True)
    report = ExcelImporter(engine=engine, root=args.root).run()
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
