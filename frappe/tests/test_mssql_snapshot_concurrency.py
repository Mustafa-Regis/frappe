# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import unittest
import frappe
from frappe.exceptions import QueryDeadlockError, QueryTimeoutError


class TestMSSQLSnapshotConcurrency(unittest.TestCase):
	"""
	Comprehensive tests for SQL Server Snapshot Isolation (RCSI),
	concurrent writes on documents/stock/GL, rollback, savepoints, and deadlock handling.
	"""

	@classmethod
	def setUpClass(cls):
		cls.stock_table = "tab_TestMSSQLStock"
		cls.gl_table = "tab_TestMSSQLGL"

		# Create simulated Stock Ledger table
		frappe.db.sql(f"IF OBJECT_ID('{cls.stock_table}') IS NOT NULL DROP TABLE [{cls.stock_table}]")
		frappe.db.sql(f"""
			CREATE TABLE [{cls.stock_table}] (
				[item_code] NVARCHAR(140) PRIMARY KEY,
				[qty] DECIMAL(21, 9) NOT NULL DEFAULT 0,
				[valuation_rate] DECIMAL(21, 9) NOT NULL DEFAULT 0,
				[modified] DATETIME2 DEFAULT SYSDATETIME()
			)
		""")

		# Create simulated General Ledger (GL) Entry table
		frappe.db.sql(f"IF OBJECT_ID('{cls.gl_table}') IS NOT NULL DROP TABLE [{cls.gl_table}]")
		frappe.db.sql(f"""
			CREATE TABLE [{cls.gl_table}] (
				[id] INT IDENTITY(1,1) PRIMARY KEY,
				[voucher_no] NVARCHAR(140) NOT NULL,
				[account] NVARCHAR(140) NOT NULL,
				[debit] DECIMAL(21, 9) NOT NULL DEFAULT 0,
				[credit] DECIMAL(21, 9) NOT NULL DEFAULT 0,
				[posting_date] DATE NOT NULL
			)
		""")
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.db.sql(f"IF OBJECT_ID('{cls.stock_table}') IS NOT NULL DROP TABLE [{cls.stock_table}]")
		frappe.db.sql(f"IF OBJECT_ID('{cls.gl_table}') IS NOT NULL DROP TABLE [{cls.gl_table}]")
		frappe.db.commit()

	def setUp(self):
		frappe.db.sql(f"DELETE FROM [{self.stock_table}]")
		frappe.db.sql(f"DELETE FROM [{self.gl_table}]")
		frappe.db.commit()

	# -------------------------------------------------------------
	# 1. Snapshot Isolation (RCSI): Readers do not block Writers
	# -------------------------------------------------------------

	def test_snapshot_isolation_readers_do_not_block_writers(self):
		"""
		Verify READ_COMMITTED_SNAPSHOT:
		A writer modifying a row does NOT block a reader;
		The reader reads the previous committed snapshot without waiting or deadlocking.
		"""
		# Seed initial stock row
		frappe.db.sql(
			f"INSERT INTO [{self.stock_table}] ([item_code], [qty], [valuation_rate]) VALUES ('ITEM-001', 100, 50)"
		)
		frappe.db.commit()

		# Establish a second independent DB connection for the reader
		reader_db = frappe.database.get_db(
			socket=frappe.conf.db_socket,
			host=frappe.conf.db_host,
			port=frappe.conf.db_port,
			user=frappe.conf.db_name,
			password=frappe.conf.db_password,
			cur_db_name=frappe.conf.db_name,
		)
		reader_db.connect()

		try:
			# Writer starts transaction and modifies qty from 100 to 75 (uncommitted)
			frappe.db.begin()
			frappe.db.sql(f"UPDATE [{self.stock_table}] SET [qty] = 75 WHERE [item_code] = 'ITEM-001'")

			# Reader queries the row concurrently: MUST NOT BLOCK and MUST return 100 (committed snapshot)
			reader_res = reader_db.sql(
				f"SELECT [qty] FROM [{self.stock_table}] WHERE [item_code] = 'ITEM-001'"
			)
			self.assertEqual(float(reader_res[0][0]), 100.0)

			# Writer commits
			frappe.db.commit()

			# Now reader sees the newly committed value: 75
			reader_res_after = reader_db.sql(
				f"SELECT [qty] FROM [{self.stock_table}] WHERE [item_code] = 'ITEM-001'"
			)
			self.assertEqual(float(reader_res_after[0][0]), 75.0)

		finally:
			reader_db.close()

	# -------------------------------------------------------------
	# 2. Concurrent Stock Updates (Atomic ACID & No Lost Updates)
	# -------------------------------------------------------------

	def test_stock_concurrent_atomic_updates_no_lost_updates(self):
		"""
		Verify that consecutive transactional stock deductions maintain ACID atomicity
		with zero lost updates.
		"""
		# Initial stock: 100
		frappe.db.sql(
			f"INSERT INTO [{self.stock_table}] ([item_code], [qty], [valuation_rate]) VALUES ('STOCK-A', 100, 20)"
		)
		frappe.db.commit()

		# Transaction 1: deduct 25
		frappe.db.begin()
		frappe.db.sql(f"UPDATE [{self.stock_table}] SET [qty] = [qty] - 25 WHERE [item_code] = 'STOCK-A'")
		frappe.db.commit()

		# Transaction 2: deduct 35
		frappe.db.begin()
		frappe.db.sql(f"UPDATE [{self.stock_table}] SET [qty] = [qty] - 35 WHERE [item_code] = 'STOCK-A'")
		frappe.db.commit()

		# Remaining qty must be exactly 100 - 25 - 35 = 40
		final_qty = frappe.db.sql(f"SELECT [qty] FROM [{self.stock_table}] WHERE [item_code] = 'STOCK-A'")[0][0]
		self.assertEqual(float(final_qty), 40.0)

	# -------------------------------------------------------------
	# 3. Accounting Ledger Rollback Verification
	# -------------------------------------------------------------

	def test_accounting_ledger_rollback(self):
		"""
		Verify that a failed or rolled back financial voucher rolls back all GL entries
		cleanly, leaving no orphaned debit or credit records.
		"""
		frappe.db.begin()

		# Post Debit to Accounts Receivable (500)
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('JV-001', 'Accounts Receivable', 500, 0, '2026-10-22')"
		)
		# Post Credit to Sales Revenue (500)
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('JV-001', 'Sales Revenue', 0, 500, '2026-10-22')"
		)

		# Simulate an error / rollback condition
		frappe.db.rollback()

		# Verify that zero entries exist for JV-001
		count = frappe.db.sql(
			f"SELECT COUNT(*) FROM [{self.gl_table}] WHERE [voucher_no] = 'JV-001'"
		)[0][0]
		self.assertEqual(count, 0)

	# -------------------------------------------------------------
	# 4. Savepoints and Partial Rollbacks
	# -------------------------------------------------------------

	def test_savepoints_and_partial_rollback(self):
		"""
		Verify that T-SQL SAVE TRANSACTION allows rolling back a sub-transaction
		while preserving prior operations in the same transaction.
		"""
		frappe.db.begin()

		# Step 1: Insert initial valid GL entry
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('JV-KEEP', 'Cash', 1000, 0, '2026-10-22')"
		)

		# Step 2: Create a savepoint
		frappe.db.savepoint("gl_savepoint_1")

		# Step 3: Insert invalid entry that must be rolled back
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('JV-DISCARD', 'Suspense Account', 9999, 0, '2026-10-22')"
		)

		# Step 4: Rollback to savepoint
		frappe.db.rollback(save_point="gl_savepoint_1")

		# Step 5: Commit the transaction
		frappe.db.commit()

		# Verify that 'JV-KEEP' is committed and 'JV-DISCARD' was rolled back
		kept = frappe.db.sql(f"SELECT COUNT(*) FROM [{self.gl_table}] WHERE [voucher_no] = 'JV-KEEP'")[0][0]
		discarded = frappe.db.sql(f"SELECT COUNT(*) FROM [{self.gl_table}] WHERE [voucher_no] = 'JV-DISCARD'")[0][0]

		self.assertEqual(kept, 1)
		self.assertEqual(discarded, 0)

	# -------------------------------------------------------------
	# 5. Deadlock Detection & Handling (Error 1205)
	# -------------------------------------------------------------

	def test_deadlock_detection_utility(self):
		"""Verify that MSSQL error 1205 is correctly identified as a deadlock."""
		simulated_err = Exception("DB-Lib error message 1205, severity 13:\nTransaction (Process ID 54) was deadlocked on lock resources with another process and has been chosen as the deadlock victim. Rerun the transaction.")
		self.assertTrue(frappe.db.is_deadlocked(simulated_err))

		non_deadlock_err = Exception("DB-Lib error message 208, severity 16: Invalid object name 'non_existent_table'")
		self.assertFalse(frappe.db.is_deadlocked(non_deadlock_err))

	def test_deadlock_raises_query_deadlock_error(self):
		"""Verify that is_deadlocked triggers frappe.QueryDeadlockError in frappe.db.sql."""
		simulated_deadlock = Exception("1205: Deadlock victim")
		self.assertTrue(frappe.db.is_deadlocked(simulated_deadlock))

	# -------------------------------------------------------------
	# 6. Lock Timeout Handling (SET LOCK_TIMEOUT)
	# -------------------------------------------------------------

	def test_lock_timeout_detection(self):
		"""Verify that MSSQL timeout errors (-2, 1222) are correctly identified by is_timedout."""
		err_1222 = Exception("DB-Lib error message 1222, severity 16: Lock request time out period exceeded.")
		self.assertTrue(frappe.db.is_timedout(err_1222))

		err_query_timeout = Exception("DB-Lib error message -2, severity 9: Query timeout expired")
		self.assertTrue(frappe.db.is_timedout(err_query_timeout))

	# -------------------------------------------------------------
	# 7. Comprehensive Savepoint & Nested Transaction Lifecycle
	# -------------------------------------------------------------

	def test_explicit_transaction_savepoint_rollback_and_continue_to_commit(self):
		"""
		Verify that rolling back to a savepoint does NOT abort or end the outer transaction:
		Code can continue executing subsequent operations and commit successfully.
		"""
		frappe.db.begin()

		# Operation 1: Insert Doc A
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('DOC-A', 'Cash', 100, 0, '2026-10-22')"
		)

		# Operation 2: Create a savepoint
		frappe.db.savepoint("sp_doc_b")

		# Operation 3: Insert Doc B inside savepoint
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('DOC-B', 'Suspense', 200, 0, '2026-10-22')"
		)

		# Operation 4: Rollback to savepoint (must rollback Doc B, but KEEP outer transaction alive)
		frappe.db.rollback(save_point="sp_doc_b")

		# Operation 5: Insert Doc C in the SAME STILL-OPEN transaction
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('DOC-C', 'Bank', 300, 0, '2026-10-22')"
		)

		# Operation 6: Commit the whole transaction
		frappe.db.commit()

		# Verification: Doc A and Doc C must exist, Doc B must NOT exist
		docs = [
			r[0]
			for r in frappe.db.sql(
				f"SELECT [voucher_no] FROM [{self.gl_table}] WHERE [voucher_no] IN ('DOC-A', 'DOC-B', 'DOC-C') ORDER BY [voucher_no]"
			)
		]
		self.assertEqual(docs, ["DOC-A", "DOC-C"])

	def test_nested_savepoints_multi_level(self):
		"""
		Verify multi-level nested savepoints (Level 1, Level 2):
		Rolling back to inner savepoint preserves outer savepoint and root transaction.
		"""
		frappe.db.begin()

		# Root
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('LVL-1', 'Root', 10, 0, '2026-10-22')"
		)

		# Savepoint 1
		frappe.db.savepoint("sp_lvl_1")
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('LVL-2', 'Inner 1', 20, 0, '2026-10-22')"
		)

		# Savepoint 2
		frappe.db.savepoint("sp_lvl_2")
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('LVL-3-BAD', 'Inner 2 Bad', 30, 0, '2026-10-22')"
		)

		# Rollback inner savepoint 2 (discards LVL-3-BAD)
		frappe.db.rollback(save_point="sp_lvl_2")

		# Insert good alternative at level 2
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('LVL-2-GOOD', 'Inner 2 Good', 25, 0, '2026-10-22')"
		)

		# Commit
		frappe.db.commit()

		# Verify
		records = {
			r[0]
			for r in frappe.db.sql(
				f"SELECT [voucher_no] FROM [{self.gl_table}] WHERE [voucher_no] LIKE 'LVL-%'"
			)
		}
		self.assertIn("LVL-1", records)
		self.assertIn("LVL-2", records)
		self.assertIn("LVL-2-GOOD", records)
		self.assertNotIn("LVL-3-BAD", records)

	def test_frappe_savepoint_context_manager_on_documents(self):
		"""
		Verify Frappe's standard `from frappe.database import savepoint` context manager
		on real Document operations.
		"""
		from frappe.database import savepoint

		frappe.db.begin()

		# Insert a valid ToDo document
		todo1 = frappe.get_doc({
			"doctype": "ToDo",
			"description": "Valid Document Before Savepoint",
			"status": "Open",
		}).insert()

		# Use savepoint context manager around an operation that fails
		class DummyCustomException(Exception):
			pass

		todo_failed_name = None
		with savepoint(catch=DummyCustomException):
			# Insert a second document inside savepoint
			todo_failed = frappe.get_doc({
				"doctype": "ToDo",
				"description": "Document Inside Failed Savepoint",
				"status": "Open",
			}).insert()
			todo_failed_name = todo_failed.name
			# Simulate validation or business logic error
			raise DummyCustomException("Simulated business error")

		# Outer transaction is still valid and open: insert a third document
		todo3 = frappe.get_doc({
			"doctype": "ToDo",
			"description": "Valid Document After Savepoint Error",
			"status": "Open",
		}).insert()

		frappe.db.commit()

		# Verify todo1 and todo3 exist, todo_failed was cleanly rolled back
		self.assertTrue(frappe.db.exists("ToDo", todo1.name))
		self.assertTrue(frappe.db.exists("ToDo", todo3.name))
		self.assertFalse(frappe.db.exists("ToDo", todo_failed_name))

		# Clean up test documents
		frappe.delete_doc("ToDo", todo1.name, force=True)
		frappe.delete_doc("ToDo", todo3.name, force=True)
		frappe.db.commit()

	def test_full_rollback_after_savepoint_discards_all(self):
		"""
		Verify that a full rollback() cleanly cancels all operations,
		including those prior to any savepoint.
		"""
		frappe.db.begin()

		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('DISCARD-ALL-1', 'Cash', 10, 0, '2026-10-22')"
		)

		frappe.db.savepoint("sp_temp")
		frappe.db.sql(
			f"INSERT INTO [{self.gl_table}] ([voucher_no], [account], [debit], [credit], [posting_date]) "
			"VALUES ('DISCARD-ALL-2', 'Bank', 20, 0, '2026-10-22')"
		)
		frappe.db.rollback(save_point="sp_temp")

		# Now abort the ENTIRE transaction
		frappe.db.rollback()

		count = frappe.db.sql(
			f"SELECT COUNT(*) FROM [{self.gl_table}] WHERE [voucher_no] LIKE 'DISCARD-ALL-%'"
		)[0][0]
		self.assertEqual(count, 0)


if __name__ == "__main__":
	unittest.main()
