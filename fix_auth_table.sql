-- Fix Authentication table to add missing columns
USE Ixigo_TestAutomation;
GO

-- Add status column if it doesn't exist
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Authentication' AND COLUMN_NAME = 'status')
ALTER TABLE Authentication ADD status NVARCHAR(50) DEFAULT 'Pending';
GO

-- Add role column if it doesn't exist
IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Authentication' AND COLUMN_NAME = 'role')
ALTER TABLE Authentication ADD role NVARCHAR(50) NULL;
GO

-- Update existing users to have Approved status if they don't have status
UPDATE Authentication SET status = 'Approved' WHERE status IS NULL;
GO

-- Set admin role for vanand@quinnox.com
UPDATE Authentication SET role = 'Admin' WHERE email = 'vanand@quinnox.com';
GO

PRINT 'Authentication table updated successfully!';