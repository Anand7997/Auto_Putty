-- Add index on session_id to improve query performance for extension XPaths
USE Ixigo_TestAutomation;
GO

-- Check if index already exists before creating
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ExtensionXpaths_SessionId')
BEGIN
    CREATE INDEX IX_ExtensionXpaths_SessionId ON ExtensionXpaths(session_id);
    PRINT 'Index IX_ExtensionXpaths_SessionId created successfully!';
END
ELSE
BEGIN
    PRINT 'Index IX_ExtensionXpaths_SessionId already exists.';
END
GO

-- Add composite index on session_id + created_at for even better performance
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ExtensionXpaths_SessionId_CreatedAt')
BEGIN
    CREATE INDEX IX_ExtensionXpaths_SessionId_CreatedAt ON ExtensionXpaths(session_id, created_at DESC);
    PRINT 'Composite index IX_ExtensionXpaths_SessionId_CreatedAt created successfully!';
END
ELSE
BEGIN
    PRINT 'Composite index IX_ExtensionXpaths_SessionId_CreatedAt already exists.';
END
GO

PRINT 'Database optimization complete!';