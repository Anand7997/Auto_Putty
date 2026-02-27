@echo off
REM VNC Files Cleanup Script
REM Deletes redundant VNC documentation and old patches

cd /d "c:\Users\VAnand\Downloads\Automation-main"

echo ================================================================
echo VNC FILES CLEANUP - REMOVING REDUNDANT FILES
echo ================================================================
echo.

REM Old documentation
if exist "VNC_SYSTEM_DOCUMENTATION.md" del "VNC_SYSTEM_DOCUMENTATION.md" && echo Deleted: VNC_SYSTEM_DOCUMENTATION.md
if exist "VNC_FIXES_SUMMARY.md" del "VNC_FIXES_SUMMARY.md" && echo Deleted: VNC_FIXES_SUMMARY.md
if exist "VNC_CODE_SNIPPETS.py" del "VNC_CODE_SNIPPETS.py" && echo Deleted: VNC_CODE_SNIPPETS.py
if exist "VNC_FRONTEND_SNIPPETS.js" del "VNC_FRONTEND_SNIPPETS.js" && echo Deleted: VNC_FRONTEND_SNIPPETS.js
if exist "VNC_IMPLEMENTATION_SUMMARY.md" del "VNC_IMPLEMENTATION_SUMMARY.md" && echo Deleted: VNC_IMPLEMENTATION_SUMMARY.md
if exist "VNC_LIVESTREAM_FIX.md" del "VNC_LIVESTREAM_FIX.md" && echo Deleted: VNC_LIVESTREAM_FIX.md
if exist "NOVNC_FIX_README.md" del "NOVNC_FIX_README.md" && echo Deleted: NOVNC_FIX_README.md
if exist "VNC_IMPLEMENTATION_COMPLETE.md" del "VNC_IMPLEMENTATION_COMPLETE.md" && echo Deleted: VNC_IMPLEMENTATION_COMPLETE.md
if exist "WEBSOCKET_TROUBLESHOOTING.md" del "WEBSOCKET_TROUBLESHOOTING.md" && echo Deleted: WEBSOCKET_TROUBLESHOOTING.md

REM Old patches
if exist "fix_novnc_websocket.py" del "fix_novnc_websocket.py" && echo Deleted: fix_novnc_websocket.py
if exist "fix_vnc_session_manager.py" del "fix_vnc_session_manager.py" && echo Deleted: fix_vnc_session_manager.py
if exist "fix_novnc_ui.py" del "fix_novnc_ui.py" && echo Deleted: fix_novnc_ui.py
if exist "fix_vnc_binding.ps1" del "fix_vnc_binding.ps1" && echo Deleted: fix_vnc_binding.ps1
if exist "fix_novnc_check.ps1" del "fix_novnc_check.ps1" && echo Deleted: fix_novnc_check.ps1
if exist "novnc_ui_patch.js" del "novnc_ui_patch.js" && echo Deleted: novnc_ui_patch.js
if exist "enhance_vnc_autoconnect.py" del "enhance_vnc_autoconnect.py" && echo Deleted: enhance_vnc_autoconnect.py

REM Old setup scripts
if exist "simple_novnc_fix.sh" del "simple_novnc_fix.sh" && echo Deleted: simple_novnc_fix.sh
if exist "setup_novnc.sh" del "setup_novnc.sh" && echo Deleted: setup_novnc.sh
if exist "start_vnc_stream.sh" del "start_vnc_stream.sh" && echo Deleted: start_vnc_stream.sh
if exist "apply_novnc_fix.sh" del "apply_novnc_fix.sh" && echo Deleted: apply_novnc_fix.sh
if exist "fix_novnc_manual.sh" del "fix_novnc_manual.sh" && echo Deleted: fix_novnc_manual.sh
if exist "check_vnc_setup.sh" del "check_vnc_setup.sh" && echo Deleted: check_vnc_setup.sh
if exist "novnc-stream.service" del "novnc-stream.service" && echo Deleted: novnc-stream.service

echo.
echo ================================================================
echo CLEANUP COMPLETE
echo ================================================================
echo.
echo Remaining VNC files (Production Ready):
echo  - new_backend/vnc_session_manager.py
echo  - new_backend/server_execution_manager.py
echo  - src/components/TestExecutionDashboard.tsx
echo  - VNC_IMPLEMENTATION_GUIDE.md
echo  - VNC_FILES_CLEANUP.txt
echo.
echo Reduction: 23 files ^-^> 5 files ^(78%% cleanup^)
echo.
pause
