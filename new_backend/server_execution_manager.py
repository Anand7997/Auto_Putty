import threading
import time
import uuid
from datetime import datetime
import os
import socket
import hashlib
import pyodbc
import re
import webbrowser
import pytz

from selenium_executor import SeleniumTestExecutor
from playwright_executor import PlaywrightTestExecutor
from cypress_executor import CypressTestExecutor

# Optional imports from main app
try:
    from new_backend.app import (
        generate_unique_table_name,
        sanitize_table_name,
        generate_testrun_id,
        generate_result_id,
        format_timestamp,
        get_db_connection,
    )
except ImportError:
    try:
        from app import (
            generate_unique_table_name,
            sanitize_table_name,
            generate_testrun_id,
            generate_result_id,
            format_timestamp,
            get_db_connection,
        )
    except ImportError:
        generate_unique_table_name = None
        sanitize_table_name = None
        generate_testrun_id = None
        generate_result_id = None
        format_timestamp = None
        get_db_connection = None

# VNC session managers
try:
    from vnc_session_manager import vnc_manager
except ImportError:
    vnc_manager = None
    print("[WARNING] VNC session manager not available")

try:
    from vnc_lifecycle_manager import vnc_lifecycle_manager
except ImportError:
    vnc_lifecycle_manager = None
    print("[WARNING] VNC lifecycle manager not available")


class ServerExecutionManager:
    """Manages test execution on server with optional live streaming"""

    def __init__(
        self,
        execution_id,
        test_cases,
        selected_suites,
        executor_type="selenium",
        browser_name="",
        enable_isolation=True,
        enable_parallel=False,
        max_concurrent=3,
        enable_streaming=True,
        user_email=None,
        vnc_session_info=None,
    ):
        self.execution_id = execution_id
        self.test_cases = test_cases
        self.selected_suites = selected_suites
        self.executor_type = executor_type
        self.browser_name = str(browser_name or "").strip().lower()
        self.enable_isolation = enable_isolation
        self.enable_parallel = enable_parallel
        self.max_concurrent = max_concurrent
        self.enable_streaming = enable_streaming
        self.user_email = user_email

        # Server config
        self.server_host = "10.30.3.85"

        # DB config
        self.DB_CONFIG = {
            "server": "10.30.3.85",
            "port": "1433",
            "database": "AppDB",
            "driver": "ODBC Driver 17 for SQL Server",
            "uid": "appuser",
            "pwd": "MyPass135",
        }

        self.executor = None
        self.is_running = False
        self.vnc_session = vnc_session_info
        self.vnc_failed = False
        self.running_headless = False

        print(f"[SERVER_MGR] Initialized for execution {execution_id}")
        if self.vnc_session:
            print(f"[SERVER_MGR] Using pre-created VNC session: {self.vnc_session.get('novnc_url')}")

    # -------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------

    def execute(self):
        """Main execution entry"""
        try:
            self.is_running = True
            print(f"[SERVER_EXEC] Starting execution {self.execution_id}")

            if self.enable_streaming and not self.vnc_session:
                self._start_vnc_session()

            results = self._execute_tests()
            print(f"[SERVER_EXEC] Execution completed")

            return results

        finally:
            self.is_running = False

            time.sleep(2)

            # VNC session cleanup removed - keep VNC alive for remote viewing
            # Users must explicitly stop VNC or it will timeout after idle period
            # if self.vnc_session and vnc_manager:
            #     print("[SERVER_EXEC] Cleaning up VNC session")
            #     vnc_manager.stop_user_vnc_session(self.vnc_session.get("session_id"))

    # -------------------------------------------------------
    # VNC
    # -------------------------------------------------------

    def _start_vnc_session(self):
        print(f"[VNC_SESSION] Starting VNC for execution {self.execution_id}")

        if not vnc_manager:
            print("[VNC_SESSION] VNC manager not available, will run headless")
            self.vnc_failed = True
            self.running_headless = True
            return

        max_retries = 3
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                print(f"[VNC_SESSION] Attempt {attempt + 1}/{max_retries} to start VNC session")
                
                session = vnc_manager.start_streaming_session(
                    self.user_email,
                    self.execution_id
                )

                if session:
                    self.vnc_session = session
                    print(f"[VNC_SESSION] Started successfully on attempt {attempt + 1}: {session['novnc_url']}")
                    
                    if self._validate_vnc_session(session):
                        print("[VNC_SESSION] ✓ Session validation successful")
                        
                        if vnc_lifecycle_manager and self.user_email:
                            try:
                                vnc_lifecycle_manager.user_sessions[self.user_email] = {
                                    'session_id': session.get('session_id'),
                                    'display': session.get('display'),
                                    'vnc_port': session.get('vnc_port'),
                                    'novnc_port': session.get('novnc_port'),
                                    'novnc_url': session.get('novnc_url'),
                                    'pids': session.get('pids', []),
                                    'created_at': datetime.now().isoformat(),
                                    'status': 'active'
                                }
                                print(f"[VNC_SESSION] Registered session with lifecycle manager for {self.user_email}")
                            except Exception as lm_error:
                                print(f"[VNC_SESSION] Warning: Could not register with lifecycle manager: {lm_error}")
                        
                        try:
                            webbrowser.open(session['novnc_url'])
                            print(f"[VNC_SESSION] Opened browser to: {session['novnc_url']}")
                        except Exception as e:
                            print(f"[VNC_SESSION] Failed to open browser: {e}")
                        return
                    else:
                        print("[VNC_SESSION] Session validation failed, trying again...")
                        if attempt < max_retries - 1:
                            time.sleep(base_delay * (2 ** attempt))
                            continue
                else:
                    print(f"[VNC_SESSION] Failed to create session on attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        print(f"[VNC_SESSION] Waiting {delay}s before retry...")
                        time.sleep(delay)
                        
            except Exception as e:
                print(f"[VNC_SESSION] Exception on attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"[VNC_SESSION] Waiting {delay}s before retry...")
                    time.sleep(delay)
                    
        print("[VNC_SESSION] ✗ All retry attempts failed, falling back to headless execution")
        self.vnc_failed = True
        self.running_headless = True
        self.vnc_session = None

    def _validate_vnc_session(self, session):
        """Validate that the VNC session is actually working"""
        try:
            import socket
            import time
            
            novnc_port = session.get('novnc_port')
            if not novnc_port:
                print("[VNC_VALIDATE] No noVNC port found")
                return False
                
            # Try to connect to the noVNC port
            for attempt in range(3):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    result = sock.connect_ex(('localhost', novnc_port))
                    sock.close()
                    
                    if result == 0:
                        print(f"[VNC_VALIDATE] Port {novnc_port} is accessible")
                        return True
                    else:
                        print(f"[VNC_VALIDATE] Port {novnc_port} not accessible on attempt {attempt + 1}")
                        if attempt < 2:
                            time.sleep(1)
                        
                except Exception as e:
                    print(f"[VNC_VALIDATE] Socket test failed on attempt {attempt + 1}: {e}")
                    if attempt < 2:
                        time.sleep(1)
                        
            return False
            
        except Exception as e:
            print(f"[VNC_VALIDATE] Validation error: {e}")
            return False

    # -------------------------------------------------------
    # EXECUTION
    # -------------------------------------------------------

    def _execute_tests(self):
        print(f"[EXECUTE] Executing {len(self.test_cases)} test cases")
        
        if self.vnc_failed:
            print(f"[EXECUTE] ⚠ VNC Failed - Running in Headless mode")
            self.running_headless = True

        display_id = self.vnc_session.get('display') if self.vnc_session else None
        
        if self.executor_type == "playwright":
            self.executor = PlaywrightTestExecutor(
                enable_isolation=self.enable_isolation,
                server_execution=True,
                vnc_session=self.vnc_session if (self.enable_streaming and not self.vnc_failed) else None,
                display_id=display_id,
                browser_name=self.browser_name,
            )

        elif self.executor_type == "cypress":
            self.executor = CypressTestExecutor(
                enable_isolation=self.enable_isolation,
                server_execution=True,
                vnc_session=self.vnc_session if (self.enable_streaming and not self.vnc_failed) else None,
                display_id=display_id,
                browser_name=self.browser_name,
            )

        else:
            self.executor = SeleniumTestExecutor(
                enable_isolation=self.enable_isolation,
                enable_remote_viewing=bool(self.vnc_session and self.enable_streaming and not self.vnc_failed),
                server_execution=True,
                headless=True if self.vnc_failed else None,
                vnc_session=self.vnc_session if (self.enable_streaming and not self.vnc_failed) else None,
                display_id=display_id,
                browser_name=self.browser_name,
            )

        if self.enable_parallel:
            return self._execute_parallel()

        return self._execute_sequential()

    def _execute_sequential(self):
        results = []
        for i, tc in enumerate(self.test_cases, 1):
            print(f"[SEQUENTIAL] Test {i}/{len(self.test_cases)}: {tc.get('name')}")
            results.append(self._execute_single_test(tc))
        return results

    def _execute_parallel(self):
        results = []
        threads = []

        def run(tc):
            results.append(self._execute_single_test(tc))

        for tc in self.test_cases:
            t = threading.Thread(target=run, args=(tc,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=300)

        return results

    def _execute_single_test(self, test_case):
        try:
            steps = self._get_test_steps(test_case)
            if not steps:
                raise RuntimeError("No test steps found")

            testcase_name = test_case.get("name")
            # FIX 1: Use actual suite_type from test case, don't default to "regression" unless truly missing
            suite_type = test_case.get("suite_type") or test_case.get("testsuitename")
            
            # If suite_type is still missing, try to fetch from database
            if not suite_type:
                try:
                    from app import get_db_connection
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT suite_type FROM TestCases WHERE name = ?", (testcase_name,))
                    result = cursor.fetchone()
                    cursor.close()
                    conn.close()
                    if result and result[0]:
                        suite_type = result[0]
                        print(f"[SERVER_EXEC] Fetched suite_type from database: '{suite_type}' for {testcase_name}")
                    else:
                        suite_type = "regression"
                        print(f"[SERVER_EXEC] No suite_type in database for {testcase_name}, defaulting to 'regression'")
                except Exception as e:
                    suite_type = "regression"
                    print(f"[SERVER_EXEC] Error fetching suite_type from database: {e}, defaulting to 'regression'")
            else:
                print(f"[SERVER_EXEC] Using suite_type from test case: '{suite_type}' for {testcase_name}")
            
            # FIX 2: Use Indian timezone (IST) for execution timing
            ist = pytz.timezone('Asia/Kolkata')
            execution_start_time = datetime.now(ist)
            print(f"[SERVER_EXEC] Execution started at: {execution_start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            
            module_name = test_case.get("module") or test_case.get("modulename") or "Unknown Module"
            project_name = test_case.get("project") or test_case.get("projectname") or "Unknown Project"
            testcase_id = test_case.get("testcase_id")
            if not testcase_id:
                testcase_id = f"TC_{testcase_name}_001"
            testrun_id = test_case.get("testrun_id")
            result_id = test_case.get("result_id")
            if not testrun_id and generate_testrun_id:
                try:
                    testrun_id = generate_testrun_id(suite_type, testcase_name)
                    print(f"[SERVER_EXEC] Generated testrun_id: {testrun_id}")
                except Exception as e:
                    print(f"[SERVER_EXEC] Error generating testrun_id: {e}")
                    testrun_id = f"{suite_type}_{testcase_name}_TR001"
            if not result_id and generate_result_id and testrun_id:
                try:
                    result_id = generate_result_id(testcase_id, testrun_id)
                    print(f"[SERVER_EXEC] Generated result_id: {result_id}")
                except Exception as e:
                    print(f"[SERVER_EXEC] Error generating result_id: {e}")
                    result_id = f"TC001_TR001"

            # Ensure all metadata is set and not defaulted
            test_metadata = {
                "user": self.user_email,
                "execution_id": self.execution_id,
                "module_name": module_name,
                "project_name": project_name,
                "suite_type": suite_type,
                "module_id": test_case.get("module_id"),
                "project_id": test_case.get("project_id"),
                "testcase_id": testcase_id,
                "testrun_id": testrun_id,
                "result_id": result_id,
                "run_id": test_case.get("run_id"),
                "browser_name": self.browser_name,
            }

            result = self.executor.execute_test_case(
                testcase_name=testcase_name,
                test_steps=steps,
                test_metadata=test_metadata,
            )

            # FIX 2 & 3: Calculate pass rate and determine overall status correctly
            total_steps = result.get("total_steps", 0)
            passed_steps = result.get("passed_steps", 0)
            failed_steps = result.get("failed_steps", 0)
            
            # Calculate pass rate
            pass_rate = 0
            if total_steps > 0:
                pass_rate = round((passed_steps / total_steps) * 100, 2)
            
            # Determine overall status with proper logic
            if result.get("status") == "ERROR":
                overall_status = "ERROR"
            elif failed_steps == 0 and passed_steps > 0:
                overall_status = "PASS"
            elif passed_steps > 0 and failed_steps > 0:
                overall_status = "PARTIAL_PASS"
            elif passed_steps == 0 and failed_steps > 0:
                overall_status = "FAIL"
            else:
                overall_status = "UNKNOWN"

            result["execution_id"] = self.execution_id
            result["executor_type"] = self.executor_type
            result["browser_name"] = self.browser_name
            result["suite_type"] = suite_type
            result["module_name"] = module_name
            result["project_name"] = project_name
            result["testcase_id"] = testcase_id
            result["testrun_id"] = testrun_id
            result["result_id"] = result_id
            result["pass_rate"] = pass_rate
            result["overall_status"] = overall_status
            result["status"] = overall_status
            result["execution_start_time"] = format_timestamp(execution_start_time) if format_timestamp else execution_start_time.isoformat().rstrip('Z')
            result["execution_date"] = execution_start_time.strftime('%d/%m/%Y, %H:%M:%S')
            
            result["vnc_status"] = {
                "vnc_failed": self.vnc_failed,
                "running_headless": self.running_headless,
                "execution_mode": "headless" if self.running_headless else "vnc"
            }
            
            mode_str = "🖥️ Headless" if self.running_headless else "🎥 VNC"
            print(f"[SERVER_EXEC] Test {testcase_name} completed [{mode_str}]: Status={overall_status}, Pass Rate={pass_rate}%, Steps={passed_steps}/{total_steps}")
            return result

        except Exception as e:
            print(f"[SERVER_EXEC] Test execution error: {e}")
            import traceback
            traceback.print_exc()
            
            mode_str = "🖥️ Headless" if self.running_headless else "🎥 VNC"
            return {
                "testcase_name": test_case.get("name"),
                "status": "ERROR",
                "error": str(e),
                "execution_id": self.execution_id,
                "executor_type": self.executor_type,
                "browser_name": self.browser_name,
                "vnc_status": {
                    "vnc_failed": self.vnc_failed,
                    "running_headless": self.running_headless,
                    "execution_mode": "headless" if self.running_headless else "vnc"
                }
            }

    # -------------------------------------------------------
    # DB
    # -------------------------------------------------------

    def _get_db_connection(self):
        if callable(get_db_connection):
            try:
                return get_db_connection()
            except Exception as e:
                print(f"[SERVER_DB] App DB connection unavailable, using fallback config: {e}")

        conn_str = (
            f"DRIVER={{{self.DB_CONFIG['driver']}}};"
            f"SERVER={self.DB_CONFIG['server']};"
            f"DATABASE={self.DB_CONFIG['database']};"
            f"UID={self.DB_CONFIG['uid']};"
            f"PWD={self.DB_CONFIG['pwd']};"
        )
        return pyodbc.connect(conn_str)

    def _resolve_testcase_metadata(self, cursor, test_case):
        name = test_case.get("name")
        testcase_db_id = test_case.get("id") or test_case.get("testcase_db_id") or test_case.get("testcaseId")
        project_name = test_case.get("project_name") or test_case.get("project")
        module_name = test_case.get("module_name") or test_case.get("module")

        base_query = """
            SELECT tc.id,
                   COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                   COALESCE(m.module_name, 'Unknown') as module_name
            FROM TestCases tc
            LEFT JOIN Modules m ON tc.module_id = m.id
            LEFT JOIN Projects p1 ON tc.project_id = p1.id
            LEFT JOIN Projects p2 ON m.project_id = p2.id
        """

        if testcase_db_id not in (None, ""):
            cursor.execute(base_query + " WHERE tc.id = ?", (testcase_db_id,))
            return cursor.fetchone()

        params = [name]
        query = base_query + " WHERE tc.name = ?"
        if project_name and module_name:
            query += " AND COALESCE(p1.name, p2.name, 'Unknown') = ? AND COALESCE(m.module_name, 'Unknown') = ?"
            params.extend([project_name, module_name])
        query += " ORDER BY tc.id"

        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        if not rows:
            return None

        if len(rows) > 1 and not (project_name and module_name):
            print(f"[SERVER_EXEC] Multiple testcase rows found for '{name}', using first match")
        return rows[0]

    def _get_test_steps(self, test_case):
        conn = self._get_db_connection()
        cursor = conn.cursor()

        name = test_case.get("name")
        table = None

        try:
            metadata = self._resolve_testcase_metadata(cursor, test_case)
            if metadata:
                table = self._generate_unique_table_name(metadata[1], metadata[2], name)
                print(
                    f"[SERVER_EXEC] Resolved steps table for '{name}' using "
                    f"tc.id={metadata[0]}, project='{metadata[1]}', module='{metadata[2]}'"
                )
        except Exception as e:
            print(f"[SERVER_EXEC] Table resolution by metadata failed for '{name}': {e}")

        if not table:
            table = self._generate_unique_table_name(
                test_case.get("project", ""),
                test_case.get("module", ""),
                name,
            )

        cursor.execute(
            f"SELECT tc_id, step_no, test_step_description, element_name, action_type, xpath, [values] FROM [{table}] ORDER BY step_no"
        )
        rows = cursor.fetchall()

        steps = []
        for r in rows:
            steps.append({
                "step_no": r.step_no,
                "test_step_description": r.test_step_description,
                "element_name": r.element_name,
                "action_type": r.action_type,
                "xpath": r.xpath,
                "values": r.values,
            })

        # Mirror local execution behavior: apply Excel mapping when with_values is enabled.
        with_values = bool(test_case.get("with_values"))
        value_set_index = test_case.get("value_set_index")
        if with_values and value_set_index is not None:
            try:
                mapped = self._apply_excel_values_to_steps(cursor, name, steps, value_set_index)
                if mapped:
                    steps = mapped
            except Exception as e:
                print(f"[SERVER_EXEC] Excel mapping skipped for '{name}': {e}")

        conn.close()

        return steps

    def _apply_excel_values_to_steps(self, cursor, testcase_name, steps, value_set_index):
        if not steps:
            return steps

        try:
            value_set_index = int(value_set_index)
        except Exception:
            print(f"[SERVER_EXEC] Invalid value_set_index '{value_set_index}' for {testcase_name}")
            return steps

        cursor.execute("""
            SELECT TOP 1 v.original_name, em.sheet_name
            FROM [dbo].[ExcelMapping] em
            INNER JOIN [dbo].[TestCases] tc ON tc.id = em.testcase_id
            LEFT JOIN [dbo].[Values] v ON v.id = em.excel_file_id
            WHERE tc.name = ?
        """, (testcase_name,))
        result = cursor.fetchone()

        if not result or not result[0]:
            cursor.execute("""
                SELECT mapped_excel_file_name, mapped_excel_sheet_name
                FROM [dbo].[TestCases]
                WHERE name = ?
            """, (testcase_name,))
            result = cursor.fetchone()

        mapped_excel_name = result[0] if result and result[0] else None
        mapped_sheet_name = result[1] if result and len(result) > 1 and result[1] else None

        if not mapped_excel_name:
            print(f"[SERVER_EXEC] No mapped Excel file for {testcase_name}")
            return steps

        cursor.execute("""
            SELECT TOP 1 file_path
            FROM [dbo].[Values]
            WHERE original_name = ? AND status = 'Active'
            ORDER BY id DESC
        """, (mapped_excel_name,))
        file_row = cursor.fetchone()

        if not file_row:
            cursor.execute("""
                SELECT TOP 1 file_path
                FROM [dbo].[Values]
                WHERE LOWER(original_name) = LOWER(?) AND status = 'Active'
                ORDER BY id DESC
            """, (mapped_excel_name,))
            file_row = cursor.fetchone()

        if not file_row or not file_row[0] or not os.path.exists(file_row[0]):
            print(f"[SERVER_EXEC] Mapped Excel file not found for {testcase_name}: {mapped_excel_name}")
            return steps

        from openpyxl import load_workbook

        file_path = file_row[0]
        workbook = load_workbook(file_path, data_only=True, read_only=True)
        try:
            if not workbook.sheetnames:
                return steps

            if mapped_sheet_name and mapped_sheet_name in workbook.sheetnames:
                sheet = workbook[mapped_sheet_name]
            else:
                sheet = workbook[workbook.sheetnames[0]]

            all_rows = list(sheet.iter_rows(values_only=True))
            if not all_rows:
                return steps

            headers = list(all_rows[0]) if all_rows else []
            data_rows = all_rows[1:] if len(all_rows) > 1 else []

            active_col_indices = []
            for col_idx, header_value in enumerate(headers):
                header_text = '' if header_value is None else str(header_value).strip()
                has_non_empty_data = any(
                    (col_idx < len(row_vals))
                    and (row_vals[col_idx] is not None)
                    and str(row_vals[col_idx]).strip() != ''
                    for row_vals in data_rows
                )
                if header_text != '' or has_non_empty_data:
                    active_col_indices.append(col_idx)

            active_row_indices = []
            for row_idx, row_vals in enumerate(data_rows):
                has_non_empty_data = any(
                    (actual_col_idx < len(row_vals))
                    and (row_vals[actual_col_idx] is not None)
                    and str(row_vals[actual_col_idx]).strip() != ''
                    for actual_col_idx in active_col_indices
                )
                if has_non_empty_data:
                    active_row_indices.append(row_idx)

            num_cols = len(active_col_indices)
            if value_set_index < 0 or value_set_index >= num_cols:
                print(
                    f"[SERVER_EXEC] value_set_index {value_set_index} out of range for {testcase_name} (columns={num_cols})"
                )
                return steps

            selected_col = active_col_indices[value_set_index]
            selected_header = headers[selected_col] if selected_col < len(headers) else ''
            selected_header = '' if selected_header is None else str(selected_header).strip()
            header_is_url = bool(re.match(r'^https?://', selected_header, re.IGNORECASE))

            mapped_steps = []
            for step_index, step in enumerate(steps):
                mapped_step = dict(step)
                if step_index == 0 and header_is_url:
                    cell_value = selected_header
                else:
                    row_index = step_index - 1 if header_is_url else step_index
                    if row_index < 0 or row_index >= len(active_row_indices):
                        cell_value = ''
                    else:
                        actual_row_idx = active_row_indices[row_index]
                        row_vals = data_rows[actual_row_idx] if actual_row_idx < len(data_rows) else ()
                        raw = row_vals[selected_col] if selected_col < len(row_vals) else None
                        if raw is None:
                            cell_value = ''
                        elif hasattr(raw, 'isoformat'):
                            cell_value = raw.isoformat()
                        else:
                            cell_value = str(raw)

                mapped_step["values"] = cell_value

                if mapped_step.get("element_name") and "{{" in str(mapped_step.get("element_name", "")):
                    mapped_step["element_name"] = re.sub(
                        r"\{\{\s*\w+\s*\}\}",
                        cell_value,
                        str(mapped_step["element_name"]),
                    )

                mapped_steps.append(mapped_step)

            print(
                f"[SERVER_EXEC] Applied Excel mapping for {testcase_name}: dataset={value_set_index}, steps={len(mapped_steps)}"
            )
            return mapped_steps
        finally:
            workbook.close()

    # -------------------------------------------------------
    # TABLE NAMING
    # -------------------------------------------------------

    def _generate_unique_table_name(self, project, module, testcase):
        if generate_unique_table_name:
            return generate_unique_table_name(project, module, testcase)

        def sanitize(x):
            return re.sub(r"[^\w]", "", re.sub(r"[ \-]+", "_", x))

        return f"{sanitize(project)}_{sanitize(module)}_{sanitize(testcase)}"

    # -------------------------------------------------------
    # STATUS
    # -------------------------------------------------------

    def get_status(self):
        return {
            "execution_id": self.execution_id,
            "is_running": self.is_running,
            "executor_type": self.executor_type,
            "enable_streaming": self.enable_streaming,
            "novnc_url": self.vnc_session.get("novnc_url") if self.vnc_session else "",
            "novnc_port": self.vnc_session.get("novnc_port") if self.vnc_session else "",
            "vnc_status": {
                "vnc_failed": self.vnc_failed,
                "running_headless": self.running_headless,
                "execution_mode": "headless" if self.running_headless else "vnc"
            }
        }
