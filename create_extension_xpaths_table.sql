-- Create ExtensionXpaths table for storing XPaths from Chrome extension
USE Ixigo_TestAutomation;
GO

-- Create ExtensionXpaths table
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ExtensionXpaths' AND xtype='U')
CREATE TABLE ExtensionXpaths (
    id INT IDENTITY(1,1) PRIMARY KEY,
    xpath NVARCHAR(2000) NOT NULL,
    element_name NVARCHAR(255) NULL,
    page_name NVARCHAR(1000) NULL,
    action_type NVARCHAR(100) DEFAULT 'CLICK',
    values NVARCHAR(500) NULL,
    test_step_description NVARCHAR(1000) NULL,
    created_at DATETIME DEFAULT GETDATE(),
    source NVARCHAR(100) DEFAULT 'extension', -- 'extension', 'manual', etc.
    is_processed BIT DEFAULT 0, -- 0 = not added to test steps, 1 = added to test steps
    metadata NVARCHAR(MAX) NULL, -- JSON string for additional metadata
    session_id NVARCHAR(255) NULL -- Session ID for grouping XPaths captured in the same batch
);
GO

-- Create indexes for better query performance
CREATE INDEX IX_ExtensionXpaths_CreatedAt ON ExtensionXpaths(created_at DESC);
CREATE INDEX IX_ExtensionXpaths_IsProcessed ON ExtensionXpaths(is_processed);
CREATE INDEX IX_ExtensionXpaths_PageName ON ExtensionXpaths(page_name);
CREATE INDEX IX_ExtensionXpaths_ElementName ON ExtensionXpaths(element_name);
GO

-- Create a unique index to prevent duplicate XPaths (optional)
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_ExtensionXpaths_XPath_Unique')
CREATE UNIQUE INDEX IX_ExtensionXpaths_XPath_Unique ON ExtensionXpaths(xpath, element_name, session_id)
WHERE session_id IS NOT NULL;
GO

PRINT 'ExtensionXpaths table created successfully!';
GO