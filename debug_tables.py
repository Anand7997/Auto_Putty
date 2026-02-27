import sys
sys.path.insert(0, 'new_backend')

import pyodbc
from app import get_db_connection

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check all tables to see if there's a relationship between TestCases and Values
    cursor.execute("""
        SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_TYPE='BASE TABLE' 
        ORDER BY TABLE_NAME
    """)
    
    tables = [row[0] for row in cursor.fetchall()]
    print("All tables in database:")
    for table in tables:
        print(f"  - {table}")
    
    # Check if there's a TestCaseValues or similar mapping table
    if 'TestCaseValues' in tables:
        print("\n✅ TestCaseValues table exists")
        cursor.execute("SELECT * FROM TestCaseValues LIMIT 5")
        print("Sample data:")
        for row in cursor.fetchall():
            print(f"  {row}")
    
    if 'Values' in tables:
        print("\nValues table exists")
        cursor.execute("""
            SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_NAME='Values'
        """)
        print("Columns in Values table:")
        for col in cursor.fetchall():
            print(f"  - {col[0]}")
        
        # Check if any test case is referenced in Values table
        cursor.execute("SELECT COUNT(*) as total FROM Values")
        count = cursor.fetchone()[0]
        print(f"\nTotal values in Values table: {count}")
        
        if count > 0:
            cursor.execute("SELECT TOP 3 * FROM Values")
            cols = [description[0] for description in cursor.description]
            print("Sample Values:")
            for row in cursor.fetchall():
                print(f"  {dict(zip(cols, row))}")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
