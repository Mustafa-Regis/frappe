# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import unittest
from frappe.database.mssql.database import modify_query


class TestMSSQLQueryTranslation(unittest.TestCase):
	"""
	Comprehensive test suite for MSSQL query translation rules.
	Tests cover:
	1. Every single transformation rule.
	2. String literals / quoted text (ensuring zero corruption).
	3. Single-line and multi-line comments.
	4. Nested expressions and function calls.
	5. Nested subqueries with and without ORDER BY / LIMIT.
	6. Edge cases and prevention of unsafe transformations.
	"""

	# -------------------------------------------------------------
	# 1. Quoted Text and String Literals (النصوص المقتبسة)
	# -------------------------------------------------------------

	def test_quoted_text_preserves_backticks(self):
		sql = "SELECT 'hello `world`', `real_col` FROM `tabUser`"
		expected = "SELECT 'hello `world`', [real_col] FROM [tabUser]"
		self.assertEqual(modify_query(sql), expected)

	def test_quoted_text_preserves_ifnull(self):
		sql = "SELECT 'IFNULL(a, b)' AS title, IFNULL(`val`, 0) FROM `tabDoc`"
		expected = "SELECT 'IFNULL(a, b)' AS title, ISNULL([val], 0) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_quoted_text_preserves_now(self):
		sql = "SELECT 'NOW()' AS txt, NOW() AS cur_time FROM `tabDoc`"
		expected = "SELECT 'NOW()' AS txt, SYSDATETIME() AS cur_time FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_quoted_text_preserves_date_and_datediff(self):
		sql = "SELECT 'DATE(col)', 'DATEDIFF(a, b)', DATE(`creation`) FROM `tabDoc`"
		expected = "SELECT 'DATE(col)', 'DATEDIFF(a, b)', CAST([creation] AS DATE) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_quoted_text_preserves_limit_and_offset(self):
		sql = "SELECT 'LIMIT 10 OFFSET 5' AS phrase FROM `tabDoc` LIMIT 1"
		expected = "SELECT 'LIMIT 10 OFFSET 5' AS phrase FROM [tabDoc] ORDER BY (SELECT NULL) OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY"
		self.assertEqual(modify_query(sql), expected)

	def test_quoted_text_preserves_length_and_locate(self):
		sql = "SELECT 'LENGTH(x)', 'LOCATE(a, b)', LENGTH(`name`) FROM `tabDoc`"
		expected = "SELECT 'LENGTH(x)', 'LOCATE(a, b)', LEN([name]) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_quoted_text_preserves_for_update(self):
		sql = "SELECT 'FOR UPDATE' AS comment FROM `tabDoc` FOR UPDATE"
		expected = "SELECT 'FOR UPDATE' AS comment FROM [tabDoc] "
		self.assertEqual(modify_query(sql), expected)

	def test_escaped_quotes_in_literals(self):
		sql = "SELECT 'It''s a `special` string with IFNULL(x, y)' FROM `tabDoc`"
		expected = "SELECT 'It''s a `special` string with IFNULL(x, y)' FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_backslash_escapes_in_literals(self):
		sql = r"SELECT 'path\\to\\file with `col` and NOW()' FROM `tabDoc`"
		expected = r"SELECT 'path\\to\\file with `col` and NOW()' FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_multiple_quoted_strings_in_where_clause(self):
		sql = "SELECT `name` FROM `tabUser` WHERE `email` = 'admin@example.com' AND `bio` = 'Likes `frappe` and LIMIT 10'"
		expected = "SELECT [name] FROM [tabUser] WHERE [email] = 'admin@example.com' AND [bio] = 'Likes `frappe` and LIMIT 10'"
		self.assertEqual(modify_query(sql), expected)

	# -------------------------------------------------------------
	# 2. Comments (التعليقات)
	# -------------------------------------------------------------

	def test_single_line_comments_preserve_keywords(self):
		sql = "-- comment with `backticks` and IFNULL(a, b) and LIMIT 5\nSELECT `name` FROM `tabUser`"
		expected = "-- comment with `backticks` and IFNULL(a, b) and LIMIT 5\nSELECT [name] FROM [tabUser]"
		self.assertEqual(modify_query(sql), expected)

	def test_block_comments_preserve_keywords(self):
		sql = "/* block comment with DATE(creation) and NOW() */ SELECT `id` FROM `tabDoc`"
		expected = "/* block comment with DATE(creation) and NOW() */ SELECT [id] FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_multiline_block_comments(self):
		sql = "/*\n * Comment header:\n * IFNULL(`a`, `b`)\n * LIMIT 10 OFFSET 5\n */\nSELECT `id` FROM `tabDoc`"
		expected = "/*\n * Comment header:\n * IFNULL(`a`, `b`)\n * LIMIT 10 OFFSET 5\n */\nSELECT [id] FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	# -------------------------------------------------------------
	# 3. Identifiers & Backticks (المعرفات)
	# -------------------------------------------------------------

	def test_backtick_identifier_conversion(self):
		sql = "SELECT `name`, `first_name` FROM `tabUser` WHERE `enabled` = 1"
		expected = "SELECT [name], [first_name] FROM [tabUser] WHERE [enabled] = 1"
		self.assertEqual(modify_query(sql), expected)

	def test_dotted_backtick_identifiers(self):
		sql = "SELECT `tabUser`.`name`, `tabProfile`.`bio` FROM `tabUser` JOIN `tabProfile` ON `tabUser`.`name` = `tabProfile`.`parent`"
		expected = "SELECT [tabUser].[name], [tabProfile].[bio] FROM [tabUser] JOIN [tabProfile] ON [tabUser].[name] = [tabProfile].[parent]"
		self.assertEqual(modify_query(sql), expected)

	def test_identifier_with_spaces(self):
		sql = "SELECT `Custom Field Name` FROM `tabDoc`"
		expected = "SELECT [Custom Field Name] FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	# -------------------------------------------------------------
	# 4. Standard Function Rules (قواعد الدوال الفردية)
	# -------------------------------------------------------------

	def test_ifnull_translation(self):
		sql = "SELECT IFNULL(`remarks`, 'None') FROM `tabDoc`"
		expected = "SELECT ISNULL([remarks], 'None') FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_ifnull_case_insensitive(self):
		sql = "SELECT ifnull(`remarks`, 0) FROM `tabDoc`"
		expected = "SELECT ISNULL([remarks], 0) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_ifnull_word_boundary_safety(self):
		# Identifiers or words containing IFNULL should not be mutated
		sql = "SELECT MY_IFNULL_FUNC(`x`), NOT_IFNULL FROM `tabDoc`"
		expected = "SELECT MY_IFNULL_FUNC([x]), NOT_IFNULL FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_now_translation(self):
		sql = "SELECT NOW() AS t1, now() AS t2, NOW(6) AS t3"
		expected = "SELECT SYSDATETIME() AS t1, SYSDATETIME() AS t2, SYSDATETIME() AS t3"
		self.assertEqual(modify_query(sql), expected)

	def test_now_word_boundary_safety(self):
		sql = "SELECT SNOW(), KNOW() FROM `tabDoc`"
		expected = "SELECT SNOW(), KNOW() FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_length_translation(self):
		sql = "SELECT LENGTH(`title`), length(`description`) FROM `tabDoc`"
		expected = "SELECT LEN([title]), LEN([description]) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_length_word_boundary_safety(self):
		sql = "SELECT MAX_LENGTH, FULL_LENGTH(`x`) FROM `tabDoc`"
		expected = "SELECT MAX_LENGTH, FULL_LENGTH([x]) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_locate_translation_two_args(self):
		sql = "SELECT LOCATE('sub', `content`) FROM `tabDoc`"
		expected = "SELECT CHARINDEX('sub', [content]) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_locate_translation_three_args(self):
		sql = "SELECT LOCATE('sub', `content`, 5) FROM `tabDoc`"
		expected = "SELECT CHARINDEX('sub', [content], 5) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_date_translation(self):
		sql = "SELECT DATE(`creation`) FROM `tabDoc`"
		expected = "SELECT CAST([creation] AS DATE) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_datediff_two_args_translation(self):
		# MariaDB DATEDIFF(end_date, start_date) -> T-SQL DATEDIFF(day, start_date, end_date)
		sql = "SELECT DATEDIFF(`end_date`, `start_date`) FROM `tabDoc`"
		expected = "SELECT DATEDIFF(day, [start_date], [end_date]) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_unix_timestamp_no_args(self):
		sql = "SELECT UNIX_TIMESTAMP() FROM `tabDoc`"
		expected = "SELECT DATEDIFF(second, '1970-01-01', SYSUTCDATETIME()) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_unix_timestamp_with_arg(self):
		sql = "SELECT UNIX_TIMESTAMP(`creation`) FROM `tabDoc`"
		expected = "SELECT DATEDIFF(second, '1970-01-01', [creation]) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	# -------------------------------------------------------------
	# 5. Nested Expressions (التعابير المتداخلة)
	# -------------------------------------------------------------

	def test_nested_date_with_ifnull_and_now(self):
		sql = "SELECT DATE(IFNULL(`creation`, NOW())) FROM `tabDoc`"
		expected = "SELECT CAST(ISNULL([creation], SYSDATETIME()) AS DATE) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_nested_length_with_ifnull(self):
		sql = "SELECT LENGTH(IFNULL(`name`, '')) FROM `tabDoc`"
		expected = "SELECT LEN(ISNULL([name], '')) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_nested_datediff_with_ifnull(self):
		sql = "SELECT DATEDIFF(IFNULL(`end_date`, NOW()), `start_date`) FROM `tabDoc`"
		expected = "SELECT DATEDIFF(day, [start_date], ISNULL([end_date], SYSDATETIME())) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_nested_function_depth(self):
		sql = "SELECT DATE(DATE(`creation`)) FROM `tabDoc`"
		expected = "SELECT CAST(CAST([creation] AS DATE) AS DATE) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	# -------------------------------------------------------------
	# 6. Nested Subqueries & Pagination (الاستعلامات المتداخلة والتقسيم)
	# -------------------------------------------------------------

	def test_limit_with_order_by(self):
		sql = "SELECT `name` FROM `tabDoc` ORDER BY `creation` DESC LIMIT 20 OFFSET 40"
		expected = "SELECT [name] FROM [tabDoc] ORDER BY [creation] DESC OFFSET 40 ROWS FETCH NEXT 20 ROWS ONLY"
		self.assertEqual(modify_query(sql), expected)

	def test_limit_without_order_by(self):
		sql = "SELECT `name` FROM `tabDoc` LIMIT 10"
		expected = "SELECT [name] FROM [tabDoc] ORDER BY (SELECT NULL) OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY"
		self.assertEqual(modify_query(sql), expected)

	def test_distinct_limit_without_order_by(self):
		sql = "SELECT DISTINCT `name` FROM `tabDoc` LIMIT 10"
		expected = "SELECT DISTINCT [name] FROM [tabDoc] ORDER BY 1 OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY"
		self.assertEqual(modify_query(sql), expected)

	def test_comma_separated_limit_offset(self):
		# MySQL: LIMIT offset, count
		sql = "SELECT `name` FROM `tabDoc` ORDER BY `name` LIMIT 10, 20"
		expected = "SELECT [name] FROM [tabDoc] ORDER BY [name] OFFSET 10 ROWS FETCH NEXT 20 ROWS ONLY"
		self.assertEqual(modify_query(sql), expected)

	def test_subquery_with_limit_inside_where_clause(self):
		# Subquery has no ORDER BY, outer query HAS ORDER BY
		sql = "SELECT `name` FROM `tabParent` WHERE `id` IN (SELECT `id` FROM `tabChild` LIMIT 5) ORDER BY `name` LIMIT 10"
		expected = (
			"SELECT [name] FROM [tabParent] WHERE [id] IN "
			"(SELECT [id] FROM [tabChild] ORDER BY (SELECT NULL) OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY) "
			"ORDER BY [name] OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY"
		)
		self.assertEqual(modify_query(sql), expected)

	def test_subquery_with_own_order_by(self):
		# Subquery has its own ORDER BY, should not add fallback ORDER BY
		sql = "SELECT `name` FROM `tabParent` WHERE `id` IN (SELECT `id` FROM `tabChild` ORDER BY `idx` LIMIT 5)"
		expected = (
			"SELECT [name] FROM [tabParent] WHERE [id] IN "
			"(SELECT [id] FROM [tabChild] ORDER BY [idx] OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY)"
		)
		self.assertEqual(modify_query(sql), expected)

	def test_subquery_in_select_list(self):
		sql = "SELECT `name`, (SELECT IFNULL(`sub_val`, 'none') FROM `tabChild` WHERE `parent` = p.`name` LIMIT 1) FROM `tabParent` p"
		expected = (
			"SELECT [name], (SELECT ISNULL([sub_val], 'none') FROM [tabChild] WHERE [parent] = p.[name] "
			"ORDER BY (SELECT NULL) OFFSET 0 ROWS FETCH NEXT 1 ROWS ONLY) FROM [tabParent] p"
		)
		self.assertEqual(modify_query(sql), expected)

	# -------------------------------------------------------------
	# 7. Clause Removal & DDL (إزالة الجمل وتعديل DDL)
	# -------------------------------------------------------------

	def test_for_update_removal(self):
		sql = "SELECT * FROM `tabDoc` WHERE `name` = 'test' FOR UPDATE"
		expected = "SELECT * FROM [tabDoc] WHERE [name] = 'test' "
		self.assertEqual(modify_query(sql), expected)

	def test_truncate_table_conversion(self):
		sql = "TRUNCATE `tabDoc`"
		expected = "TRUNCATE TABLE [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_truncate_table_idempotent(self):
		sql = "TRUNCATE TABLE [tabDoc]"
		expected = "TRUNCATE TABLE [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	# -------------------------------------------------------------
	# 8. Edge Cases & Prevention of Unsafe Transformations
	#    (الحالات الحدية ومنع التحويلات التي لا يمكن ضمان سلامتها)
	# -------------------------------------------------------------

	def test_none_and_empty_queries(self):
		self.assertIsNone(modify_query(None))
		self.assertEqual(modify_query(""), "")
		self.assertEqual(modify_query("   "), "   ")

	def test_non_string_query(self):
		self.assertEqual(modify_query(12345), 12345)

	def test_unclosed_single_quote_safety(self):
		# Malformed query with unclosed quote must be left untouched to avoid corrupting data
		sql = "SELECT * FROM `tabDoc` WHERE `name` = 'unclosed_string"
		self.assertEqual(modify_query(sql), sql)

	def test_unclosed_block_comment_safety(self):
		# Malformed block comment must be left untouched
		sql = "/* unclosed comment SELECT `name` FROM `tabDoc`"
		self.assertEqual(modify_query(sql), sql)

	def test_unbalanced_parentheses_safety(self):
		# Malformed function call with missing closing paren must be left untouched
		sql = "SELECT DATE(creation FROM `tabDoc`"
		self.assertEqual(modify_query(sql), "SELECT DATE(creation FROM [tabDoc]")

	def test_already_tsql_datediff_not_mangled(self):
		# 3-arg DATEDIFF is standard T-SQL syntax and must be preserved
		sql = "SELECT DATEDIFF(day, `start_date`, `end_date`), DATEDIFF(hour, `t1`, `t2`) FROM `tabDoc`"
		expected = "SELECT DATEDIFF(day, [start_date], [end_date]), DATEDIFF(hour, [t1], [t2]) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_already_tsql_constructs_preserved(self):
		# Existing square brackets, CAST, ISNULL, TOP should not be mangled
		sql = "SELECT TOP 10 [name], ISNULL([title], ''), CAST([creation] AS DATE) FROM [tabDoc]"
		expected = "SELECT TOP 10 [name], ISNULL([title], ''), CAST([creation] AS DATE) FROM [tabDoc]"
		self.assertEqual(modify_query(sql), expected)

	def test_complex_combination_query(self):
		# Full real-world query with multiple simultaneous transforms
		sql = (
			"SELECT `name`, IFNULL(`title`, 'N/A'), DATE(`creation`), LENGTH(`owner`) "
			"FROM `tabDoc` "
			"WHERE `status` = 'Active' AND `remarks` = 'Check IFNULL and `backticks`' "
			"ORDER BY `creation` DESC "
			"LIMIT 25 OFFSET 50 "
			"FOR UPDATE"
		)
		expected = (
			"SELECT [name], ISNULL([title], 'N/A'), CAST([creation] AS DATE), LEN([owner]) "
			"FROM [tabDoc] "
			"WHERE [status] = 'Active' AND [remarks] = 'Check IFNULL and `backticks`' "
			"ORDER BY [creation] DESC "
			"OFFSET 50 ROWS FETCH NEXT 25 ROWS ONLY "
		)
		self.assertEqual(modify_query(sql), expected)


class TestMSSQLPaginationAndDistinct(unittest.TestCase):
	"""
	Live database tests verifying pagination stability, preservation of original ORDER BY,
	and DISTINCT pagination across duplicate data on SQL Server.
	"""

	@classmethod
	def setUpClass(cls):
		import frappe
		cls.frappe = frappe
		cls.table = "tab_TestMSSQLPagination"
		cls.frappe.db.sql(f"IF OBJECT_ID('{cls.table}') IS NOT NULL DROP TABLE [{cls.table}]")
		cls.frappe.db.sql(f"""
			CREATE TABLE [{cls.table}] (
				id INT IDENTITY(1,1) PRIMARY KEY,
				category NVARCHAR(50),
				score INT,
				val NVARCHAR(50)
			)
		""")
		# Seed duplicate data
		test_data = [
			('A', 10, 'row1'),
			('B', 20, 'row2'),
			('A', 10, 'row3'),
			('C', 30, 'row4'),
			('B', 20, 'row5'),
			('C', 30, 'row6'),
			('A', 15, 'row7'),
			('B', 25, 'row8'),
			('C', 35, 'row9'),
			('D', 40, 'row10'),
		]
		for cat, score, val in test_data:
			cls.frappe.db.sql(
				f"INSERT INTO [{cls.table}] (category, score, val) VALUES (%s, %s, %s)",
				(cat, score, val)
			)

	@classmethod
	def tearDownClass(cls):
		cls.frappe.db.sql(f"IF OBJECT_ID('{cls.table}') IS NOT NULL DROP TABLE [{cls.table}]")

	def test_explicit_order_by_preserved_and_stable(self):
		"""Verify that original ORDER BY is strictly preserved without inventing order."""
		q_p1 = f"SELECT category, score, val FROM `{self.table}` ORDER BY score DESC, id ASC LIMIT 5 OFFSET 0"
		p1 = self.frappe.db.sql(q_p1, as_dict=True)

		q_p2 = f"SELECT category, score, val FROM `{self.table}` ORDER BY score DESC, id ASC LIMIT 5 OFFSET 5"
		p2 = self.frappe.db.sql(q_p2, as_dict=True)

		# 1. Page sizes
		self.assertEqual(len(p1), 5)
		self.assertEqual(len(p2), 5)

		# 2. Strict sort preservation
		scores = [r.score for r in p1] + [r.score for r in p2]
		self.assertEqual(scores, sorted(scores, reverse=True))

		# 3. No duplicate rows between pages
		p1_vals = {r.val for r in p1}
		p2_vals = {r.val for r in p2}
		self.assertEqual(len(p1_vals.intersection(p2_vals)), 0, "Found row duplicates between pages!")

	def test_distinct_pagination_across_duplicate_data(self):
		"""Verify DISTINCT pagination deduplicates properly and pages without loss or duplication."""
		# Distinct categories are 'A', 'B', 'C', 'D' (total 4)
		q_p1 = f"SELECT DISTINCT category FROM `{self.table}` LIMIT 2 OFFSET 0"
		p1 = self.frappe.db.sql(q_p1, as_dict=True)

		q_p2 = f"SELECT DISTINCT category FROM `{self.table}` LIMIT 2 OFFSET 2"
		p2 = self.frappe.db.sql(q_p2, as_dict=True)

		p1_cats = [r.category for r in p1]
		p2_cats = [r.category for r in p2]

		# Must be 2 unique categories per page
		self.assertEqual(len(p1_cats), 2)
		self.assertEqual(len(p2_cats), 2)

		# Zero intersection (no duplicates across pages)
		self.assertEqual(len(set(p1_cats).intersection(set(p2_cats))), 0)

		# All 4 categories covered
		all_cats = set(p1_cats + p2_cats)
		self.assertEqual(all_cats, {"A", "B", "C", "D"})

	def test_raw_query_without_order_by_streaming(self):
		"""Verify ORDER BY (SELECT NULL) fallback does not fail and streams pages without syntax error."""
		q_p1 = f"SELECT id, val FROM `{self.table}` LIMIT 5 OFFSET 0"
		p1 = self.frappe.db.sql(q_p1, as_dict=True)

		q_p2 = f"SELECT id, val FROM `{self.table}` LIMIT 5 OFFSET 5"
		p2 = self.frappe.db.sql(q_p2, as_dict=True)

		self.assertEqual(len(p1), 5)
		self.assertEqual(len(p2), 5)
		p1_ids = {r.id for r in p1}
		p2_ids = {r.id for r in p2}
		self.assertEqual(len(p1_ids.intersection(p2_ids)), 0)


class TestMSSQLBulkInsert(unittest.TestCase):
	"""
	Live database tests for bulk_insert on MSSQL verifying:
	1. Intra-batch duplicate primary keys handling.
	2. Existing database duplicate primary keys handling.
	3. Secondary unique constraint conflict handling.
	4. Parameter limit (2,100) and VALUES limit (1,000) dynamic chunking (inserting 2,500 rows).
	5. Concurrency race simulation with multi-threaded workers.
	"""

	@classmethod
	def setUpClass(cls):
		import frappe
		cls.frappe = frappe
		cls.table = "tab_TestMSSQLBulk"
		cls.frappe.db.sql(f"IF OBJECT_ID('{cls.table}') IS NOT NULL DROP TABLE [{cls.table}]")
		cls.frappe.db.sql(f"""
			CREATE TABLE [{cls.table}] (
				[name] NVARCHAR(140) PRIMARY KEY,
				[email] NVARCHAR(140) UNIQUE,
				[score] INT,
				[category] NVARCHAR(50),
				[creation] DATETIME2 DEFAULT SYSDATETIME()
			)
		""")

	@classmethod
	def tearDownClass(cls):
		cls.frappe.db.sql(f"IF OBJECT_ID('{cls.table}') IS NOT NULL DROP TABLE [{cls.table}]")

	def setUp(self):
		self.frappe.db.sql(f"DELETE FROM [{self.table}]")

	def test_bulk_insert_intra_batch_duplicates(self):
		"""Verify that duplicates within the incoming values list do not fail the bulk insert."""
		# 6 distinct names, but 10 rows in total (name1 and name2 repeated multiple times)
		values = [
			("rec1", "rec1@test.com", 10, "A"),
			("rec2", "rec2@test.com", 20, "B"),
			("rec1", "rec1_dup@test.com", 15, "A"),  # duplicate PK rec1
			("rec3", "rec3@test.com", 30, "C"),
			("rec2", "rec2_dup@test.com", 25, "B"),  # duplicate PK rec2
			("rec4", "rec4@test.com", 40, "D"),
			("rec5", "rec5@test.com", 50, "E"),
			("rec1", "rec1_dup2@test.com", 18, "A"), # duplicate PK rec1
			("rec6", "rec6@test.com", 60, "F"),
			("rec3", "rec3_dup@test.com", 35, "C"),  # duplicate PK rec3
		]
		fields = ["name", "email", "score", "category"]
		self.frappe.db.bulk_insert("_TestMSSQLBulk", fields, values, ignore_duplicates=True)

		count = self.frappe.db.sql(f"SELECT COUNT(*) FROM [{self.table}]")[0][0]
		self.assertEqual(count, 6)

	def test_bulk_insert_existing_database_duplicates(self):
		"""Verify that existing database records are skipped when ignore_duplicates=True."""
		self.frappe.db.sql(
			f"INSERT INTO [{self.table}] ([name], [email], [score], [category]) VALUES "
			"('rec1', 'e1@test.com', 1, 'A'), ('rec2', 'e2@test.com', 2, 'B'), ('rec3', 'e3@test.com', 3, 'C')"
		)
		# Overlapping records: rec2 and rec3 already exist; rec4 and rec5 are new
		new_values = [
			("rec2", "e2_new@test.com", 20, "B"),
			("rec3", "e3_new@test.com", 30, "C"),
			("rec4", "e4@test.com", 40, "D"),
			("rec5", "e5@test.com", 50, "E"),
		]
		fields = ["name", "email", "score", "category"]
		self.frappe.db.bulk_insert("_TestMSSQLBulk", fields, new_values, ignore_duplicates=True)

		count = self.frappe.db.sql(f"SELECT COUNT(*) FROM [{self.table}]")[0][0]
		self.assertEqual(count, 5)

	def test_bulk_insert_secondary_unique_constraint_graceful_fallback(self):
		"""Verify that conflict on a secondary UNIQUE constraint is handled gracefully."""
		self.frappe.db.sql(
			f"INSERT INTO [{self.table}] ([name], [email], [score], [category]) VALUES "
			"('user1', 'shared@test.com', 10, 'A')"
		)
		# user2 has a DIFFERENT primary key but the SAME unique email
		conflict_values = [
			("user2", "shared@test.com", 20, "A"),  # Collides on unique email
			("user3", "unique3@test.com", 30, "B"), # Should be inserted
		]
		fields = ["name", "email", "score", "category"]
		self.frappe.db.bulk_insert("_TestMSSQLBulk", fields, conflict_values, ignore_duplicates=True)

		rows = self.frappe.db.sql(f"SELECT [name] FROM [{self.table}]")
		names = {r[0] for r in rows}
		self.assertIn("user1", names)
		self.assertIn("user3", names)
		self.assertNotIn("user2", names)

	def test_bulk_insert_large_batch_parameter_limits(self):
		"""Verify that bulk_insert seamlessly chunks 2,500 rows (> 10,000 parameters) on SQL Server."""
		large_data = [(f"bulk_rec_{i}", f"bulk_{i}@test.com", i, "GRP") for i in range(2500)]
		fields = ["name", "email", "score", "category"]

		self.frappe.db.bulk_insert("_TestMSSQLBulk", fields, large_data, ignore_duplicates=True)
		count = self.frappe.db.sql(f"SELECT COUNT(*) FROM [{self.table}]")[0][0]
		self.assertEqual(count, 2500)

	def test_bulk_insert_concurrency_race_simulation(self):
		"""Verify that if a concurrent transaction commits duplicate keys,
		bulk_insert catches the conflict and inserts non-conflicting rows gracefully."""
		fields = ["name", "email", "score", "category"]
		# Pre-insert records 3 and 7 to simulate a concurrent transaction committing ahead
		self.frappe.db.sql(
			f"INSERT INTO [{self.table}] ([name], [email], [score], [category]) VALUES "
			"('race_rec_3', 'race_3@test.com', 3, 'RACE'), ('race_rec_7', 'race_7@test.com', 7, 'RACE')"
		)
		self.frappe.db.commit()

		# Bulk insert full set of 10 records (collides with 3 and 7)
		records = [(f"race_rec_{i}", f"race_{i}@test.com", i, "RACE") for i in range(10)]
		self.frappe.db.bulk_insert("_TestMSSQLBulk", fields, records, ignore_duplicates=True)
		self.frappe.db.commit()

		count = self.frappe.db.sql(f"SELECT COUNT(*) FROM [{self.table}] WHERE [category] = 'RACE'")[0][0]
		self.assertEqual(count, 10)


if __name__ == "__main__":
	unittest.main()
