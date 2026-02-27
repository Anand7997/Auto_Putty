import sys
sys.path.insert(0, 'c:\\Users\\VAnand\\Downloads\\Automation-main\\new_backend')

import pyodbc
from app import get_db_connection, generate_unique_table_name

try:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get SearchingFL test case details
    cursor.execute("""
        SELECT tc.id, tc.name, COALESCE(p1.name, p2.name, 'Unknown') as project_name,
               COALESCE(m.module_name, 'Unknown') as module_name
        FROM TestCases tc
        LEFT JOIN Modules m ON tc.module_id = m.id
        LEFT JOIN Projects p1 ON tc.project_id = p1.id
        LEFT JOIN Projects p2 ON m.project_id = p2.id
        WHERE tc.name = 'SearchingFL'
    """)
    
    result = cursor.fetchone()
    if result:
        tc_id, tc_name, project, module = result
        print(f"Found test case: {tc_name}")
        print(f"Project: {project}, Module: {module}")
        
        # Generate table name
        table_name = generate_unique_table_name(project, module, tc_name)
        print(f"Table name: {table_name}")
        
        # Get ALL steps
        cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
        total_steps = cursor.fetchone()[0]
        print(f"\nTotal steps: {total_steps}")
        
        # Get steps with values
        cursor.execute(f"SELECT COUNT(*) FROM [{table_name}] WHERE [values] IS NOT NULL AND [values] != ''")
        steps_with_values_count = cursor.fetchone()[0]
        print(f"Steps with non-empty values: {steps_with_values_count}")
        
        # Show first 3 steps with values
        cursor.execute(f"SELECT step_no, [values], test_step_description FROM [{table_name}] WHERE [values] IS NOT NULL AND [values] != '' ORDER BY step_no")
        
        steps = cursor.fetchall()
        for step in steps[:3]:
            value_preview = step[1][:100] if step[1] else "NULL"
            print(f"  Step {step[0]}: values='{value_preview}' description='{step[2]}'")
    else:
        print("Test case SearchingFL not found")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
