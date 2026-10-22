# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import os
import frappe
from frappe.utils import cstr


def setup_database():
	root_conn = get_root_connection(frappe.flags.root_login, frappe.flags.root_password)
	db_name = frappe.conf.db_name
	db_password = frappe.conf.db_password

	if hasattr(root_conn, "_conn") and root_conn._conn:
		try:
			root_conn._conn.commit()
		except Exception:
			pass
		root_conn._conn.autocommit(True)

	# Close active connections and recreate DB
	root_conn.sql(
		f"""
		IF DB_ID('{db_name}') IS NOT NULL
		BEGIN
			ALTER DATABASE [{db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
			DROP DATABASE [{db_name}];
		END
		"""
	)

	# Create DB and enable SNAPSHOT isolation to avoid deadlocks
	root_conn.sql(f"CREATE DATABASE [{db_name}]")
	root_conn.sql(f"ALTER DATABASE [{db_name}] SET READ_COMMITTED_SNAPSHOT ON")
	root_conn.sql(f"ALTER DATABASE [{db_name}] SET ALLOW_SNAPSHOT_ISOLATION ON")

	# Create Login and User
	root_conn.sql(
		f"""
		IF NOT EXISTS (SELECT * FROM sys.server_principals WHERE name = '{db_name}')
			CREATE LOGIN [{db_name}] WITH PASSWORD = '{db_password}', CHECK_POLICY = OFF;
		ELSE
			ALTER LOGIN [{db_name}] WITH PASSWORD = '{db_password}';
		"""
	)

	root_conn.sql(
		f"""
		USE [{db_name}];
		IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = '{db_name}')
			CREATE USER [{db_name}] FOR LOGIN [{db_name}];
		ALTER ROLE [db_owner] ADD MEMBER [{db_name}];
		"""
	)

	root_conn.close()
	frappe.local.flags.root_connection = None
	if hasattr(frappe.local, "db"):
		delattr(frappe.local, "db")
	frappe.db = frappe.local("db")


def bootstrap_database(verbose, source_sql=None):
	if hasattr(frappe.local, "db"):
		delattr(frappe.local, "db")
	frappe.db = frappe.local("db")
	frappe.connect()
	if verbose:
		print(f"Bootstrapping MSSQL database [{frappe.local.db.cur_db_name}]...")
	if not source_sql:
		source_sql = os.path.join(os.path.dirname(__file__), "framework_mssql.sql")

	if os.path.exists(source_sql):
		with open(source_sql, "r", encoding="utf-8") as f:
			sql_content = f.read()

		# Split by statements
		statements = [stmt.strip() for stmt in sql_content.split(";") if stmt.strip()]
		for stmt in statements:
			frappe.db.sql(stmt)

	frappe.db.create_auth_table()
	frappe.db.create_user_settings_table()
	frappe.db.create_global_search_table()
	frappe.db.commit()



def get_root_connection(root_login=None, root_password=None):
	if not frappe.local.flags.root_connection:
		if not root_login:
			root_login = frappe.conf.get("root_login") or "sa"

		if not root_password:
			root_password = frappe.conf.get("root_password") or None

		if not root_password:
			from getpass import getpass

			root_password = getpass("MSSQL 'sa' password: ")

		from frappe.database.mssql.database import MSSQLDatabase

		frappe.local.flags.root_connection = MSSQLDatabase(
			host=frappe.conf.db_host or "127.0.0.1",
			port=frappe.conf.db_port or "1433",
			user=root_login,
			password=root_password,
			cur_db_name="master",
		)

	return frappe.local.flags.root_connection


def drop_user_and_database(db_name, root_login, root_password):
	root_conn = get_root_connection(
		frappe.flags.root_login or root_login, frappe.flags.root_password or root_password
	)
	root_conn.sql(
		f"""
		IF DB_ID('{db_name}') IS NOT NULL
		BEGIN
			ALTER DATABASE [{db_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
			DROP DATABASE [{db_name}];
		END
		IF EXISTS (SELECT * FROM sys.server_principals WHERE name = '{db_name}')
			DROP LOGIN [{db_name}];
		"""
	)
	root_conn.close()
