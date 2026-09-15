"""Database smoke tests. Run with: python -m unittest discover -s tests -v"""
import os
import tempfile
import unittest


class DatabaseTests(unittest.TestCase):
    def test_schema_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DB_PATH"] = os.path.join(tmp, "test.db")
            import importlib
            import core.database as db
            importlib.reload(db)
            db.init_db()
            db.update_settings(123, unverified_role_id=10, verified_role_id=20, verification_code="1234")
            row = db.get_settings(123)
            self.assertEqual(row["unverified_role_id"], 10)
            self.assertEqual(row["verified_role_id"], 20)
            self.assertEqual(row["verification_code"], "1234")


if __name__ == "__main__":
    unittest.main()
