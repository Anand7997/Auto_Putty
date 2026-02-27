-- SQL Server Database Setup for Authentication Module
-- Run this script in SQL Server Management Studio (SSMS) on your Ixigo_TestAutomation database

USE Ixigo_TestAutomation;
GO

-- Create Authentication table
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Authentication' AND xtype='U')
CREATE TABLE Authentication (
    id INT IDENTITY(1,1) PRIMARY KEY,
    username NVARCHAR(255) NOT NULL UNIQUE,
    email NVARCHAR(255) NOT NULL UNIQUE,
    password_hash NVARCHAR(255) NOT NULL,
    status NVARCHAR(50) DEFAULT 'Pending',
    role NVARCHAR(50) DEFAULT NULL,
    created_at DATETIME DEFAULT GETDATE(),
    last_login DATETIME NULL,
    is_active BIT DEFAULT 1
);
GO

-- Create index on email for faster lookups
CREATE INDEX IX_Authentication_Email ON Authentication(email);
GO

-- Create index on username for faster lookups
CREATE INDEX IX_Authentication_Username ON Authentication(username);
GO

-- Create FunctionAssignments table
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='FunctionAssignments' AND xtype='U')
CREATE TABLE FunctionAssignments (
    id INT IDENTITY(1,1) PRIMARY KEY,
    function_name NVARCHAR(255) NOT NULL,
    user_email NVARCHAR(255) NOT NULL,
    assigned_by NVARCHAR(255) NOT NULL,
    assigned_on DATETIME DEFAULT GETDATE(),
    FOREIGN KEY (user_email) REFERENCES Authentication(email) ON DELETE CASCADE
);
GO

-- Create index on function_name for faster queries
CREATE INDEX IX_FunctionAssignments_FunctionName ON FunctionAssignments(function_name);
GO

-- Create index on user_email for faster queries
CREATE INDEX IX_FunctionAssignments_UserEmail ON FunctionAssignments(user_email);
GO

-- Create BRD table for storing uploaded Business Requirements Documents
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='BRD' AND xtype='U')
CREATE TABLE BRD (
    id INT IDENTITY(1,1) PRIMARY KEY,
    file_name NVARCHAR(255) NOT NULL,
    file_type NVARCHAR(50) NOT NULL, -- 'document', 'pdf', 'excel'
    original_name NVARCHAR(255) NOT NULL,
    file_path NVARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    uploaded_by NVARCHAR(255) NOT NULL,
    uploaded_at DATETIME DEFAULT GETDATE(),
    description NVARCHAR(1000) NULL,
    status NVARCHAR(50) DEFAULT 'Active',
    FOREIGN KEY (uploaded_by) REFERENCES Authentication(email) ON DELETE CASCADE
);
GO

-- Create index on file_type for faster queries
CREATE INDEX IX_BRD_FileType ON BRD(file_type);
GO

-- Create index on uploaded_by for faster queries
CREATE INDEX IX_BRD_UploadedBy ON BRD(uploaded_by);
GO

-- Optional: Create a login attempts table for security (future enhancement)
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='LoginAttempts' AND xtype='U')
CREATE TABLE LoginAttempts (
    id INT IDENTITY(1,1) PRIMARY KEY,
    email NVARCHAR(255) NOT NULL,
    attempt_time DATETIME DEFAULT GETDATE(),
    success BIT DEFAULT 0,
    ip_address NVARCHAR(45) NULL
);
GO

-- Set default admin user (vanand@quinnox.com as Admin)
IF NOT EXISTS (SELECT * FROM Authentication WHERE email = 'vanand@quinnox.com')
BEGIN
    INSERT INTO Authentication (username, email, password_hash, status, role)
    VALUES ('vanand', 'vanand@quinnox.com', 'dummy_hash', 'Approved', 'Admin');
END
GO

PRINT 'Authentication module database setup completed successfully!';
GO