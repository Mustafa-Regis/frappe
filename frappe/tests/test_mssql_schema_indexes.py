# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.database.mssql.schema import MSSQLTable
from frappe.database.schema import DbColumn


def make_db_column(table, fieldname, fieldtype, length=None, default=None, set_index=0, options=None, unique=0, precision=None):
	return DbColumn(table, fieldname, fieldtype, length, default, set_index, options, unique, precision)


class DummyMeta:
	issingle = 0
	istable = 0
	autoname = None
	track_seen = 0

	def get(self, key, default=None):
		return getattr(self, key, default)

	def get_fieldnames_with_value(self, with_field_meta=True):
		return []


class TestMSSQLSchemaIndexes(FrappeTestCase):
	def setUp(self):
		super().setUp()
		self.table_name = "tabTestSchemaAlter"
		self.cleanup_tables()

	def tearDown(self):
		self.cleanup_tables()
		super().tearDown()

	def cleanup_tables(self):
		try:
			frappe.db.sql(f"IF OBJECT_ID('{self.table_name}', 'U') IS NOT NULL DROP TABLE [{self.table_name}]")
			frappe.db.commit()
		except Exception:
			pass

	def create_sample_table_with_dependencies(self):
		"""
		Create an existing table with data, composite index, included columns,
		filtered unique index, check constraint, and default constraint.
		"""
		frappe.db.sql(f"""
			CREATE TABLE [{self.table_name}] (
				[name] NVARCHAR(140) PRIMARY KEY,
				[title] NVARCHAR(100) NOT NULL,
				[status] NVARCHAR(50) CONSTRAINT [DF_status_val] DEFAULT 'Draft',
				[score] INT CONSTRAINT [CK_score_val] CHECK ([score] >= 0),
				[extra_info] NVARCHAR(200) NULL,
				[idx] BIGINT DEFAULT 0
			);
		""")

		# 1. Filtered Unique Index on title
		frappe.db.sql(f"""
			CREATE UNIQUE INDEX [uq_title_filtered] ON [{self.table_name}] ([title])
			WHERE [title] IS NOT NULL;
		""")

		# 2. Composite Index with Included Column
		frappe.db.sql(f"""
			CREATE INDEX [idx_status_composite] ON [{self.table_name}] ([status] ASC, [idx] DESC)
			INCLUDE ([extra_info]);
		""")

		# 3. Populate initial data
		frappe.db.sql(f"""
			INSERT INTO [{self.table_name}] ([name], [title], [status], [score], [extra_info], [idx])
			VALUES ('ROW-1', 'Alpha', 'Draft', 10, 'Info 1', 1),
			       ('ROW-2', 'Beta', 'Open', 20, 'Info 2', 2);
		""")
		frappe.db.commit()

	def test_metadata_extraction_for_complex_indexes(self):
		"""
		Verify that get_column_indexes_metadata extracts composite,
		included columns, and filtered unique index definitions accurately.
		"""
		self.create_sample_table_with_dependencies()

		table = MSSQLTable("TestSchemaAlter", meta=DummyMeta())
		metadata = table.get_column_indexes_metadata("status")

		self.assertEqual(len(metadata), 1)
		idx = metadata[0]
		self.assertEqual(idx["name"], "idx_status_composite")
		self.assertFalse(idx["is_unique"])
		self.assertIn("INCLUDE ([extra_info])", idx["create_sql"])
		self.assertIn("[status] ASC", idx["create_sql"])
		self.assertIn("[idx] DESC", idx["create_sql"])

		# Title metadata
		title_meta = table.get_column_indexes_metadata("title")
		self.assertEqual(len(title_meta), 1)
		t_idx = title_meta[0]
		self.assertEqual(t_idx["name"], "uq_title_filtered")
		self.assertTrue(t_idx["is_unique"])
		self.assertIn("WHERE ([title] IS NOT NULL)", t_idx["create_sql"])

	def test_successful_alter_column_restores_all_dependencies(self):
		"""
		Verify that modifying a column type from NVARCHAR(50) to NVARCHAR(150)
		safely drops and accurately recreates:
		- Composite index with included columns
		- Check constraints
		- Default constraints
		"""
		self.create_sample_table_with_dependencies()

		table = MSSQLTable("TestSchemaAlter", meta=DummyMeta())
		table.current_columns = {
			"name": {"type": "nvarchar(140)"},
			"title": {"type": "nvarchar(100)"},
			"status": {"type": "nvarchar(50)"},
			"score": {"type": "int"},
			"extra_info": {"type": "nvarchar(200)"},
			"idx": {"type": "bigint"},
		}

		# Define altered status column: NVARCHAR(150)
		new_col = make_db_column(
			table=table,
			fieldname="status",
			fieldtype="Data",
			length=150,
			default="Draft",
		)
		table.change_type = [new_col]

		# Execute alter
		table.alter()
		frappe.db.commit()

		# 1. Verify column type updated
		col_desc = frappe.db.sql(f"""
			SELECT CHARACTER_MAXIMUM_LENGTH
			FROM INFORMATION_SCHEMA.COLUMNS
			WHERE TABLE_NAME = '{self.table_name}' AND COLUMN_NAME = 'status'
		""")[0][0]
		self.assertEqual(col_desc, 150)

		# 2. Verify composite index with INCLUDE was recreated and intact
		idx_meta = table.get_column_indexes_metadata("status")
		self.assertEqual(len(idx_meta), 1)
		self.assertEqual(idx_meta[0]["name"], "idx_status_composite")
		self.assertIn("INCLUDE ([extra_info])", idx_meta[0]["create_sql"])

		# 3. Verify Default Constraint was restored
		df_constraints = frappe.db.sql(f"""
			SELECT d.name, d.definition
			FROM sys.default_constraints d
			JOIN sys.columns c ON d.parent_column_id = c.column_id AND d.parent_object_id = c.object_id
			WHERE d.parent_object_id = OBJECT_ID('[{self.table_name}]') AND c.name = 'status'
		""", as_dict=True)
		self.assertTrue(len(df_constraints) >= 1)
		self.assertIn("Draft", df_constraints[0]["definition"])

		# 4. Verify existing data preserved
		rows = frappe.db.sql(f"SELECT COUNT(*) FROM [{self.table_name}]")[0][0]
		self.assertEqual(rows, 2)

	def test_failed_alter_column_restores_indexes_and_constraints_via_rollback(self):
		"""
		Verify that when ALTER COLUMN fails midway (e.g. incompatible type conversion
		with existing string data 'Alpha' converted to INT), the savepoint rollback
		automatically restores all dropped indexes and constraints in SQL Server.
		"""
		self.create_sample_table_with_dependencies()

		table = MSSQLTable("TestSchemaAlter", meta=DummyMeta())
		table.current_columns = {
			"name": {"type": "nvarchar(140)"},
			"title": {"type": "nvarchar(100)"},
			"status": {"type": "nvarchar(50)"},
			"score": {"type": "int"},
			"extra_info": {"type": "nvarchar(200)"},
			"idx": {"type": "bigint"},
		}

		# Incompatible change: title (contains 'Alpha', 'Beta') -> Int
		bad_col = make_db_column(
			table=table,
			fieldname="title",
			fieldtype="Int",
		)
		table.change_type = [bad_col]

		# Execution must raise error due to conversion failure
		with self.assertRaises(Exception):
			table.alter()

		# Verify that title column type remains NVARCHAR(100)
		data_type = frappe.db.sql(f"""
			SELECT DATA_TYPE
			FROM INFORMATION_SCHEMA.COLUMNS
			WHERE TABLE_NAME = '{self.table_name}' AND COLUMN_NAME = 'title'
		""")[0][0]
		self.assertEqual(data_type, "nvarchar")

		# Verify that filtered unique index uq_title_filtered STILL EXISTS
		title_indexes = table.get_column_indexes_metadata("title")
		self.assertEqual(len(title_indexes), 1)
		self.assertEqual(title_indexes[0]["name"], "uq_title_filtered")
		self.assertTrue(title_indexes[0]["is_unique"])

		# Verify data is still intact
		rows = frappe.db.sql(f"SELECT COUNT(*) FROM [{self.table_name}]")[0][0]
		self.assertEqual(rows, 2)

	def test_alter_column_with_check_constraint(self):
		"""
		Verify altering a column that has a CHECK constraint ([score] >= 0):
		Column type altered (INT -> BIGINT) while preserving the check constraint.
		"""
		self.create_sample_table_with_dependencies()

		table = MSSQLTable("TestSchemaAlter", meta=DummyMeta())
		table.current_columns = {
			"name": {"type": "nvarchar(140)"},
			"title": {"type": "nvarchar(100)"},
			"status": {"type": "nvarchar(50)"},
			"score": {"type": "int"},
			"extra_info": {"type": "nvarchar(200)"},
			"idx": {"type": "bigint"},
		}

		# Change score: Int -> Long Int (bigint)
		score_col = make_db_column(
			table=table,
			fieldname="score",
			fieldtype="Long Int",
		)
		table.change_type = [score_col]

		table.alter()
		frappe.db.commit()

		# Verify column changed to BIGINT
		data_type = frappe.db.sql(f"""
			SELECT DATA_TYPE
			FROM INFORMATION_SCHEMA.COLUMNS
			WHERE TABLE_NAME = '{self.table_name}' AND COLUMN_NAME = 'score'
		""")[0][0]
		self.assertEqual(data_type, "bigint")

		# Verify CHECK constraint is active by attempting to insert negative value
		with self.assertRaises(Exception):
			frappe.db.sql(f"""
				INSERT INTO [{self.table_name}] ([name], [title], [status], [score])
				VALUES ('BAD-SCORE', 'Gamma', 'Open', -5)
			""")
		frappe.db.rollback()

	def test_existing_doctype_schema_upgrade_workflow(self):
		"""
		Test real DocType schema upgrade on an existing table with rows:
		- Modify existing field properties
		- Run frappe.db.updatedb
		- Verify schema changes and index preservation
		"""
		doctype_name = "MSSQL Schema Upgrade Test"
		if frappe.db.exists("DocType", doctype_name):
			frappe.delete_doc("DocType", doctype_name, force=True)
			frappe.db.commit()

		# Create new DocType
		doc = frappe.get_doc({
			"doctype": "DocType",
			"name": doctype_name,
			"module": "Core",
			"custom": 1,
			"fields": [
				{
					"fieldname": "code",
					"fieldtype": "Data",
					"label": "Code",
					"reqd": 1,
					"unique": 1,
				},
				{
					"fieldname": "description",
					"fieldtype": "Data",
					"label": "Description",
					"length": 100,
					"search_index": 1,
				},
				{
					"fieldname": "status",
					"fieldtype": "Select",
					"label": "Status",
					"options": "Draft\nOpen\nClosed",
					"default": "Draft",
				},
			],
			"permissions": [{"role": "System Manager", "read": 1, "write": 1}],
		}).insert()

		# Insert a test document
		test_record = frappe.get_doc({
			"doctype": doctype_name,
			"code": "CODE-100",
			"description": "Original Description",
			"status": "Draft",
		}).insert()
		frappe.db.commit()

		# Upgrade schema: Expand description length from 100 to 250
		doc.fields[1].length = 250
		doc.save()
		frappe.db.updatedb(doctype_name)
		frappe.db.commit()

		# Verify column length was upgraded in SQL Server
		table_name = f"tab{doctype_name}"
		col_len = frappe.db.sql(f"""
			SELECT CHARACTER_MAXIMUM_LENGTH
			FROM INFORMATION_SCHEMA.COLUMNS
			WHERE TABLE_NAME = '{table_name}' AND COLUMN_NAME = 'description'
		""")[0][0]
		self.assertEqual(col_len, 250)

		# Verify search index was preserved
		indexes = frappe.db.get_column_indexes(table_name, "description", unique_only=False)
		self.assertTrue(len(indexes) >= 1)

		# Verify unique index on code was preserved
		code_unique = frappe.db.get_column_indexes(table_name, "code", unique_only=True)
		self.assertTrue(len(code_unique) >= 1)

		# Clean up
		frappe.delete_doc(doctype_name, test_record.name, force=True)
		frappe.delete_doc("DocType", doctype_name, force=True)
		frappe.db.commit()


if __name__ == "__main__":
	unittest.main()
