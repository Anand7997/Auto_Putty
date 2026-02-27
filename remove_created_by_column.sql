-- Remove created_by column from ExtensionXpaths table
USE Ixigo_TestAutomation;
GO

-- Check if created_by column exists and drop it
IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ExtensionXpaths' AND COLUMN_NAME = 'created_by')
BEGIN
    ALTER TABLE ExtensionXpaths DROP COLUMN created_by;
    PRINT 'Column created_by removed from ExtensionXpaths table successfully!';
END
ELSE
BEGIN
    PRINT 'Column created_by does not exist in ExtensionXpaths table.';
END
GO