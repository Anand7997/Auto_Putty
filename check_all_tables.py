import pyodbc

# Database configuration
DB_CONFIG = {
    'server': 'LPT2084-B1',
    'database': 'Ixigo_TestAutomation',
    'driver': 'ODBC Driver 17 for SQL Server',
    'uid': 'myuser',
    'pwd': 'MyPass135'
}

def get_db_connection():
    conn_str = (
        f"DRIVER={{{DB_CONFIG['driver']}}};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['uid']};"
        f"PWD={DB_CONFIG['pwd']};"
    )
    conn = pyodbc.connect(conn_str)
    return conn

try:
    conn = get_db_connection()
    cursor = conn.cursor()

    print("=== CHECKING ALL TEST STEP TABLES ===")

    # Get all user tables that might be test steps tables
    cursor.execute("""
        SELECT name 
        FROM sysobjects 
        WHERE xtype='U' 
        AND name NOT LIKE 'sys%'
        AND name NOT LIKE 'MS%'
        ORDER BY name
    """)
    
    all_tables = [row[0] for row in cursor.fetchall()]
    print(f"All user tables in database: {len(all_tables)}")
    print(f"Tables: {all_tables}")
    
    # Check which test steps tables exist (assuming they follow naming pattern)
    cursor.execute("""
        SELECT tc.name, tc.testcase_id 
        FROM TestCases tc 
        ORDER BY tc.name
    """)
    
    test_cases = cursor.fetchall()
    print(f"\n=== TEST CASES vs TEST STEP TABLES ===")
    
    for tc_name, tc_id in test_cases:
        # Sanitize table name (same logic as server_execution_manager.py)
        table_name = tc_name.replace(' ', '_').replace('-', '_')
        
        # Check if corresponding table exists
        cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name=? AND xtype='U'", (table_name,))
        table_exists = cursor.fetchone()[0] > 0
        
        status = "EXISTS" if table_exists else "MISSING"
        print(f"{tc_name:<40} -> {table_name:<25} {status}")

    conn.close()

except Exception as e:
    print(f"Database error: {e}")