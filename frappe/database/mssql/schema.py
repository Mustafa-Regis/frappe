# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.database.schema import DBTable, get_definition
from frappe.utils import cint, flt


class MSSQLTable(DBTable):
	def create(self):
		varchar_len = frappe.db.VARCHAR_LEN
		name_column = f"[name] nvarchar({varchar_len}) primary key"

		additional_definitions = []
		column_defs = self.get_column_definitions()
		if column_defs:
			additional_definitions.extend(column_defs)

		# child table columns
		if self.meta.get("istable") or 0:
			additional_definitions.extend(
				[
					f"[parent] nvarchar({varchar_len})",
					f"[parentfield] nvarchar({varchar_len})",
					f"[parenttype] nvarchar({varchar_len})",
				]
			)

		# sequences / autoincrement
		if not self.meta.issingle and self.meta.autoname == "autoincrement":
			frappe.db.create_sequence(self.doctype, check_not_exists=True)
			name_column = "[name] bigint primary key"

		all_defs = ",\n\t\t\t".join(additional_definitions)
		if all_defs:
			all_defs = ",\n\t\t\t" + all_defs

		query = f"""CREATE TABLE [{self.table_name}] (
			{name_column},
			[creation] datetime2(6),
			[modified] datetime2(6),
			[modified_by] nvarchar({varchar_len}),
			[owner] nvarchar({varchar_len}),
			[docstatus] tinyint not null default 0,
			[idx] bigint not null default 0{all_defs}
		)"""

		frappe.db.sql_ddl(query)
		self.create_indexes()
		frappe.db.commit()

	def get_column_definitions(self):
		column_list = [*frappe.db.DEFAULT_COLUMNS]
		ret = []
		for k in list(self.columns):
			if k not in column_list:
				d = self.columns[k].get_definition()
				if d:
					# In MSSQL, do not add inline unique constraints to CREATE TABLE because they reject multiple NULLs.
					# Filtered unique indexes (WHERE col IS NOT NULL) are created in create_indexes() instead.
					if " unique" in d:
						d = d.replace(" unique", "")
					ret.append(f"[{k}] {d}")
					column_list.append(k)
		return ret

	def create_indexes(self):
		for col in self.columns.values():
			if (
				col.fieldtype in frappe.db.type_map
				and frappe.db.type_map.get(col.fieldtype)[0] not in ("text", "longtext", "nvarchar(max)")
			):
				if col.unique:
					index_name = f"unique_{self.table_name}_{col.fieldname}"[:128]
					frappe.db.sql(
						f"""IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = '{index_name}' AND object_id = OBJECT_ID('[{self.table_name}]'))
						CREATE UNIQUE INDEX [{index_name}] ON [{self.table_name}] ([{col.fieldname}]) WHERE [{col.fieldname}] IS NOT NULL"""
					)
				elif col.set_index:
					index_name = f"idx_{self.table_name}_{col.fieldname}"[:128]
					frappe.db.sql(
						f"""IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = '{index_name}' AND object_id = OBJECT_ID('[{self.table_name}]'))
						CREATE INDEX [{index_name}] ON [{self.table_name}] ([{col.fieldname}])"""
					)

	def get_column_indexes_metadata(self, fieldname):
		"""
		Returns detailed definitions of all indexes that depend on fieldname (as key or included column),
		capturing:
		- index name
		- is_unique flag
		- composite key columns in proper key_ordinal sequence with ASC/DESC
		- included columns (INCLUDE (col1, col2))
		- filter definition (WHERE condition for filtered indexes)
		- exact create_sql string to reconstruct the index with 100% fidelity.
		"""
		idx_rows = frappe.db.sql(
			"""
			SELECT DISTINCT i.name, i.is_unique, i.has_filter, i.filter_definition
			FROM sys.indexes i
			JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
			JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
			WHERE i.object_id = OBJECT_ID(%s) AND c.name = %s AND i.is_primary_key = 0
			""",
			(f"[{self.table_name}]", fieldname),
			as_dict=True,
		)

		detailed = []
		for idx in idx_rows:
			cols = frappe.db.sql(
				"""
				SELECT c.name, ic.key_ordinal, ic.is_included_column, ic.is_descending_key
				FROM sys.indexes i
				JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
				JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
				WHERE i.object_id = OBJECT_ID(%s) AND i.name = %s
				ORDER BY ic.is_included_column, ic.key_ordinal
				""",
				(f"[{self.table_name}]", idx["name"]),
				as_dict=True,
			)

			key_cols = [
				f"[{c['name']}]" + (" DESC" if c["is_descending_key"] else " ASC")
				for c in cols
				if not c["is_included_column"]
			]
			inc_cols = [f"[{c['name']}]" for c in cols if c["is_included_column"]]

			unique_clause = "UNIQUE " if idx["is_unique"] else ""
			create_sql = f"CREATE {unique_clause}INDEX [{idx['name']}] ON [{self.table_name}] ({', '.join(key_cols)})"
			if inc_cols:
				create_sql += f" INCLUDE ({', '.join(inc_cols)})"
			if idx["has_filter"] and idx["filter_definition"]:
				create_sql += f" WHERE {idx['filter_definition']}"

			detailed.append({
				"name": idx["name"],
				"create_sql": create_sql,
				"is_unique": idx["is_unique"],
			})
		return detailed

	def drop_check_constraints(self, fieldname):
		"""Drop check constraints on fieldname, returning their definitions for subsequent restoration."""
		constraints = frappe.db.sql(
			"""
			SELECT cc.name, cc.definition
			FROM sys.check_constraints cc
			JOIN sys.columns c ON cc.parent_object_id = c.object_id AND cc.parent_column_id = c.column_id
			WHERE cc.parent_object_id = OBJECT_ID(%s) AND c.name = %s
			""",
			(f"[{self.table_name}]", fieldname),
			as_dict=True,
		)
		for c in constraints:
			frappe.db.sql(f"ALTER TABLE [{self.table_name}] DROP CONSTRAINT [{c['name']}]")
		return constraints

	def drop_default_constraints(self, fieldname):
		"""Drop default constraints on fieldname, returning their definitions for subsequent restoration."""
		constraints = frappe.db.sql(
			"""
			SELECT d.name, d.definition
			FROM sys.default_constraints d
			JOIN sys.columns c ON d.parent_column_id = c.column_id AND d.parent_object_id = c.object_id
			WHERE d.parent_object_id = OBJECT_ID(%s) AND c.name = %s
			""",
			(f"[{self.table_name}]", fieldname),
			as_dict=True,
		)
		for c in constraints:
			frappe.db.sql(f"ALTER TABLE [{self.table_name}] DROP CONSTRAINT [{c['name']}]")
		return constraints

	def drop_default_constraint(self, fieldname):
		"""MSSQL creates automatic names for default constraints. We must drop them before modifying column type."""
		return self.drop_default_constraints(fieldname)

	def alter(self):
		for col in self.columns.values():
			col.build_for_alter_table(self.current_columns.get(col.fieldname.lower()))

		# Add columns
		for col in self.add_column:
			frappe.db.sql(
				f"ALTER TABLE [{self.table_name}] ADD [{col.fieldname}] {col.get_definition()}"
			)

		# Modify column types
		for col in self.change_type:
			sp_name = f"sp_alter_{col.fieldname}"[:32]
			frappe.db.savepoint(sp_name)
			try:
				# 1. Capture and drop check constraints
				check_constraints = self.drop_check_constraints(col.fieldname)

				# 2. Capture and drop default constraints
				default_constraints = self.drop_default_constraints(col.fieldname)

				# 3. Capture full index definitions (composite, filtered, included, unique) and drop them
				indexes = self.get_column_indexes_metadata(col.fieldname)
				for idx in indexes:
					frappe.db.sql(f"DROP INDEX [{idx['name']}] ON [{self.table_name}]")

				# 4. Alter the column type
				def_str = get_definition(col.fieldtype, precision=col.precision, length=col.length)
				frappe.db.sql(
					f"ALTER TABLE [{self.table_name}] ALTER COLUMN [{col.fieldname}] {def_str}"
				)

				# 5. Restore original indexes with exact metadata
				for idx in indexes:
					frappe.db.sql(idx["create_sql"])

				# 6. Restore check constraints
				for ck in check_constraints:
					frappe.db.sql(
						f"ALTER TABLE [{self.table_name}] ADD CONSTRAINT [{ck['name']}] CHECK {ck['definition']}"
					)

				# 7. Restore default constraints if not scheduled to be modified by set_default
				if col not in self.set_default:
					for df in default_constraints:
						frappe.db.sql(
							f"ALTER TABLE [{self.table_name}] ADD CONSTRAINT [{df['name']}] DEFAULT {df['definition']} FOR [{col.fieldname}]"
						)

				frappe.db.release_savepoint(sp_name)
			except Exception:
				# Clean rollback to savepoint: restores dropped constraints and indexes in SQL Server!
				frappe.db.rollback(save_point=sp_name)
				raise

		# Modify defaults
		for col in self.set_default:
			if col.fieldname == "name":
				continue

			self.drop_default_constraint(col.fieldname)

			if col.fieldtype in ("Check", "Int"):
				col_default = cint(col.default)
			elif col.fieldtype in ("Currency", "Float", "Percent"):
				col_default = flt(col.default)
			elif not col.default:
				col_default = "NULL"
			else:
				col_default = frappe.db.escape(col.default)

			const_name = f"DF_{self.table_name}_{col.fieldname}"[:128]
			frappe.db.sql(
				f"ALTER TABLE [{self.table_name}] ADD CONSTRAINT [{const_name}] DEFAULT {col_default} FOR [{col.fieldname}]"
			)

		# Drop non-unique indexes
		for col in self.drop_index:
			if col.fieldname == "name":
				continue
			indexes = frappe.db.get_column_indexes(self.table_name, col.fieldname, unique_only=False)
			for idx in indexes:
				frappe.db.sql(f"DROP INDEX [{idx}] ON [{self.table_name}]")

		# Drop unique indexes
		for col in self.drop_unique:
			if col.fieldname == "name":
				continue
			indexes = frappe.db.get_column_indexes(self.table_name, col.fieldname, unique_only=True)
			for idx in indexes:
				frappe.db.sql(f"DROP INDEX [{idx}] ON [{self.table_name}]")

		# Add indexes
		for col in self.add_index:
			index_name = f"idx_{self.table_name}_{col.fieldname}"[:128]
			frappe.db.sql(
				f"""IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = '{index_name}' AND object_id = OBJECT_ID('[{self.table_name}]'))
				CREATE INDEX [{index_name}] ON [{self.table_name}] ([{col.fieldname}])"""
			)

		# Add unique indexes
		for col in self.add_unique:
			index_name = f"unique_{self.table_name}_{col.fieldname}"[:128]
			frappe.db.sql(
				f"""IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = '{index_name}' AND object_id = OBJECT_ID('[{self.table_name}]'))
				CREATE UNIQUE INDEX [{index_name}] ON [{self.table_name}] ([{col.fieldname}]) WHERE [{col.fieldname}] IS NOT NULL"""
			)
