import unittest

from sqlalchemy import CHAR, BigInteger, Identity, Index, Text


class SchemaModelTest(unittest.TestCase):
    def setUp(self) -> None:
        from app.db.models import Base

        self.metadata = Base.metadata

    def test_core_tables_are_registered(self) -> None:
        expected = {
            "site",
            "meter",
            "room",
            "room_meter_assignment",
            "meter_reading",
            "tenant_contract",
            "billing_run",
            "billing_run_detail",
            "billing_run_charge_line",
            "app_user",
            "column_meta",
            "import_batch",
            "legacy_key_map",
            "stg_room",
        }

        self.assertTrue(expected.issubset(set(self.metadata.tables)))

    def test_every_table_has_identity_pk_and_audit_columns(self) -> None:
        for table in self.metadata.sorted_tables:
            with self.subTest(table=table.name):
                self.assertIn("id", table.c)
                self.assertIsInstance(table.c.id.type, BigInteger)
                self.assertTrue(table.c.id.primary_key)
                self.assertIsInstance(table.c.id.identity, Identity)
                self.assertIn("created_at", table.c)
                self.assertIn("updated_at", table.c)
                self.assertIn("deleted_at", table.c)

    def test_key_column_types_preserve_business_codes(self) -> None:
        meter = self.metadata.tables["meter"]
        room = self.metadata.tables["room"]
        assignment = self.metadata.tables["room_meter_assignment"]
        billing_run = self.metadata.tables["billing_run"]

        self.assertIsInstance(meter.c.electricity_code.type, Text)
        self.assertIsInstance(room.c.room_code.type, Text)
        self.assertIsInstance(assignment.c.meter_category.type, Text)
        self.assertIsInstance(billing_run.c.billing_ym.type, CHAR)
        self.assertEqual(billing_run.c.billing_ym.type.length, 6)

    def test_natural_keys_use_partial_unique_indexes(self) -> None:
        table = self.metadata.tables["meter"]
        indexes = {index.name: index for index in table.indexes}
        index = indexes["uq_meter_electricity_code_active"]

        self.assertIsInstance(index, Index)
        self.assertTrue(index.unique)
        self.assertEqual(str(index.dialect_options["postgresql"]["where"]), "deleted_at IS NULL")


if __name__ == "__main__":
    unittest.main()
