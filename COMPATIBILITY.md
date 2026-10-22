# Compatibility & Environment Specifications

This document outlines the verified environment specifications, compatibility matrix, and prerequisite configurations for running **Frappe Framework** and **ERPNext** on **Microsoft SQL Server (MSSQL)**.

---

## 1. Verified Compatibility Matrix

The MSSQL database adapter has been comprehensively verified and validated across the following stack:

| Component | Tested & Verified Version | Supported Versions | Notes |
| :--- | :--- | :--- | :--- |
| **Microsoft SQL Server** | **2022 CU27** (`16.0.4305.5`) X64 | SQL Server 2022+, Azure SQL Database, Azure SQL Managed Instance | Requires `READ_COMMITTED_SNAPSHOT ON` |
| **Frappe Framework** | **v15.107.0** & **v15.124.0** | Version 15.x | Full suite: 82/82 automated tests passed (100%) |
| **ERPNext** | **v15.107.0** | Version 15.x | 100% upstream clean; zero modifications required |
| **Python** | **3.14.2** | 3.10, 3.11, 3.12, 3.14 | Standard CPython |
| **pymssql (DB-API)** | **2.4.5** | `>= 2.2.8` | Built against FreeTDS 1.4+ (TDS Protocol 7.4) |
| **PyPika** | **0.48.9** | `>= 0.48.9` | Query builder with custom MSSQL dialect |
| **sqlparse** | **0.5.5** | `>= 0.4.4` | SQL tokenization and parser engine |

---

## 2. Business Flow & Test Coverage Verification

All 7 core ERPNext business lifecycles and 4 Frappe test suites passed with **100% success rate (82 out of 82 tests passing)**:

1. **ERPNext Schema Integrity:** 710 ERPNext tables verified with identical column definitions, constraints, and indexes.
2. **Procurement & Inventory (Buying Cycle):**
   - Purchase Invoice with `update_stock=1`.
   - Stock Ledger Entry creation and valuation rate calculation.
   - General Ledger Entry creation ($5,000.00 balanced debits and credits).
3. **Sales & Distribution (Selling Cycle):**
   - Sales Invoice with `update_stock=1`.
   - Stock Ledger Entry decrement (-40 units).
   - General Ledger balanced entry ($6,800.00).
4. **Treasury & Reconciliation (Payment Entry):**
   - Payment Entry reconciliation against outstanding invoices.
   - Invoice `outstanding_amount` cleared to exactly `0.0`.
   - Balanced General Ledger posting.
5. **Warehouse Management (Stock Transfer):**
   - Stock Entry (Material Transfer) moving stock between warehouses.
   - Stock Ledger Entry consistency and quantity verification.
6. **Financial Reporting:**
   - General Ledger report generation (`erpnext.accounts.report.general_ledger.general_ledger.execute`).
   - Total Debits == Total Credits verified.
7. **Inventory Valuation Reporting:**
   - Stock Balance report generation (`erpnext.stock.report.stock_balance.stock_balance.execute`).
   - Streaming unbuffered cursor compatibility verified.

---

## 3. Database Server Requirements

### 3.1. Concurrency (Read Committed Snapshot Isolation)
SQL Server's default locking model blocks concurrent readers and writers. Frappe and ERPNext rely on Multi-Version Concurrency Control (MVCC) similar to MariaDB InnoDB.

**Mandatory Database Settings:**
```sql
ALTER DATABASE [<database_name>] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
ALTER DATABASE [<database_name>] SET ALLOW_SNAPSHOT_ISOLATION ON;
```

### 3.2. Collation
- Recommended Collation: `Latin1_General_100_CI_AI_SC_UTF8` or server-default UTF-8 collation.
- Case-insensitivity (`_CI`) is required for Frappe document name lookups and standard email/user authentication.

### 3.3. Standard Session Settings
The adapter automatically enforces the following connection options upon every connection:
- `SET ANSI_NULLS ON;`
- `SET ANSI_PADDING ON;`
- `SET ANSI_WARNINGS ON;`
- `SET QUOTED_IDENTIFIER ON;`
- `SET NUMERIC_ROUNDABORT OFF;`
