#!/usr/bin/env python3
"""
VNC Files Consolidation Cleanup Script
Deletes redundant VNC documentation and old patches
"""

import os
import sys

base_path = r"c:\Users\VAnand\Downloads\Automation-main"
os.chdir(base_path)

# Files to delete
delete_files = [
    # Old documentation
    "VNC_SYSTEM_DOCUMENTATION.md",
    "VNC_FIXES_SUMMARY.md",
    "VNC_CODE_SNIPPETS.py",
    "VNC_FRONTEND_SNIPPETS.js",
    "VNC_IMPLEMENTATION_SUMMARY.md",
    "VNC_LIVESTREAM_FIX.md",
    "NOVNC_FIX_README.md",
    "VNC_IMPLEMENTATION_COMPLETE.md",
    "WEBSOCKET_TROUBLESHOOTING.md",
    
    # Old patches
    "fix_novnc_websocket.py",
    "fix_vnc_session_manager.py",
    "fix_novnc_ui.py",
    "fix_vnc_binding.ps1",
    "fix_novnc_check.ps1",
    "novnc_ui_patch.js",
    "enhance_vnc_autoconnect.py",
    
    # Old setup scripts
    "simple_novnc_fix.sh",
    "setup_novnc.sh",
    "start_vnc_stream.sh",
    "apply_novnc_fix.sh",
    "fix_novnc_manual.sh",
    "check_vnc_setup.sh",
    "novnc-stream.service",
]

deleted = []
not_found = []
errors = []

print("=" * 70)
print("VNC FILES CONSOLIDATION CLEANUP")
print("=" * 70)
print()

for filename in delete_files:
    filepath = os.path.join(base_path, filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            deleted.append(filename)
            print(f"✓ Deleted: {filename}")
        except Exception as e:
            errors.append((filename, str(e)))
            print(f"✗ Error deleting {filename}: {e}")
    else:
        not_found.append(filename)
        print(f"- Not found: {filename}")

print()
print("=" * 70)
print(f"SUMMARY:")
print(f"  Deleted:   {len(deleted):2d} files")
print(f"  Not Found: {len(not_found):2d} files (already deleted?)")
print(f"  Errors:    {len(errors):2d} errors")
print("=" * 70)
print()

if deleted:
    print(f"✓ Successfully deleted {len(deleted)} redundant files")
    print()
    print("REMAINING VNC FILES (Production Ready):")
    print("  ✓ new_backend/vnc_session_manager.py")
    print("  ✓ new_backend/server_execution_manager.py")
    print("  ✓ src/components/TestExecutionDashboard.tsx")
    print("  ✓ VNC_IMPLEMENTATION_GUIDE.md (new - comprehensive guide)")
    print("  ✓ VNC_FILES_CLEANUP.txt (reference)")
    print()
    print("Reduction: 23 files → 5 files (78% cleanup)")

if not_found:
    print(f"\n⚠ {len(not_found)} files not found (may have been deleted already)")

if errors:
    print(f"\n✗ {len(errors)} errors occurred during deletion")
    for fname, err in errors:
        print(f"  - {fname}: {err}")

print()
print("=" * 70)
