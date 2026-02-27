import pandas as pd

file_path = r'C:\Users\VAnand\Downloads\Values.xlsx'

excel_data = pd.read_excel(file_path, sheet_name=None, header=0)
sheet_name = list(excel_data.keys())[0]
df = excel_data[sheet_name]

headers = df.columns.tolist()
row_labels = df.index.tolist()

print("="*70)
print("EXCEL PARSING FIX VERIFICATION")
print("="*70)
print(f"\nExcel Structure:")
print(f"  Sheet: {sheet_name}")
print(f"  Columns: {headers}")
print(f"  Column count: {len(headers)}")
print(f"  Row count: {len(row_labels)}")

# Test the FIXED parsing logic
values = []
for col_idx in range(len(headers)):
    col_dict = {}
    col_header = headers[col_idx]
    
    for row_idx in range(len(row_labels)):
        field_name = str(row_labels[row_idx])
        cell_value = df.iloc[row_idx, col_idx]
        
        if pd.isna(cell_value):
            cell_value = ''
        elif hasattr(cell_value, 'item'):
            cell_value = cell_value.item()
        
        col_dict[field_name] = cell_value
    
    values.append(col_dict)

print(f"\nParsing Result:")
print(f"  Data sets created: {len(values)}")
print(f"  Expected: 3")

if len(values) == 3:
    print(f"\n✓ SUCCESS: Got exactly 3 data sets as expected!")
    print(f"\nData Sets:")
    for i, data_set in enumerate(values, 1):
        print(f"\n  Data Set {i} (Column: '{headers[i-1]}'):")
        print(f"    Fields: {len(data_set)}")
        for key, val in list(data_set.items())[:3]:
            if val:
                print(f"      {key}: {val}")
        if len(data_set) > 3:
            print(f"      ... and {len(data_set) - 3} more fields")
else:
    print(f"\n✗ ERROR: Got {len(values)} data sets instead of 3")
    for i, data_set in enumerate(values, 1):
        print(f"  Data Set {i}: {len(data_set)} fields")
