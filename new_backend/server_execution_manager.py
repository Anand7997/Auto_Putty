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
    from new_backend.app import generate_unique_table_name, sanitize_table_name, generate_testrun_id, generate_result_id, format_timestamp
except ImportError:
    try:
        from app import generate_unique_table_name, sanitize_table_name, generate_testrun_id, generate_result_id, format_timestamp
    except ImportError:
        generate_unique_table_name = None
        sanitize_table_name = None
        generate_testrun_id = None
        generate_result_id = None
        format_timestamp = None

# VNC session manager
try:
    from vnc_session_manager import vnc_manager
except ImportError:
    vnc_manager = None
    print("[WARNING] VNC session manager not available")


class ServerExecutionManager:
    """Manages test execution on server with optional live streaming"""

    def __init__(
        self,
        execution_id,
        test_cases,
        selected_suites,
        executor_type="selenium",
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
            print("[VNC_SESSION] VNC manager not available")
            return

        # Try multiple times with exponential backoff
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
                    
                    # Validate the session is actually working
                    if self._validate_vnc_session(session):
                        print("[VNC_SESSION] Session validation successful")
                        # Automatically open browser to VNC session for live viewing
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
                    
        print("[VNC_SESSION] All retry attempts failed")

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

        display_id = self.vnc_session.get('display') if self.vnc_session else None
        
        if self.executor_type == "playwright":
            self.executor = PlaywrightTestExecutor(
                enable_isolation=self.enable_isolation,
                server_execution=True,
                vnc_session=self.vnc_session if self.enable_streaming else None,
                display_id=display_id,
            )

        elif self.executor_type == "cypress":
            self.executor = CypressTestExecutor(
                enable_isolation=self.enable_isolation,
                server_execution=True,
                vnc_session=self.vnc_session if self.enable_streaming else None,
                display_id=display_id,
            )

        else:
            self.executor = SeleniumTestExecutor(
                enable_isolation=self.enable_isolation,
                enable_remote_viewing=bool(self.vnc_session and self.enable_streaming),
                server_execution=True,
                headless=None,  # AUTO
                vnc_session=self.vnc_session if self.enable_streaming else None,
                display_id=display_id,
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

            # Overwrite with correct metadata if executor returned defaults
            result["execution_id"] = self.execution_id
            result["executor_type"] = self.executor_type
            result["suite_type"] = suite_type
            result["module_name"] = module_name
            result["project_name"] = project_name
            result["testcase_id"] = testcase_id
            result["testrun_id"] = testrun_id
            result["result_id"] = result_id
            result["pass_rate"] = pass_rate
            result["overall_status"] = overall_status
            result["execution_start_time"] = format_timestamp(execution_start_time) if format_timestamp else execution_start_time.isoformat().rstrip('Z')
            result["execution_date"] = execution_start_time.strftime('%d/%m/%Y, %H:%M:%S')
            
            print(f"[SERVER_EXEC] Test {testcase_name} completed: Status={overall_status}, Pass Rate={pass_rate}%, Steps={passed_steps}/{total_steps}")
            return result

        except Exception as e:
            print(f"[SERVER_EXEC] Test execution error: {e}")
            import traceback
            traceback.print_exc()
            return {
                "testcase_name": test_case.get("name"),
                "status": "ERROR",
                "error": str(e),
                "execution_id": self.execution_id,
                "executor_type": self.executor_type,
            }

    # -------------------------------------------------------
    # DB
    # -------------------------------------------------------

    def _get_db_connection(self):
        conn_str = (
            f"DRIVER={{{self.DB_CONFIG['driver']}}};"
            f"SERVER={self.DB_CONFIG['server']};"
            f"DATABASE={self.DB_CONFIG['database']};"
            f"UID={self.DB_CONFIG['uid']};"
            f"PWD={self.DB_CONFIG['pwd']};"
        )
        return pyodbc.connect(conn_str)

    def _get_test_steps(self, test_case):
        conn = self._get_db_connection()
        cursor = conn.cursor()

        name = test_case.get("name")

        table = self._generate_unique_table_name(
            test_case.get("project", ""),
            test_case.get("module", ""),
            name,
        )

        cursor.execute(f"SELECT * FROM [{table}] ORDER BY step_no")
        rows = cursor.fetchall()
        conn.close()

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

        return steps

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
        }
