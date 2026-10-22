-- ============================================================================
-- Frappe Framework - Microsoft SQL Server Initialization Script
-- ============================================================================
-- Description:
--   This script configures a Microsoft SQL Server database for optimal
--   concurrency, MVCC compatibility, and collation for Frappe Framework & ERPNext.
--
-- Prerequisites:
--   - SQL Server 2022 CU12+ (Linux or Windows)
--   - User executing this script must have sysadmin or dbcreator permissions.
-- ============================================================================

SET NOCOUNT ON;
GO

-- 1. Configuration Variables
DECLARE @DatabaseName NVARCHAR(128) = N'$(DB_NAME)';     -- e.g. frappe_site
DECLARE @LoginName    NVARCHAR(128) = N'$(DB_USER)';     -- e.g. frappe_user
DECLARE @Password     NVARCHAR(128) = N'$(DB_PASSWORD)'; -- Strong Password

-- 2. Validate Parameters
IF @DatabaseName IS NULL OR @DatabaseName = N'$(DB_NAME)'
BEGIN
    SET @DatabaseName = N'frappe_site';
END;

IF @LoginName IS NULL OR @LoginName = N'$(DB_USER)'
BEGIN
    SET @LoginName = @DatabaseName;
END;

PRINT '>> Setting up Frappe MSSQL Database: ' + @DatabaseName;

-- 3. Create Database if not exists
IF DB_ID(@DatabaseName) IS NULL
BEGIN
    PRINT '>> Creating database [' + @DatabaseName + ']...';
    DECLARE @CreateDBSQL NVARCHAR(MAX) = N'CREATE DATABASE [' + @DatabaseName + N'] COLLATE Latin1_General_100_CI_AI_SC_UTF8;';
    EXEC sp_executesql @CreateDBSQL;
END
ELSE
BEGIN
    PRINT '>> Database [' + @DatabaseName + '] already exists.';
END
GO

-- 4. Crucial Engine Options for MVCC (Non-blocking reads/writes)
-- Frappe and ERPNext rely heavily on multi-version concurrency control (MVCC).
-- Without READ_COMMITTED_SNAPSHOT and ALLOW_SNAPSHOT_ISOLATION, readers block writers
-- and writers block readers, resulting in Lock Timeout (1222) or Deadlock (1205).
DECLARE @DB NVARCHAR(128) = N'$(DB_NAME)';
IF @DB IS NULL OR @DB = N'$(DB_NAME)' SET @DB = N'frappe_site';

DECLARE @AlterSQL NVARCHAR(MAX) = N'
    ALTER DATABASE [' + @DB + N'] SET READ_COMMITTED_SNAPSHOT ON WITH ROLLBACK IMMEDIATE;
    ALTER DATABASE [' + @DB + N'] SET ALLOW_SNAPSHOT_ISOLATION ON;
    ALTER DATABASE [' + @DB + N'] SET AUTO_CLOSE OFF;
    ALTER DATABASE [' + @DB + N'] SET ANSI_NULLS ON;
    ALTER DATABASE [' + @DB + N'] SET ANSI_PADDING ON;
    ALTER DATABASE [' + @DB + N'] SET ANSI_WARNINGS ON;
    ALTER DATABASE [' + @DB + N'] SET QUOTED_IDENTIFIER ON;
    ALTER DATABASE [' + @DB + N'] SET NUMERIC_ROUNDABORT OFF;
';
EXEC sp_executesql @AlterSQL;
PRINT '>> MVCC and Engine options successfully configured on [' + @DB + '].';
GO

-- 5. Create Login and Database User with appropriate permissions
DECLARE @DB NVARCHAR(128) = N'$(DB_NAME)';
DECLARE @User NVARCHAR(128) = N'$(DB_USER)';
DECLARE @Pass NVARCHAR(128) = N'$(DB_PASSWORD)';

IF @DB IS NULL OR @DB = N'$(DB_NAME)' SET @DB = N'frappe_site';
IF @User IS NULL OR @User = N'$(DB_USER)' SET @User = @DB;
IF @Pass IS NULL OR @Pass = N'$(DB_PASSWORD)' SET @Pass = N'FrappeStrong@Pass123';

-- Server Login
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = @User)
BEGIN
    DECLARE @CreateLoginSQL NVARCHAR(MAX) = N'CREATE LOGIN [' + @User + N'] WITH PASSWORD = ''' + REPLACE(@Pass, '''', '''''') + N''', CHECK_POLICY = OFF;';
    EXEC sp_executesql @CreateLoginSQL;
    PRINT '>> Server Login [' + @User + '] created.';
END

-- Database User & db_owner membership
DECLARE @CreateUserSQL NVARCHAR(MAX) = N'
    USE [' + @DB + N'];
    IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = ''' + @User + N''')
    BEGIN
        CREATE USER [' + @User + N'] FOR LOGIN [' + @User + N'];
    END
    ALTER ROLE [db_owner] ADD MEMBER [' + @User + N'];
';
EXEC sp_executesql @CreateUserSQL;
PRINT '>> Database User [' + @User + '] granted db_owner on [' + @DB + '].';
GO

PRINT '>> Frappe MSSQL Database provisioning completed successfully!';
GO
