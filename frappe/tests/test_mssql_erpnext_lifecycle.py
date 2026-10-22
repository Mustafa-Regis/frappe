# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import unittest
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today, nowdate, flt


class TestMSSQLERPNextLifecycle(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company_name = "_Test MSSQL Company"
		cls.currency = "USD"
		cls.item_code = "_Test Item Alpha"
		cls.supplier_name = "_Test Supplier Alpha"
		cls.customer_name = "_Test Customer Alpha"
		cls.warehouse_stores = "Stores - TMC"
		cls.warehouse_fg = "Finished Goods - TMC"

		cls.init_entities()

	@classmethod
	def init_entities(cls):
		# Clean previous test transactions if any to ensure clean test state
		frappe.db.sql("DELETE FROM [tabStock Ledger Entry] WHERE company = %s", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabStock Ledger Entry] WHERE item_code = %s", (cls.item_code,))
		frappe.db.sql("DELETE FROM [tabBin] WHERE item_code = %s", (cls.item_code,))
		frappe.db.sql("DELETE FROM [tabPayment Ledger Entry] WHERE company = %s", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabGL Entry] WHERE company = %s", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabPayment Entry] WHERE company = %s", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabSales Invoice Item] WHERE parent IN (SELECT name FROM [tabSales Invoice] WHERE company = %s)", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabSales Invoice] WHERE company = %s", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabPurchase Invoice Item] WHERE parent IN (SELECT name FROM [tabPurchase Invoice] WHERE company = %s)", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabPurchase Invoice] WHERE company = %s", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabStock Entry Detail] WHERE parent IN (SELECT name FROM [tabStock Entry] WHERE company = %s)", (cls.company_name,))
		frappe.db.sql("DELETE FROM [tabStock Entry] WHERE company = %s", (cls.company_name,))
		frappe.db.commit()

		# Ensure Fiscal Year exists
		if not frappe.db.exists("Fiscal Year", "2026"):
			fy = frappe.get_doc({
				"doctype": "Fiscal Year",
				"year": "2026",
				"year_start_date": "2026-01-01",
				"year_end_date": "2026-12-31",
			})
			fy.flags.ignore_permissions = True
			fy.insert()

		# Ensure Item exists
		if not frappe.db.exists("Item", cls.item_code):
			item = frappe.get_doc({
				"doctype": "Item",
				"item_code": cls.item_code,
				"item_name": "Test Alpha Product",
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"opening_stock": 0,
				"valuation_rate": 50.0,
			}).insert()

		# Ensure Standard Price Lists exist
		if not frappe.db.exists("Price List", "Standard Selling"):
			frappe.get_doc({
				"doctype": "Price List",
				"price_list_name": "Standard Selling",
				"currency": cls.currency,
				"selling": 1,
				"buying": 0,
			}).insert()

		if not frappe.db.exists("Price List", "Standard Buying"):
			frappe.get_doc({
				"doctype": "Price List",
				"price_list_name": "Standard Buying",
				"currency": cls.currency,
				"selling": 0,
				"buying": 1,
			}).insert()

		# Ensure Supplier exists
		if not frappe.db.exists("Supplier", cls.supplier_name):
			frappe.get_doc({
				"doctype": "Supplier",
				"supplier_name": cls.supplier_name,
				"supplier_group": "Local",
			}).insert()

		# Ensure Customer exists
		if not frappe.db.exists("Customer", cls.customer_name):
			frappe.get_doc({
				"doctype": "Customer",
				"customer_name": cls.customer_name,
				"customer_group": "Commercial",
				"territory": "United States",
			}).insert()

		# Ensure Company has standard default accounts configured
		company = frappe.get_doc("Company", cls.company_name)
		company.round_off_account = "Round Off - TMC"
		company.default_expense_account = "Cost of Goods Sold - TMC"
		company.default_income_account = "Sales - TMC"
		company.stock_received_but_not_billed = "Stock Received But Not Billed - TMC"
		company.stock_adjustment_account = "Stock Adjustment - TMC"
		company.expenses_included_in_valuation = "Expenses Included In Valuation - TMC"
		company.default_inventory_account = "Stock In Hand - TMC"
		company.default_cost_center = "Main - TMC"
		company.flags.ignore_permissions = True
		company.flags.ignore_mandatory = True
		company.save()

		frappe.db.commit()

	def test_01_erpnext_tables_exist_in_sql_server(self):
		"""Verify that core ERPNext tables are created and healthy in SQL Server."""
		core_tables = [
			"tabCompany",
			"tabItem",
			"tabSupplier",
			"tabCustomer",
			"tabPurchase Invoice",
			"tabPurchase Invoice Item",
			"tabSales Invoice",
			"tabSales Invoice Item",
			"tabGL Entry",
			"tabStock Ledger Entry",
			"tabPayment Entry",
		]
		for table in core_tables:
			with self.subTest(table=table):
				res = frappe.db.sql(f"SELECT COUNT(*) FROM [{table}]")
				self.assertTrue(isinstance(res[0][0], int))

	def test_02_buying_cycle_purchase_invoice_with_stock(self):
		"""
		Execute Buying Cycle:
		Create and submit Purchase Invoice with update_stock=1 (100 units @ $50).
		Verify:
		- Purchase Invoice submitted (docstatus=1)
		- Stock Ledger Entry (+100 in Stores)
		- GL Entry created with balanced debits and credits ($5,000)
		"""
		prev = frappe.db.sql(
			"SELECT TOP 1 qty_after_transaction FROM [tabStock Ledger Entry] WHERE item_code = %s AND warehouse = %s ORDER BY creation DESC",
			(self.item_code, self.warehouse_stores),
		)
		self.__class__.initial_stock = flt(prev[0][0]) if prev else 0.0

		pi = frappe.get_doc({
			"doctype": "Purchase Invoice",
			"company": self.company_name,
			"supplier": self.supplier_name,
			"posting_date": today(),
			"update_stock": 1,
			"set_warehouse": self.warehouse_stores,
			"currency": self.currency,
			"items": [
				{
					"item_code": self.item_code,
					"qty": 100,
					"rate": 50.0,
					"warehouse": self.warehouse_stores,
					"expense_account": "Stock Received But Not Billed - TMC",
					"cost_center": "Main - TMC",
				}
			],
		})
		pi.insert()
		pi.submit()
		frappe.db.commit()

		self.assertEqual(pi.docstatus, 1)

		# 1. Verify Stock Ledger Entry
		sles = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_type": "Purchase Invoice", "voucher_no": pi.name},
			fields=["actual_qty", "qty_after_transaction", "warehouse"],
		)
		self.assertTrue(len(sles) >= 1)
		self.assertEqual(flt(sles[0].actual_qty), 100.0)
		self.__class__.pi_qty_after = flt(sles[0].qty_after_transaction)
		self.assertEqual(flt(sles[0].qty_after_transaction), self.__class__.initial_stock + 100.0)
		self.assertEqual(sles[0].warehouse, self.warehouse_stores)

		# 2. Verify GL Entries
		gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Purchase Invoice", "voucher_no": pi.name},
			fields=["account", "debit", "credit"],
		)
		self.assertTrue(len(gl_entries) >= 2)
		total_debit = sum(flt(g.debit) for g in gl_entries)
		total_credit = sum(flt(g.credit) for g in gl_entries)
		self.assertEqual(total_debit, 5000.0)
		self.assertEqual(total_credit, 5000.0)

	def test_03_selling_cycle_sales_invoice_with_stock(self):
		"""
		Execute Selling Cycle:
		Create and submit Sales Invoice with update_stock=1 (40 units @ $120).
		Verify:
		- Sales Invoice submitted (docstatus=1)
		- Stock Ledger Entry deducted (-40 in Stores, balance 60)
		- GL Entry created with balanced debits and credits
		"""
		si = frappe.get_doc({
			"doctype": "Sales Invoice",
			"company": self.company_name,
			"customer": self.customer_name,
			"posting_date": today(),
			"update_stock": 1,
			"set_warehouse": self.warehouse_stores,
			"currency": self.currency,
			"selling_price_list": "Standard Selling",
			"price_list_currency": self.currency,
			"plc_conversion_rate": 1.0,
			"conversion_rate": 1.0,
			"items": [
				{
					"item_code": self.item_code,
					"qty": 40,
					"rate": 120.0,
					"warehouse": self.warehouse_stores,
					"income_account": "Sales - TMC",
					"expense_account": "Cost of Goods Sold - TMC",
					"cost_center": "Main - TMC",
				}
			],
		})
		si.insert()
		si.submit()
		frappe.db.commit()

		self.__class__.sales_invoice_name = si.name
		self.assertEqual(si.docstatus, 1)

		# 1. Verify Stock Ledger Entry deduction
		sles = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_type": "Sales Invoice", "voucher_no": si.name},
			fields=["actual_qty", "qty_after_transaction", "warehouse"],
		)
		self.assertTrue(len(sles) >= 1)
		self.assertEqual(flt(sles[0].actual_qty), -40.0)
		si_qty_after = flt(sles[0].qty_after_transaction)
		pi_qty = getattr(self.__class__, "pi_qty_after", getattr(self.__class__, "initial_stock", 0.0) + 100.0)
		self.assertEqual(pi_qty - si_qty_after, 40.0)
		self.assertEqual(si_qty_after, getattr(self.__class__, "initial_stock", 0.0) + 60.0)

		# 2. Verify GL Entries
		gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Sales Invoice", "voucher_no": si.name},
			fields=["account", "debit", "credit"],
		)
		self.assertTrue(len(gl_entries) >= 2)
		total_debit = sum(flt(g.debit) for g in gl_entries)
		total_credit = sum(flt(g.credit) for g in gl_entries)
		self.assertEqual(total_debit, total_credit)
		self.assertAlmostEqual(total_debit, 6800.0)  # 4800 (Revenue) + 2000 (COGS)

		# Save for payment entry test
		self.__class__.sales_invoice_name = si.name

	def test_04_payment_entry_reconciliation(self):
		"""
		Execute Payment Entry against the Sales Invoice:
		- Receive $4,800 from customer
		- Verify invoice outstanding balance reduced to 0
		- Verify GL Entry balanced
		"""
		si_name = getattr(self.__class__, "sales_invoice_name", None)
		if not si_name:
			self.skipTest("Sales Invoice not available")

		si = frappe.get_doc("Sales Invoice", si_name)

		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
		pe = get_payment_entry("Sales Invoice", si.name)
		pe.reference_no = f"PAY-{si.name}"
		pe.reference_date = today()
		pe.insert()
		pe.submit()
		frappe.db.commit()

		self.assertEqual(pe.docstatus, 1)

		# Verify Sales Invoice is now marked Paid (outstanding == 0)
		si.reload()
		self.assertEqual(flt(si.outstanding_amount), 0.0)

		# Verify Payment GL
		gl_entries = frappe.get_all(
			"GL Entry",
			filters={"voucher_type": "Payment Entry", "voucher_no": pe.name},
			fields=["account", "debit", "credit"],
		)
		self.assertTrue(len(gl_entries) >= 2)
		total_debit = sum(flt(g.debit) for g in gl_entries)
		total_credit = sum(flt(g.credit) for g in gl_entries)
		self.assertEqual(total_debit, total_credit)
		self.assertEqual(total_debit, 4800.0)

	def test_05_stock_entry_transfer(self):
		"""
		Execute Material Transfer in Stock:
		- Transfer 10 units from Stores to Finished Goods
		- Verify Stock Ledger Entries update both warehouses
		"""
		se = frappe.get_doc({
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": self.company_name,
			"posting_date": today(),
			"items": [
				{
					"item_code": self.item_code,
					"qty": 10,
					"basic_rate": 50.0,
					"s_warehouse": self.warehouse_stores,
					"t_warehouse": self.warehouse_fg,
				}
			],
		})
		se.insert()
		se.submit()
		frappe.db.commit()

		self.assertEqual(se.docstatus, 1)

		# Verify 2 SLE records created (+10 in FG, -10 in Stores)
		sles = frappe.get_all(
			"Stock Ledger Entry",
			filters={"voucher_type": "Stock Entry", "voucher_no": se.name},
			fields=["warehouse", "actual_qty"],
		)
		self.assertEqual(len(sles), 2)
		qty_map = {s.warehouse: flt(s.actual_qty) for s in sles}
		self.assertEqual(qty_map.get(self.warehouse_stores), -10.0)
		self.assertEqual(qty_map.get(self.warehouse_fg), 10.0)

	def test_06_financial_report_general_ledger_execution(self):
		"""
		Execute General Ledger Financial Report:
		Verify report runs without any SQL translation or syntax errors on MSSQL.
		"""
		from erpnext.accounts.report.general_ledger.general_ledger import execute

		filters = frappe._dict({
			"company": self.company_name,
			"from_date": "2026-01-01",
			"to_date": "2026-12-31",
			"group_by": "Group by Voucher (Consolidated)",
		})

		columns, data = execute(filters)
		self.assertTrue(len(columns) > 0)
		self.assertTrue(len(data) > 0)

		# Ensure balanced ledger in report rows
		total_debit = sum(flt(row.get("debit")) for row in data if isinstance(row, dict))
		total_credit = sum(flt(row.get("credit")) for row in data if isinstance(row, dict))
		self.assertEqual(total_debit, total_credit)

	def test_07_inventory_report_stock_balance_execution(self):
		"""
		Execute Stock Balance Inventory Report:
		Verify report executes without any SQL translation or syntax errors on MSSQL.
		"""
		from erpnext.stock.report.stock_balance.stock_balance import execute

		filters = frappe._dict({
			"company": self.company_name,
			"from_date": "2026-01-01",
			"to_date": "2026-12-31",
			"item_code": [self.item_code],
		})

		columns, data = execute(filters)
		self.assertTrue(len(columns) > 0)
		self.assertTrue(len(data) > 0)

		# Total balance in stock must equal 60 + initial_stock (50 in Stores, 10 in Finished Goods)
		item_rows = [row for row in data if isinstance(row, dict) and row.get("item_code") == self.item_code]
		self.assertTrue(len(item_rows) >= 1)
		total_bal = sum(flt(row.get("bal_qty")) for row in item_rows)
		self.assertEqual(total_bal, getattr(self.__class__, "initial_stock", 0.0) + 60.0)


if __name__ == "__main__":
	unittest.main()
