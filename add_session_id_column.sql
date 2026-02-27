-- Add session_id column to ExtensionXpaths table if it doesn't exist
USE Ixigo_TestAutomation;
GO

-- Check if session_id column already exists
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ExtensionXpaths' AND COLUMN_NAME = 'session_id')
BEGIN
    ALTER TABLE ExtensionXpaths
    ADD session_id NVARCHAR(255) NULL;
    
    PRINT 'Column session_id added to ExtensionXpaths table successfully!';
END
ELSE
BEGIN
    PRINT 'Column session_id already exists in ExtensionXpaths table.';
END
GO

PRINT 'Migration complete!';
