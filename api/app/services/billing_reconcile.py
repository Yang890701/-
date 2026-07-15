from __future__ import annotations

import argparse
import json
from typing import Any

from app.db.session import SessionLocal
from app.services.billing import reconciliation_report, validate_billing_ym


def build_report(ym: str) -> dict[str, Any]:
    billing_ym = validate_billing_ym(ym)
    with SessionLocal() as db:
        return reconciliation_report(db, billing_ym, scope={"type": "all"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare computed electricity against rent_confirm imports.")
    parser.add_argument("--ym", required=True, help="Billing period in YYYYMM format")
    args = parser.parse_args()
    print(json.dumps(build_report(args.ym), sort_keys=True))


if __name__ == "__main__":
    main()
