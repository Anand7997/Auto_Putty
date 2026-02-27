-- Create Values table for storing Excel files used in test execution
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Values' AND xtype='U')
CREATE TABLE [Values] (
    id INT IDENTITY(1,1) PRIMARY KEY,
    file_name NVARCHAR(255) NOT NULL,
    original_name NVARCHAR(255) NOT NULL,
    file_path NVARCHAR(500) NOT NULL,
    file_size BIGINT NOT NULL,
    uploaded_by NVARCHAR(255) NULL,  -- Allow anonymous uploads
    uploaded_at DATETIME DEFAULT GETDATE(),
    status NVARCHAR(50) DEFAULT 'Active'
    -- Removed foreign key constraint to allow anonymous uploads
);

-- Create index on uploaded_by for faster queries
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Values_UploadedBy')
CREATE INDEX IX_Values_UploadedBy ON [Values](uploaded_by);

-- Create index on uploaded_at for faster queries
IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_Values_UploadedAt')
CREATE INDEX IX_Values_UploadedAt ON [Values](uploaded_at);

PRINT 'Values table created successfully!';