import re

# Read the file
with open(r"c:\Users\VAnand\Downloads\Automation-main\new_backend\app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find and replace the Excel parsing section
# This is the problematic code that reads rows instead of columns
old_pattern = r"""            # Get column headers \(these are the data set names\)
            headers = df\.columns\.tolist\(\)
            
            if len\(headers\) < 1:
                return jsonify\(\{'error': 'No columns found in Excel file'\}\), 400

            # Get row indices \(these will be the field names\)
            row_labels = df\.index\.tolist\(\)

            # Convert columns to data sets \(each column is one iteration\)
            # Treat the first column as row labels if it contains field names
            values = \[\]
            
            # Check if we should use the first column as row labels
            use_first_column_as_labels = True
            if len\(headers\) > 0:
                # We'll use the index \(first column\) as field names
                for col_idx, header in enumerate\(headers\):
                    col_dict = \{\}
                    # Add data from each row in this column
                    for row_idx, row_label in enumerate\(row_labels\):
                        # Use the row index/label as the field name
                        field_name = str\(row_label\)
                        cell_value = df\.iloc\[row_idx, col_idx\]
                        
                        # Convert numpy types to native Python types
                        if pd\.isna\(cell_value\):
                            cell_value = ''
                        elif hasattr\(cell_value, 'item'\):  # numpy types
                            cell_value = cell_value\.item\(\)
                        
                        col_dict\[field_name\] = cell_value
                    
                    # Append completed column data set \(one iteration per column\)
                    # This happens AFTER all rows have been processed for this column
                    values\.append\(col_dict\)"""

new_code = """            # Get column headers (these are the data set names)
            headers = df.columns.tolist()
            
            if len(headers) < 1:
                return jsonify({'error': 'No columns found in Excel file'}), 400

            # Get row indices (these will be the field names)
            row_labels = df.index.tolist()

            # Convert columns to data sets (each column is one iteration)
            values = []
            
            # Check if first column contains field names (not data)
            use_first_col_as_labels = False
            if len(headers) > 1 and len(row_labels) > 0:
                first_col_values = df.iloc[:, 0].tolist()
                non_numeric_count = sum(1 for v in first_col_values if isinstance(v, str) or (pd.notna(v) and not isinstance(v, (int, float))))
                if non_numeric_count > len(first_col_values) * 0.7:
                    use_first_col_as_labels = True
            
            start_col_idx = 1 if use_first_col_as_labels else 0
            field_names = df.iloc[:, 0].tolist() if use_first_col_as_labels else [str(label) for label in row_labels]
            
            for col_idx in range(start_col_idx, len(headers)):
                col_dict = {}
                for row_idx in range(len(row_labels)):
                    if use_first_col_as_labels:
                        field_name = str(field_names[row_idx]) if row_idx < len(field_names) else str(row_idx)
                    else:
                        field_name = str(row_labels[row_idx])
                    
                    cell_value = df.iloc[row_idx, col_idx]
                    
                    if pd.isna(cell_value):
                        cell_value = ''
                    elif hasattr(cell_value, 'item'):
                        cell_value = cell_value.item()
                    
                    col_dict[field_name] = cell_value
                
                values.append(col_dict)"""

# Try exact string match first
old_code_exact = """            # Get column headers (these are the data set names)
            headers = df.columns.tolist()
            
            if len(headers) < 1:
                return jsonify({'error': 'No columns found in Excel file'}), 400

            # Get row indices (these will be the field names)
            row_labels = df.index.tolist()

            # Convert columns to data sets (each column is one iteration)
            # Treat the first column as row labels if it contains field names
            values = []
            
            # Check if we should use the first column as row labels
            use_first_column_as_labels = True
            if len(headers) > 0:
                # We'll use the index (first column) as field names
                for col_idx, header in enumerate(headers):
                    col_dict = {}
                    # Add data from each row in this column
                    for row_idx, row_label in enumerate(row_labels):
                        # Use the row index/label as the field name
                        field_name = str(row_label)
                        cell_value = df.iloc[row_idx, col_idx]
                        
                        # Convert numpy types to native Python types
                        if pd.isna(cell_value):
                            cell_value = ''
                        elif hasattr(cell_value, 'item'):  # numpy types
                            cell_value = cell_value.item()
                        
                        col_dict[field_name] = cell_value
                    
                    # Append completed column data set (one iteration per column)
                    # This happens AFTER all rows have been processed for this column
                    values.append(col_dict)"""

if old_code_exact in content:
    content = content.replace(old_code_exact, new_code)
    with open(r"c:\Users\VAnand\Downloads\Automation-main\new_backend\app.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("[SUCCESS] Excel parsing logic has been fixed!")
    print("Changes made:")
    print("  - Detects if the first column contains field names")
    print("  - Iterates through DATA COLUMNS only (not the label column)")
    print("  - Creates ONE data set per column (not per row)")
    print("  - Result: 3 executions for Values 1, 2, 3 (not 11)")
else:
    print("[ERROR] Could not find exact code match")
    if "Get column headers" in content:
        print("[INFO] Found the section, but indentation or formatting differs")
        import sys
        sys.exit(1)
    else:
        print("[ERROR] Could not locate the section in file")
        sys.exit(1)
