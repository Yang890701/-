from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GoldenCase
from app.db.session import SessionLocal


GOLDEN_CASES: list[dict] = [
    {
        "case_code": "billing_normal_001",
        "input_data": {"mode": "normal", "initial_reading": 100, "current_reading": 120, "avg_price": "4.10"},
        "expected_output": {"electricity_amount": 82},
    },
    {
        "case_code": "billing_normal_002",
        "input_data": {"mode": "normal", "prior_reading": 17, "current_reading": 20, "avg_price": "3.3333"},
        "expected_output": {"electricity_amount": 10},
    },
    {
        "case_code": "billing_normal_003",
        "input_data": {"mode": "normal", "prior_reading": 40, "current_reading": 65, "avg_price": "4.50"},
        "expected_output": {"electricity_amount": 113},
    },
    {
        "case_code": "billing_special_001",
        "input_data": {
            "mode": "special_price",
            "prior_reading": 10,
            "current_reading": 25,
            "special_price": "6.50",
        },
        "expected_output": {"electricity_amount": 98},
    },
    {
        "case_code": "billing_special_002",
        "input_data": {
            "mode": "special_price",
            "prior_reading": 100,
            "current_reading": 200,
            "special_price": "4.00",
        },
        "expected_output": {"electricity_amount": 400},
    },
    {
        "case_code": "billing_special_003",
        "input_data": {
            "mode": "special_price",
            "prior_reading": 8,
            "current_reading": 15,
            "special_price": "2.25",
        },
        "expected_output": {"electricity_amount": 16},
    },
    {
        "case_code": "billing_jingping_001",
        "input_data": {
            "mode": "jingping_merge",
            "components": [
                {"prior_reading": 100, "current_reading": 110},
                {"prior_reading": 50, "current_reading": 55},
            ],
            "avg_price": "4.00",
        },
        "expected_output": {"electricity_amount": 60},
    },
    {
        "case_code": "billing_jingping_002",
        "input_data": {
            "mode": "jingping_merge",
            "components": [
                {"prior_reading": 10, "current_reading": 13},
                {"prior_reading": 5, "current_reading": 7},
            ],
            "avg_price": "3.3333",
        },
        "expected_output": {"electricity_amount": 17},
    },
    {
        "case_code": "billing_jingping_003",
        "input_data": {
            "mode": "jingping_merge",
            "components": [
                {"prior_reading": 70, "current_reading": 70},
                {"prior_reading": 20, "current_reading": 32},
            ],
            "avg_price": "5.50",
        },
        "expected_output": {"electricity_amount": 66},
    },
    {
        "case_code": "billing_total_sub_001",
        "input_data": {
            "mode": "total_sub",
            "total": {"prior_reading": 100, "current_reading": 200},
            "sub": {"prior_reading": 10, "current_reading": 40},
            "avg_price": "4.00",
        },
        "expected_output": {"electricity_amount": 280},
    },
    {
        "case_code": "billing_total_sub_002",
        "input_data": {
            "mode": "total_sub",
            "total": {"prior_reading": 10, "current_reading": 20},
            "sub": {"prior_reading": 4, "current_reading": 7},
            "avg_price": "2.25",
        },
        "expected_output": {"electricity_amount": 16},
    },
    {
        "case_code": "billing_total_sub_003",
        "input_data": {
            "mode": "total_sub",
            "total": {"prior_reading": 30, "current_reading": 37},
            "sub": {"prior_reading": 5, "current_reading": 12},
            "avg_price": "5.00",
        },
        "expected_output": {"electricity_amount": 0},
    },
    {
        "case_code": "billing_total_bill_split_001",
        "input_data": {
            "mode": "total_bill_split",
            "taipower_bill_total": 1000,
            "child_electricity_amounts": [200, 300],
        },
        "expected_output": {"electricity_amount": 500},
    },
    {
        "case_code": "billing_total_bill_split_002",
        "input_data": {
            "mode": "total_bill_split",
            "taipower_bill_total": 999,
            "child_electricity_amounts": [333, 333],
        },
        "expected_output": {"electricity_amount": 333},
    },
    {
        "case_code": "billing_total_bill_split_003",
        "input_data": {
            "mode": "total_bill_split",
            "taipower_bill_total": 1200,
            "child_electricity_amounts": [0, 125, 126],
        },
        "expected_output": {"electricity_amount": 949},
    },
]


def seed_golden_cases(db: Session) -> dict[str, int]:
    counts = {"inserted": 0, "updated": 0, "total": len(GOLDEN_CASES)}
    for case in GOLDEN_CASES:
        existing = db.scalar(
            select(GoldenCase).where(
                GoldenCase.case_code == case["case_code"],
                GoldenCase.deleted_at.is_(None),
            )
        )
        if existing is None:
            db.add(GoldenCase(**case))
            counts["inserted"] += 1
        else:
            existing.input_data = case["input_data"]
            existing.expected_output = case["expected_output"]
            counts["updated"] += 1
    db.commit()
    return counts


def main() -> None:
    with SessionLocal() as db:
        print(seed_golden_cases(db))


if __name__ == "__main__":
    main()
