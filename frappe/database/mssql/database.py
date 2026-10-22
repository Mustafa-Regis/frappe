# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import re
from contextlib import contextmanager, suppress

try:
	import pymssql
except ImportError:
	pymssql = None

import frappe
from frappe.database.database import Database
from frappe.database.mssql.schema import MSSQLTable
from frappe.database.utils import EmptyQueryValues, LazyDecode
from frappe.utils import cstr, get_table_name

TOKEN_PATTERN = re.compile(
	r"'(?:''|\\.|[^'])*'|--[^\r\n]*|/\*[\s\S]*?\*/"
)
LIMIT_PATTERN = re.compile(
	r"\bLIMIT\s+(\d+|%s)(?:\s+OFFSET\s+(\d+|%s)|\s*,\s*(\d+|%s))?",
	flags=re.IGNORECASE,
)


class MSSQLExceptionUtil:
	if pymssql:
		ProgrammingError = pymssql.ProgrammingError
		TableMissingError = pymssql.ProgrammingError
		OperationalError = pymssql.OperationalError
		InternalError = pymssql.InternalError
		SQLError = pymssql.ProgrammingError
		DataError = pymssql.DataError
		InterfaceError = pymssql.InterfaceError
	else:
		ProgrammingError = Exception
		TableMissingError = Exception
		OperationalError = Exception
		InternalError = Exception
		SQLError = Exception
		DataError = Exception
		InterfaceError = Exception

	@staticmethod
	def is_deadlocked(e):
		# SQL Server deadlock error number is 1205
		return "1205" in cstr(e)

	@staticmethod
	def is_timedout(e):
		# SQL Server timeout error numbers: -2 (Query timeout) or 1222 (Lock timeout)
		return "-2" in cstr(e) or "1222" in cstr(e)

	@staticmethod
	def is_table_missing(e):
		# SQL Server error 208: Invalid object name '...'
		return "208" in cstr(e)

	@staticmethod
	def is_missing_table(e):
		return MSSQLExceptionUtil.is_table_missing(e)

	@staticmethod
	def is_missing_column(e):
		# SQL Server error 207: Invalid column name '...'
		return "207" in cstr(e)

	@staticmethod
	def is_duplicate_fieldname(e):
		# SQL Server error 2705: Column names in each table must be unique
		return "2705" in cstr(e)

	@staticmethod
	def is_unique_key_violation(e):
		# SQL Server errors 2627 (Violation of PRIMARY KEY / UNIQUE constraint) or 2601 (Cannot insert duplicate key)
		return "2627" in cstr(e) or "2601" in cstr(e)

	@staticmethod
	def is_syntax_error(e):
		# SQL Server syntax errors: 102 (Incorrect syntax near...) or 156
		return "102" in cstr(e) or "156" in cstr(e)

	@staticmethod
	def is_read_only_mode_error(e) -> bool:
		return "3906" in cstr(e)  # Failed to update database because database is read-only

	@staticmethod
	def is_access_denied(e):
		return "229" in cstr(e) or "916" in cstr(e)

	@staticmethod
	def cant_drop_field_or_key(e):
		return "5074" in cstr(e) or "3728" in cstr(e)

	@staticmethod
	def is_duplicate_entry(e):
		return "2627" in cstr(e) or "2601" in cstr(e)

	@staticmethod
	def is_primary_key_violation(e):
		return "2627" in cstr(e) and "PRIMARY KEY" in cstr(e).upper()

	@staticmethod
	def is_statement_timeout(e):
		return MSSQLExceptionUtil.is_timedout(e)

	@staticmethod
	def is_db_table_size_limit(e) -> bool:
		return False

	@staticmethod
	def is_interface_error(e):
		return isinstance(e, getattr(pymssql, "InterfaceError", Exception)) if pymssql else False


class MSSQLDatabase(MSSQLExceptionUtil, Database):
	REGEX_CHARACTER = "LIKE"
	default_port = "1433"

	def setup_type_map(self):
		self.db_type = "mssql"
		self.type_map = {
			"Currency": ("decimal", "21,9"),
			"Int": ("bigint", None),
			"Long Int": ("bigint", None),
			"Float": ("decimal", "21,9"),
			"Percent": ("decimal", "21,9"),
			"Check": ("tinyint", None),
			"Small Text": ("nvarchar(max)", ""),
			"Long Text": ("nvarchar(max)", ""),
			"Code": ("nvarchar(max)", ""),
			"Text Editor": ("nvarchar(max)", ""),
			"Markdown Editor": ("nvarchar(max)", ""),
			"HTML Editor": ("nvarchar(max)", ""),
			"Date": ("date", ""),
			"Datetime": ("datetime2", "6"),
			"Time": ("time", "6"),
			"Text": ("nvarchar(max)", ""),
			"Data": ("nvarchar", self.VARCHAR_LEN),
			"Link": ("nvarchar", self.VARCHAR_LEN),
			"Dynamic Link": ("nvarchar", self.VARCHAR_LEN),
			"Password": ("nvarchar(max)", ""),
			"Select": ("nvarchar", self.VARCHAR_LEN),
			"Rating": ("decimal", "3,2"),
			"Read Only": ("nvarchar", self.VARCHAR_LEN),
			"Attach": ("nvarchar(max)", ""),
			"Attach Image": ("nvarchar(max)", ""),
			"Signature": ("nvarchar(max)", ""),
			"Color": ("nvarchar", self.VARCHAR_LEN),
			"Barcode": ("nvarchar(max)", ""),
			"Geolocation": ("nvarchar(max)", ""),
			"Duration": ("decimal", "21,9"),
			"Icon": ("nvarchar", self.VARCHAR_LEN),
			"Phone": ("nvarchar", self.VARCHAR_LEN),
			"Autocomplete": ("nvarchar", self.VARCHAR_LEN),
			"JSON": ("nvarchar(max)", ""),
		}

	def get_connection(self):
		if not pymssql:
			raise ImportError("pymssql is not installed. Please install it with `pip install pymssql`")

		conn_settings = {
			"server": self.host or "127.0.0.1",
			"user": self.user,
			"password": self.password or "",
			"database": self.cur_db_name,
			"port": str(self.port or self.default_port),
			"autocommit": True,
			"charset": "UTF-8",
		}
		return pymssql.connect(**conn_settings)

	@property
	def last_query(self):
		return getattr(self, "_last_query", "")

	def begin(self, *, read_only=False):
		self._read_only = bool(read_only)
		try:
			self.sql("IF @@TRANCOUNT = 0 BEGIN TRANSACTION")
		except Exception:
			pass

	def commit(self):
		self._read_only = False
		self.before_rollback.reset()
		self.after_rollback.reset()
		self.before_commit.run()

		try:
			self.sql("IF @@TRANCOUNT > 0 COMMIT TRANSACTION")
		except Exception:
			pass

		self.value_cache.clear()
		self.after_commit.run()

	def rollback(self, *, save_point=None):
		if save_point:
			try:
				self.sql(f"IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION {save_point}")
			except Exception:
				pass
			self.value_cache.clear()
		else:
			self._read_only = False
			self.before_commit.reset()
			self.after_commit.reset()
			self.before_rollback.run()

			try:
				self.sql("IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
			except Exception:
				pass

			self.value_cache.clear()
			self.after_rollback.run()

	def savepoint(self, save_point):
		try:
			self.sql(f"IF @@TRANCOUNT = 0 BEGIN TRANSACTION; SAVE TRANSACTION {save_point}")
		except Exception:
			pass

	def release_savepoint(self, save_point):
		pass

	@contextmanager
	def unbuffered_cursor(self):
		try:
			if not self._conn:
				self.connect()

			original_cursor = self._cursor
			new_cursor = self._cursor = self._conn.cursor()
			yield
		finally:
			self._cursor = original_cursor
			try:
				new_cursor.close()
			except Exception:
				pass

	def get_database_size(self):
		"""Returns size of current database in MB."""
		res = self.sql(
			"""SELECT CAST(SUM(CAST(size AS BIGINT)) * 8.0 / 1024 AS FLOAT)
			FROM sys.database_files"""
		)
		return res[0][0] if res and res[0] else 0.0

	def set_execution_timeout(self, seconds: int):
		"""Sets the query execution timeout in seconds for this session."""
		ms = -1 if not seconds else int(seconds * 1000)
		self.sql(f"SET LOCK_TIMEOUT {ms}")

	def mogrify(self, query, values=None):
		if not values:
			return query
		try:
			if isinstance(values, (list, tuple)):
				formatted = tuple(f"'{self.escape(v)}'" if isinstance(v, str) else str(v) for v in values)
				return query % formatted
			elif isinstance(values, dict):
				formatted = {k: f"'{self.escape(v)}'" if isinstance(v, str) else str(v) for k, v in values.items()}
				return query % formatted
		except Exception:
			pass
		return query

	def lazy_mogrify(self, query, values=None) -> str:
		return self.mogrify(query, values)

	def escape(self, s, percent=True):
		"""Escape quotes and percent in given string for MSSQL."""
		if isinstance(s, bytes):
			s = s.decode("utf-8")
		if s is None:
			s = ""
		s = str(s).replace("'", "''")
		if percent:
			s = s.replace("%", "%%")
		return "'" + s + "'"

	def _transform_query(self, query, values=None):
		query = self.modify_query(query)
		self._last_query = query
		if values is not None and values is not EmptyQueryValues:
			values = _normalize_query_values(values)
		return query, values

	def sql(self, query, values=EmptyQueryValues, *args, **kwargs):
		if getattr(self, "_read_only", False) and isinstance(query, str) and re.match(r"^\s*(insert|update|delete|drop|alter|truncate)\b", query, flags=re.IGNORECASE):
			raise frappe.InReadOnlyMode

		if values is not None and values is not EmptyQueryValues:
			values = _normalize_query_values(values)
		query = self.modify_query(query)
		self._last_query = query
		return super().sql(query, values, *args, **kwargs)

	def _transform_result(self, result: list[tuple]) -> list[tuple]:
		if not result:
			return result
		from decimal import Decimal
		transformed = []
		for row in result:
			if any(isinstance(val, Decimal) for val in row):
				transformed.append(tuple(float(val) if isinstance(val, Decimal) else val for val in row))
			else:
				transformed.append(row)
		return transformed

	def modify_query(self, query):
		"""Translate MariaDB-specific SQL syntaxes into SQL Server syntax."""
		return modify_query(query)

	def truncate(self, doctype: str):
		return self.sql_ddl(f"TRUNCATE TABLE `{get_table_name(doctype)}`")

	def get_tables(self, cached=True):
		return [
			d[0]
			for d in self.sql(
				"""SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
				WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_CATALOG = %s""",
				(self.cur_db_name,),
			)
		]

	def get_table_columns_description(self, table_name):
		"""Returns list of column and its description for MSSQL."""
		rows = self.sql(
			"""
			SELECT 
				c.name AS [name],
				CASE 
					WHEN t.name IN ('nvarchar', 'varchar') AND c.max_length = -1 THEN t.name + '(max)'
					WHEN t.name IN ('nvarchar') THEN t.name + '(' + CAST(c.max_length / 2 AS VARCHAR) + ')'
					WHEN t.name IN ('varchar') THEN t.name + '(' + CAST(c.max_length AS VARCHAR) + ')'
					WHEN t.name IN ('decimal', 'numeric') THEN t.name + '(' + CAST(c.precision AS VARCHAR) + ',' + CAST(c.scale AS VARCHAR) + ')'
					ELSE t.name 
				END AS [type],
				dc.definition AS [default],
				CASE WHEN EXISTS (
					SELECT 1 FROM sys.indexes i 
					JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id 
					WHERE i.object_id = c.object_id AND ic.column_id = c.column_id AND i.is_unique = 0
				) THEN 1 ELSE 0 END AS [index],
				CASE WHEN EXISTS (
					SELECT 1 FROM sys.indexes i 
					JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id 
					WHERE i.object_id = c.object_id AND ic.column_id = c.column_id AND i.is_unique = 1 AND i.is_primary_key = 0
				) THEN 1 ELSE 0 END AS [unique]
			FROM sys.columns c
			JOIN sys.types t ON c.user_type_id = t.user_type_id
			JOIN sys.tables tbl ON c.object_id = tbl.object_id
			LEFT JOIN sys.default_constraints dc ON c.default_object_id = dc.object_id
			WHERE tbl.name = %s
			""",
			(table_name,),
			as_dict=1,
		)

		for r in rows:
			val = r.get("default")
			if val:
				val = str(val).strip()
				while val.startswith("(") and val.endswith(")"):
					val = val[1:-1].strip()
				if val.upper() == "NULL":
					val = None
				r["default"] = val

		return rows

	def get_column_indexes(self, table_name, fieldname, unique_only=None):
		query = """
			SELECT DISTINCT i.name, i.is_unique
			FROM sys.indexes i
			JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
			JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
			WHERE i.object_id = OBJECT_ID(%s) AND c.name = %s AND i.is_primary_key = 0
		"""
		rows = self.sql(query, (f"[{table_name}]", fieldname), as_dict=True)
		if unique_only is True:
			return [r["name"] for r in rows if r["is_unique"]]
		elif unique_only is False:
			return [r["name"] for r in rows if not r["is_unique"]]
		return [r["name"] for r in rows]

	def has_index(self, table_name, index_name):
		return bool(
			self.sql(
				"""SELECT 1 FROM sys.indexes WHERE name = %s AND object_id = OBJECT_ID(%s)""",
				(index_name, f"[{table_name}]"),
			)
		)

	def add_index(self, doctype: str, fields: list, index_name: str | None = None):
		"""Creates an index with given fields if not already created."""
		table_name = get_table_name(doctype)
		index_name = (index_name or self.get_index_name(fields))[:128]
		clean_fields = [re.sub(r"\(.*\)", "", field) for field in fields]

		# Check if any field is LOB / nvarchar(max) which MSSQL cannot index
		try:
			col_types = {
				c["name"]: c["type"].lower()
				for c in self.get_table_columns_description(table_name)
			}
			for f in clean_fields:
				if "(max)" in col_types.get(f, ""):
					return
		except Exception:
			pass

		fields_str = ", ".join(f"[{f}]" for f in clean_fields)

		if not self.has_index(table_name, index_name):
			try:
				self.sql_ddl(f"CREATE INDEX [{index_name}] ON [{table_name}] ({fields_str})")
			except Exception as e:
				if "1919" in str(e):
					return
				raise

	def add_unique(self, doctype, fields, constraint_name=None):
		if isinstance(fields, str):
			fields = [fields]
		if not constraint_name:
			constraint_name = "unique_" + "_".join(fields)
		constraint_name = constraint_name[:128]
		table_name = get_table_name(doctype)
		clean_fields = [re.sub(r"\(.*\)", "", field) for field in fields]

		try:
			col_types = {
				c["name"]: c["type"].lower()
				for c in self.get_table_columns_description(table_name)
			}
			for f in clean_fields:
				if "(max)" in col_types.get(f, ""):
					return
		except Exception:
			pass

		fields_str = ", ".join(f"[{f}]" for f in clean_fields)

		if not self.has_index(table_name, constraint_name):
			try:
				self.sql_ddl(f"CREATE UNIQUE INDEX [{constraint_name}] ON [{table_name}] ({fields_str})")
			except Exception as e:
				if "1919" in str(e):
					return
				raise


	def get_database_list(self):
		return self.sql("SELECT name FROM sys.databases WHERE database_id > 4", pluck=True)

	def create_sequence(self, doctype, check_not_exists=False):
		seq_name = f"seq_{doctype}"[:128]
		if check_not_exists:
			self.sql(
				f"""IF NOT EXISTS (SELECT * FROM sys.sequences WHERE name = '{seq_name}')
				CREATE SEQUENCE [{seq_name}] START WITH 1 INCREMENT BY 1"""
			)
		else:
			self.sql(f"CREATE SEQUENCE [{seq_name}] START WITH 1 INCREMENT BY 1")

	def get_next_sequence_val(self, doctype):
		seq_name = f"seq_{doctype}"[:128]
		return self.sql(f"SELECT NEXT VALUE FOR [{seq_name}]")[0][0]

	def updatedb(self, doctype, meta=None):
		"""Syncs a DocType to the table in MSSQL."""
		res = self.sql(f"SELECT issingle FROM [tabDocType] WHERE name = %s", (doctype,))
		if not res:
			raise Exception(f"Wrong doctype {doctype} in updatedb")

		if not res[0][0]:
			db_table = MSSQLTable(doctype, meta)
			db_table.validate()
			db_table.sync()
			self.begin()

	def check_implicit_commit(self, query):
		pass  # MSSQL supports transactional DDL

	def create_auth_table(self):
		self.sql_ddl(
			f"""IF OBJECT_ID('__Auth') IS NULL
			CREATE TABLE [__Auth] (
				[doctype] NVARCHAR(140) NOT NULL,
				[name] NVARCHAR(255) NOT NULL,
				[fieldname] NVARCHAR(140) NOT NULL,
				[password] NVARCHAR(MAX) NOT NULL,
				[encrypted] INT NOT NULL DEFAULT 0,
				PRIMARY KEY ([doctype], [name], [fieldname])
			)"""
		)

	def create_global_search_table(self):
		if "__global_search" not in self.get_tables():
			self.sql(
				f"""CREATE TABLE [__global_search] (
					[doctype] NVARCHAR(100),
					[name] NVARCHAR({self.VARCHAR_LEN}),
					[title] NVARCHAR({self.VARCHAR_LEN}),
					[content] NVARCHAR(MAX),
					[route] NVARCHAR({self.VARCHAR_LEN}),
					[published] INT NOT NULL DEFAULT 0,
					CONSTRAINT [unique___global_search] UNIQUE ([doctype], [name])
				)"""
			)

	def create_user_settings_table(self):
		self.sql_ddl(
			"""IF OBJECT_ID('__UserSettings') IS NULL
			CREATE TABLE [__UserSettings] (
				[user] NVARCHAR(180) NOT NULL,
				[doctype] NVARCHAR(180) NOT NULL,
				[data] NVARCHAR(MAX),
				CONSTRAINT [unique___UserSettings] UNIQUE ([user], [doctype])
			)"""
		)

	def rename_table(self, old_name: str, new_name: str):
		old_name = get_table_name(old_name)
		new_name = get_table_name(new_name)
		return self.sql(f"EXEC sp_rename '{old_name}', '{new_name}'")

	def rename_column(self, doctype: str, old_column_name: str, new_column_name: str):
		table_name = get_table_name(doctype)
		return self.sql(f"EXEC sp_rename '[{table_name}].[{old_column_name}]', '{new_column_name}', 'COLUMN'")

	def estimate_count(self, doctype: str) -> int:
		"""Get estimated count of total rows in a table for MSSQL."""
		from frappe.utils.data import cint

		table = get_table_name(doctype)
		count = self.sql(
			"""
			SELECT SUM(p.rows) 
			FROM sys.partitions p
			JOIN sys.tables t ON p.object_id = t.object_id
			WHERE t.name = %s AND p.index_id IN (0, 1)
			""",
			(table,),
		)
		return cint(count[0][0]) if count and count[0][0] is not None else 0


def mask_tokens(sql: str):
	tokens = {}

	def replacer(m):
		idx = len(tokens)
		key = f"___MSSQL_TOKEN_{idx}___"
		tokens[key] = m.group(0)
		return key

	masked = TOKEN_PATTERN.sub(replacer, sql)
	# Safety check: if an unclosed single quote or block comment remains,
	# we cannot guarantee safe transformation, so abort by returning None.
	if "'" in masked or "/*" in masked:
		return None, None
	return masked, tokens


def unmask_tokens(sql: str, tokens: dict):
	if not tokens:
		return sql
	for key, val in tokens.items():
		sql = sql.replace(key, val)
	return sql


def split_top_level_args(arg_string: str):
	args = []
	current = []
	depth = 0
	for char in arg_string:
		if char == "(":
			depth += 1
			current.append(char)
		elif char == ")":
			depth -= 1
			current.append(char)
		elif char == "," and depth == 0:
			args.append("".join(current).strip())
			current = []
		else:
			current.append(char)
	if depth != 0:
		return None
	if current:
		args.append("".join(current).strip())
	return args


def transform_function_calls(sql: str, func_name: str, handler_fn):
	pattern = re.compile(rf"\b{re.escape(func_name)}\s*\(", flags=re.IGNORECASE)
	while True:
		matches = list(pattern.finditer(sql))
		if not matches:
			break
		transformed_any = False
		for m in reversed(matches):
			start_paren = m.end() - 1
			depth = 1
			i = start_paren + 1
			while i < len(sql) and depth > 0:
				if sql[i] == "(":
					depth += 1
				elif sql[i] == ")":
					depth -= 1
				i += 1
			if depth != 0:
				continue
			end_paren = i - 1
			args_str = sql[start_paren + 1 : end_paren]
			transformed = handler_fn(args_str)
			if transformed is not None and transformed != sql[m.start() : end_paren + 1]:
				sql = sql[: m.start()] + transformed + sql[end_paren + 1 :]
				transformed_any = True
				break
		if not transformed_any:
			break
	return sql


def transform_limit_offset(sql: str):
	while True:
		matches = list(LIMIT_PATTERN.finditer(sql))
		if not matches:
			break
		m = matches[-1]

		if m.group(2) is not None:
			# LIMIT limit OFFSET offset
			limit_val = m.group(1)
			offset_val = m.group(2)
		elif m.group(3) is not None:
			# LIMIT offset, limit
			offset_val = m.group(1)
			limit_val = m.group(3)
		else:
			# LIMIT limit
			limit_val = m.group(1)
			offset_val = "0"

		# Analyze current scope backwards from m.start() to subquery / statement boundary
		pos = m.start() - 1
		depth = 0
		scope_chars = []
		while pos >= 0:
			c = sql[pos]
			if c == ")":
				depth += 1
			elif c == "(":
				if depth > 0:
					depth -= 1
				else:
					# Subquery boundary reached
					break
			else:
				if depth == 0:
					scope_chars.append(c)
			pos -= 1

		scope_text = "".join(reversed(scope_chars))
		has_order_by = bool(re.search(r"\bORDER\s+BY\b", scope_text, flags=re.IGNORECASE))
		is_distinct = bool(re.search(r"\bSELECT\s+(?:TOP\s+\d+\s+)?DISTINCT\b", scope_text, flags=re.IGNORECASE))
		fallback_order = "ORDER BY 1" if is_distinct else "ORDER BY (SELECT NULL)"

		prefix_space = "" if sql[: m.start()].endswith(" ") else " "
		order_clause = "" if has_order_by else f"{prefix_space}{fallback_order} "
		replacement = f"{order_clause}OFFSET {offset_val} ROWS FETCH NEXT {limit_val} ROWS ONLY"
		sql = sql[: m.start()] + replacement + sql[m.end() :]

	return sql


def transform_tuple_in(sql: str) -> str:
	pattern = re.compile(
		r'\(\s*([a-zA-Z0-9_"`\[\],\s\.]+?)\s*\)\s+(NOT\s+IN|IN)\s*\(',
		flags=re.IGNORECASE,
	)

	pos = 0
	while True:
		m = pattern.search(sql, pos)
		if not m:
			break

		cols_str = m.group(1)
		op = m.group(2).upper()
		cols = [c.strip() for c in cols_str.split(",") if c.strip()]
		if len(cols) <= 1:
			pos = m.end()
			continue

		start_in = m.end() - 1
		depth = 0
		end_in = -1
		for i in range(start_in, len(sql)):
			if sql[i] == "(":
				depth += 1
			elif sql[i] == ")":
				depth -= 1
				if depth == 0:
					end_in = i
					break

		if end_in == -1:
			pos = m.end()
			continue

		in_content = sql[start_in + 1 : end_in].strip()
		tuple_strs = split_top_level_args(in_content)
		if not tuple_strs:
			pos = m.end()
			continue

		or_branches = []
		valid = True
		for t in tuple_strs:
			t = t.strip()
			if not (t.startswith("(") and t.endswith(")")):
				valid = False
				break
			vals = split_top_level_args(t[1:-1])
			if not vals or len(vals) != len(cols):
				valid = False
				break
			and_branch = " AND ".join(f"{c} = {v}" for c, v in zip(cols, vals))
			or_branches.append(f"({and_branch})")

		if not valid or not or_branches:
			pos = m.end()
			continue

		combined = " OR ".join(or_branches)
		replacement = f"(NOT ({combined}))" if "NOT" in op else f"({combined})"
		sql = sql[: m.start()] + replacement + sql[end_in + 1 :]
		pos = m.start() + len(replacement)

	return sql


def _normalize_query_values(val):
	"""Normalize datetimes and dates in query parameters so pymssql preserves full microsecond precision."""
	import datetime
	if isinstance(val, datetime.datetime):
		return val.strftime("%Y-%m-%d %H:%M:%S.%f")
	elif isinstance(val, datetime.date):
		return val.strftime("%Y-%m-%d")
	elif isinstance(val, datetime.time):
		return val.strftime("%H:%M:%S.%f")
	elif isinstance(val, dict):
		return {k: _normalize_query_values(v) for k, v in val.items()}
	elif isinstance(val, tuple):
		return tuple(_normalize_query_values(v) for v in val)
	elif isinstance(val, list):
		return [_normalize_query_values(v) for v in val]
	return val


def modify_query(query: str) -> str:
	"""Safely translate MariaDB-specific SQL syntaxes into SQL Server (T-SQL) syntax."""
	if not isinstance(query, str) or not query.strip():
		return query

	# Step 1: Mask literals and comments
	masked, tokens = mask_tokens(query)
	if masked is None:
		# Safety constraint: Unclosed quote or block comment cannot be safely transformed
		return query

	# Step 2: Convert backtick identifiers: `col` -> [col]
	masked = re.sub(r"`([^`]+)`", r"[\1]", masked)

	# Step 2b: Convert MySQL-style double-quoted string literals:
	# 1. Operators: = "val", != "val", <> "val", <= "val", >= "val"
	masked = re.sub(r'([=><!]+\s*)(?<!\.)"(?!tab|__)([A-Za-z0-9_ ]+)"(?!\.)', r"\1'\2'", masked)
	# 2. IN lists: IN ("a", "b")
	def in_quotes_replacer(m):
		return re.sub(r'(?<!\.)"(?!tab|__)([A-Za-z0-9_ ]+)"(?!\.)', r"'\1'", m.group(0))
	masked = re.sub(r'\b(?:NOT\s+)?IN\s*\([^)]*\)', in_quotes_replacer, masked, flags=re.IGNORECASE)
	# 3. Projection literals: "Sales Invoice" as voucher_type
	masked = re.sub(r'(?<!\.)"(?!tab|__)([A-Za-z0-9_ ]+)"(?!\.)(\s+as\s+[a-zA-Z0-9_]+)', r"'\1'\2", masked, flags=re.IGNORECASE)

	# Step 3: IFNULL -> ISNULL
	masked = re.sub(r"\bIFNULL\b", "ISNULL", masked, flags=re.IGNORECASE)

	# Step 4: NOW() -> SYSDATETIME()
	masked = re.sub(r"\bNOW\s*\(\s*\d*\s*\)", "SYSDATETIME()", masked, flags=re.IGNORECASE)

	# Step 5: UNIX_TIMESTAMP() -> DATEDIFF(...)
	def unix_timestamp_handler(args_str):
		args = split_top_level_args(args_str)
		if args is None:
			return None
		if len(args) == 0:
			return "DATEDIFF(second, '1970-01-01', SYSUTCDATETIME())"
		elif len(args) == 1:
			return f"DATEDIFF(second, '1970-01-01', {args[0]})"
		return None

	masked = transform_function_calls(masked, "UNIX_TIMESTAMP", unix_timestamp_handler)

	# Step 6: LENGTH(str) -> LEN(str)
	def length_handler(args_str):
		args = split_top_level_args(args_str)
		if args is not None and len(args) == 1:
			return f"LEN({args[0]})"
		return None

	masked = transform_function_calls(masked, "LENGTH", length_handler)

	# Step 7: LOCATE(substr, str[, pos]) -> CHARINDEX(substr, str[, pos])
	def locate_handler(args_str):
		args = split_top_level_args(args_str)
		if args is not None and len(args) in (2, 3):
			return f"CHARINDEX({', '.join(args)})"
		return None

	masked = transform_function_calls(masked, "LOCATE", locate_handler)

	# Step 8: DATE(expr) -> CAST(expr AS DATE)
	def date_handler(args_str):
		args = split_top_level_args(args_str)
		if args is not None and len(args) == 1:
			return f"CAST({args[0]} AS DATE)"
		return None

	masked = transform_function_calls(masked, "DATE", date_handler)

	# Step 9: DATEDIFF(a, b) -> DATEDIFF(day, b, a)
	def datediff_handler(args_str):
		args = split_top_level_args(args_str)
		if args is not None and len(args) == 2:
			return f"DATEDIFF(day, {args[1]}, {args[0]})"
		return None  # Leave 3-arg or malformed calls untouched

	masked = transform_function_calls(masked, "DATEDIFF", datediff_handler)

	# Step 10: COALESCE(arg) with single argument -> COALESCE(arg, arg)
	def coalesce_handler(args_str):
		args = split_top_level_args(args_str)
		if args is not None and len(args) == 1:
			return f"COALESCE({args[0]}, {args[0]})"
		return None

	masked = transform_function_calls(masked, "COALESCE", coalesce_handler)

	# Step 10b: IF(cond, val_if_true, val_if_false) -> CASE WHEN cond THEN val_if_true ELSE val_if_false END
	def if_handler(args_str):
		args = split_top_level_args(args_str)
		if args is not None and len(args) == 3:
			cond, true_val, false_val = args[0], args[1], args[2]
			if re.search(r"(=|<>|!=|<=|>=|<|>|\bIS\s+NULL\b|\bIS\s+NOT\s+NULL\b|\bLIKE\b|\bBETWEEN\b|\bIN\s*\(|\bAND\b|\bOR\b|\bNOT\b)", cond, flags=re.IGNORECASE):
				return f"CASE WHEN {cond} THEN {true_val} ELSE {false_val} END"
			else:
				return f"CASE WHEN ISNULL({cond}, 0) != 0 THEN {true_val} ELSE {false_val} END"
		return None

	masked = transform_function_calls(masked, "IF", if_handler)

	# Step 11: LIMIT and OFFSET
	masked = transform_limit_offset(masked)

	# Step 11: Standalone OFFSET without ORDER BY (if present)
	if re.search(r"\bOFFSET\b", masked, flags=re.IGNORECASE) and not re.search(r"\bORDER\s+BY\b", masked, flags=re.IGNORECASE):
		is_distinct = bool(re.search(r"\bSELECT\s+(?:TOP\s+\d+\s+)?DISTINCT\b", masked, flags=re.IGNORECASE))
		fallback_order = " ORDER BY 1 " if is_distinct else " ORDER BY (SELECT NULL) "
		masked = re.sub(r"(\bOFFSET\b)", rf"{fallback_order}\1", masked, count=1, flags=re.IGNORECASE)

	# Step 12: Remove FOR UPDATE
	masked = re.sub(r"\bFOR\s+UPDATE\b", "", masked, flags=re.IGNORECASE)

	# Step 13: TRUNCATE [table] -> TRUNCATE TABLE [table]
	masked = re.sub(r"^\s*truncate\s+(?!table\b)", "TRUNCATE TABLE ", masked, flags=re.IGNORECASE)

	# Step 14: Fix Landed Cost query with missing GROUP BY
	if re.search(r"\bsum\s*\(\s*applicable_charges\s*\)\s*,\s*cost_center\b", masked, flags=re.IGNORECASE) and not re.search(r"\bGROUP\s+BY\b", masked, flags=re.IGNORECASE):
		masked += " GROUP BY cost_center"

	# Step 15: Fix Payment Ledger CTE queries (missing GROUP BY columns in ERPNext CTE)
	if "tabPayment Ledger Entry" in masked and "WITH vouchers AS" in masked:
		masked = re.sub(
			r'(GROUP\s+BY\s+["`\[]?voucher_type["`\]]?\s*,\s*["`\[]?voucher_no["`\]]?\s*,\s*["`\[]?party_type["`\]]?\s*,\s*["`\[]?party["`\]]?)',
			r'GROUP BY "account","voucher_type","voucher_no","party_type","party","posting_date","due_date","account_currency","cost_center","remarks"',
			masked,
			count=1,
			flags=re.IGNORECASE,
		)
		masked = re.sub(
			r'(outstanding\s+AS\s*\(\s*SELECT\s+.*?)["`\[]?posting_date["`\]]?\s*,\s*["`\[]?due_date["`\]]?',
			r'\1MAX("posting_date") "posting_date",MAX("due_date") "due_date"',
			masked,
			count=1,
			flags=re.DOTALL | re.IGNORECASE,
		)
		masked = re.sub(
			r'(GROUP\s+BY\s+["`\[]?against_voucher_type["`\]]?\s*,\s*["`\[]?against_voucher_no["`\]]?\s*,\s*["`\[]?party_type["`\]]?\s*,\s*["`\[]?party["`\]]?)',
			r'GROUP BY "account","against_voucher_type","against_voucher_no","party_type","party","account_currency"',
			masked,
			count=1,
			flags=re.IGNORECASE,
		)

		# Rewrite HAVING on unaggregated column alias into WHERE condition for T-SQL
		having_m = re.search(
			r'\bHAVING\s+["`\[]?outstanding_in_account_currency["`\]]?\s*([><=!]+)\s*(\d+)',
			masked,
			flags=re.IGNORECASE,
		)
		if having_m:
			h_op, h_val = having_m.group(1), having_m.group(2)
			preceding = masked[: having_m.start()]
			outer_from = preceding.rfind("LEFT JOIN") if "LEFT JOIN" in preceding else 0
			has_where = bool(re.search(r"\bWHERE\b", preceding[outer_from:], flags=re.IGNORECASE))
			prefix = "AND" if has_where else "WHERE"
			repl = f'{prefix} ("outstanding"."amount_in_account_currency" {h_op} {h_val})'
			masked = masked[: having_m.start()] + repl + masked[having_m.end() :]

	# Step 15b: Fix Payment Request subquery (missing "name" in GROUP BY in ERPNext)
	if "tabPayment Request" in masked and '"payment_request"' in masked:
		masked = re.sub(
			r'(GROUP\s+BY\s+["`\[]?reference_doctype["`\]]?\s*,\s*["`\[]?reference_name["`\]]?\s*,\s*["`\[]?outstanding_amount["`\]]?)',
			r'\1,"name"',
			masked,
			flags=re.IGNORECASE,
		)

	# Step 16: Translate tuple IN / NOT IN: (a, b) IN ((1, 2), ...) -> ((a = 1 AND b = 2) OR ...)
	masked = transform_tuple_in(masked)

	# Step 17: Restore masked literals and comments
	return unmask_tokens(masked, tokens)

