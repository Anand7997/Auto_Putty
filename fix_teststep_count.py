#!/usr/bin/env python3

file_path = r"c:\Users\VAnand\Downloads\Automation-main\src\components\TestExecutionDashboard.tsx"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the fallback logic that causes 11 iterations
old_line = "const dataSetsCount = actualDataSets > 0 ? actualDataSets : stepsWithValues.length;"
new_line = "const dataSetsCount = actualDataSets; // Must use Excel row count, never fall back to step count"

if old_line in content:
    new_content = content.replace(old_line, new_line)
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("[OK] Successfully fixed dataSetsCount logic in TestExecutionDashboard.tsx")
else:
    print("[FAIL] Could not find the line to replace")
    print("Looking for:", old_line)
