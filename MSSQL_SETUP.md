# Microsoft SQL Server Setup Guide for Frappe & ERPNext

This guide provides step-by-step instructions for provisioning, configuring, and connecting a Microsoft SQL Server database with Frappe Framework and ERPNext.

---

## 1. System Prerequisites

### 1.1. Python Environment & Drivers
Install FreeTDS development libraries and the Python MSSQL driver:

**On Ubuntu / Debian:**
```bash
sudo apt-get update
sudo apt-get install -y freetds-bin freetds-dev libkrb5-dev
pip install pymssql>=2.2.8
```

**FreeTDS Client Configuration (`/etc/freetds/freetds.conf`):**
Ensure the client uses TDS version 7.4 with UTF-8 character encoding:
```ini
[global]
tds version = 7.4
client charset = UTF-8
text size = 2147483647
```

---

## 2. SQL Server Database Provisioning

### 2.1. Method A: Automated Provisioning via Bench (Recommended)
When creating a new site using Frappe Bench:

```bash
bench new-site mssql.local \
  --db-type mssql \
  --db-host 127.0.0.1 \
  --db-port 1433 \
  --db-root-username sa \
  --db-root-password 'YourStrong@Password' \
  --admin-password 'admin'
```
*Frappe will automatically create the database, enable `READ_COMMITTED_SNAPSHOT`, provision the site login, and apply the bootstrap schema.*

---

### 2.2. Method B: Manual Database Provisioning (For DBAs)
If you prefer or need to create the database manually using SQL Server Management Studio (SSMS), Azure Data Studio, or `sqlcmd`, run the provided SQL script:

```bash
sqlcmd -S 127.0.0.1,1433 -U sa -P 'YourStrong@Password' \
  -v DB_NAME="frappe_site" DB_USER="frappe_user" DB_PASSWORD="SiteUser@Strong123" \
  -i frappe/database/mssql/setup_mssql_database.sql
```

**Manual T-SQL Commands:**
```sql
-- 1. Create Database with UTF-8 collation
CREATE DATABASE [frappe_site] COLLATE Latin1_General_100_CI_AI_SC_UTF8;
GO

-- 2. Enable Non-blocking Concurrency (Mandatory)
ALTER DATABASE [frappe_site] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
ALTER DATABASE [frappe_site] SET ALLOW_SNAPSHOT_ISOLATION ON;
ALTER DATABASE [frappe_site] SET AUTO_CLOSE OFF;
GO

-- 3. Create Login & User
CREATE LOGIN [frappe_user] WITH PASSWORD = 'SiteUser@Strong123', CHECK_POLICY = OFF;
GO

USE [frappe_site];
CREATE USER [frappe_user] FOR LOGIN [frappe_user];
ALTER ROLE [db_owner] ADD MEMBER [frappe_user];
GO
```

---

## 3. Site Configuration (`site_config.json`)

Ensure your site's `site_config.json` (located at `sites/<site_name>/site_config.json`) has the following keys:

```json
{
  "db_type": "mssql",
  "db_host": "127.0.0.1",
  "db_port": 1433,
  "db_name": "frappe_site",
  "db_user": "frappe_user",
  "db_password": "SiteUser@Strong123"
}
```

---

## 4. Troubleshooting & Best Practices

1. **Deadlock or Lock Timeout (1205 / 1222):**
   - Check if `READ_COMMITTED_SNAPSHOT` is enabled:
     ```sql
     SELECT name, is_read_committed_snapshot_on, snapshot_isolation_state_desc 
     FROM sys.databases WHERE name = 'frappe_site';
     ```
   - Both `is_read_committed_snapshot_on` must be `1` and `snapshot_isolation_state_desc` must be `ON`.

2. **Microsecond Precision in Timestamps:**
   - Datetime columns in MSSQL use `datetime2(6)`.
   - The adapter automatically preserves 6-digit microsecond precision across all query bindings.

3. **Port and Network Accessibility:**
   - Verify that TCP/IP protocol is enabled in SQL Server Configuration Manager and listening on port `1433`.
