from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import pyodbc
import json
import time
from datetime import datetime, timezone
import traceback
import re
import subprocess
import os
import shutil
import uuid
import threading
import requests
import platform
import pytz
from urllib.parse import unquote
from werkzeug.security import generate_password_hash, check_password_hash
from selenium_executor import SeleniumTestExecutor
from playwright_executor import PlaywrightTestExecutor
from cypress_executor import CypressTestExecutor
from server_execution_manager import ServerExecutionManager
from system_monitor import setup_system_monitor_routes
from vnc_session_manager import vnc_manager
from vnc_lifecycle_manager import vnc_lifecycle_manager

app = Flask(__name__)

# Configure CORS to allow requests from frontend AND Chrome Extension
# NOTE: Extension can be loaded from any origin, so we must whitelist common ones
CORS(app,
      origins=[
        # Local development
        'http://localhost:8081',
        'http://localhost:3000',
        'http://127.0.0.1:8081',
        'http://127.0.0.1:3000',
        'http://10.30.3.85:8081',
        # HTTPS versions (for production/staging)
        'https://localhost:8081',
        'https://localhost:3000',
        'https://127.0.0.1:8081',
        'https://127.0.0.1:3000',
        'https://10.30.3.85:8081',
        'https://172.31.18.64:8081',
        # DevTunnels domains - for remote development
        'https://hsn9x7cd-5000.inc1.devtunnels.ms',
        'https://hsn9x7cd-8081.inc1.devtunnels.ms',
        'https://*.inc1.devtunnels.ms',
        'https://*.devtunnels.ms',
        'https://*.devtunnels.com',
        # Ixigo domains - for extension testing
        'https://www.ixigo.com',
        'https://ixigo.com',
        'http://www.ixigo.com',
        'http://ixigo.com',
      ],
      methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
      allow_headers=['Content-Type', 'Authorization', 'X-User-Email', 'Accept', 'Origin', 'X-Requested-With'],
      supports_credentials=False)  # Disable credentials when allowing multiple origins

# Initialize Socket.IO for real-time communication
socketio = SocketIO(app, cors_allowed_origins=[
        'http://localhost:8081',
        'http://localhost:3000',
        'http://127.0.0.1:8081',
        'http://127.0.0.1:3000',
        'http://10.30.3.85:8081',
        'https://localhost:8081',
        'https://localhost:3000',
        'https://127.0.0.1:8081',
        'https://127.0.0.1:3000',
        'https://10.30.3.85:8081',
        'https://172.31.18.64:8081',
        # DevTunnels domains - for remote development
        'https://hsn9x7cd-5000.inc1.devtunnels.ms',
        'https://hsn9x7cd-8081.inc1.devtunnels.ms',
        'https://*.inc1.devtunnels.ms',
        'https://*.devtunnels.ms',
        'https://*.devtunnels.com',
        'https://www.ixigo.com',
        'https://ixigo.com',
        'http://www.ixigo.com',
        'http://ixigo.com',
      ])

# Global variables for remote viewing sessions
remote_viewing_sessions = {}
active_test_sessions = {}
# Global variables for server execution tracking
execution_results = {}

# Remote Viewing Session Management
class RemoteViewingSession:
    def __init__(self, session_id, user_email, testcase_name=None):
        self.session_id = session_id
        self.user_email = user_email
        self.testcase_name = testcase_name
        self.created_at = datetime.now(pytz.timezone('Asia/Kolkata'))
        self.last_activity = datetime.now(pytz.timezone('Asia/Kolkata'))
        self.status = 'active'  # active, paused, stopped
        self.viewers = set()  # Set of connected viewer IDs
        self.executor = None  # Selenium/Playwright executor instance
        self.stream_url = None
        self.novnc_url = None  # noVNC streaming URL for server execution
        self.current_step = 0
        self.total_steps = 0
        self.execution_id = None  # For server execution tracking
        self.execution_mode = 'local'  # 'local' or 'server'
        self.test_cases = []  # For server execution
        self.selected_suites = []  # For server execution

    def add_viewer(self, viewer_id):
        self.viewers.add(viewer_id)
        self.last_activity = datetime.now(pytz.timezone('Asia/Kolkata'))

    def remove_viewer(self, viewer_id):
        self.viewers.discard(viewer_id)
        self.last_activity = datetime.now(pytz.timezone('Asia/Kolkata'))

    def update_activity(self):
        self.last_activity = datetime.now(pytz.timezone('Asia/Kolkata'))

    def to_dict(self):
        return {
            'session_id': self.session_id,
            'user_email': self.user_email,
            'testcase_name': self.testcase_name,
            'created_at': format_timestamp(self.created_at),
            'last_activity': format_timestamp(self.last_activity),
            'status': self.status,
            'viewer_count': len(self.viewers),
            'stream_url': self.stream_url,
            'novnc_url': self.novnc_url,
            'current_step': self.current_step,
            'total_steps': self.total_steps,
            'execution_id': self.execution_id,
            'execution_mode': self.execution_mode,
            'streaming_active': self.novnc_url is not None
        }

DB_CONFIG = {
            "server": "10.30.3.85",
            "port": "1433",
            "database": "AppDB",
            "driver": "ODBC Driver 17 for SQL Server",
            "uid": "appuser",
            "pwd": "MyPass135",
        }

def get_db_connection():
    """Create a NEW database connection (thread-safe)"""
    try:
        conn_str = (
            f"DRIVER={{{DB_CONFIG['driver']}}};"
            f"SERVER={DB_CONFIG['server']};"
            f"PORT={DB_CONFIG['port']};"
            f"DATABASE={DB_CONFIG['database']};"
            f"UID={DB_CONFIG['uid']};"
            f"PWD={DB_CONFIG['pwd']};"
            f"Encrypt=no;"
            f"Connection Timeout=120;Login Timeout=120;"
        )

        conn = pyodbc.connect(conn_str, autocommit=True)
        return conn

    except pyodbc.Error as e:
        print(f"[DB_ERROR] Failed to connect to database: {e}")
        raise


def table_exists(cursor, table_name: str, schema_name: str = 'dbo') -> bool:
    """Check if a table exists in SQL Server."""
    cursor.execute("""
        SELECT 1
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
    """, (schema_name, table_name))
    return cursor.fetchone() is not None



def get_allure_report_host():
    """Get the correct host for Allure report URL based on OS"""
    if platform.system() == 'Linux':
        return '10.30.3.85:5000'
    else:
        return 'localhost:5000'



def format_timestamp(dt):
    """Format datetime to ISO format with proper timezone handling"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        # If datetime is naive (no timezone), assume it's UTC for server execution
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # Return ISO format with timezone information preserved
        return dt.isoformat()
    return dt


def sanitize_table_name(name: str) -> str:
    """Sanitize the testcase name to create a safe SQL Server table name"""
    sanitized = re.sub(r'[ \-]+', '_', name)
    sanitized = re.sub(r'[^\w]', '', sanitized)
    return sanitized

def generate_unique_table_name(project_name: str, module_name: str, testcase_name: str) -> str:
    """Generate a unique table name that includes project and module to avoid conflicts"""
    # Sanitize each component
    proj_part = sanitize_table_name(project_name)
    mod_part = sanitize_table_name(module_name)
    tc_part = sanitize_table_name(testcase_name)

    # Create unique table name: project_module_testcase
    table_name = f"{proj_part}_{mod_part}_{tc_part}"

    # Ensure it's not too long (SQL Server limit is 128 chars)
    if len(table_name) > 128:
        # Truncate intelligently, keeping the testcase name as much as possible
        max_proj_mod_len = 60  # Leave room for testcase and separators
        available_for_tc = 128 - len(f"{proj_part[:30]}_{mod_part[:30]}_") - 1
        tc_part = tc_part[:available_for_tc] if available_for_tc > 0 else tc_part[:50]
        table_name = f"{proj_part[:30]}_{mod_part[:30]}_{tc_part}"

    return table_name

def sanitize_id_component(name: str) -> str:
    """Sanitize name components for ID generation"""
    sanitized = re.sub(r'[^a-zA-Z0-9]', '', name)
    return sanitized  # Don't truncate - keep full names for clarity

def generate_testcase_id(project_name: str, module_name: str, testcase_name: str, conn) -> str:
    """Generate testcase_ID in format: projectname_modulename_testcasename_TC001"""
    cursor = conn.cursor()
    
    # Sanitize components (remove special characters, keep original case)
    proj_part = sanitize_id_component(project_name)
    mod_part = sanitize_id_component(module_name)
    tc_part = sanitize_id_component(testcase_name)
    
    # Debug: Print the sanitized parts
    print(f"[DEBUG] Generating ID for: {project_name} -> {proj_part}, {module_name} -> {mod_part}, {testcase_name} -> {tc_part}")
    
    # Get the next sequence number for this PROJECT-MODULE combination (regardless of test case name)
    # Use exact prefix matching to avoid false matches like IRCTC_Trains matching IRCTC_Train
    exact_prefix = f"{proj_part}_{mod_part}_"
    print(f"[DEBUG] Looking for existing IDs with exact prefix: {exact_prefix}")
    
    cursor.execute("""
        SELECT testcase_id FROM [dbo].[TestCases]
        WHERE testcase_id LIKE ?
        ORDER BY testcase_id
    """, (f"{exact_prefix}%_TC%",))
    
    all_matching_ids = cursor.fetchall()
    
    # Filter to ensure exact project-module match (avoid IRCTC_Trains matching IRCTC_Train)
    existing_ids = []
    import re
    for row in all_matching_ids:
        tc_id = row[0]
        # Check if it starts with exact prefix and has the correct format
        if tc_id.startswith(exact_prefix):
            # Extract the part after the prefix and before _TC
            remaining = tc_id[len(exact_prefix):]
            if re.match(r'^.+_TC\d{3}$', remaining):
                existing_ids.append(row)
    
    print(f"[DEBUG] Found {len(all_matching_ids)} potential matches, {len(existing_ids)} exact matches")
    
    if existing_ids:
        # Extract all TC numbers from existing test cases in this project-module
        existing_numbers = []
        import re
        for row in existing_ids:
            tc_id = row[0]
            # Extract the TC number from the end using regex
            match = re.search(r'_TC(\d{3})$', tc_id)
            if match:
                tc_num = int(match.group(1))
                existing_numbers.append(tc_num)
        
        if existing_numbers:
            # Sort the existing numbers to find the first gap
            existing_numbers.sort()
            next_num = 1
            
            # Find the first available number (fill gaps)
            for num in existing_numbers:
                if num == next_num:
                    next_num += 1
                else:
                    # Found a gap, use this number
                    break
            
            print(f"[DEBUG] Found {len(existing_ids)} existing test cases in {proj_part}_{mod_part}")
            print(f"[DEBUG] Existing TC numbers: {existing_numbers}")
            print(f"[DEBUG] Next available TC number: TC{next_num:03d}")
        else:
            next_num = 1
        
        print(f"[DEBUG] Generating TC{next_num:03d}")
    else:
        # No existing test cases in this project-module, start with TC001
        next_num = 1
        print(f"[DEBUG] No existing test cases found in {proj_part}_{mod_part}, generating TC{next_num:03d}")
    
    # Generate the ID in format: projectname_modulename_testcasename_TC001
    testcase_id = f"{proj_part}_{mod_part}_{tc_part}_TC{next_num:03d}"
    print(f"[DEBUG] Generated testcase_id: {testcase_id}")
    return testcase_id

def generate_testrun_id(suite_type: str, testcase_name: str, conn=None) -> str:
    """Generate TestRun_id in format: testsuitename_testcasename_TR001"""
    # Create a fresh connection to avoid "connection busy" errors
    fresh_conn = get_db_connection()
    cursor = fresh_conn.cursor()
    
    # Sanitize components
    suite_part = sanitize_id_component(suite_type)
    tc_part = sanitize_id_component(testcase_name)
    
    # Get the next sequence number for this combination
    cursor.execute("""
        SELECT COUNT(*) FROM selenium_results 
        WHERE testrun_id LIKE ?
    """, (f"{suite_part}_{tc_part}_TR%",))
    
    count = cursor.fetchone()[0] + 1
    cursor.close()
    fresh_conn.close()
    
    # Generate the ID
    testrun_id = f"{suite_part}_{tc_part}_TR{count:03d}"
    return testrun_id


def generate_result_id(testcase_id: str, testrun_id: str) -> str:
    """Generate Result_id by combining testcase_id and testrun_id"""
    # Extract TC and TR numbers
    tc_num = testcase_id.split('_TC')[-1] if '_TC' in testcase_id else '001'
    tr_num = testrun_id.split('_TR')[-1] if '_TR' in testrun_id else '001'
    
    result_id = f"TC{tc_num}_TR{tr_num}"
    return result_id



def migrate_test_steps(source_testcase_name: str, target_testcase_name: str, conn) -> bool:
    """Migrate test steps from source test case to target test case"""
    try:
        cursor = conn.cursor()
        
        # Get project and module info for both source and target test cases
        cursor.execute("""
            SELECT tc.name, COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                   COALESCE(m.module_name, 'Unknown') as module_name
            FROM TestCases tc
            LEFT JOIN Modules m ON tc.module_id = m.id
            LEFT JOIN Projects p1 ON tc.project_id = p1.id
            LEFT JOIN Projects p2 ON m.project_id = p2.id
            WHERE tc.name IN (?, ?)
        """, (source_testcase_name, target_testcase_name))

        testcase_metadata = cursor.fetchall()
        metadata_dict = {row[0]: (row[1], row[2]) for row in testcase_metadata}

        # Generate table names using project/module info
        if source_testcase_name in metadata_dict:
            source_proj, source_mod = metadata_dict[source_testcase_name]
            source_table = generate_unique_table_name(source_proj, source_mod, source_testcase_name)
        else:
            source_table = sanitize_table_name(source_testcase_name)

        if target_testcase_name in metadata_dict:
            target_proj, target_mod = metadata_dict[target_testcase_name]
            target_table = generate_unique_table_name(target_proj, target_mod, target_testcase_name)
        else:
            target_table = sanitize_table_name(target_testcase_name)
        
        print(f"[MIGRATE] Copying test steps from {source_table} to {target_table}")
        
        # Check if source table exists
        cursor.execute(f"""
            SELECT COUNT(*) FROM sysobjects WHERE name='{source_table}' AND xtype='U'
        """)
        if cursor.fetchone()[0] == 0:
            print(f"[ERROR] Source table '{source_table}' does not exist")
            return False
        
        # Create target table if it doesn't exist
        cursor.execute(f"""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{target_table}' AND xtype='U')
            CREATE TABLE [{target_table}] (
                id INT IDENTITY(1,1) PRIMARY KEY,
                tc_id NVARCHAR(255),
                step_no INT,
                test_step_description NVARCHAR(500),
                element_name NVARCHAR(255),
                action_type NVARCHAR(100),
                xpath NVARCHAR(1000),
                [values] NVARCHAR(500),
                expected_result NVARCHAR(500),
                actual_result NVARCHAR(500),
                status NVARCHAR(20) DEFAULT 'Not Executed',
                page NVARCHAR(255) NULL
            )
        """)
        
        # Get the proper testcase_id for the target test case
        cursor.execute("SELECT testcase_id FROM TestCases WHERE name = ?", (target_testcase_name,))
        testcase_result = cursor.fetchone()
        target_testcase_id = testcase_result[0] if testcase_result else target_testcase_name
        print(f"[MIGRATE] Using target testcase_id: {target_testcase_id}")
        
        # Clear existing data in target table
        cursor.execute(f"DELETE FROM [{target_table}]")
        
        # Copy all test steps from source to target with proper testcase_id
        cursor.execute(f"""
            INSERT INTO [{target_table}] (tc_id, step_no, test_step_description, element_name, action_type, xpath, [values])
            SELECT ?, step_no, test_step_description, element_name, action_type, xpath, [values]
            FROM [{source_table}]
            ORDER BY step_no
        """, (target_testcase_id,))
        
        # Get count of copied steps
        cursor.execute(f"SELECT COUNT(*) FROM [{target_table}]")
        copied_count = cursor.fetchone()[0]
        
        print(f"[SUCCESS] Copied {copied_count} test steps from {source_testcase_name} to {target_testcase_name}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to migrate test steps: {str(e)}")
        return False

def renumber_testcases_after_deletion(cursor, project_name: str, module_name: str, deleted_testcase_id_string: str) -> dict:
    """Renumber test cases in a project-module after deletion to fill gaps"""
    try:
        # Sanitize components for matching
        proj_part = sanitize_id_component(project_name)
        mod_part = sanitize_id_component(module_name)
        exact_prefix = f"{proj_part}_{mod_part}_"
        
        print(f"[RENUMBER] Starting renumbering for project-module: {exact_prefix}")
        
        # Get all test cases in this project-module, ordered by TC number
        cursor.execute("""
            SELECT id, name, testcase_id 
            FROM TestCases 
            WHERE testcase_id LIKE ?
            ORDER BY testcase_id
        """, (f"{exact_prefix}%_TC%",))
        
        all_testcases = cursor.fetchall()
        
        # Filter to ensure exact project-module match and extract TC numbers
        valid_testcases = []
        for row in all_testcases:
            tc_id = row[2]  # testcase_id
            if tc_id and tc_id.startswith(exact_prefix):
                # Extract the part after the prefix and before _TC
                remaining = tc_id[len(exact_prefix):]
                match = re.match(r'^(.+)_TC(\d{3})$', remaining)
                if match:
                    tc_name_part = match.group(1)
                    tc_num = int(match.group(2))
                    valid_testcases.append({
                        'id': row[0],
                        'name': row[1],
                        'old_testcase_id': tc_id,
                        'tc_name_part': tc_name_part,
                        'old_tc_num': tc_num
                    })
        
        # Sort by TC number
        valid_testcases.sort(key=lambda x: x['old_tc_num'])
        
        renumber_info = {
            'total_renumbered': 0,
            'renumbering_details': []
        }
        
        # Renumber sequentially starting from TC001
        for i, testcase in enumerate(valid_testcases):
            new_tc_num = i + 1
            old_tc_num = testcase['old_tc_num']
            
            if new_tc_num != old_tc_num:
                # Generate new testcase_id
                new_testcase_id = f"{exact_prefix}{testcase['tc_name_part']}_TC{new_tc_num:03d}"
                old_testcase_id = testcase['old_testcase_id']
                
                print(f"[RENUMBER] {old_testcase_id} -> {new_testcase_id}")
                
                # Update TestCases table
                cursor.execute("""
                    UPDATE TestCases 
                    SET testcase_id = ? 
                    WHERE id = ?
                """, (new_testcase_id, testcase['id']))
                
                # Update test steps table (tc_id column)
                # Get project and module info for generating unique table name
                cursor.execute("""
                    SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                           COALESCE(m.module_name, 'Unknown') as module_name
                    FROM TestCases tc
                    LEFT JOIN Modules m ON tc.module_id = m.id
                    LEFT JOIN Projects p1 ON tc.project_id = p1.id
                    LEFT JOIN Projects p2 ON m.project_id = p2.id
                    WHERE tc.id = ?
                """, (testcase['id'],))

                metadata = cursor.fetchone()
                if metadata:
                    project_name = metadata[0]
                    module_name = metadata[1]
                    old_table_name = generate_unique_table_name(project_name, module_name, testcase['name'])
                else:
                    # Fallback to old naming
                    old_table_name = sanitize_table_name(testcase['name'])

                try:
                    cursor.execute(f"""
                        UPDATE [{old_table_name}]
                        SET tc_id = ?
                        WHERE tc_id = ?
                    """, (new_testcase_id, old_testcase_id))
                    print(f"[RENUMBER] Updated test steps table: {old_table_name}")
                except Exception as e:
                    print(f"[WARNING] Could not update test steps table {old_table_name}: {str(e)}")
                
                # Update selenium_results table
                cursor.execute("""
                    UPDATE selenium_results 
                    SET testcase_id = ? 
                    WHERE testcase_id = ?
                """, (new_testcase_id, old_testcase_id))
                
                renumber_info['total_renumbered'] += 1
                renumber_info['renumbering_details'].append({
                    'testcase_name': testcase['name'],
                    'old_id': old_testcase_id,
                    'new_id': new_testcase_id,
                    'old_number': old_tc_num,
                    'new_number': new_tc_num
                })
        
        print(f"[RENUMBER] Completed renumbering. Total renumbered: {renumber_info['total_renumbered']}")
        return renumber_info
        
    except Exception as e:
        print(f"[ERROR] Error during renumbering: {str(e)}")
        return {'total_renumbered': 0, 'renumbering_details': [], 'error': str(e)}

def cascade_delete_testcase(cursor, testcase_id: int, testcase_name: str, testcase_id_string: str = None) -> dict:
    """Helper function to cascade delete a test case and all its related data (preserving reports)"""
    deletion_info = {
        'testcase_name': testcase_name,
        'test_steps_table_deleted': False,
        'execution_results_preserved': 0
    }
    
    try:
        # Delete test steps table for this test case
        table_name = sanitize_table_name(testcase_name)
        cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")
        deletion_info['test_steps_table_deleted'] = True
        print(f"[CASCADE DELETE] Dropped test steps table: {table_name}")
    except Exception as e:
        print(f"[WARNING] Could not drop table {table_name}: {str(e)}")
    
    # Count execution results but DON'T delete them (preserve reports)
    cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_name = ?", (testcase_name,))
    results_count = cursor.fetchone()[0]
    deletion_info['execution_results_preserved'] += results_count
    
    # Also count by testcase_id if it exists
    if testcase_id_string:
        cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_id = ?", (testcase_id_string,))
        additional_count = cursor.fetchone()[0]
        deletion_info['execution_results_preserved'] += additional_count
    
    print(f"[CASCADE DELETE] Preserving {deletion_info['execution_results_preserved']} execution results/reports for {testcase_name}")
    
    # Delete from TestCases table
    cursor.execute("DELETE FROM TestCases WHERE id = ?", (testcase_id,))
    
    return deletion_info

def create_selenium_results_table():
    """Create selenium_results table if it doesn't exist"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='selenium_results' AND xtype='U')
            CREATE TABLE selenium_results (
                id INT IDENTITY(1,1) PRIMARY KEY,
                testcase_name NVARCHAR(255) NOT NULL,
                projectname NVARCHAR(255),
                modulename NVARCHAR(255),
                testsuitename NVARCHAR(255),
                testcasename NVARCHAR(255),
                status NVARCHAR(20) NOT NULL,
                total_steps INT DEFAULT 0,
                passed_steps INT DEFAULT 0,
                failed_steps INT DEFAULT 0,
                skipped_steps INT DEFAULT 0,
                execution_time NVARCHAR(50),
                start_time DATETIME,
                end_time DATETIME,
                error_message NVARCHAR(MAX),
                step_details NVARCHAR(MAX),
                browser_info NVARCHAR(500),
                created_date DATETIME DEFAULT GETUTCDATE(),
                testcase_id NVARCHAR(255),
                testrun_id NVARCHAR(255),
                result_id NVARCHAR(255)
            )
        """)

        # Add new columns if they don't exist (for existing tables)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'projectname')
            ALTER TABLE selenium_results ADD projectname NVARCHAR(255)
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'modulename')
            ALTER TABLE selenium_results ADD modulename NVARCHAR(255)
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'testsuitename')
            ALTER TABLE selenium_results ADD testsuitename NVARCHAR(255)
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'testcasename')
            ALTER TABLE selenium_results ADD testcasename NVARCHAR(255)
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'testcase_id')
            ALTER TABLE selenium_results ADD testcase_id NVARCHAR(255)
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'testrun_id')
            ALTER TABLE selenium_results ADD testrun_id NVARCHAR(255)
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'result_id')
            ALTER TABLE selenium_results ADD result_id NVARCHAR(255)
        """)

        # Add page column if it doesn't exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'page')
            ALTER TABLE selenium_results ADD page NVARCHAR(255)
        """)

        # Add username column if it doesn't exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'username')
            ALTER TABLE selenium_results ADD username NVARCHAR(255)
        """)

        # Add role column if it doesn't exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'role')
            ALTER TABLE selenium_results ADD role NVARCHAR(50)
        """)

        # Add executor_type column if it doesn't exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'selenium_results' AND COLUMN_NAME = 'executor_type')
            ALTER TABLE selenium_results ADD executor_type NVARCHAR(50)
        """)

        conn.commit()
        conn.close()
        print("[SUCCESS] selenium_results table created/verified")
    except Exception as e:
        print(f"[ERROR] Error creating selenium_results table: {str(e)}")

def create_testcases_table_if_missing(conn=None):
    """Create/upgrade TestCases table for environments where it is not pre-provisioned."""
    owns_conn = conn is None
    try:
        if owns_conn:
            conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TestCases' AND xtype='U')
            CREATE TABLE [dbo].[TestCases] (
                id INT IDENTITY(1,1) PRIMARY KEY,
                name NVARCHAR(255) NOT NULL,
                status NVARCHAR(50) DEFAULT 'Active',
                project_id INT NULL,
                module_id INT NULL,
                suite_type NVARCHAR(100) NULL,
                testcase_id NVARCHAR(255) NULL,
                mapped_excel_file_name NVARCHAR(255) NULL,
                mapped_excel_sheet_name NVARCHAR(255) NULL,
                created_date DATETIME DEFAULT GETUTCDATE(),
                updated_date DATETIME DEFAULT GETUTCDATE()
            )
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'suite_type')
            ALTER TABLE [dbo].[TestCases] ADD suite_type NVARCHAR(100) NULL
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'module_id')
            ALTER TABLE [dbo].[TestCases] ADD module_id INT NULL
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'project_id')
            ALTER TABLE [dbo].[TestCases] ADD project_id INT NULL
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'testcase_id')
            ALTER TABLE [dbo].[TestCases] ADD testcase_id NVARCHAR(255) NULL
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'mapped_excel_file_name')
            ALTER TABLE [dbo].[TestCases] ADD mapped_excel_file_name NVARCHAR(255) NULL
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'mapped_excel_sheet_name')
            ALTER TABLE [dbo].[TestCases] ADD mapped_excel_sheet_name NVARCHAR(255) NULL
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'created_date')
            ALTER TABLE [dbo].[TestCases] ADD created_date DATETIME DEFAULT GETUTCDATE()
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'updated_date')
            ALTER TABLE [dbo].[TestCases] ADD updated_date DATETIME DEFAULT GETUTCDATE()
        """)

        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'IX_TestCases_Name' AND object_id = OBJECT_ID('[dbo].[TestCases]')
            )
            CREATE INDEX IX_TestCases_Name ON [dbo].[TestCases]([name])
        """)

        conn.commit()
        if owns_conn:
            conn.close()
        print("[SUCCESS] TestCases table created/verified")
    except Exception as e:
        if owns_conn and conn:
            conn.close()
        print(f"[ERROR] Error creating TestCases table: {str(e)}")

def create_values_table_if_missing(conn=None):
    """Create/upgrade Values table used for uploaded Excel files."""
    owns_conn = conn is None
    try:
        if owns_conn:
            conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Values' AND xtype='U')
            CREATE TABLE [dbo].[Values] (
                id INT IDENTITY(1,1) PRIMARY KEY,
                file_name NVARCHAR(255) NOT NULL,
                original_name NVARCHAR(255) NOT NULL,
                file_path NVARCHAR(500) NOT NULL,
                file_size BIGINT NULL,
                uploaded_by NVARCHAR(255) NULL,
                uploaded_at DATETIME DEFAULT GETDATE(),
                status NVARCHAR(50) DEFAULT 'Active'
            )
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Values' AND COLUMN_NAME = 'status')
            ALTER TABLE [dbo].[Values] ADD status NVARCHAR(50) DEFAULT 'Active'
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Values' AND COLUMN_NAME = 'uploaded_at')
            ALTER TABLE [dbo].[Values] ADD uploaded_at DATETIME DEFAULT GETDATE()
        """)

        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'IX_Values_UploadedByStatus' AND object_id = OBJECT_ID('[dbo].[Values]')
            )
            CREATE INDEX IX_Values_UploadedByStatus ON [dbo].[Values]([uploaded_by], [status])
        """)

        conn.commit()
        if owns_conn:
            conn.close()
        print("[SUCCESS] Values table created/verified")
    except Exception as e:
        if owns_conn and conn:
            conn.close()
        print(f"[ERROR] Error creating Values table: {str(e)}")

def create_excel_mapping_table_if_missing(conn=None):
    """Create/upgrade ExcelMapping table that maps testcase -> excel file/sheet."""
    owns_conn = conn is None
    try:
        if owns_conn:
            conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='ExcelMapping' AND xtype='U')
            CREATE TABLE [dbo].[ExcelMapping] (
                id INT IDENTITY(1,1) PRIMARY KEY,
                testcase_id INT NOT NULL,
                excel_file_id INT NOT NULL,
                sheet_name NVARCHAR(255) NOT NULL,
                data_sets INT DEFAULT 0,
                created_at DATETIME DEFAULT GETDATE(),
                updated_at DATETIME NULL
            )
        """)

        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ExcelMapping' AND COLUMN_NAME = 'data_sets')
            ALTER TABLE [dbo].[ExcelMapping] ADD data_sets INT DEFAULT 0
        """)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'ExcelMapping' AND COLUMN_NAME = 'updated_at')
            ALTER TABLE [dbo].[ExcelMapping] ADD updated_at DATETIME NULL
        """)

        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'UQ_ExcelMapping_Testcase' AND object_id = OBJECT_ID('[dbo].[ExcelMapping]')
            )
            CREATE UNIQUE INDEX UQ_ExcelMapping_Testcase ON [dbo].[ExcelMapping]([testcase_id])
        """)
        cursor.execute("""
            IF NOT EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = 'IX_ExcelMapping_File' AND object_id = OBJECT_ID('[dbo].[ExcelMapping]')
            )
            CREATE INDEX IX_ExcelMapping_File ON [dbo].[ExcelMapping]([excel_file_id])
        """)

        conn.commit()
        if owns_conn:
            conn.close()
        print("[SUCCESS] ExcelMapping table created/verified")
    except Exception as e:
        if owns_conn and conn:
            conn.close()
        print(f"[ERROR] Error creating ExcelMapping table: {str(e)}")

def ensure_excel_mapping_infrastructure(conn=None):
    """Ensure TestCases/Values/ExcelMapping infra exists for Excel mapping flows."""
    create_testcases_table_if_missing(conn)
    create_values_table_if_missing(conn)
    create_excel_mapping_table_if_missing(conn)

def create_pages_table():
    """Create pages table if it doesn't exist"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='pages' AND xtype='U')
            CREATE TABLE pages (
                id INT IDENTITY(1,1) PRIMARY KEY,
                page_name NVARCHAR(255) NOT NULL,
                object_name NVARCHAR(255) NOT NULL,
                xpath NVARCHAR(1000) NOT NULL,
                created_at DATETIME DEFAULT GETUTCDATE(),
                updated_at DATETIME DEFAULT GETUTCDATE()
            )
            """
        )
        conn.commit()
        conn.close()
        print("[SUCCESS] pages table created/verified")
    except Exception as e:
        print(f"[ERROR] Error creating pages table: {str(e)}")

def create_brd_table_if_not_exists():
    """Create BRD table if it doesn't exist"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='BRD' AND xtype='U')
            CREATE TABLE BRD (
                id INT IDENTITY(1,1) PRIMARY KEY,
                file_name NVARCHAR(255) NOT NULL,
                file_type NVARCHAR(50) NOT NULL,
                original_name NVARCHAR(255) NOT NULL,
                file_path NVARCHAR(500) NOT NULL,
                file_size BIGINT NOT NULL,
                uploaded_by NVARCHAR(255) NOT NULL,
                uploaded_at DATETIME DEFAULT GETDATE(),
                description NVARCHAR(1000) NULL,
                status NVARCHAR(50) DEFAULT 'Active',
                FOREIGN KEY (uploaded_by) REFERENCES Authentication(email) ON DELETE CASCADE
            )
        """)
        
        # Create indexes if they don't exist
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_BRD_FileType')
            CREATE INDEX IX_BRD_FileType ON BRD(file_type)
        """)
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_BRD_UploadedBy')
            CREATE INDEX IX_BRD_UploadedBy ON BRD(uploaded_by)
        """)
        
        conn.commit()
        conn.close()
        print("[SUCCESS] BRD table created/verified")
    except Exception as e:
        print(f"[ERROR] Error creating BRD table: {str(e)}")

def auto_generate_allure_report():
    """Automatically generate Allure report after test execution"""
    try:
        # Get the project root directory (parent of new_backend)
        current_dir = os.getcwd()
        if current_dir.endswith('new_backend'):
            project_root = os.path.dirname(current_dir)
        else:
            project_root = current_dir

        allure_results_path = os.path.join(project_root, 'allure-results-new')
        allure_report_path = os.path.join(project_root, 'allure-report')

        print(f"[ALLURE] Looking for results in: {allure_results_path}")

        # CRITICAL: Clear old allure report to prevent stale data
        if os.path.exists(allure_report_path):
            print(f"[ALLURE_CLEAR] Clearing old allure report: {allure_report_path}")
            try:
                import shutil
                shutil.rmtree(allure_report_path)
                print(f"[ALLURE_CLEAR] Successfully cleared old allure report")
            except Exception as e:
                print(f"[ALLURE_CLEAR] Warning: Could not clear old report: {str(e)}")

        if not os.path.exists(allure_results_path):
            print("[ALLURE] No allure-results-new directory found")
            return False

        # Check if there are any result files
        result_files = [f for f in os.listdir(allure_results_path) if f.endswith('.json')]
        if not result_files:
            print("[ALLURE] No test results available for report generation")
            return False

        print(f"[ALLURE] Found {len(result_files)} result files for auto-generation")

        # Check if report needs regeneration by comparing timestamps
        report_index_path = os.path.join(allure_report_path, 'index.html')
        if os.path.exists(report_index_path):
            report_time = os.path.getmtime(report_index_path)
            latest_result_time = max([os.path.getmtime(os.path.join(allure_results_path, f))
                                    for f in result_files])

            if report_time >= latest_result_time:
                print("[ALLURE] Report is already up-to-date, skipping auto-generation")
                return True

        allure_report_path = os.path.join(project_root, 'allure-report')

        # Clean previous report
        if os.path.exists(allure_report_path):
            shutil.rmtree(allure_report_path)

        # Create report directory
        os.makedirs(allure_report_path, exist_ok=True)

        # Try multiple possible Allure CLI locations
        # Detect OS and use appropriate executable
        import platform
        is_windows = platform.system() == 'Windows'
        print(f"[ALLURE] Detected OS: {platform.system()}, is_windows: {is_windows}")

        if is_windows:
            local_allure_path = os.path.join(project_root, 'allure-2.24.0', 'bin', 'allure.bat')
            possible_allure_commands = [
                local_allure_path,  # Local repo path first
                r'C:\allure\allure-2.24.0\bin\allure.bat',
                r'C:\allure\bin\allure.bat',
                'allure.bat',
                'allure'
            ]
        else:
            # Linux/Unix systems - use executable without .bat extension
            possible_allure_commands = [
                local_allure_path, 
                'allure', # Local repo path first  # Older server path fallback
                '/usr/local/bin/allure',
                '/usr/bin/allure'
                
            ]

        # Debug: Print the local allure path we're trying to use
        print(f"[ALLURE] Local allure path: {local_allure_path}")
        print(f"[ALLURE] Local allure exists: {os.path.exists(local_allure_path)}")

        allure_cli_worked = False

        for allure_cmd in possible_allure_commands:
            try:
                print(f"[ALLURE] Auto-generation trying CLI: {allure_cmd}")
                result = subprocess.run([
                    allure_cmd, 'generate', allure_results_path,
                    '-o', allure_report_path, '--clean'
                ], check=True, capture_output=True, text=True, timeout=30)

                print(f"[SUCCESS] Auto-generated Allure report with: {allure_cmd}")
                allure_cli_worked = True
                break

            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
                print(f"[ALLURE] Auto-generation failed with {allure_cmd}: {str(e)}")
                continue

        if not allure_cli_worked:
            print("[ALLURE] All CLI attempts failed, using HTML fallback for auto-generation")
            # Fall back to simple HTML report
            html_report = generate_html_report(allure_results_path, result_files)
            report_file = os.path.join(allure_report_path, 'index.html')
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(html_report)
            print("[ALLURE] Auto-generated fallback HTML report")

        return True

    except Exception as e:
        print(f"[ERROR] Failed to auto-generate Allure report: {str(e)}")
        return False

def generate_html_report(allure_results_path, result_files):
    """Generate HTML report from JSON results"""
    try:
        # Load all test results
        test_results = []
        for result_file in result_files:
            file_path = os.path.join(allure_results_path, result_file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    result_data = json.load(f)
                    test_results.append(result_data)
            except Exception as e:
                print(f"[WARNING] Could not load result file {result_file}: {e}")
        
        # Calculate summary stats
        total_tests = len(test_results)
        passed_tests = len([r for r in test_results if r.get('status') == 'passed'])
        failed_tests = len([r for r in test_results if r.get('status') == 'failed'])
        
        # Generate HTML
        html_template = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Test Results Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #eee;
        }}
        .summary {{
            display: flex;
            justify-content: space-around;
            margin-bottom: 30px;
            padding: 20px;
            background-color: #f8f9fa;
            border-radius: 6px;
        }}
        .stat {{
            text-align: center;
        }}
        .stat-number {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}
        .stat-label {{
            font-size: 0.9em;
            color: #666;
        }}
        .passed {{ color: #28a745; }}
        .failed {{ color: #dc3545; }}
        .total {{ color: #007bff; }}
        .test-result {{
            margin-bottom: 20px;
            padding: 15px;
            border-radius: 6px;
            border-left: 4px solid #ddd;
        }}
        .test-result.passed {{
            background-color: #d4edda;
            border-left-color: #28a745;
        }}
        .test-result.failed {{
            background-color: #f8d7da;
            border-left-color: #dc3545;
        }}
        .test-name {{
            font-weight: bold;
            font-size: 1.1em;
            margin-bottom: 10px;
        }}
        .test-details {{
            font-size: 0.9em;
            color: #666;
        }}
        .error-details {{
            margin-top: 10px;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.8em;
        }}
        .timestamp {{
            font-size: 0.8em;
            color: #999;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Test Results Report</h1>
            <p class="timestamp">Generated on {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="summary">
            <div class="stat">
                <div class="stat-number total">{total_tests}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat">
                <div class="stat-number passed">{passed_tests}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat">
                <div class="stat-number failed">{failed_tests}</div>
                <div class="stat-label">Failed</div>
            </div>
        </div>
        
        <div class="test-results">
            <h2>Test Details</h2>
"""
        
        # Add individual test results
        for result in test_results:
            status = result.get('status', 'unknown')
            name = result.get('name', 'Unknown Test')
            full_name = result.get('fullName', name)
            
            # Calculate duration
            start_time = result.get('start', 0)
            stop_time = result.get('stop', 0)
            duration = (stop_time - start_time) / 1000 if stop_time > start_time else 0
            
            # Format timestamps
            start_str = datetime.fromtimestamp(start_time / 1000).strftime('%H:%M:%S') if start_time else 'N/A'
            
            html_template += f"""
            <div class="test-result {status}">
                <div class="test-name">{name}</div>
                <div class="test-details">
                    <strong>Full Name:</strong> {full_name}<br>
                    <strong>Status:</strong> {status.upper()}<br>
                    <strong>Duration:</strong> {duration:.2f}s<br>
                    <strong>Start Time:</strong> {start_str}
                </div>
"""
            
            # Add error details if test failed
            if status == 'failed' and result.get('statusDetails'):
                error_msg = result['statusDetails'].get('message', 'No error message')
                html_template += f"""
                <div class="error-details">
                    <strong>Error:</strong><br>
                    {error_msg}
                </div>
"""
            
            html_template += "</div>"
        
        html_template += """
        </div>
    </div>
</body>
</html>
"""
        
        return html_template
        
    except Exception as e:
        print(f"[ERROR] Failed to generate HTML report: {str(e)}")
        return f"<html><body><h1>Error generating report</h1><p>{str(e)}</p></body></html>"

def store_selenium_results(testcase_name, result, user_email=None):
    """Store test execution results in selenium_results table"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure selenium_results table exists
        create_selenium_results_table()

        # HISTORY: Keep execution history - do not delete old results
        print(f"[DB_HISTORY] Storing new execution result for testcase: {testcase_name}")
        # Note: Not deleting old results to maintain execution history

        # Debug: Log what we're about to store
        print(f"[DB_STORE] Storing results for testcase: {testcase_name}")
        print(f"  project_name: '{result.get('project_name', '')}'")
        print(f"  module_name: '{result.get('module_name', '')}'")
        print(f"  suite_type: '{result.get('suite_type', '')}'")
        print(f"  status: '{result.get('status', 'UNKNOWN')}'")
        print(f"  user_email: '{user_email}'")

        # Get current user information from passed parameter
        current_user_email = user_email
        username = ''
        role = ''

        if current_user_email:
            try:
                # Get user details from Authentication table
                user_cursor = conn.cursor()
                user_cursor.execute("""
                    SELECT username, role FROM Authentication
                    WHERE email = ? AND status = 'Approved'
                """, (current_user_email,))
                user_data = user_cursor.fetchone()
                if user_data:
                    username = user_data[0] or ''
                    role = user_data[1] or ''
                    print(f"[DB_STORE] Found user info: username='{username}', role='{role}'")
                else:
                    print(f"[DB_STORE] No user data found for email: {current_user_email}")
                user_cursor.close()
            except Exception as e:
                print(f"[WARNING] Could not retrieve user info for {current_user_email}: {str(e)}")
        else:
            print(f"[DB_STORE] No user_email provided, storing with empty username/role")

        cursor.execute("""
            INSERT INTO selenium_results (
                testcase_name, projectname, modulename, testsuitename, testcasename, status, total_steps, passed_steps,
                failed_steps, skipped_steps, execution_time, start_time, end_time,
                error_message, step_details, browser_info, testcase_id, testrun_id, result_id, username, role, executor_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            testcase_name,
            result.get('project_name', ''),
            result.get('module_name', ''),
            result.get('suite_type', ''),
            testcase_name,  # testcasename is same as testcase_name
            result.get('status', 'UNKNOWN'),
            result.get('total_steps', 0),
            result.get('passed_steps', 0),
            result.get('failed_steps', 0),
            result.get('skipped_steps', 0),
            result.get('execution_time', ''),
            result.get('start_time'),
            result.get('end_time'),
            result.get('error_message', ''),
            json.dumps(result.get('step_results', [])),
            result.get('browser_info', 'Chrome'),
            result.get('testcase_id', ''),
            result.get('testrun_id', ''),
            result.get('result_id', ''),
            username,
            role,
            result.get('executor_type', 'selenium')  # Default to selenium if not specified
        ))
        
        conn.commit()
        conn.close()
        print(f"[SUCCESS] Results stored in selenium_results table for: {testcase_name}")
        
    except Exception as e:
        print(f"[ERROR] Error storing selenium results: {str(e)}")

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'database': 'Ixigo_TestAutomation',
        'server': 'LPT2084-B1',
    })

# Authentication Routes
@app.route('/api/signup', methods=['POST'])
def signup():
    """User registration endpoint"""
    try:
        print(f"[SIGNUP] Starting signup process")
        print(f"[SIGNUP] Request method: {request.method}")
        print(f"[SIGNUP] Request headers: {dict(request.headers)}")
        print(f"[SIGNUP] Request data: {request.data}")
        data = request.get_json()
        print(f"[SIGNUP] Parsed JSON data: {data}")

        if not data or not data.get('username') or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Username, email, and password are required'}), 400

        username = data['username'].strip()
        email = data['email'].strip().lower()
        password = data['password']

        print(f"[SIGNUP] Processing user: {username}, {email}")

        # Basic validation
        if len(username) < 3:
            return jsonify({'error': 'Username must be at least 3 characters long'}), 400
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters long'}), 400
        if '@' not in email:
            return jsonify({'error': 'Invalid email format'}), 400

        print(f"[SIGNUP] Validation passed, getting DB connection")
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure authentication and authorization tables exist before signup
        print(f"[SIGNUP] Ensuring authentication and authorization tables exist")
        create_authentication_table()
        create_functions_table()
        create_function_assignments_table()

        print(f"[SIGNUP] Checking if user exists")
        # Check if user already exists
        cursor.execute("SELECT id FROM Authentication WHERE username = ? OR email = ?", (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            print(f"[SIGNUP] User already exists: {username}, {email}")
            return jsonify({'error': 'Username or email already exists'}), 409

        print(f"[SIGNUP] Hashing password")
        # Hash the password
        password_hash = generate_password_hash(password)
        print(f"[SIGNUP] Password hashed successfully")

        print(f"[SIGNUP] Inserting new user")
        # Insert new user with pending status (as per authorization system requirements)
        cursor.execute("""
            INSERT INTO Authentication (username, email, password_hash, status, role, created_at)
            VALUES (?, ?, ?, 'Pending', NULL, GETDATE())
        """, (username, email, password_hash))

        print(f"[SIGNUP] Committing transaction")
        conn.commit()
        conn.close()

        print(f"[SIGNUP] Signup successful for: {username}, {email}")
        return jsonify({
            'message': 'User registered successfully',
            'username': username,
            'email': email
        }), 201

    except Exception as e:
        print(f"[ERROR] Signup failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        data = request.get_json()

        if not data or not data.get('email') or not data.get('password'):
            return jsonify({'error': 'Email and password are required'}), 400

        email = data['email'].strip().lower()
        password = data['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Find user by email
        cursor.execute("""
            SELECT id, username, email, password_hash, is_active, status, role
            FROM Authentication
            WHERE email = ?
        """, (email,))

        user = cursor.fetchone()

        if not user:
            conn.close()
            return jsonify({'error': 'Invalid email or password'}), 401

        user_id, username, user_email, password_hash, is_active, status, role = user

        # Check if account is active
        if not is_active:
            conn.close()
            return jsonify({'error': 'Account is deactivated'}), 401

        # Verify password
        if not check_password_hash(password_hash, password):
            conn.close()
            return jsonify({'error': 'Invalid email or password'}), 401

        # Update last login time
        cursor.execute("""
            UPDATE Authentication
            SET last_login = GETDATE()
            WHERE id = ?
        """, (user_id,))

        conn.commit()
        conn.close()

        return jsonify({
            'message': 'Login successful',
            'user': {
                'id': user_id,
                'username': username,
                'email': user_email,
                'status': status,
                'role': role,
                'last_login': format_timestamp(datetime.now(pytz.timezone('Asia/Kolkata')))
            }
        }), 200

    except Exception as e:
        print(f"[ERROR] Login failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

# Authorization Routes (Admin Only)
@app.route('/api/users', methods=['GET'])
def get_users():
    """Get all users (admin only)"""
    try:
        # Get current user from session/token (simplified for now)
        # In production, implement proper JWT/session validation
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        # Check if current user is admin
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        user_result = cursor.fetchone()
        if not user_result or user_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Get all users
        cursor.execute("""
            SELECT id, username, email, status, role, created_at, last_login
            FROM Authentication
            ORDER BY created_at DESC
        """)

        users = []
        for row in cursor.fetchall():
            users.append({
                'id': row[0],
                'username': row[1],
                'email': row[2],
                'status': row[3],
                'role': row[4],
                'created_at': format_timestamp(row[5]) if row[5] else None,
                'last_login': format_timestamp(row[6]) if row[6] else None
            })

        conn.close()
        return jsonify({'users': users}), 200

    except Exception as e:
        print(f"[ERROR] Get users failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/users/approve', methods=['PUT'])
def approve_user():
    """Approve user and set role (admin only)"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        role = data.get('role')  # 'User' or 'Admin'

        if not user_id or not role or role not in ['User', 'Admin']:
            return jsonify({'error': 'Valid user_id and role (User/Admin) required'}), 400

        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if current user is admin
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        admin_result = cursor.fetchone()
        if not admin_result or admin_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Update user status and role
        cursor.execute("""
            UPDATE Authentication
            SET status = 'Approved', role = ?
            WHERE id = ?
        """, (role, user_id))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        conn.commit()
        conn.close()

        return jsonify({'message': f'User approved with role: {role}'}), 200

    except Exception as e:
        print(f"[ERROR] Approve user failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/users/reject', methods=['PUT'])
def reject_user():
    """Reject user (admin only)"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')

        if not user_id:
            return jsonify({'error': 'user_id required'}), 400

        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if current user is admin
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        admin_result = cursor.fetchone()
        if not admin_result or admin_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Update user status
        cursor.execute("""
            UPDATE Authentication
            SET status = 'Rejected', role = NULL
            WHERE id = ?
        """, (user_id,))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        conn.commit()
        conn.close()

        return jsonify({'message': 'User rejected successfully'}), 200

    except Exception as e:
        print(f"[ERROR] Reject user failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/users', methods=['POST'])
def create_user():
    """Create a new user (admin only)"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password')
        role = data.get('role', 'User')
        status = data.get('status', 'Pending')

        if not username or not email or not password:
            return jsonify({'error': 'Username, email, and password are required'}), 400

        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if current user is admin
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        admin_result = cursor.fetchone()
        if not admin_result or admin_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Check if user already exists
        cursor.execute("SELECT id FROM Authentication WHERE username = ? OR email = ?", (username, email))
        existing_user = cursor.fetchone()

        if existing_user:
            conn.close()
            return jsonify({'error': 'Username or email already exists'}), 409

        # Hash the password
        password_hash = generate_password_hash(password)

        # Insert new user
        cursor.execute("""
            INSERT INTO Authentication (username, email, password_hash, status, role, created_at)
            VALUES (?, ?, ?, ?, ?, GETDATE())
        """, (username, email, password_hash, status, role))

        user_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        conn.commit()
        conn.close()

        return jsonify({
            'message': 'User created successfully',
            'user': {
                'id': user_id,
                'username': username,
                'email': email,
                'status': status,
                'role': role
            }
        }), 201

    except Exception as e:
        print(f"[ERROR] Create user failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """Update user details (admin only)"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        email = data.get('email', '').strip().lower()
        role = data.get('role')
        status = data.get('status')

        if not username or not email:
            return jsonify({'error': 'Username and email are required'}), 400

        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if current user is admin
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        admin_result = cursor.fetchone()
        if not admin_result or admin_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Check if user exists
        cursor.execute("SELECT username, email FROM Authentication WHERE id = ?", (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        # Check if username/email conflicts with other users
        cursor.execute("SELECT id FROM Authentication WHERE (username = ? OR email = ?) AND id != ?", (username, email, user_id))
        conflict_user = cursor.fetchone()
        if conflict_user:
            conn.close()
            return jsonify({'error': 'Username or email already exists'}), 409

        # Update user
        cursor.execute("""
            UPDATE Authentication
            SET username = ?, email = ?, role = ?, status = ?
            WHERE id = ?
        """, (username, email, role, status, user_id))

        conn.commit()
        conn.close()

        return jsonify({'message': 'User updated successfully'}), 200

    except Exception as e:
        print(f"[ERROR] Update user failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete user (admin only)"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if current user is admin
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        admin_result = cursor.fetchone()
        if not admin_result or admin_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Check if user exists
        cursor.execute("SELECT username FROM Authentication WHERE id = ?", (user_id,))
        user_result = cursor.fetchone()
        if not user_result:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        username = user_result[0]

        # Delete user
        cursor.execute("DELETE FROM Authentication WHERE id = ?", (user_id,))

        # Also delete any function assignments for this user
        cursor.execute("DELETE FROM FunctionAssignments WHERE user_email = (SELECT email FROM Authentication WHERE id = ?)", (user_id,))

        conn.commit()
        conn.close()

        return jsonify({'message': f'User {username} deleted successfully'}), 200

    except Exception as e:
        print(f"[ERROR] Delete user failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/functions', methods=['GET'])
def get_functions():
    """Get all available functions from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, name, description, icon, color
            FROM Functions
            ORDER BY name
        """)

        functions = []
        for row in cursor.fetchall():
            functions.append({
                'id': row[0],
                'name': row[1],
                'description': row[2],
                'icon': row[3],
                'color': row[4]
            })

        conn.close()
        return jsonify({'functions': functions}), 200

    except Exception as e:
        print(f"[ERROR] Get functions failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/assign-function', methods=['POST'])
def assign_function():
    """Assign user to function (admin only)"""
    try:
        data = request.get_json()
        function_name = data.get('function_name')
        user_email = data.get('user_email')

        if not function_name or not user_email:
            return jsonify({'error': 'function_name and user_email required'}), 400

        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if current user is admin
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        admin_result = cursor.fetchone()
        if not admin_result or admin_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Check if user exists and is approved
        cursor.execute("SELECT status FROM Authentication WHERE email = ?", (user_email,))
        user_result = cursor.fetchone()
        if not user_result or user_result[0] != 'Approved':
            conn.close()
            return jsonify({'error': 'User not found or not approved'}), 400

        # Check if assignment already exists
        cursor.execute("""
            SELECT id FROM FunctionAssignments
            WHERE function_name = ? AND user_email = ?
        """, (function_name, user_email))

        if cursor.fetchone():
            conn.close()
            return jsonify({'error': 'User already assigned to this function'}), 409

        # Create assignment
        cursor.execute("""
            INSERT INTO FunctionAssignments (function_name, user_email, assigned_by)
            VALUES (?, ?, ?)
        """, (function_name, user_email, current_user_email))

        conn.commit()
        conn.close()

        return jsonify({'message': f'User {user_email} assigned to {function_name}'}), 201

    except Exception as e:
        print(f"[ERROR] Assign function failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/function-assignments/<function_name>', methods=['GET'])
def get_function_assignments(function_name):
    """Get users assigned to a specific function"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT fa.id, fa.user_email, fa.assigned_by, fa.assigned_on,
                   a.username, a.role
            FROM FunctionAssignments fa
            JOIN Authentication a ON fa.user_email = a.email
            WHERE fa.function_name = ? AND a.status = 'Approved'
            ORDER BY fa.assigned_on DESC
        """, (function_name,))

        assignments = []
        for row in cursor.fetchall():
            assignments.append({
                'id': row[0],
                'user_email': row[1],
                'assigned_by': row[2],
                'assigned_on': format_timestamp(row[3]) if row[3] else None,
                'username': row[4],
                'role': row[5]
            })

        conn.close()
        return jsonify({'assignments': assignments}), 200

    except Exception as e:
        print(f"[ERROR] Get function assignments failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/user-authorization/<function_name>', methods=['GET'])
def check_user_authorization(function_name):
    """Check if current user is authorized for a specific function"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'authorized': False, 'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if user exists and is approved
        cursor.execute("SELECT status, role FROM Authentication WHERE email = ?", (current_user_email,))
        user_result = cursor.fetchone()
        if not user_result:
            conn.close()
            return jsonify({'authorized': False, 'error': 'User not found'}), 404

        user_status, user_role = user_result

        # Check if user is approved
        if user_status != 'Approved':
            conn.close()
            return jsonify({'authorized': False, 'error': 'User not approved'}), 403

        # Admin users have access to all functions
        if user_role == 'Admin':
            conn.close()
            return jsonify({'authorized': True}), 200

        # Check if user is assigned to the specific function
        cursor.execute("""
            SELECT id FROM FunctionAssignments
            WHERE function_name = ? AND user_email = ?
        """, (function_name, current_user_email))

        assignment = cursor.fetchone()
        conn.close()

        authorized = assignment is not None
        return jsonify({'authorized': authorized}), 200

    except Exception as e:
        print(f"[ERROR] Check user authorization failed: {str(e)}")
        return jsonify({'authorized': False, 'error': 'Internal server error'}), 500

@app.route('/api/function-assignments/<int:assignment_id>', methods=['DELETE'])
def remove_function_assignment(assignment_id):
    """Remove user from function assignment (admin only)"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if current user is admin
        cursor.execute("SELECT role FROM Authentication WHERE email = ?", (current_user_email,))
        admin_result = cursor.fetchone()
        if not admin_result or admin_result[0] != 'Admin':
            conn.close()
            return jsonify({'error': 'Admin access required'}), 403

        # Delete assignment
        cursor.execute("DELETE FROM FunctionAssignments WHERE id = ?", (assignment_id,))

        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Assignment not found'}), 404

        conn.commit()
        conn.close()

        return jsonify({'message': 'Assignment removed successfully'}), 200

    except Exception as e:
        print(f"[ERROR] Remove assignment failed: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


# In-memory staging for page objects (not persisted to DB)
PAGE_OBJECTS_STAGING = {}

def ensure_extension_xpaths_table(conn) -> bool:
    """Ensure dbo.ExtensionXpaths and required columns/indexes exist."""
    cursor = conn.cursor()

    if not table_exists(cursor, 'ExtensionXpaths'):
        cursor.execute("""
            CREATE TABLE [dbo].[ExtensionXpaths] (
                id INT IDENTITY(1,1) PRIMARY KEY,
                element_name NVARCHAR(255) NOT NULL,
                xpath NVARCHAR(1000) NOT NULL,
                page_name NVARCHAR(255) NULL,
                created_at DATETIME DEFAULT GETDATE(),
                session_id NVARCHAR(255) NULL
            )
        """)

    cursor.execute("""
        IF COL_LENGTH('dbo.ExtensionXpaths', 'page_url') IS NULL
            ALTER TABLE [dbo].[ExtensionXpaths] ADD page_url NVARCHAR(1000) NULL
    """)

    cursor.execute("""
        IF COL_LENGTH('dbo.ExtensionXpaths', 'page_domain') IS NULL
            ALTER TABLE [dbo].[ExtensionXpaths] ADD page_domain NVARCHAR(255) NULL
    """)

    cursor.execute("""
        IF NOT EXISTS (
            SELECT 1
            FROM sys.indexes
            WHERE name = 'IX_ExtensionXpaths_SessionId'
              AND object_id = OBJECT_ID(N'[dbo].[ExtensionXpaths]')
        )
            CREATE INDEX IX_ExtensionXpaths_SessionId ON [dbo].[ExtensionXpaths](session_id)
    """)

    cursor.execute("""
        IF NOT EXISTS (
            SELECT 1
            FROM sys.indexes
            WHERE name = 'IX_ExtensionXpaths_SessionId_CreatedAt'
              AND object_id = OBJECT_ID(N'[dbo].[ExtensionXpaths]')
        )
            CREATE INDEX IX_ExtensionXpaths_SessionId_CreatedAt ON [dbo].[ExtensionXpaths](session_id, created_at DESC)
    """)

    conn.commit()
    return True

def create_extension_xpaths_table():
    """Create ExtensionXpaths table if it doesn't exist"""
    try:
        conn = get_db_connection()
        ensure_extension_xpaths_table(conn)

        conn.commit()
        conn.close()
        print("[SUCCESS] ExtensionXpaths table created/verified")
    except Exception as e:
        print(f"[ERROR] Error creating ExtensionXpaths table: {str(e)}")

# ExtensionXpaths API endpoints
@app.route('/api/extension-xpaths', methods=['POST'])
def store_extension_xpaths():
    """Store xpaths from extension to database - handles both single and batch xpaths"""
    try:
        print("[DEBUG] /api/extension-xpaths POST endpoint called")
        print(f"[DEBUG] Request method: {request.method}")
        print(f"[DEBUG] Request headers: {dict(request.headers)}")
        print(f"[DEBUG] Request data: {request.data}")
        print(f"[DEBUG] Request data type: {type(request.data)}")
        print(f"[DEBUG] Request data length: {len(request.data) if request.data else 0}")

        data = request.get_json()
        print(f"[DEBUG] Parsed JSON data: {data}")
        print(f"[DEBUG] Data type: {type(data)}")
        print(f"[DEBUG] Data keys: {list(data.keys()) if data and isinstance(data, dict) else 'Not a dict'}")

        # Add more detailed logging
        print(f"[DEBUG] Data keys: {list(data.keys()) if data else 'None'}")
        if data:
            for key, value in data.items():
                print(f"[DEBUG] {key}: {value}")

        if not data:
            print("[ERROR] No data provided in request")
            return jsonify({'error': 'No data provided'}), 400

        # Handle both 'xpath' and 'xpaths' keys for flexibility
        xpaths_data = data.get('xpaths', [])
        print(f"[DEBUG] xpaths_data from 'xpaths' key: {xpaths_data}")

        if not xpaths_data and 'xpath' in data:
            # Single XPath case
            single_xpath = data.get('xpath', '')
            print(f"[DEBUG] Single xpath found: {single_xpath}")
            if single_xpath:
                xpaths_data = [{
                    'element_name': data.get('element_name', 'Captured Element'),
                    'xpath': single_xpath,
                    'page_name': data.get('page_name', 'Unknown Page')
                }]
                print(f"[DEBUG] Created xpaths_data from single xpath: {xpaths_data}")

        session_id = data.get('session_id')
        print(f"[DEBUG] session_id: {session_id}")

        if not xpaths_data:
            print("[WARNING] No xpaths provided in request after processing")
            return jsonify({'error': 'No xpaths provided'}), 400

        print(f"[INFO] Storing {len(xpaths_data)} XPaths to database for session {session_id}")
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_extension_xpaths_table(conn)

        stored_xpaths = []
        for xpath_item in xpaths_data:
            # Handle both dict and string formats
            if isinstance(xpath_item, str):
                element_name = 'Captured Element'
                xpath = xpath_item
                page_name = 'Unknown Page'
                page_url = 'Unknown URL'
                page_domain = 'Unknown Domain'
            else:
                element_name = xpath_item.get('element_name', 'Captured Element')
                xpath = xpath_item.get('xpath', '')
                page_name = xpath_item.get('page_name', 'Unknown Page')
                page_url = xpath_item.get('page_url', 'Unknown URL')
                page_domain = xpath_item.get('page_domain', 'Unknown Domain')

            # Extract element name from xpath if it's a text-based selector
            if xpath and xpath.strip():
                # Check for pattern: //tag[contains(text(), "text")]
                import re
                match = re.search(r'//(\w+)\[contains\(text\(\),\s*"([^"]+)"\)\]', xpath)
                if match:
                    tag_name = match.group(1)
                    text_content = match.group(2)
                    # Use the extracted text as element name if it's meaningful
                    if text_content and len(text_content.strip()) > 0:
                        element_name = text_content.strip()
                        print(f"[DEBUG] Extracted element name from xpath: '{element_name}'")

            if element_name and xpath and xpath.strip():
                print(f"[DEBUG] Storing XPath: {xpath[:100]}... with element_name: '{element_name}'")
                try:
                    # ⚡ Use OUTPUT clause to get inserted data in one query
                    cursor.execute("""
                        DECLARE @NewId INT;
                        INSERT INTO [dbo].[ExtensionXpaths] (element_name, xpath, page_name, page_url, page_domain, session_id)
                        OUTPUT inserted.id, inserted.element_name, inserted.xpath, inserted.page_name, inserted.page_url, inserted.page_domain, inserted.created_at, inserted.session_id
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (element_name, xpath, page_name, page_url, page_domain, session_id))
                    
                    row = cursor.fetchone()
                    if row:
                        stored_xpaths.append({
                            'id': row[0],
                            'element_name': row[1],
                            'xpath': row[2],
                            'page_name': row[3],
                            'page_url': row[4],
                            'page_domain': row[5],
                            'created_at': format_timestamp(row[6]) if row[6] else None,
                            'session_id': row[7]
                        })
                        print(f"[SUCCESS] Stored XPath with ID {row[0]}")
                    else:
                        print(f"[WARNING] Could not get inserted row data")
                except Exception as insert_error:
                    print(f"[ERROR] Failed to store individual xpath: {str(insert_error)}")
                    traceback.print_exc()

        conn.commit()
        conn.close()

        print(f"[SUCCESS] Stored {len(stored_xpaths)} XPaths to database")

        return jsonify({
            'success': True,
            'message': f'Successfully stored {len(stored_xpaths)} xpaths',
            'stored_count': len(stored_xpaths),
            'stored_xpaths': stored_xpaths,
            'session_id': session_id
        }), 201

    except Exception as e:
        print(f"[ERROR] Store extension xpaths failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

        @app.route('/api/testcases/<testcase_name>/mapped-excel/debug', methods=['GET'])
        def get_mapped_excel_debug(testcase_name):
            """Debug endpoint: return mapped file info, file path and sheet names/row counts"""
            try:
                testcase_name = unquote(testcase_name).strip()
                print(f"[DEBUG_EXCEL] Fetching debug info for test case: '{testcase_name}'")
                conn = get_db_connection()
                cursor = conn.cursor()

                # Ensure the mapped_excel_file_name column exists
                cursor.execute("""
                    IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'mapped_excel_file_name')
                    ALTER TABLE TestCases ADD mapped_excel_file_name NVARCHAR(255)
                """)

                cursor.execute("""
                    SELECT id, mapped_excel_file_name
                    FROM TestCases
                    WHERE name = ?
                """, (testcase_name,))
                result = cursor.fetchone()

                # case-insensitive fallback
                if not result:
                    cursor.execute("""
                        SELECT id, mapped_excel_file_name
                        FROM TestCases
                        WHERE LOWER(name) = LOWER(?)
                    """, (testcase_name,))
                    result = cursor.fetchone()

                if not result:
                    conn.close()
                    print(f"[DEBUG_EXCEL] No test case found for '{testcase_name}'")
                    return jsonify({'excelSheetName': '', 'found': False, 'dataSets': 0}), 200

                mapped_file = result[1] or ''
                print(f"[DEBUG_EXCEL] Mapped value for '{testcase_name}': '{mapped_file}'")

                # Try to locate the file record in Values table
                cursor2 = get_db_connection().cursor()
                file_row = None
                try:
                    cursor2.execute("""
                        SELECT id, file_path, original_name FROM [Values]
                        WHERE original_name = ? AND status = 'Active'
                        ORDER BY id DESC
                    """, (mapped_file,))
                    file_row = cursor2.fetchone()
                except Exception as e:
                    print(f"[DEBUG_EXCEL] Error querying Values table: {e}")

                file_id = None
                file_path = None
                sheet_names = []
                sheet_row_counts = {}
                data_sets = 0

                if file_row:
                    file_id = file_row[0]
                    file_path = file_row[1]
                    print(f"[DEBUG_EXCEL] Found Values entry id={file_id}, path={file_path}")
                    try:
                        import pandas as pd
                        if file_path and os.path.exists(file_path):
                            xls = pd.ExcelFile(file_path)
                            sheet_names = xls.sheet_names
                            for s in sheet_names:
                                try:
                                    df = xls.parse(s, header=0)
                                    row_count = len(df)
                                    sheet_row_counts[s] = row_count
                                    data_sets += row_count
                                except Exception as e:
                                    print(f"[DEBUG_EXCEL] Could not parse sheet {s}: {e}")
                        else:
                            print(f"[DEBUG_EXCEL] File path does not exist: {file_path}")
                    except Exception as e:
                        print(f"[DEBUG_EXCEL] Pandas parse error: {e}")

                cursor2.close()
                cursor.close()
                conn.close()

                return jsonify({
                    'excelSheetName': mapped_file,
                    'found': True,
                    'dataSets': data_sets,
                    'file_id': file_id,
                    'file_path': file_path,
                    'sheet_names': sheet_names,
                    'sheet_row_counts': sheet_row_counts
                }), 200

            except Exception as e:
                print(f"[ERROR] Failed to get mapped Excel debug info: {str(e)}")
                import traceback
                traceback.print_exc()
                return jsonify({'error': str(e), 'found': False}), 500

@app.route('/api/extension-xpaths', methods=['GET'])
def get_extension_xpaths():
    """Get extension xpaths from database without deleting anything - with session_id filtering"""
    try:
        session_id = request.args.get('session_id')
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_extension_xpaths_table(conn)

        # Build query with proper session_id filtering (uses index for fast lookup)
        if session_id:
            print(f"[DEBUG] Fetching XPaths for session_id: {session_id}")
            query = """
                SELECT id, element_name, xpath, page_name, page_url, page_domain, created_at, session_id
                FROM [dbo].[ExtensionXpaths]
                WHERE session_id = ?
                ORDER BY created_at ASC
            """
            params = [session_id]
        else:
            print(f"[DEBUG] Fetching all XPaths (no session_id filter)")
            query = """
                SELECT id, element_name, xpath, page_name, page_url, page_domain, created_at, session_id
                FROM [dbo].[ExtensionXpaths]
                ORDER BY created_at DESC
            """
            params = []

        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        xpaths = []
        for row in rows:
            xpaths.append({
                'id': row[0],
                'element_name': row[1],
                'xpath': row[2],
                'page_name': row[3],
                'page_url': row[4],
                'page_domain': row[5],
                'created_at': format_timestamp(row[6]) if row[6] else None,
                'session_id': row[7]
            })

        conn.close()

        print(f"[INFO]  Returning {len(xpaths)} xpaths from database")

        return jsonify({
            'xpaths': xpaths,
            'total_count': len(xpaths)
        }), 200

    except Exception as e:
        print(f"[ERROR] Get extension xpaths failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/extension-xpaths/reset', methods=['POST', 'DELETE'])
def reset_extension_xpaths():
    """Reset/delete extension xpaths - only when user clicks the reset button"""
    try:
        data = request.get_json() if request.method == 'POST' else {}
        session_id = data.get('session_id') if data else request.args.get('session_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_extension_xpaths_table(conn)

        # Delete xpaths based on session_id
        delete_query = "DELETE FROM [dbo].[ExtensionXpaths] WHERE 1=1"
        params = []

        
        if session_id:
            delete_query += " AND session_id = ?"
            params.append(session_id)

        cursor.execute(delete_query, params)
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        print(f"[INFO] Reset: Deleted {deleted_count} xpaths" + 
              (f" for session {session_id}" if session_id else ""))

        return jsonify({
            'success': True,
            'message': f'Successfully deleted {deleted_count} xpaths',
            'deleted_count': deleted_count
        }), 200

    except Exception as e:
        print(f"[ERROR] Reset extension xpaths failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

# NEW SESSION-SPECIFIC ENDPOINT - For fetching XPaths from a specific session
@app.route('/api/extension-xpaths/session/<session_id>', methods=['GET'])
def get_extension_xpaths_by_session(session_id: str):
    """Get extension xpaths for a specific session from database"""
    try:
        print(f"[INFO] Getting XPaths for session: {session_id}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_extension_xpaths_table(conn)

        query = """
            SELECT id, element_name, xpath, page_name, created_at, session_id
            FROM [dbo].[ExtensionXpaths]
            WHERE session_id = ?
            ORDER BY created_at DESC
        """

        cursor.execute(query, (session_id,))

        xpaths = []
        for row in cursor.fetchall():
            xpaths.append({
                'id': row[0],
                'element_name': row[1],
                'xpath': row[2],
                'page_name': row[3],
                'created_at': format_timestamp(row[4]) if row[4] else None,
                'session_id': row[5]
            })

        conn.close()

        print(f"[INFO] Found {len(xpaths)} XPaths for session {session_id}")

        return jsonify({
            'xpaths': xpaths,
            'total_count': len(xpaths),
            'session_id': session_id
        }), 200

    except Exception as e:
        print(f"[ERROR] Get extension xpaths by session failed: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/extension-xpaths/clear', methods=['DELETE'])
def clear_extension_xpaths():
    """Clear extension xpaths from database"""
    try:
        session_id = request.args.get('session_id')

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_extension_xpaths_table(conn)

        query = "DELETE FROM [dbo].[ExtensionXpaths]"
        params = []


        
        if session_id:
            query += " WHERE session_id = ?"
            params.append(session_id)

        

        cursor.execute(query, params)
        deleted_count = cursor.rowcount

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Successfully cleared {deleted_count} xpaths',
            'deleted_count': deleted_count
        }), 200

    except Exception as e:
        print(f"[ERROR] Clear extension xpaths failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pages/staging/<page_name>', methods=['GET', 'POST', 'DELETE'])
def page_objects_staging(page_name: str):
    """
    Staging area for page objects per page_name.
    - GET: return staged rows
    - POST: replace staged rows with provided array of {object_name, xpath}
    - DELETE: clear staged rows
    """
    try:
        normalized = page_name.strip()
        global PAGE_OBJECTS_STAGING
        if request.method == 'GET':
            return jsonify(PAGE_OBJECTS_STAGING.get(normalized, []))
        if request.method == 'POST':
            data = request.get_json() or {}
            objects = data.get('objects', [])
            # ensure array of dicts with the two fields
            cleaned = []
            for o in objects:
                obj = {
                    'object_name': (o.get('object_name') or '').strip(),
                    'xpath': (o.get('xpath') or '').strip()
                }
                cleaned.append(obj)
            PAGE_OBJECTS_STAGING[normalized] = cleaned
            return jsonify({'message': 'staged', 'count': len(cleaned)})
        # DELETE
        PAGE_OBJECTS_STAGING.pop(normalized, None)
        return jsonify({'message': 'cleared'})
    except Exception as e:
        print(f"[ERROR] staging page objects: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Pages API
@app.route('/api/pages', methods=['POST'])
def save_page_objects():
    """Save page objects - delegate to bulk insert for CORS compatibility"""
    return bulk_insert_page_objects()

@app.route('/api/page-names', methods=['GET'])
def get_page_names():
    """Get all page names from pages_master table"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, page_name FROM pages_master ORDER BY page_name")
        rows = cursor.fetchall()
        
        pages = []
        for row in rows:
            pages.append({
                'id': row[0],
                'page_name': row[1]
            })
        
        conn.close()
        return jsonify(pages)
    except Exception as e:
        print(f"[ERROR] Get page names: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/page-names', methods=['POST'])
def create_page_name():
    """Create a new page in pages_master table"""
    try:
        data = request.get_json()
        page_name = data.get('page_name', '').strip()
        
        if not page_name:
            return jsonify({'error': 'Page name is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if page already exists
        cursor.execute("SELECT COUNT(*) FROM pages_master WHERE page_name = ?", (page_name,))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return jsonify({'error': 'Page name already exists'}), 400
        
        # Insert new page
        cursor.execute("INSERT INTO pages_master (page_name) VALUES (?)", (page_name,))
        conn.commit()
        
        # Get the inserted ID
        cursor.execute("SELECT @@IDENTITY")
        page_id = cursor.fetchone()[0]
        
        conn.close()
        return jsonify({'id': page_id, 'page_name': page_name, 'message': 'Page created successfully'})
    except Exception as e:
        print(f"[ERROR] Create page name: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/page-names/<int:page_id>', methods=['PUT'])
def update_page_name(page_id):
    """Update a page name in pages_master table"""
    try:
        data = request.get_json()
        page_name = data.get('page_name', '').strip()
        
        if not page_name:
            return jsonify({'error': 'Page name is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if page exists
        cursor.execute("SELECT page_name FROM pages_master WHERE id = ?", (page_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Page not found'}), 404
        
        old_name = row[0]
        
        # Check if new name already exists (excluding current page)
        cursor.execute("SELECT COUNT(*) FROM pages_master WHERE page_name = ? AND id != ?", (page_name, page_id))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return jsonify({'error': 'Page name already exists'}), 400
        
        # Update page name
        cursor.execute("UPDATE pages_master SET page_name = ? WHERE id = ?", (page_name, page_id))
        
        # Also update all objects in pages table that reference this page
        cursor.execute("UPDATE pages SET page_name = ? WHERE page_name = ?", (page_name, old_name))
        
        conn.commit()
        conn.close()
        
        return jsonify({'id': page_id, 'page_name': page_name, 'message': 'Page updated successfully'})
    except Exception as e:
        print(f"[ERROR] Update page name: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/page-names/<int:page_id>', methods=['DELETE'])
def delete_page_name(page_id):
    """Delete a page and all its objects"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get page name first
        cursor.execute("SELECT page_name FROM pages_master WHERE id = ?", (page_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Page not found'}), 404
        
        page_name = row[0]
        
        # Delete all objects for this page
        cursor.execute("DELETE FROM pages WHERE page_name = ?", (page_name,))
        objects_deleted = cursor.rowcount
        
        # Delete the page itself
        cursor.execute("DELETE FROM pages_master WHERE id = ?", (page_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': f'Page "{page_name}" and {objects_deleted} objects deleted successfully'
        })
    except Exception as e:
        print(f"[ERROR] Delete page name: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pages/<page_name>', methods=['GET'])
def get_page_objects(page_name):
    """Get all objects for a specific page"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, object_name, xpath 
            FROM pages 
            WHERE page_name = ? 
            ORDER BY object_name
        """, (page_name,))
        
        rows = cursor.fetchall()
        objects = []
        for row in rows:
            objects.append({
                'id': row[0],
                'object_name': row[1],
                'xpath': row[2]
            })
        
        conn.close()
        return jsonify(objects)
    except Exception as e:
        print(f"[ERROR] Get page objects: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pages/bulk', methods=['POST'])
def bulk_insert_page_objects():
    """Bulk insert/update objects for a page with auto-update of affected test steps"""

    try:
        data = request.get_json()
        page_name = data.get('page_name', '').strip()
        objects = data.get('objects', [])

        if not page_name:
            return jsonify({'error': 'Page name is required'}), 400

        if not objects:
            return jsonify({'error': 'Objects array is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Validate objects and track changes for auto-update
        valid_objects = []
        updated_objects = []
        inserted_objects = []

        for obj in objects:
            object_name = obj.get('object_name', '').strip()
            xpath = obj.get('xpath', '').strip()
            if object_name and xpath:
                # Check if object already exists
                cursor.execute("""
                    SELECT id, xpath FROM pages
                    WHERE page_name = ? AND object_name = ?
                """, (page_name, object_name))

                existing = cursor.fetchone()
                if existing:
                    existing_id, old_xpath = existing
                    if old_xpath != xpath:
                        # Update existing object
                        cursor.execute("""
                            UPDATE pages
                            SET xpath = ?, updated_at = GETUTCDATE()
                            WHERE id = ?
                        """, (xpath, existing_id))
                        updated_objects.append({
                            'id': existing_id,
                            'object_name': object_name,
                            'old_xpath': old_xpath,
                            'new_xpath': xpath
                        })
                else:
                    # Insert new object
                    valid_objects.append((page_name, object_name, xpath))
                    inserted_objects.append({
                        'object_name': object_name,
                        'xpath': xpath
                    })

        # Insert new objects
        if valid_objects:
            cursor.executemany("""
                INSERT INTO pages (page_name, object_name, xpath)
                VALUES (?, ?, ?)
            """, valid_objects)

        # AUTO-UPDATE AFFECTED TEST STEPS for updated objects
        total_updated_steps = 0
        affected_testcases = []

        if updated_objects:
            print(f"[AUTO-UPDATE] Processing {len(updated_objects)} updated objects for auto-update")

            for updated_obj in updated_objects:
                object_name = updated_obj['object_name']
                new_xpath = updated_obj['new_xpath']
                old_xpath = updated_obj['old_xpath']

                try:
                    # Get all test cases and their table names
                    cursor.execute("""
                        SELECT tc.name, tc.testcase_id,
                               COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                               COALESCE(m.module_name, 'Unknown') as module_name
                        FROM TestCases tc
                        LEFT JOIN Modules m ON tc.module_id = m.id
                        LEFT JOIN Projects p1 ON tc.project_id = p1.id
                        LEFT JOIN Projects p2 ON m.project_id = p2.id
                    """)

                    testcases = cursor.fetchall()

                    for tc_row in testcases:
                        tc_name = tc_row[0]
                        tc_id = tc_row[1]
                        project_name = tc_row[2]
                        module_name = tc_row[3]

                        # Generate table name for this test case
                        table_name = generate_unique_table_name(project_name, module_name, tc_name)

                        try:
                            # Check if table exists and has steps with this element name
                            cursor.execute(f"""
                                SELECT COUNT(*) FROM [{table_name}]
                                WHERE element_name = ?
                            """, (object_name,))

                            count_result = cursor.fetchone()
                            if count_result and count_result[0] > 0:
                                steps_count = count_result[0]

                                # Update XPath for all matching steps
                                cursor.execute(f"""
                                    UPDATE [{table_name}]
                                    SET xpath = ?
                                    WHERE element_name = ?
                                """, (new_xpath, object_name))

                                total_updated_steps += steps_count
                                affected_testcases.append({
                                    'testcase_name': tc_name,
                                    'table_name': table_name,
                                    'steps_updated': steps_count,
                                    'object_name': object_name
                                })

                                print(f"[AUTO-UPDATE] Updated {steps_count} steps in {tc_name} for object {object_name}")

                        except Exception as table_error:
                            print(f"[WARNING] Could not update test steps in table {table_name}: {str(table_error)}")
                            continue

                except Exception as query_error:
                    print(f"[ERROR] Failed to query test cases for auto-update: {str(query_error)}")

        conn.commit()
        conn.close()

        response_data = {
            'message': f'Successfully processed {len(valid_objects)} insertions and {len(updated_objects)} updates for page "{page_name}"',
            'inserted_count': len(valid_objects),
            'updated_count': len(updated_objects),
            'auto_updated_steps': total_updated_steps,
            'affected_testcases': affected_testcases
        }

        if updated_objects:
            response_data['message'] += f'. Auto-updated {total_updated_steps} test steps across {len(affected_testcases)} test cases.'

        print(f"[BULK SAVE] Inserted: {len(valid_objects)}, Updated: {len(updated_objects)}, Auto-updated steps: {total_updated_steps}")

        return jsonify(response_data)
    except Exception as e:
        print(f"[ERROR] Bulk insert/update page objects: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pages/<int:object_id>', methods=['PUT'])
def update_page_object(object_id):
    """Update a specific page object with timestamp tracking and auto-update affected test steps"""

    conn = None
    try:
        data = request.get_json()
        object_name = data.get('object_name', '').strip()
        xpath = data.get('xpath', '').strip()

        if not object_name or not xpath:
            return jsonify({'error': 'Object name and xpath are required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if object exists and get old values
        cursor.execute("SELECT object_name, xpath, page_name FROM pages WHERE id = ?", (object_id,))
        result = cursor.fetchone()
        if not result:
            return jsonify({'error': 'Object not found'}), 404

        old_object_name = result[0]
        old_xpath = result[1]
        page_name = result[2]

        # Update object with timestamp
        cursor.execute("""
            UPDATE pages
            SET object_name = ?, xpath = ?, updated_at = GETUTCDATE()
            WHERE id = ?
        """, (object_name, xpath, object_id))

        # AUTO-UPDATE AFFECTED TEST STEPS
        # Find all test steps that use the old object name and update their XPath
        updated_steps_count = 0
        updated_testcases = []

        try:
            # Get all test cases and their table names
            cursor.execute("""
                SELECT tc.name, tc.testcase_id,
                       COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
            """)

            testcases = cursor.fetchall()
            print(f"[AUTO-UPDATE] Found {len(testcases)} test cases to check for updates")

            for tc_row in testcases:
                tc_name = tc_row[0]
                tc_id = tc_row[1]
                project_name = tc_row[2]
                module_name = tc_row[3]

                # Generate table name for this test case
                table_name = generate_unique_table_name(project_name, module_name, tc_name)

                try:
                    # Check if table exists and has steps with the old element name
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM [{table_name}]
                        WHERE element_name = ?
                    """, (old_object_name,))

                    count_result = cursor.fetchone()
                    if count_result and count_result[0] > 0:
                        steps_count = count_result[0]

                        # Update XPath for all matching steps
                        cursor.execute(f"""
                            UPDATE [{table_name}]
                            SET xpath = ?
                            WHERE element_name = ?
                        """, (xpath, old_object_name))

                        updated_steps_count += steps_count
                        updated_testcases.append({
                            'testcase_name': tc_name,
                            'table_name': table_name,
                            'steps_updated': steps_count
                        })

                        print(f"[AUTO-UPDATE] Updated {steps_count} steps in {tc_name} (table: {table_name})")

                except Exception as table_error:
                    print(f"[WARNING] Could not update test steps in table {table_name}: {str(table_error)}")
                    continue

        except Exception as query_error:
            print(f"[ERROR] Failed to query test cases for auto-update: {str(query_error)}")
            # Don't fail the entire operation if auto-update fails
            updated_steps_count = 0
            updated_testcases = []

        conn.commit()

        try:
            print(f"[AUDIT] Updated object {object_id}: {page_name}.{old_object_name} -> {object_name}")
            print(f"[AUDIT] XPath changed: {old_xpath[:60]}... -> {xpath[:60]}...")
            print(f"[AUTO-UPDATE] Updated {updated_steps_count} test steps across {len(updated_testcases)} test cases")
        except Exception as encode_err:
            print(f"[AUDIT] Updated object {object_id} (encoding issues in display)")

        return jsonify({
            'id': object_id,
            'object_name': object_name,
            'xpath': xpath,
            'page_name': page_name,
            'old_xpath': old_xpath,
            'old_object_name': old_object_name,
            'updated_at': format_timestamp(datetime.utcnow()),
            'auto_updated_steps': updated_steps_count,
            'affected_testcases': updated_testcases,
            'message': f'Object updated successfully. Auto-updated {updated_steps_count} test steps.'
        })
    except Exception as e:
        print(f"[ERROR] Update page object: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        # Ensure connection is always closed
        if conn:
            try:
                conn.close()
            except Exception as close_error:
                print(f"[WARNING] Error closing database connection: {str(close_error)}")

# ===== NEW ENDPOINT: Get page object changes =====
@app.route('/api/page-objects/changes', methods=['GET'])
def get_page_objects_changes():
    """
    Get page objects that were modified after a specific timestamp.
    This enables automatic XPath refresh in test steps.
    
    Query parameter: since_timestamp (ISO format, e.g., 2024-01-15T10:30:00)
    """
    try:
        since_timestamp = request.args.get('since_timestamp', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure updated_at and created_at columns exist
        cursor.execute("""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pages' AND COLUMN_NAME = 'updated_at'
            )
            BEGIN
                ALTER TABLE pages ADD updated_at DATETIME DEFAULT GETUTCDATE();
            END
        """)
        cursor.execute("""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'pages' AND COLUMN_NAME = 'created_at'
            )
            BEGIN
                ALTER TABLE pages ADD created_at DATETIME DEFAULT GETUTCDATE();
            END
        """)
        conn.commit()

        # Query objects modified after timestamp
        if since_timestamp:
            try:
                # Parse ISO format timestamp
                sync_time = datetime.fromisoformat(since_timestamp.replace('Z', '+00:00'))
                cursor.execute("""
                    SELECT 
                        id,
                        page_name,
                        object_name,
                        xpath,
                        updated_at
                    FROM pages
                    WHERE updated_at > ? OR created_at > ?
                    ORDER BY updated_at DESC
                """, (sync_time, sync_time))
            except ValueError:
                print(f"[WARNING] Invalid timestamp format: {since_timestamp}")
                cursor.execute("SELECT id, page_name, object_name, xpath, updated_at FROM pages LIMIT 0")
        else:
            # If no timestamp, get recently modified (last 1 hour)
            cursor.execute("""
                SELECT 
                    id,
                    page_name,
                    object_name,
                    xpath,
                    updated_at
                FROM pages
                WHERE updated_at > DATEADD(HOUR, -1, GETUTCDATE())
                OR created_at > DATEADD(HOUR, -1, GETUTCDATE())
                ORDER BY updated_at DESC
            """)

        rows = cursor.fetchall()
        conn.close()

        changes = []
        for row in rows:
            changes.append({
                'id': row[0],
                'page_name': row[1],
                'object_name': row[2],
                'xpath': row[3],
                'updated_at': format_timestamp(row[4]) if row[4] else None,
            })

        print(f"[API] Found {len(changes)} page object changes since {since_timestamp}")

        return jsonify({
            'timestamp': format_timestamp(datetime.utcnow()),
            'changes': changes,
            'total_changes': len(changes)
        })

    except Exception as e:
        print(f"[ERROR] Get page object changes: {str(e)}")
        return jsonify({'error': str(e), 'changes': []}), 500


@app.route('/api/pages/<int:object_id>', methods=['DELETE'])
def delete_page_object(object_id):
    """Delete a specific page object"""

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if object exists
        cursor.execute("SELECT object_name FROM pages WHERE id = ?", (object_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Object not found'}), 404

        object_name = row[0];

        # Delete object
        cursor.execute("DELETE FROM pages WHERE id = ?", (object_id,))
        conn.commit()
        conn.close();

        return jsonify({'message': f'Object "{object_name}" deleted successfully'})
    except Exception as e:
        print(f"[ERROR] Delete page object: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/page-objects/dropdown', methods=['GET'])
def get_page_objects_for_dropdown():
    """Get all page objects formatted for dropdown usage in test steps"""

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all page objects grouped by page
        cursor.execute("""
            SELECT page_name, object_name, xpath
            FROM pages
            ORDER BY page_name, object_name
        """)

        rows = cursor.fetchall()

        # Group objects by page
        pages_data = {}
        all_objects = []

        for row in rows:
            page_name = row[0]
            object_name = row[1]
            xpath = row[2]

            # Add to all objects list for flat dropdown
            all_objects.append({
                'page_name': page_name,
                'object_name': object_name,
                'xpath': xpath,
                'display_name': f"{page_name} - {object_name}"
            })

            # Group by page for hierarchical dropdown
            if page_name not in pages_data:
                pages_data[page_name] = []

            pages_data[page_name].append({
                'object_name': object_name,
                'xpath': xpath
            })

        conn.close()

        return jsonify({
            'all_objects': all_objects,
            'pages_data': pages_data
        })
    except Exception as e:
        print(f"[ERROR] Get page objects for dropdown: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Projects API
@app.route('/api/projects', methods=['GET'])
def get_projects():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create Projects table if not exists
        cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name='Projects' AND xtype='U'")
        table_exists = cursor.fetchone()[0] > 0
       
        if not table_exists:
            cursor.execute("""
                CREATE TABLE Projects (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    name NVARCHAR(255) NOT NULL,
                    description NVARCHAR(500),
                    status NVARCHAR(50) DEFAULT 'Active',
                    created_date DATETIME DEFAULT GETUTCDATE()
                )
            """)
            conn.commit()
        
        cursor.execute("SELECT id, name, description, status, created_date FROM Projects")
        projects = []
        for row in cursor.fetchall():
            projects.append({
                'id': row[0],
                'name': row[1],
                'description': row[2],
                'status': row[3],
                'created_date': format_timestamp(row[4]) if row[4] else None
            })
        
        conn.close()
        return jsonify(projects)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects', methods=['POST'])
def create_project():
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'error': 'Project name is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if project with same name already exists
        cursor.execute("SELECT COUNT(*) FROM Projects WHERE name = ?", (data['name'],))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return jsonify({'error': 'Project with this name already exists'}), 409
        
        cursor.execute("""
            INSERT INTO Projects (name, description, status)
            VALUES (?, ?, ?)
        """, (
            data['name'],
            data.get('description', ''),
            data.get('status', 'Active')
        ))
        
        project_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
        conn.commit()
        
        # Return the created project
        cursor.execute("SELECT id, name, description, status, created_date FROM Projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        project = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'status': row[3],
            'created_date': format_timestamp(row[4]) if row[4] else None
        }
        
        conn.close()
        return jsonify(project), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<int:project_id>', methods=['PUT'])
def update_project(project_id):
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'error': 'Project name is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if project exists
        cursor.execute("SELECT COUNT(*) FROM Projects WHERE id = ?", (project_id,))
        if cursor.fetchone()[0] == 0:
            conn.close()
            return jsonify({'error': 'Project not found'}), 404
        
        # Check if another project with same name exists (excluding current)
        cursor.execute("SELECT COUNT(*) FROM Projects WHERE name = ? AND id != ?", (data['name'], project_id))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return jsonify({'error': 'Another project with this name already exists'}), 409
        
        cursor.execute("""
            UPDATE Projects 
            SET name = ?, description = ?
            WHERE id = ?
        """, (
            data['name'],
            data.get('description', ''),
            project_id
        ))
        
        conn.commit()
        
        # Return the updated project
        cursor.execute("SELECT id, name, description, status, created_date FROM Projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        project = {
            'id': row[0],
            'name': row[1],
            'description': row[2],
            'status': row[3],
            'created_date': format_timestamp(row[4]) if row[4] else None
        }
        
        conn.close()
        return jsonify(project)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/projects/<int:project_id>', methods=['DELETE'])
def delete_project(project_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if project exists and get project name
        cursor.execute("SELECT name FROM Projects WHERE id = ?", (project_id,))
        project_result = cursor.fetchone()
        if not project_result:
            conn.close()
            return jsonify({'error': 'Project not found'}), 404
        
        project_name = project_result[0]
        print(f"[CASCADE DELETE] Starting cascade deletion for project: {project_name} (ID: {project_id})")
        
        deletion_summary = {
            'project_name': project_name,
            'modules_deleted': 0,
            'test_suites_deleted': 0,
            'test_cases_deleted': 0,
            'test_steps_tables_deleted': 0,
            'execution_results_preserved': 0
        }
        
        # Check if Modules table exists
        cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name='Modules' AND xtype='U'")
        modules_table_exists = cursor.fetchone()[0] > 0
        
        if modules_table_exists:
            # Get all modules in this project
            cursor.execute("SELECT id, module_name FROM Modules WHERE project_id = ?", (project_id,))
            modules = cursor.fetchall()
            
            for module_id, module_name in modules:
                print(f"[CASCADE DELETE] Processing module: {module_name} (ID: {module_id})")
                
                # Check if TestSuites table exists
                cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name='TestSuites' AND xtype='U'")
                test_suites_table_exists = cursor.fetchone()[0] > 0
                
                if test_suites_table_exists:
                    # Get all test suites in this module
                    cursor.execute("SELECT id, suite_name FROM TestSuites WHERE module_id = ?", (module_id,))
                    test_suites = cursor.fetchall()
                    
                    for suite_id, suite_name in test_suites:
                        print(f"[CASCADE DELETE] Processing test suite: {suite_name} (ID: {suite_id})")
                        deletion_summary['test_suites_deleted'] += 1
                    
                    # Delete all test suites in this module
                    cursor.execute("DELETE FROM TestSuites WHERE module_id = ?", (module_id,))
                else:
                    print(f"[INFO] TestSuites table does not exist, skipping test suite deletion")
                
                deletion_summary['modules_deleted'] += 1
        else:
            print(f"[INFO] Modules table does not exist, skipping module deletion")
        
        # Check if TestCases table exists
        cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name='TestCases' AND xtype='U'")
        test_cases_table_exists = cursor.fetchone()[0] > 0
        
        if test_cases_table_exists:
            # Get all test cases in this project
            cursor.execute("SELECT id, name, testcase_id FROM TestCases WHERE project_id = ?", (project_id,))
            test_cases = cursor.fetchall()
            
            for testcase_id, testcase_name, testcase_id_string in test_cases:
                print(f"[CASCADE DELETE] Processing test case: {testcase_name} (ID: {testcase_id})")
                
                # Delete test steps table for this test case
                # Get project and module info for generating unique table name
                cursor.execute("""
                    SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                           COALESCE(m.module_name, 'Unknown') as module_name
                    FROM TestCases tc
                    LEFT JOIN Modules m ON tc.module_id = m.id
                    LEFT JOIN Projects p1 ON tc.project_id = p1.id
                    LEFT JOIN Projects p2 ON m.project_id = p2.id
                    WHERE tc.id = ?
                """, (testcase_id,))

                metadata = cursor.fetchone()
                if metadata:
                    project_name = metadata[0]
                    module_name = metadata[1]
                    table_name = generate_unique_table_name(project_name, module_name, testcase_name)
                else:
                    # Fallback to old naming
                    table_name = sanitize_table_name(testcase_name)

                try:
                    cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")
                    deletion_summary['test_steps_tables_deleted'] += 1
                    print(f"[CASCADE DELETE] Dropped test steps table: {table_name}")
                except Exception as e:
                    print(f"[WARNING] Could not drop table {table_name}: {str(e)}")
                
                # Count execution results but DON'T delete them (preserve reports)
                try:
                    cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_name = ?", (testcase_name,))
                    results_count = cursor.fetchone()[0]
                    deletion_summary['execution_results_preserved'] += results_count
                    
                    # Also count by testcase_id if it exists
                    if testcase_id_string:
                        cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_id = ?", (testcase_id_string,))
                        additional_count = cursor.fetchone()[0]
                        deletion_summary['execution_results_preserved'] += additional_count
                    
                    print(f"[CASCADE DELETE] Preserving {results_count} execution results/reports for {testcase_name}")
                except Exception as e:
                    print(f"[WARNING] Could not count execution results: {str(e)}")
                
                deletion_summary['test_cases_deleted'] += 1
            
            # Delete all test cases in this project
            cursor.execute("DELETE FROM TestCases WHERE project_id = ?", (project_id,))
        else:
            print(f"[INFO] TestCases table does not exist, skipping test case deletion")
        
        # Delete all modules in this project (if table exists)
        if modules_table_exists:
            cursor.execute("DELETE FROM Modules WHERE project_id = ?", (project_id,))
        
        # Finally, delete the project itself
        cursor.execute("DELETE FROM Projects WHERE id = ?", (project_id,))
        
        conn.commit()
        conn.close()
        
        print(f"[CASCADE DELETE SUCCESS] Project '{project_name}' and related data processed:")
        print(f"  - Modules: {deletion_summary['modules_deleted']} deleted")
        print(f"  - Test Suites: {deletion_summary['test_suites_deleted']} deleted")
        print(f"  - Test Cases: {deletion_summary['test_cases_deleted']} deleted")
        print(f"  - Test Steps Tables: {deletion_summary['test_steps_tables_deleted']} deleted")
        print(f"  - Execution Results: {deletion_summary['execution_results_preserved']} preserved (reports kept)")
        
        return jsonify({
            'message': 'Project and all related data deleted successfully',
            'deletion_summary': deletion_summary
        })
    except Exception as e:
        print(f"[CASCADE DELETE ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

# Modules API
@app.route('/api/modules', methods=['GET'])
def get_modules():
    try:
        project_id = request.args.get('project_id')
        if not project_id:
            return jsonify({'error': 'project_id parameter is required'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create Modules table if not exists
        cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name='Modules' AND xtype='U'")
        table_exists = cursor.fetchone()[0] > 0
       
        if not table_exists:
            cursor.execute("""
                CREATE TABLE Modules (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    project_id INT,
                    module_name NVARCHAR(255) NOT NULL,
                    description NVARCHAR(500),
                    created_at DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (project_id) REFERENCES Projects(id)
                )
            """)
            conn.commit()
        
        cursor.execute("SELECT id, module_name, description, created_at FROM Modules WHERE project_id = ?", (project_id,))
        modules = []
        for row in cursor.fetchall():
            modules.append({
                'id': row[0],
                'module_name': row[1],
                'description': row[2],
                'created_at': format_timestamp(row[3]) if row[3] else None
            })
        
        conn.close()
        return jsonify({'modules': modules})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/modules', methods=['POST'])
def create_module():
    try:
        data = request.get_json()
        if not data or not data.get('name') or not data.get('project_id'):
            return jsonify({'error': 'Module name and project_id are required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if project exists
        cursor.execute("SELECT COUNT(*) FROM Projects WHERE id = ?", (data['project_id'],))
        if cursor.fetchone()[0] == 0:
            conn.close()
            return jsonify({'error': 'Project not found'}), 404
        
        # Check if module with same name already exists in this project
        cursor.execute("SELECT COUNT(*) FROM Modules WHERE module_name = ? AND project_id = ?", 
                      (data['name'], data['project_id']))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return jsonify({'error': 'Module with this name already exists in the project'}), 409
        
        cursor.execute("""
            INSERT INTO Modules (module_name, description, project_id)
            VALUES (?, ?, ?)
        """, (
            data['name'],
            data.get('description', ''),
            data['project_id']
        ))
        
        module_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
        conn.commit()
        
        # Return the created module
        cursor.execute("SELECT id, module_name, description, created_at FROM Modules WHERE id = ?", (module_id,))
        row = cursor.fetchone()
        module = {
            'id': row[0],
            'module_name': row[1],
            'description': row[2],
            'created_at': format_timestamp(row[3]) if row[3] else None
        }
        
        conn.close()
        return jsonify(module), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/modules/<int:module_id>', methods=['PUT'])
def update_module(module_id):
    try:
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'error': 'Module name is required'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if module exists
        cursor.execute("SELECT project_id FROM Modules WHERE id = ?", (module_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return jsonify({'error': 'Module not found'}), 404
        
        project_id = result[0]
        
        # Check if another module with same name exists in same project (excluding current)
        cursor.execute("SELECT COUNT(*) FROM Modules WHERE module_name = ? AND project_id = ? AND id != ?", 
                      (data['name'], project_id, module_id))
        if cursor.fetchone()[0] > 0:
            conn.close()
            return jsonify({'error': 'Another module with this name already exists in the project'}), 409
        
        cursor.execute("""
            UPDATE Modules 
            SET module_name = ?, description = ?
            WHERE id = ?
        """, (
            data['name'],
            data.get('description', ''),
            module_id
        ))
        
        conn.commit()
        
        # Return the updated module
        cursor.execute("SELECT id, module_name, description, created_at FROM Modules WHERE id = ?", (module_id,))
        row = cursor.fetchone()
        module = {
            'id': row[0],
            'module_name': row[1],
            'description': row[2],
            'created_at': format_timestamp(row[3]) if row[3] else None
        }
        
        conn.close()
        return jsonify(module)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/modules/<int:module_id>', methods=['DELETE'])
def delete_module(module_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if module exists and get module name
        cursor.execute("SELECT module_name, project_id FROM Modules WHERE id = ?", (module_id,))
        module_result = cursor.fetchone()
        if not module_result:
            conn.close()
            return jsonify({'error': 'Module not found'}), 404
        
        module_name, project_id = module_result
        print(f"[CASCADE DELETE] Starting cascade deletion for module: {module_name} (ID: {module_id})")
        
        deletion_summary = {
            'module_name': module_name,
            'test_suites_deleted': 0,
            'test_cases_deleted': 0,
            'test_steps_tables_deleted': 0,
            'execution_results_preserved': 0
        }
        
        # Check if TestSuites table exists
        cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name='TestSuites' AND xtype='U'")
        test_suites_table_exists = cursor.fetchone()[0] > 0
        
        if test_suites_table_exists:
            # Get all test suites in this module
            cursor.execute("SELECT id, suite_name FROM TestSuites WHERE module_id = ?", (module_id,))
            test_suites = cursor.fetchall()
            
            for suite_id, suite_name in test_suites:
                print(f"[CASCADE DELETE] Processing test suite: {suite_name} (ID: {suite_id})")
                deletion_summary['test_suites_deleted'] += 1
            
            # Delete all test suites in this module
            cursor.execute("DELETE FROM TestSuites WHERE module_id = ?", (module_id,))
        else:
            print(f"[INFO] TestSuites table does not exist, skipping test suite deletion")
        
        # Check if TestCases table exists
        cursor.execute("SELECT COUNT(*) FROM sysobjects WHERE name='TestCases' AND xtype='U'")
        test_cases_table_exists = cursor.fetchone()[0] > 0
        
        if test_cases_table_exists:
            # Get all test cases that might be related to this module (check both module_id and project_id)
            # First check if TestCases table has module_id column
            cursor.execute("""
                SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS 
                WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'module_id'
            """)
            has_module_id = cursor.fetchone() is not None
            
            if has_module_id:
                # If TestCases has module_id, use it
                cursor.execute("SELECT id, name, testcase_id FROM TestCases WHERE module_id = ?", (module_id,))
            else:
                # Otherwise, we need to find test cases by project_id (less precise but safer)
                cursor.execute("SELECT id, name, testcase_id FROM TestCases WHERE project_id = ?", (project_id,))
            
            test_cases = cursor.fetchall()
            
            for testcase_id, testcase_name, testcase_id_string in test_cases:
                print(f"[CASCADE DELETE] Processing test case: {testcase_name} (ID: {testcase_id})")
                
                # Delete test steps table for this test case
                # Get project and module info to generate correct table name
                cursor.execute("""
                    SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                           COALESCE(m.module_name, 'Unknown') as module_name
                    FROM TestCases tc
                    LEFT JOIN Modules m ON tc.module_id = m.id
                    LEFT JOIN Projects p1 ON tc.project_id = p1.id
                    LEFT JOIN Projects p2 ON m.project_id = p2.id
                    WHERE tc.id = ?
                """, (testcase_id,))

                metadata = cursor.fetchone()
                if metadata:
                    project_name = metadata[0]
                    module_name = metadata[1]
                    table_name = generate_unique_table_name(project_name, module_name, testcase_name)
                else:
                    # Fallback to old naming
                    table_name = sanitize_table_name(testcase_name)

                try:
                    cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")
                    deletion_summary['test_steps_tables_deleted'] += 1
                    print(f"[CASCADE DELETE] Dropped test steps table: {table_name}")
                except Exception as e:
                    print(f"[WARNING] Could not drop table {table_name}: {str(e)}")
                
                # Count execution results but DON'T delete them (preserve reports)
                try:
                    cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_name = ?", (testcase_name,))
                    results_count = cursor.fetchone()[0]
                    deletion_summary['execution_results_preserved'] += results_count
                    
                    # Also count by testcase_id if it exists
                    if testcase_id_string:
                        cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_id = ?", (testcase_id_string,))
                        additional_count = cursor.fetchone()[0]
                        deletion_summary['execution_results_preserved'] += additional_count
                    
                    print(f"[CASCADE DELETE] Preserving {results_count} execution results/reports for {testcase_name}")
                except Exception as e:
                    print(f"[WARNING] Could not count execution results: {str(e)}")
                
                deletion_summary['test_cases_deleted'] += 1
            
            # Delete all test cases related to this module
            if has_module_id:
                cursor.execute("DELETE FROM TestCases WHERE module_id = ?", (module_id,))
            else:
                # If no module_id column, we can't safely delete by module, so we skip this step
                print("[WARNING] TestCases table doesn't have module_id column, skipping test case deletion by module")
        else:
            print(f"[INFO] TestCases table does not exist, skipping test case deletion")
        
        # Finally, delete the module itself
        cursor.execute("DELETE FROM Modules WHERE id = ?", (module_id,))
        
        conn.commit()
        conn.close()
        
        print(f"[CASCADE DELETE SUCCESS] Module '{module_name}' and related data processed:")
        print(f"  - Test Suites: {deletion_summary['test_suites_deleted']} deleted")
        print(f"  - Test Cases: {deletion_summary['test_cases_deleted']} deleted")
        print(f"  - Test Steps Tables: {deletion_summary['test_steps_tables_deleted']} deleted")
        print(f"  - Execution Results: {deletion_summary['execution_results_preserved']} preserved (reports kept)")
        
        return jsonify({
            'message': 'Module and all related data deleted successfully',
            'deletion_summary': deletion_summary
        })
    except Exception as e:
        print(f"[CASCADE DELETE ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

# Test Suites API

@app.route('/api/custom-test-suites', methods=['GET'])
def get_custom_test_suites():
    """Get all custom test suites created through the UI"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create CustomTestSuites table if not exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='CustomTestSuites' AND xtype='U')
            CREATE TABLE CustomTestSuites (
                id NVARCHAR(50) PRIMARY KEY,
                name NVARCHAR(255) NOT NULL,
                description NVARCHAR(500),
                icon NVARCHAR(50) DEFAULT 'Settings',
                gradient NVARCHAR(100) DEFAULT 'from-gray-500 to-slate-500',
                test_count INT DEFAULT 0,
                last_run NVARCHAR(50) DEFAULT 'Never',
                status NVARCHAR(20) DEFAULT 'active',
                created_at DATETIME DEFAULT GETDATE(),
                updated_at DATETIME DEFAULT GETDATE()
            )
        """)
        
        # Create CustomTestSuiteTestCases table if not exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='CustomTestSuiteTestCases' AND xtype='U')
            CREATE TABLE CustomTestSuiteTestCases (
                id INT IDENTITY(1,1) PRIMARY KEY,
                suite_id NVARCHAR(50) NOT NULL,
                testcase_id INT NOT NULL,
                order_index INT DEFAULT 0,
                added_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (suite_id) REFERENCES CustomTestSuites(id) ON DELETE CASCADE,
                FOREIGN KEY (testcase_id) REFERENCES TestCases(id) ON DELETE CASCADE
            )
        """)
        
        cursor.execute("""
            SELECT id, name, description, icon, gradient, test_count, last_run, status, created_at, updated_at 
            FROM CustomTestSuites 
            ORDER BY created_at DESC
        """)
        
        test_suites = []
        for row in cursor.fetchall():
            test_suites.append({
                'id': row[0],
                'name': row[1],
                'description': row[2],
                'icon': row[3],
                'gradient': row[4],
                'testCount': row[5],
                'lastRun': row[6],
                'status': row[7],
                'created_at': format_timestamp(row[8]) if row[8] else None,
                'updated_at': format_timestamp(row[9]) if row[9] else None
            })
        
        conn.close()
        return jsonify({'test_suites': test_suites})
    except Exception as e:
        print(f"[ERROR] Get custom test suites: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/custom-test-suites', methods=['POST'])
def create_custom_test_suite():
    """Create a new custom test suite"""
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create tables if not exist (same as in GET)
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='CustomTestSuites' AND xtype='U')
            CREATE TABLE CustomTestSuites (
                id NVARCHAR(50) PRIMARY KEY,
                name NVARCHAR(255) NOT NULL,
                description NVARCHAR(500),
                icon NVARCHAR(50) DEFAULT 'Settings',
                gradient NVARCHAR(100) DEFAULT 'from-gray-500 to-slate-500',
                test_count INT DEFAULT 0,
                last_run NVARCHAR(50) DEFAULT 'Never',
                status NVARCHAR(20) DEFAULT 'active',
                created_at DATETIME DEFAULT GETDATE(),
                updated_at DATETIME DEFAULT GETDATE()
            )
        """)
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='CustomTestSuiteTestCases' AND xtype='U')
            CREATE TABLE CustomTestSuiteTestCases (
                id INT IDENTITY(1,1) PRIMARY KEY,
                suite_id NVARCHAR(50) NOT NULL,
                testcase_id INT NOT NULL,
                order_index INT DEFAULT 0,
                added_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (suite_id) REFERENCES CustomTestSuites(id) ON DELETE CASCADE,
                FOREIGN KEY (testcase_id) REFERENCES TestCases(id) ON DELETE CASCADE
            )
        """)
        
        # Generate unique ID
        suite_id = f"suite-{int(time.time() * 1000)}"
        
        cursor.execute("""
            INSERT INTO CustomTestSuites (id, name, description, icon, gradient, test_count, last_run, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            suite_id,
            data['name'],
            data.get('description', ''),
            data.get('icon', 'Settings'),
            data.get('gradient', 'from-gray-500 to-slate-500'),
            data.get('testCount', 0),
            data.get('lastRun', 'Never'),
            data.get('status', 'active')
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'id': suite_id,
            'message': 'Custom test suite created successfully'
        })
    except Exception as e:
        print(f"[ERROR] Create custom test suite: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/custom-test-suites/<suite_id>', methods=['PUT'])
def update_custom_test_suite(suite_id):
    """Update a custom test suite"""
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE CustomTestSuites 
            SET name = ?, description = ?, test_count = ?, updated_at = GETDATE()
            WHERE id = ?
        """, (
            data['name'],
            data.get('description', ''),
            data.get('testCount', 0),
            suite_id
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Custom test suite updated successfully'})
    except Exception as e:
        print(f"[ERROR] Update custom test suite: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/custom-test-suites/<suite_id>', methods=['DELETE'])
def delete_custom_test_suite(suite_id):
    """Delete a custom test suite and all its test case assignments"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if suite exists
        cursor.execute("SELECT name FROM CustomTestSuites WHERE id = ?", (suite_id,))
        suite_result = cursor.fetchone()
        if not suite_result:
            conn.close()
            return jsonify({'error': 'Test suite not found'}), 404
        
        suite_name = suite_result[0]
        
        # Delete test case assignments (will be handled by CASCADE)
        cursor.execute("DELETE FROM CustomTestSuiteTestCases WHERE suite_id = ?", (suite_id,))
        
        # Delete the suite
        cursor.execute("DELETE FROM CustomTestSuites WHERE id = ?", (suite_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': f'Test suite "{suite_name}" deleted successfully'
        })
    except Exception as e:
        print(f"[ERROR] Delete custom test suite: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/custom-test-suites/<suite_id>/test-cases', methods=['GET'])
def get_custom_test_suite_test_cases(suite_id):
    """Get all test cases assigned to a custom test suite"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT tc.id, tc.testcase_id, tc.name, tc.description, tc.project_id, tc.module_id, 
                   tc.created_date, tc.status, tc.priority, cstc.order_index,
                   p.name as project_name, m.module_name as module_name
            FROM CustomTestSuiteTestCases cstc
            INNER JOIN TestCases tc ON cstc.testcase_id = tc.id
            LEFT JOIN Projects p ON tc.project_id = p.id
            LEFT JOIN Modules m ON tc.module_id = m.id
            WHERE cstc.suite_id = ?
            ORDER BY cstc.order_index, cstc.added_at
        """, (suite_id,))
        
        test_cases = []
        for row in cursor.fetchall():
            test_cases.append({
                'id': row[0],
                'testcase_id': row[1],
                'name': row[2],
                'description': row[3],
                'project_id': row[4],
                'module_id': row[5],
                'created_date': format_timestamp(row[6]) if row[6] else None,
                'status': row[7],
                'priority': row[8],
                'order_index': row[9],
                'project_name': row[10] or 'Unknown Project',
                'module_name': row[11] or 'Unknown Module',
                'isInSuite': True
            })
        
        conn.close()
        return jsonify({'test_cases': test_cases})
    except Exception as e:
        print(f"[ERROR] Get custom test suite test cases: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/custom-test-suites/<suite_id>/test-cases', methods=['POST'])
def save_custom_test_suite_test_cases(suite_id):
    """Save test cases for a custom test suite"""
    try:
        data = request.json
        test_cases = data.get('test_cases', [])
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Clear existing test case assignments
        cursor.execute("DELETE FROM CustomTestSuiteTestCases WHERE suite_id = ?", (suite_id,))
        
        # Add new test case assignments
        for index, test_case in enumerate(test_cases):
            cursor.execute("""
                INSERT INTO CustomTestSuiteTestCases (suite_id, testcase_id, order_index)
                VALUES (?, ?, ?)
            """, (suite_id, test_case['id'], index))
        
        # Update test count in the suite
        cursor.execute("""
            UPDATE CustomTestSuites 
            SET test_count = ?, updated_at = GETDATE()
            WHERE id = ?
        """, (len(test_cases), suite_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Test cases saved successfully',
            'test_count': len(test_cases)
        })
    except Exception as e:
        print(f"[ERROR] Save custom test suite test cases: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Original Test Suites API (for module-based suites)

@app.route('/api/test-suites', methods=['GET'])
def get_test_suites():
    try:
        module_id = request.args.get('module_id')
        if not module_id:
            return jsonify({'error': 'module_id parameter is required'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create TestSuites table if not exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TestSuites' AND xtype='U')
            CREATE TABLE TestSuites (
                id INT IDENTITY(1,1) PRIMARY KEY,
                module_id INT,
                suite_name NVARCHAR(255) NOT NULL,
                suite_type NVARCHAR(50) NOT NULL CHECK (suite_type IN ('smoke', 'sanity', 'regression')),
                description NVARCHAR(500),
                executor_type NVARCHAR(50) DEFAULT 'selenium',
                created_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (module_id) REFERENCES Modules(id)
            )
        """)
        
        cursor.execute("SELECT id, suite_name, suite_type, description, created_at, executor_type FROM TestSuites WHERE module_id = ?", (module_id,))
        test_suites = []
        for row in cursor.fetchall():
            test_suites.append({
                'id': row[0],
                'suite_name': row[1],
                'suite_type': row[2],
                'description': row[3],
                'created_at': format_timestamp(row[4]) if row[4] else None,
                'executor_type': row[5]
            })
        
        conn.close()
        return jsonify({'test_suites': test_suites})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-suites', methods=['POST'])
def create_test_suite():
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create TestSuites table if not exists
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='TestSuites' AND xtype='U')
            CREATE TABLE TestSuites (
                id INT IDENTITY(1,1) PRIMARY KEY,
                module_id INT,
                suite_name NVARCHAR(255) NOT NULL,
                suite_type NVARCHAR(50) NOT NULL CHECK (suite_type IN ('smoke', 'sanity', 'regression')),
                description NVARCHAR(500),
                executor_type NVARCHAR(50) DEFAULT 'selenium',
                created_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (module_id) REFERENCES Modules(id)
            )
        """)
        
        cursor.execute("""
            INSERT INTO TestSuites (module_id, suite_name, suite_type, description, executor_type)
            VALUES (?, ?, ?, ?, ?)
        """, (data['module_id'], data['suite_name'], data['suite_type'], data['description'], data.get('executor_type', 'selenium')))
        
        conn.commit()
        suite_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
        conn.close()
        
        return jsonify({'id': suite_id, 'message': 'Test suite created successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-suites/<int:suite_id>', methods=['PUT'])
def update_test_suite(suite_id):
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE TestSuites 
            SET suite_name = ?, suite_type = ?, description = ?, executor_type = ?
            WHERE id = ?
        """, (data['suite_name'], data['suite_type'], data['description'], data.get('executor_type', 'selenium'), suite_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Test suite updated successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/test-suites/<int:suite_id>', methods=['DELETE'])
def delete_test_suite(suite_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if test suite exists and get suite info
        cursor.execute("SELECT suite_name, module_id FROM TestSuites WHERE id = ?", (suite_id,))
        suite_result = cursor.fetchone()
        if not suite_result:
            conn.close()
            return jsonify({'error': 'Test suite not found'}), 404
        
        suite_name, module_id = suite_result
        print(f"[CASCADE DELETE] Starting cascade deletion for test suite: {suite_name} (ID: {suite_id})")
        
        deletion_summary = {
            'suite_name': suite_name,
            'execution_results_preserved': 0
        }
        
        # Count execution results but DON'T delete them (preserve reports)
        # Note: selenium_results has testsuitename field that we can use
        try:
            cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testsuitename = ?", (suite_name,))
            results_count = cursor.fetchone()[0]
            deletion_summary['execution_results_preserved'] = results_count;
            
            print(f"[CASCADE DELETE] Preserving {results_count} execution results/reports for test suite: {suite_name}")
        except Exception as e:
            print(f"[WARNING] Could not count execution results: {str(e)}")
        
        # Delete the test suite itself
        cursor.execute("DELETE FROM TestSuites WHERE id = ?", (suite_id,))
        
        conn.commit()
        conn.close()
        
        print(f"[CASCADE DELETE SUCCESS] Test suite '{suite_name}' deleted:")
        print(f"  - Execution Results: {deletion_summary['execution_results_preserved']} preserved (reports kept)")
        
        return jsonify({
            'message': 'Test suite and all related data deleted successfully',
            'deletion_summary': deletion_summary
        })
    except Exception as e:
        print(f"[CASCADE DELETE ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

# Test Steps Migration API
@app.route('/api/migrate-test-steps', methods=['POST'])
def migrate_test_steps_api():
    """API endpoint to migrate test steps from one test case to another"""
    try:
        data = request.json
        source_testcase = data.get('source_testcase_name')
        target_testcase = data.get('target_testcase_name')
        
        if not source_testcase or not target_testcase:
            return jsonify({
                'success': False,
                'error': 'Both source_testcase_name and target_testcase_name are required'
            }), 400
        
        conn = get_db_connection()
        
        # Perform migration
        success = migrate_test_steps(source_testcase, target_testcase, conn)
        
        if success:
            conn.commit()
            conn.close()
            return jsonify({
                'success': True,
                'message': f'Successfully migrated test steps from {source_testcase} to {target_testcase}'
            })
        else:
            conn.close()
            return jsonify({
                'success': False,
                'error': f'Failed to migrate test steps from {source_testcase} to {target_testcase}'
            }), 500
            
    except Exception as e:
        print(f"[ERROR] Migration API error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Test Cases API
@app.route('/api/testcases', methods=['GET'])
def get_testcases_by_suite():
    try:
        suite_type = request.args.get('suite_type')
        module_id = request.args.get('module_id')
        project_id = request.args.get('project_id')
        
        if suite_type:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Update TestCases table to include suite_type and module_id
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'suite_type')
                ALTER TABLE TestCases ADD suite_type NVARCHAR(50)
            """)
            
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'module_id')
                ALTER TABLE TestCases ADD module_id INT
            """)
            
             # Build dynamic query based on available filters with JOINs to get project and module names
            query = """
                SELECT tc.id, tc.testcase_id, tc.name, tc.description, tc.priority, tc.status, tc.created_date,
                       COALESCE(p1.name, p2.name, 'Unknown Project') as project_name, 
                       COALESCE(m.module_name, 'Unknown Module') as module_name
                FROM TestCases tc 
                LEFT JOIN Modules m ON tc.module_id = m.id 
                LEFT JOIN Projects p1 ON tc.project_id = p1.id 
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.suite_type = ?
            """
            params = [suite_type]
            
            if module_id:
                query += " AND tc.module_id = ?"
                params.append(module_id)
            elif project_id:
                query += " AND tc.project_id = ?"
                params.append(project_id)

            query += " ORDER BY tc.id ASC"
            cursor.execute(query, params)
            testcases = []
            for row in cursor.fetchall():
                testcases.append({
                    'id': row[0],
                    'testcase_id': row[1],
                    'name': row[2],
                    'description': row[3],
                    'priority': row[4],
                    'status': row[5],
                    'created_date': format_timestamp(row[6]) if row[6] else None,
                    'project_name': row[7],  # Already handled by COALESCE in SQL
                    'module_name': row[8]   # Already handled by COALESCE in SQL
                })
            
            conn.close()
            return jsonify({'test_cases': testcases})
        else:
            return jsonify({'error': 'suite_type parameter is required'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/testcases/bulk', methods=['GET'])
def get_testcases_bulk():
    """Optimized endpoint to fetch test cases from multiple suite types in a single query"""
    try:
        suite_types_param = request.args.get('suite_types')  # Comma-separated list
        module_id = request.args.get('module_id')
        project_id = request.args.get('project_id')
        
        if not suite_types_param:
            return jsonify({'error': 'suite_types parameter is required (comma-separated list)'}), 400
        
        # Parse suite types
        suite_types = [s.strip() for s in suite_types_param.split(',')]
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update TestCases table to include suite_type and module_id if needed
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'suite_type')
            ALTER TABLE TestCases ADD suite_type NVARCHAR(50)
        """)
        
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'TestCases' AND COLUMN_NAME = 'module_id')
            ALTER TABLE TestCases ADD module_id INT
        """)
        
        # Build dynamic query with IN clause for multiple suite types
        placeholders = ','.join(['?' for _ in suite_types])
        query = f"""
            SELECT DISTINCT tc.id, tc.testcase_id, tc.name, tc.description, tc.priority, tc.status, tc.created_date,
                   COALESCE(p1.name, p2.name, 'Unknown Project') as project_name, 
                   COALESCE(m.module_name, 'Unknown Module') as module_name
            FROM TestCases tc 
            LEFT JOIN Modules m ON tc.module_id = m.id 
            LEFT JOIN Projects p1 ON tc.project_id = p1.id 
            LEFT JOIN Projects p2 ON m.project_id = p2.id
            WHERE tc.suite_type IN ({placeholders})
        """
        params = suite_types.copy()
        
        if module_id:
            query += " AND tc.module_id = ?"
            params.append(module_id)
        elif project_id:
            query += " AND tc.project_id = ?"
            params.append(project_id)
        
        query += " ORDER BY tc.id ASC"
        
        print(f"[BULK_TESTCASES] Executing query: {query}")
        print(f"[BULK_TESTCASES] Parameters: {params}")
        
        cursor.execute(query, params)
        testcases = []
        for row in cursor.fetchall():
            testcases.append({
                'id': row[0],
                'testcase_id': row[1],
                'name': row[2],
                'description': row[3],
                'priority': row[4],
                'status': row[5],
                'created_date': format_timestamp(row[6]) if row[6] else None,
                'project_name': row[7],  # Already handled by COALESCE in SQL
                'module_name': row[8]   # Already handled by COALESCE in SQL
            })
        
        conn.close()
        print(f"[BULK_TESTCASES] Found {len(testcases)} unique test cases across {len(suite_types)} suite types")
        return jsonify({'test_cases': testcases, 'suite_types_queried': suite_types})
        
    except Exception as e:
        print(f"[BULK_TESTCASES_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/testcases/<int:project_id>', methods=['GET'])
def get_testcases(project_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if not table_exists(cursor, 'TestCases'):
            conn.close()
            return jsonify([])

        cursor.execute("SELECT id, name, description, priority, status, created_date FROM [dbo].[TestCases] WHERE project_id = ?", (project_id,))
        testcases = []
        for row in cursor.fetchall():
            testcases.append({
                'id': row[0],
                'name': row[1],
                'description': row[2],
                'priority': row[3],
                'status': row[4],
                'created_date': format_timestamp(row[5]) if row[5] else None
            })
        
        conn.close()
        return jsonify(testcases)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/testcases', methods=['POST'])
def create_testcase():
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()

        if not table_exists(cursor, 'TestCases'):
            conn.close()
            return jsonify({'error': "Table [dbo].[TestCases] does not exist or is not accessible. Contact DBA/admin."}), 500
        
        # Get module and project information
        module_id = data.get('module_id')
        project_name = data.get('project_name', 'DefaultProj')
        module_name = data.get('module_name', 'DefaultMod')
        project_id = None
        
        if module_id:
            # Get actual module and project names
            cursor.execute("""
                SELECT m.module_name, p.name as project_name, p.id as project_id 
                FROM Modules m 
                INNER JOIN Projects p ON m.project_id = p.id 
                WHERE m.id = ?
            """, (module_id,))
            result = cursor.fetchone()
            if result:
                module_name = result[0]
                project_name = result[1]
                project_id = result[2]
        
        # Generate testcase_id
        generated_testcase_id = generate_testcase_id(project_name, module_name, data['name'], conn)
        
         # Insert test case with generated ID, project_id and module_id
        cursor.execute("""
            INSERT INTO [dbo].[TestCases] (testcase_id, suite_type, project_id, module_id, name, description, priority, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (generated_testcase_id, data['suite_type'], project_id, module_id, data['name'], data['description'], data.get('priority', 'Medium'), data.get('status', 'Active')))
        
        # Use SCOPE_IDENTITY for the current insert scope and cast to INT
        # so Flask can always serialize the response payload.
        testcase_id = cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS INT)").fetchone()[0]
        conn.commit()
        
        # Best effort: create test steps table if DB user has DDL permissions.
        # A failure here should not block test case metadata creation.
        test_steps_table_created = False
        table_name = generate_unique_table_name(project_name, module_name, data['name'])
        print(f"Creating table: {table_name}")
        escaped_table_name = table_name.replace(']', ']]')
        try:
            cursor.execute(f"""
                IF OBJECT_ID(N'[dbo].[{escaped_table_name}]', N'U') IS NULL
                CREATE TABLE [dbo].[{escaped_table_name}] (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    tc_id NVARCHAR(50),
                    step_no INT,
                    test_step_description NVARCHAR(500),
                    element_name NVARCHAR(255),
                    action_type NVARCHAR(100),
                    xpath NVARCHAR(1000),
                    [values] NVARCHAR(500),
                    expected_result NVARCHAR(500),
                    actual_result NVARCHAR(500),
                    status NVARCHAR(20) DEFAULT 'Not Executed',
                    page NVARCHAR(255) NULL
                )
            """)
            conn.commit()
            test_steps_table_created = True
        except Exception as table_err:
            print(f"[WARNING] Could not create test steps table '{table_name}': {table_err}")

        conn.close()
        
        print(f"[SUCCESS] Created test case '{data['name']}' with table: {table_name}")
        response_payload = {
            'id': testcase_id,
            'message': 'Test case created successfully',
            'test_steps_table': table_name,
            'test_steps_table_created': test_steps_table_created
        }
        if not test_steps_table_created:
            response_payload['warning'] = 'Test case created, but test steps table was not created due to insufficient DB permissions.'
        return jsonify(response_payload), 201
    except Exception as e:
        print(f"[ERROR] Error creating test case: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/testcases/<int:testcase_id>', methods=['PUT'])
def update_testcase(testcase_id):
    try:
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First get the current test case to check if name is changing
        cursor.execute("SELECT name, testcase_id FROM TestCases WHERE id = ?", (testcase_id,))
        current_testcase = cursor.fetchone()
        
        if not current_testcase:
            return jsonify({'error': 'Test case not found'}), 404
        
        old_name = current_testcase[0]
        old_testcase_id = current_testcase[1]
        new_name = data['name']
        
        # If name changed, regenerate testcase_id
        new_testcase_id = old_testcase_id
        if old_name != new_name:
            # Get project and module info for regeneration
            module_id = data.get('module_id')
            project_name = data.get('project_name', 'DefaultProj')
            module_name = data.get('module_name', 'DefaultMod')
            
            if module_id:
                cursor.execute("""
                    SELECT m.module_name, p.name as project_name 
                    FROM Modules m 
                    INNER JOIN Projects p ON m.project_id = p.id 
                    WHERE m.id = ?
                """, (module_id,))
                result = cursor.fetchone()
                if result:
                    module_name = result[0]
                    project_name = result[1]
            
            new_testcase_id = generate_testcase_id(project_name, module_name, new_name, conn)
        else:
            # Ensure the 'page' column exists in the test case table
            # Get project and module info for generating unique table name
            cursor.execute("""
                SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.id = ?
            """, (testcase_id,))

            metadata = cursor.fetchone()
            if metadata:
                project_name = metadata[0]
                module_name = metadata[1]
                table_name = generate_unique_table_name(project_name, module_name, old_name)
            else:
                # Fallback to old naming for backward compatibility
                table_name = sanitize_table_name(old_name)

            ensure_page_column_exists(cursor, table_name)
        
        # Update the test case
        cursor.execute("""
            UPDATE TestCases 
            SET testcase_id = ?, name = ?, description = ?, priority = ?, suite_type = ?
            WHERE id = ?
        """, (new_testcase_id, new_name, data['description'], data.get('priority', 'Medium'), data.get('suite_type'), testcase_id))
        
        # If name changed, rename the table
        if old_name != new_name:
            # Get project and module info for generating unique table names
            project_name = None
            module_name = None

            # Get project and module info from the testcase
            cursor.execute("""
                SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.id = ?
            """, (testcase_id,))

            metadata = cursor.fetchone()
            if metadata:
                project_name = metadata[0]
                module_name = metadata[1]

            if project_name and module_name:
                old_table_name = generate_unique_table_name(project_name, module_name, old_name)
                new_table_name = generate_unique_table_name(project_name, module_name, new_name)

                print(f"Renaming table from {old_table_name} to {new_table_name}")

                # Check if old table exists
                cursor.execute(f"SELECT COUNT(*) FROM sysobjects WHERE name='{old_table_name}' AND xtype='U'")
                if cursor.fetchone()[0] > 0:
                    # Check if new table name already exists
                    cursor.execute(f"SELECT COUNT(*) FROM sysobjects WHERE name='{new_table_name}' AND xtype='U'")
                    if cursor.fetchone()[0] > 0:
                        # If new table name exists, generate a unique name
                        counter = 1
                        unique_table_name = f"{new_table_name}_{counter}"
                        while True:
                            cursor.execute(f"SELECT COUNT(*) FROM sysobjects WHERE name='{unique_table_name}' AND xtype='U'")
                            if cursor.fetchone()[0] == 0:
                                new_table_name = unique_table_name
                                break
                            counter += 1
                            unique_table_name = f"{new_table_name}_{counter}"
                        print(f"New table name already exists, using unique name: {new_table_name}")

                    # Rename the table
                    cursor.execute(f"EXEC sp_rename '{old_table_name}', '{new_table_name}'")
                    print(f"[SUCCESS] Renamed table from {old_table_name} to {new_table_name}")
                else:
                    print(f"[WARNING] Old table {old_table_name} does not exist, skipping rename")
            else:
                print(f"[WARNING] Could not get project/module info for table rename")
        
        conn.commit()
        conn.close()
        
        print(f"[SUCCESS] Updated test case '{new_name}' with ID: {testcase_id}")
        return jsonify({'message': 'Test case updated successfully'})
    except Exception as e:
        print(f"[ERROR] Error updating test case: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/testcases/<int:testcase_id>', methods=['DELETE'])
def delete_testcase(testcase_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get test case details first
        cursor.execute("SELECT name, testcase_id FROM TestCases WHERE id = ?", (testcase_id,))
        testcase = cursor.fetchone()
        
        if not testcase:
            return jsonify({'error': 'Test case not found'}), 404
        
        testcase_name = testcase[0]
        testcase_id_string = testcase[1]
        
        # Extract project and module names from testcase_id
        # Format: projectname_modulename_testcasename_TC001
        project_name = None
        module_name = None

        if testcase_id_string and '_TC' in testcase_id_string:
            # Remove the _TC### part to get the base
            base_id = testcase_id_string.rsplit('_TC', 1)[0]
            # Split by underscores and assume first two parts are project and module
            parts = base_id.split('_')
            if len(parts) >= 2:
                project_name = parts[0]
                module_name = parts[1]
                print(f"[DELETE] Extracted from testcase_id: Project='{project_name}', Module='{module_name}'")

        # Use generate_unique_table_name if we have project/module info, otherwise fallback
        if project_name and module_name:
            table_name = generate_unique_table_name(project_name, module_name, testcase_name)
        else:
            table_name = sanitize_table_name(testcase_name)
        
        print(f"[DELETE] Starting deletion of test case: {testcase_name} (ID: {testcase_id_string})")
        print(f"[DELETE] Project: {project_name}, Module: {module_name}")
        
        # 1. Drop the test case table (test steps)
        cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")
        print(f"[DELETE] Dropped test steps table: {table_name}")
        
        # 2. Delete from selenium_results table (test execution results)
        cursor.execute("DELETE FROM selenium_results WHERE testcase_name = ?", (testcase_name,))
        selenium_results_deleted = cursor.rowcount
        print(f"[DELETE] Deleted {selenium_results_deleted} execution results from selenium_results")
        
        # 3. Delete from selenium_results by testcase_id as well (in case both are stored)
        additional_deleted = 0
        if testcase_id_string:
            cursor.execute("DELETE FROM selenium_results WHERE testcase_id = ?", (testcase_id_string,))
            additional_deleted = cursor.rowcount
            print(f"[DELETE] Deleted {additional_deleted} additional execution results by testcase_id")
        
        # 4. Delete from TestCases table (main record)
        cursor.execute("DELETE FROM TestCases WHERE id = ?", (testcase_id,))
        print(f"[DELETE] Deleted main test case record from TestCases table")
        
        # 5. RENUMBER remaining test cases in the same project-module to fill gaps
        renumber_info = {'total_renumbered': 0, 'renumbering_details': []}
        if project_name and module_name and testcase_id_string:
            print(f"[DELETE] Starting renumbering process for {project_name}-{module_name}")
            renumber_info = renumber_testcases_after_deletion(cursor, project_name, module_name, testcase_id_string)
        
        conn.commit()
        conn.close()
        
        total_execution_results_deleted = selenium_results_deleted + additional_deleted
        
        print(f"[SUCCESS] Completely deleted test case '{testcase_name}' and all related data:")
        print(f"  - Test steps table: {table_name}")
        print(f"  - Execution results: {total_execution_results_deleted} records")
        print(f"  - Main record: TestCases table")
        print(f"  - Renumbered test cases: {renumber_info['total_renumbered']}")
        
        return jsonify({
            'message': 'Test case deleted successfully with automatic renumbering',
            'details': {
                'testcase_name': testcase_name,
                'testcase_id': testcase_id_string,
                'execution_results_deleted': total_execution_results_deleted,
                'renumbering': renumber_info
            }
        })
    except Exception as e:
        print(f"[ERROR] Error deleting test case: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Test Steps API
@app.route('/api/teststeps/<testcase_name>', methods=['GET'])
def get_teststeps(testcase_name):
    try:
        testcase_name = unquote(testcase_name).strip()
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get project and module info for the testcase to generate correct table name
        # Handle multiple testcases with same name by checking query parameters
        project_name_param = request.args.get('project_name')
        module_name_param = request.args.get('module_name')

        if project_name_param and module_name_param:
            # Specific project/module requested
            cursor.execute("""
                SELECT tc.id, COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.name = ? AND COALESCE(p1.name, p2.name, 'Unknown') = ? AND COALESCE(m.module_name, 'Unknown') = ?
            """, (testcase_name, project_name_param, module_name_param))

            metadata = cursor.fetchone()
            if metadata:
                table_name = generate_unique_table_name(project_name_param, module_name_param, testcase_name)
            else:
                return jsonify({'error': f'Test case "{testcase_name}" not found in project "{project_name_param}" and module "{module_name_param}"'}), 404
        else:
            # No specific project/module - check if multiple exist
            cursor.execute("""
                SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.name = ?
            """, (testcase_name,))

            metadata_list = cursor.fetchall()
            if not metadata_list:
                return jsonify({'error': f'Test case "{testcase_name}" not found'}), 404

            if len(metadata_list) > 1:
                # Multiple testcases with same name - return error asking for clarification
                return jsonify({
                    'error': f'Multiple test cases found with name "{testcase_name}". Please specify project_name and module_name as query parameters.',
                    'available_options': [{'project': row[0], 'module': row[1]} for row in metadata_list]
                }), 400

            # Single testcase found
            metadata = metadata_list[0]
            project_name = metadata[0]
            module_name = metadata[1]
            table_name = generate_unique_table_name(project_name, module_name, testcase_name)

        ensure_page_column_exists(cursor, table_name)
        cursor.execute(f"SELECT id, tc_id, step_no, test_step_description, element_name, action_type, xpath, [values], page FROM [{table_name}] ORDER BY step_no")

        steps = []
        for row in cursor.fetchall():
            steps.append({
                'id': row[0],
                'tc_id': row[1],
                'step_no': row[2],
                'test_step_description': row[3],
                'element_name': row[4],
                'action_type': row[5],
                'xpath': row[6],
                'values': row[7],
                'page': row[8]
            })

        conn.close()
        return jsonify(steps)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/teststeps/<testcase_name>', methods=['POST'])
def create_teststep(testcase_name):
    try:
        testcase_name = unquote(testcase_name).strip()
        data = request.json
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get project and module info for the testcase to generate correct table name
        # Handle multiple testcases with same name by checking request data
        project_name_param = data.get('project_name')
        module_name_param = data.get('module_name')

        if project_name_param and module_name_param:
            # Specific project/module provided
            cursor.execute("""
                SELECT tc.id, COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.name = ? AND COALESCE(p1.name, p2.name, 'Unknown') = ? AND COALESCE(m.module_name, 'Unknown') = ?
            """, (testcase_name, project_name_param, module_name_param))

            metadata = cursor.fetchone()
            if metadata:
                table_name = generate_unique_table_name(project_name_param, module_name_param, testcase_name)
            else:
                return jsonify({'error': f'Test case "{testcase_name}" not found in project "{project_name_param}" and module "{module_name_param}"'}), 404
        else:
            # No specific project/module - check if multiple exist
            cursor.execute("""
                SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.name = ?
            """, (testcase_name,))

            metadata_list = cursor.fetchall()
            if not metadata_list:
                return jsonify({'error': f'Test case "{testcase_name}" not found'}), 404

            if len(metadata_list) > 1:
                # Multiple testcases with same name - return error asking for clarification
                return jsonify({
                    'error': f'Multiple test cases found with name "{testcase_name}". Please provide project_name and module_name in the request.',
                    'available_options': [{'project': row[0], 'module': row[1]} for row in metadata_list]
                }), 400

            # Single testcase found
            metadata = metadata_list[0]
            project_name = metadata[0]
            module_name = metadata[1]
            table_name = generate_unique_table_name(project_name, module_name, testcase_name)

        print(f"Saving test step to table: {table_name}")
        # Check if table exists before insert
        cursor.execute(f"""
            SELECT COUNT(*) FROM sysobjects WHERE name=? AND xtype='U'
        """, (table_name,))
        if cursor.fetchone()[0] == 0:
            return jsonify({'error': f"Test steps table '{table_name}' does not exist."}), 400

        # Get the proper testcase_id from TestCases table
        cursor.execute("SELECT testcase_id FROM TestCases WHERE name = ?", (testcase_name,))
        testcase_result = cursor.fetchone()
        proper_testcase_id = testcase_result[0] if testcase_result else testcase_name
        print(f"Using testcase_id: {proper_testcase_id} for test case: {testcase_name}")

        ensure_page_column_exists(cursor, table_name)
        cursor.execute(f"""
            INSERT INTO [{table_name}] (tc_id, step_no, test_step_description, element_name, action_type, xpath, [values], page)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proper_testcase_id, data['step_no'], data['test_step_description'],
            data['element_name'], data['action_type'], data.get('xpath', ''), data.get('values', ''), data.get('page', None)
        ))
        step_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
        conn.commit()
        conn.close()
        print(f"[SUCCESS] Test step saved with ID: {step_id}")
        return jsonify({'id': step_id, 'message': 'Test step created successfully'})
    except Exception as e:
        print(f"[ERROR] Error saving test step: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/teststeps/<testcase_name>/bulk', methods=['POST'])
def create_teststeps_bulk(testcase_name):
    try:
        testcase_name = unquote(testcase_name).strip()
        data = request.json
        steps = data.get('steps', [])
        if not steps:
            return jsonify({'error': 'No test steps provided'}), 400
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get project and module info for the testcase to generate correct table name
        # First try to find by exact testcase name (may return multiple if duplicates exist)
        cursor.execute("""
            SELECT tc.id, COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                   COALESCE(m.module_name, 'Unknown') as module_name
            FROM TestCases tc
            LEFT JOIN Modules m ON tc.module_id = m.id
            LEFT JOIN Projects p1 ON tc.project_id = p1.id
            LEFT JOIN Projects p2 ON m.project_id = p2.id
            WHERE tc.name = ?
            ORDER BY tc.id
        """, (testcase_name,))

        testcase_records = cursor.fetchall()

        if not testcase_records:
            return jsonify({'error': f'Test case "{testcase_name}" not found'}), 404

        if len(testcase_records) > 1:
            # Multiple testcases with same name - need project/module context from request
            project_name = data.get('project_name')
            module_name = data.get('module_name')

            if not project_name or not module_name:
                return jsonify({
                    'error': f'Multiple test cases found with name "{testcase_name}". Please provide project_name and module_name in the request.'
                }), 400

            # Find the matching record
            matching_record = None
            for record in testcase_records:
                if record[1] == project_name and record[2] == module_name:
                    matching_record = record
                    break

            if not matching_record:
                return jsonify({
                    'error': f'Test case "{testcase_name}" not found in project "{project_name}" and module "{module_name}"'
                }), 404

            table_name = generate_unique_table_name(project_name, module_name, testcase_name)
        else:
            # Single testcase found
            record = testcase_records[0]
            project_name = record[1]
            module_name = record[2]
            table_name = generate_unique_table_name(project_name, module_name, testcase_name)

        # Ensure table exists - create it if it doesn't
        cursor.execute(f"""
            SELECT COUNT(*) FROM sysobjects WHERE name=? AND xtype='U'
        """, (table_name,))
        if cursor.fetchone()[0] == 0:
            print(f"Table {table_name} doesn't exist, creating it...")
            cursor.execute(f"""
                CREATE TABLE [{table_name}] (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    tc_id NVARCHAR(255),
                    step_no INT,
                    test_step_description NVARCHAR(500),
                    element_name NVARCHAR(255),
                    action_type NVARCHAR(100),
                    xpath NVARCHAR(1000),
                    [values] NVARCHAR(500),
                    expected_result NVARCHAR(500),
                    actual_result NVARCHAR(500),
                    status NVARCHAR(20) DEFAULT 'Not Executed',
                    page NVARCHAR(255) NULL
                )
            """)
            print(f"[SUCCESS] Created table {table_name}")

        print(f"Bulk saving {len(steps)} test steps to table: {table_name}")
        # Check if table exists, if not create it
        cursor.execute(f"""
            SELECT COUNT(*) FROM sysobjects WHERE name=? AND xtype='U'
        """, (table_name,))
        if cursor.fetchone()[0] == 0:
            print(f"Table {table_name} doesn't exist, creating it...")
            cursor.execute(f"""
                CREATE TABLE [{table_name}] (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    tc_id NVARCHAR(255),
                    step_no INT,
                    test_step_description NVARCHAR(500),
                    element_name NVARCHAR(255),
                    action_type NVARCHAR(100),
                    xpath NVARCHAR(1000),
                    [values] NVARCHAR(500),
                    expected_result NVARCHAR(500),
                    actual_result NVARCHAR(500),
                    status NVARCHAR(20) DEFAULT 'Not Executed',
                    page NVARCHAR(255) NULL
                )
            """)
            print(f"[SUCCESS] Created table {table_name}")
        else:
            ensure_page_column_exists(cursor, table_name)

        # Get the proper testcase_id from TestCases table
        cursor.execute("SELECT testcase_id FROM TestCases WHERE name = ?", (testcase_name,))
        testcase_result = cursor.fetchone()
        proper_testcase_id = testcase_result[0] if testcase_result else testcase_name
        print(f"Using testcase_id: {proper_testcase_id} for test case: {testcase_name}")

        # Clear existing steps if requested
        if data.get('clear_existing', False):
            cursor.execute(f"DELETE FROM [{table_name}]")
            print(f"[DELETE] Cleared existing steps from {table_name}")
        # Insert steps in bulk
        inserted_count = 0
        for step in steps:
            cursor.execute(f"""
                INSERT INTO [{table_name}] (tc_id, step_no, test_step_description, element_name, action_type, xpath, [values], page)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                proper_testcase_id,
                step['step_no'],
                step['test_step_description'],
                step['element_name'],
                step['action_type'],
                step.get('xpath', ''),
                step.get('values', ''),
                step.get('page', None)
            ))
            inserted_count += 1
        conn.commit()
        conn.close()
        print(f"[SUCCESS] Bulk saved {inserted_count} test steps")
        return jsonify({'message': f'Successfully saved {inserted_count} test steps', 'count': inserted_count})
    except Exception as e:
        print(f"[ERROR] Error bulk saving test steps: {str(e)}")
        return jsonify({'error': str(e)}), 500

def ensure_page_column_exists(cursor, table_name):
    """Ensure the 'page' column exists in the given test step table."""
    cursor.execute(f"""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND COLUMN_NAME = 'page')
        ALTER TABLE [{table_name}] ADD page NVARCHAR(255) NULL
    """, (table_name,))

# Debug endpoint to see what test cases exist
@app.route('/api/debug-testcases', methods=['GET'])
def debug_testcases():
    """Debug endpoint to see all test cases and their IDs"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all test cases
        cursor.execute("""
            SELECT id, testcase_id, name, project_id, module_id, created_date, status
            FROM TestCases 
            ORDER BY testcase_id
        """)
        
        testcases = cursor.fetchall()
        
        result = []
        for row in testcases:
            result.append({
                'id': row[0],
                'testcase_id': row[1],
                'name': row[2],
                'project_id': row[3],
                'module_id': row[4],
                'created_date': str(row[5]) if row[5] else None,
                'status': row[6]
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'testcases': result,
            'count': len(result)
        })
        
    except Exception as e:
        print(f"[ERROR] Debug error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Debug endpoint to check VNC session counts
@app.route('/api/debug/vnc-counts', methods=['GET'])
def debug_vnc_counts():
    """Debug endpoint to check current VNC execution counts"""
    try:
        counts = vnc_manager.get_user_execution_counts()
        return jsonify({
            'user_execution_counts': counts,
            'max_parallel_executions': 3
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/reset-vnc-count/<email>', methods=['POST'])
def debug_reset_vnc_count(email):
    """Debug endpoint to reset VNC execution count for a user"""
    try:
        success = vnc_manager.reset_user_execution_count(email)
        return jsonify({
            'success': success,
            'message': f'Reset execution count for {email}' if success else f'No count found for {email}'
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vnc/autoconnect/<session_id>', methods=['GET'])
def serve_vnc_autoconnect(session_id):
    """Serve VNC auto-connect HTML files via HTTP"""
    try:
        # Find the auto-connect file for this session
        autoconnect_file = f"/tmp/vnc_autoconnect_{session_id}.html"
        
        if not os.path.exists(autoconnect_file):
            # Try to find by partial session ID
            import glob
            pattern = f"/tmp/vnc_autoconnect_*{session_id}*.html"
            matches = glob.glob(pattern)
            if matches:
                autoconnect_file = matches[0]
            else:
                return jsonify({'error': 'VNC auto-connect file not found'}), 404
        
        # Read the HTML file content
        with open(autoconnect_file, 'r') as f:
            html_content = f.read()
        
        return Response(html_content, mimetype='text/html')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vnc/custom/<session_id>', methods=['GET'])
def serve_vnc_custom(session_id):
    """Serve custom VNC HTML files that prevent DOM errors via HTTP"""
    try:
        # Find the custom VNC file for this session
        custom_file = f"/tmp/vnc_custom_{session_id}.html"
        
        if not os.path.exists(custom_file):
            # Try to find by partial session ID
            import glob
            pattern = f"/tmp/vnc_custom_*{session_id}*.html"
            matches = glob.glob(pattern)
            if matches:
                custom_file = matches[0]
            else:
                return jsonify({'error': 'VNC custom file not found'}), 404
        
        # Read the HTML file content
        with open(custom_file, 'r') as f:
            html_content = f.read()
        
        return Response(html_content, mimetype='text/html')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vnc/helper/<session_id>', methods=['GET'])
def serve_vnc_helper(session_id):
    """Serve VNC helper HTML files via HTTP"""
    try:
        # Find the helper file for this session
        helper_file = f"/tmp/vnc_helper_{session_id}.html"
        
        if not os.path.exists(helper_file):
            # Try to find by partial session ID
            import glob
            pattern = f"/tmp/vnc_helper_*{session_id}*.html"
            matches = glob.glob(pattern)
            if matches:
                helper_file = matches[0]
            else:
                return jsonify({'error': 'VNC helper file not found'}), 404
        
        # Read the HTML file content
        with open(helper_file, 'r') as f:
            html_content = f.read()
        
        return Response(html_content, mimetype='text/html')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vnc/viewer/<novnc_port>', methods=['GET'])
def serve_vnc_viewer(novnc_port):
    """Serve noVNC viewer with explicit WebSocket configuration to avoid port mismatch"""
    try:
        novnc_port = int(novnc_port)
        
        vnc_html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>noVNC</title>
    <style>
        body {{ margin:0; padding:0; background:#1a1a1a; overflow:hidden; }}
        #canvas {{ display:block; width:100%; height:100vh; }}
        #status {{ position:fixed; top:10px; left:10px; background:rgba(0,0,0,0.8); color:#0f0; padding:10px; border-radius:5px; font-family:monospace; z-index:1000; }}
    </style>
</head>
<body>
    <canvas id="canvas"></canvas>
    <div id="status">Loading noVNC libraries...</div>
    
    <script>
        // Dynamically load noVNC scripts from the same host/port
        (function() {{
            var browserHost = window.location.hostname;
            var vncPort = {novnc_port};
            var scriptBase = 'http://' + browserHost + ':' + vncPort;
            
            // Load scripts sequentially
            var scripts = [
                '/vendor/reconnect.js',
                '/vendor/eventtarget.js',
                '/vendor/base64.js',
                '/core/util.js',
                '/core/websock.js',
                '/core/des.js',
                '/core/rfb.js'
            ];
            
            var loadedCount = 0;
            var status = document.getElementById('status');
            
            function loadNextScript() {{
                if (loadedCount >= scripts.length) {{
                    initializeVNC();
                    return;
                }}
                
                var script = document.createElement('script');
                script.src = scriptBase + scripts[loadedCount];
                script.onload = function() {{
                    loadedCount++;
                    loadNextScript();
                }};
                script.onerror = function() {{
                    status.textContent = '✗ Failed to load ' + scripts[loadedCount];
                    status.style.color = '#ff0000';
                    console.error('[VNC] Failed to load:', scripts[loadedCount]);
                }};
                document.head.appendChild(script);
            }}
            
            function initializeVNC() {{
                status.textContent = 'Connecting to VNC...';
                status.style.color = '#0f0';
                
                var wsProtocol = (window.location.protocol === 'https:') ? 'wss' : 'ws';
                var wsHost = window.location.hostname;
                var wsPort = {novnc_port};
                var wsPath = '/websockify';
                var wsUrl = wsProtocol + '://' + wsHost + ':' + wsPort + wsPath;
                
                console.log('[VNC] WebSocket Configuration:');
                console.log('[VNC]   URL: ' + wsUrl);
                console.log('[VNC]   Host: ' + wsHost + ':' + wsPort);
                console.log('[VNC]   Protocol: ' + wsProtocol);
                
                var canvas = document.getElementById('canvas');
                
                try {{
                    var rfb = new RFB(canvas, wsUrl, {{ shared: true }});
                    
                    rfb.addEventListener('connect', function() {{
                        status.textContent = '✓ Connected to VNC';
                        status.style.color = '#00ff00';
                        console.log('[VNC] Connected successfully');
                    }});
                    
                    rfb.addEventListener('disconnect', function() {{
                        status.textContent = '✗ Disconnected';
                        status.style.color = '#ff0000';
                        console.log('[VNC] Disconnected');
                    }});
                    
                    rfb.addEventListener('error', function(e) {{
                        status.textContent = '✗ Error: ' + (e.detail.message || e.detail);
                        status.style.color = '#ff0000';
                        console.error('[VNC] Error:', e.detail);
                    }});
                    
                }} catch(e) {{
                    status.textContent = '✗ Init Error: ' + e.message;
                    status.style.color = '#ff0000';
                    console.error('[VNC] Failed to initialize RFB:', e);
                }}
            }}
            
            // Start loading scripts
            loadNextScript();
        }})();
    </script>
</body>
</html>'''
        
        return Response(vnc_html, mimetype='text/html')
        
    except Exception as e:
        print(f"[VNC_VIEWER_ERROR] {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vnc/health/<novnc_port>', methods=['GET'])
def check_vnc_health(novnc_port):
    """Check if VNC server is ready and accepting connections"""
    try:
        import socket
        
        novnc_port = int(novnc_port)
        server_host = '10.30.3.85'
        
        http_ok = False
        websocket_ok = False
        
        try:
            response = requests.get(
                f'http://{server_host}:{novnc_port}/vnc.html',
                timeout=5
            )
            http_ok = response.status_code == 200
            print(f"[VNC_HEALTH] HTTP check on port {novnc_port}: {response.status_code}")
        except Exception as e:
            print(f"[VNC_HEALTH] HTTP check failed on port {novnc_port}: {e}")
        
        try:
            sock = socket.create_connection(
                (server_host, novnc_port),
                timeout=5
            )
            sock.close()
            websocket_ok = True
            print(f"[VNC_HEALTH] WebSocket check on port {novnc_port}: OK")
        except Exception as e:
            print(f"[VNC_HEALTH] WebSocket check failed on port {novnc_port}: {e}")
        
        is_ready = http_ok and websocket_ok
        
        return jsonify({
            'ready': is_ready,
            'http_accessible': http_ok,
            'websocket_accessible': websocket_ok,
            'novnc_port': novnc_port,
            'server_host': server_host
        }), 200 if is_ready else 503
        
    except Exception as e:
        print(f"[VNC_HEALTH_ERROR] {e}")
        return jsonify({'error': str(e), 'ready': False}), 500


@app.route('/api/vnc/status/<user_email>', methods=['GET'])
def get_vnc_status(user_email):
    """Get VNC session status for a specific user"""
    try:
        user_email = unquote(user_email)
        print(f"[VNC_STATUS] Getting VNC status for user: {user_email}")
        
        from vnc_lifecycle_manager import vnc_lifecycle_manager
        
        status = vnc_lifecycle_manager.get_user_vnc_status(user_email)
        
        return jsonify(status), 200
        
    except Exception as e:
        print(f"[VNC_STATUS_ERROR] {e}")
        return jsonify({'error': str(e), 'has_active_session': False}), 500


@app.route('/api/vnc/cleanup/<user_email>', methods=['POST'])
def cleanup_vnc_for_user(user_email):
    """Kill/cleanup VNC session for a specific user (individual cleanup by login credentials)"""
    try:
        user_email = unquote(user_email)
        print(f"[VNC_CLEANUP] Cleanup request for user: {user_email}")
        
        from vnc_lifecycle_manager import vnc_lifecycle_manager
        
        success = vnc_lifecycle_manager.cleanup_user_vnc_session(user_email)
        
        if success:
            print(f"[VNC_CLEANUP] ✓ Successfully cleaned up VNC for {user_email}")
            return jsonify({
                'success': True,
                'message': f'VNC session terminated for {user_email}',
                'user_email': user_email
            }), 200
        else:
            print(f"[VNC_CLEANUP] ⚠ No active session found for {user_email}")
            return jsonify({
                'success': False,
                'message': f'No active VNC session found for {user_email}',
                'user_email': user_email
            }), 404
        
    except Exception as e:
        print(f"[VNC_CLEANUP_ERROR] {e}")
        return jsonify({'error': str(e), 'success': False}), 500


# Debug endpoint to simulate ID generation
@app.route('/api/debug-id-generation', methods=['POST'])
def debug_id_generation():
    """Debug endpoint to see what ID would be generated for a test case"""
    try:
        data = request.json
        project_name = data.get('project_name', 'IRCTC')
        module_name = data.get('module_name', 'Train')
        testcase_name = data.get('testcase_name', 'TestCase')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Sanitize components (same as generate_testcase_id)
        proj_part = sanitize_id_component(project_name)
        mod_part = sanitize_id_component(module_name)
        tc_part = sanitize_id_component(testcase_name)
        
        # Get the exact prefix that will be searched
        exact_prefix = f"{proj_part}_{mod_part}_"
        
        # Get existing IDs
        cursor.execute("""
            SELECT testcase_id FROM TestCases 
            WHERE testcase_id LIKE ?
            ORDER BY testcase_id
        """, (f"{exact_prefix}%_TC%",))
        
        all_matching_ids = cursor.fetchall()
        
        # Filter to ensure exact project-module match
        existing_ids = []
        import re
        for row in all_matching_ids:
            tc_id = row[0]
            if tc_id.startswith(exact_prefix):
                remaining = tc_id[len(exact_prefix):]
                if re.match(r'^.+_TC\d{3}$', remaining):
                    existing_ids.append(row)
        
        # Extract TC numbers
        existing_numbers = []
        for row in existing_ids:
            tc_id = row[0]
            match = re.search(r'_TC(\d{3})$', tc_id)
            if match:
                tc_num = int(match.group(1))
                existing_numbers.append(tc_num)
        
        # Find next available number
        if existing_numbers:
            existing_numbers.sort()
            next_num = 1
            for num in existing_numbers:
                if num == next_num:
                    next_num += 1
                else:
                    break
        else:
            next_num = 1
        
        # Generate the ID
        generated_id = f"{proj_part}_{mod_part}_{tc_part}_TC{next_num:03d}"
        
        conn.close()
        
        return jsonify({
            'success': True,
            'debug_info': {
                'project_name': project_name,
                'module_name': module_name,
                'testcase_name': testcase_name,
                'sanitized_project': proj_part,
                'sanitized_module': mod_part,
                'sanitized_testcase': tc_part,
                'exact_prefix': exact_prefix,
                'all_matching_ids': [row[0] for row in all_matching_ids],
                'filtered_existing_ids': [row[0] for row in existing_ids],
                'existing_numbers': existing_numbers,
                'next_available_number': next_num,
                'generated_id': generated_id
            }
        })
        
    except Exception as e:
        print(f"[ERROR] Debug ID generation error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/fix-testcase-ids', methods=['POST'])
def fix_testcase_ids():
    """Utility endpoint to fix tc_id values in existing test step tables"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all test cases
        cursor.execute("SELECT id, testcase_id, name FROM TestCases WHERE testcase_id IS NOT NULL")
        testcases = cursor.fetchall()
        
        fixed_count = 0
        results = []
        
        for testcase in testcases:
            testcase_db_id, proper_testcase_id, testcase_name = testcase

            # Get project and module info for generating unique table name
            cursor.execute("""
                SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.id = ?
            """, (testcase_db_id,))

            metadata = cursor.fetchone()
            if metadata:
                project_name = metadata[0]
                module_name = metadata[1]
                table_name = generate_unique_table_name(project_name, module_name, testcase_name)
            else:
                # Fallback to old naming
                table_name = sanitize_table_name(testcase_name)
            
            try:
                # Check if table exists
                cursor.execute(f"""
                    SELECT COUNT(*) FROM sysobjects WHERE name='{table_name}' AND xtype='U'
                """)
                if cursor.fetchone()[0] == 0:
                    results.append({
                        'testcase_name': testcase_name,
                        'status': 'skipped',
                        'reason': 'table_not_found'
                    })
                    continue
                
                # Check if there are steps with incorrect tc_id
                cursor.execute(f"""
                    SELECT COUNT(*) FROM [{table_name}] 
                    WHERE tc_id != ? AND tc_id IS NOT NULL
                """, (proper_testcase_id,))
                
                incorrect_count = cursor.fetchone()[0]
                
                if incorrect_count > 0:
                    # Update all tc_id values to the proper testcase_id
                    cursor.execute(f"""
                        UPDATE [{table_name}] 
                        SET tc_id = ?
                        WHERE tc_id != ? OR tc_id IS NULL
                    """, (proper_testcase_id, proper_testcase_id))
                    
                    fixed_count += 1
                    results.append({
                        'testcase_name': testcase_name,
                        'table_name': table_name,
                        'proper_testcase_id': proper_testcase_id,
                        'status': 'fixed',
                        'steps_updated': incorrect_count
                    })
                    print(f"[FIX] Updated {incorrect_count} steps in {table_name} with proper tc_id: {proper_testcase_id}")
                else:
                    results.append({
                        'testcase_name': testcase_name,
                        'status': 'already_correct',
                        'proper_testcase_id': proper_testcase_id
                    })
                    
            except Exception as table_error:
                results.append({
                    'testcase_name': testcase_name,
                    'status': 'error',
                    'error': str(table_error)
                })
                print(f"[ERROR] Failed to fix {testcase_name}: {str(table_error)}")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Fixed tc_id values for {fixed_count} test cases',
            'total_testcases': len(testcases),
            'fixed_count': fixed_count,
            'results': results
        })
        
    except Exception as e:
        print(f"[ERROR] Error fixing testcase IDs: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/renumber-testcases', methods=['POST'])
def renumber_testcases_endpoint():
    """Manually renumber test cases in a specific project-module"""
    try:
        data = request.get_json()
        project_name = data.get('project_name')
        module_name = data.get('module_name')
        
        if not project_name or not module_name:
            return jsonify({
                'success': False,
                'error': 'project_name and module_name are required'
            }), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print(f"[RENUMBER API] Manual renumbering requested for {project_name}-{module_name}")
        
        # Call the renumbering function
        renumber_info = renumber_testcases_after_deletion(cursor, project_name, module_name, "")
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'Successfully renumbered {renumber_info["total_renumbered"]} test cases',
            'details': renumber_info
        })
        
    except Exception as e:
        print(f"[ERROR] Manual renumbering error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Playwright-specific endpoints
@app.route('/api/playwright/execute/<testcase_name>', methods=['POST'])
def execute_testcase_playwright(testcase_name):
    """Execute a test case specifically using Playwright executor"""
    try:
        print(f"[PLAYWRIGHT] Starting Playwright test execution for: {testcase_name}")

        # Handle requests with or without JSON body
        request_data = None
        try:
            request_data = request.get_json()
            print(f"[PLAYWRIGHT] Request data: {request_data}")
        except Exception as e:
            print(f"[PLAYWRIGHT] No JSON body in request (this is OK): {e}")
            request_data = {}

        # Force executor type to playwright and server execution mode
        if not request_data:
            request_data = {}
        request_data['executor_type'] = 'playwright'
        request_data['server_execution'] = True

        # Use the existing execution logic
        return execute_single_testcase(testcase_name, request_data)

    except Exception as e:
        print(f"[ERROR] Playwright test execution failed: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'testcase_name': testcase_name,
            'executor_type': 'playwright'
        }), 500

@app.route('/api/selenium/execute/<testcase_name>', methods=['POST'])
def execute_testcase_selenium(testcase_name):
    """Execute a test case specifically using Selenium executor"""
    try:
        print(f"[SELENIUM] Starting Selenium test execution for: {testcase_name}")
        
        # Handle requests with or without JSON body
        request_data = None
        try:
            request_data = request.get_json()
            print(f"[SELENIUM] Request data: {request_data}")
        except Exception as e:
            print(f"[SELENIUM] No JSON body in request (this is OK): {e}")
            request_data = {}
        
        # Force executor type to selenium
        if not request_data:
            request_data = {}
        request_data['executor_type'] = 'selenium'
        
        # Use the existing execution logic
        return execute_single_testcase(testcase_name, request_data)
        
    except Exception as e:
        print(f"[ERROR] Selenium test execution failed: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': str(e),
            'testcase_name': testcase_name,
            'executor_type': 'selenium'
        }), 500


@app.route('/api/cypress/execute/<testcase_name>', methods=['POST'])
def execute_testcase_cypress(testcase_name):
    """Execute a test case specifically using Cypress executor"""
    try:
        print(f"[CYPRESS] Starting Cypress test execution for: {testcase_name}")

        # Handle requests with or without JSON body
        request_data = None
        try:
            request_data = request.get_json()
            print(f"[CYPRESS] Request data: {request_data}")
        except Exception as e:
            print(f"[CYPRESS] No JSON body in request (this is OK): {e}")
            request_data = {}

        # Force executor type to cypress
        if not request_data:
            request_data = {}
        request_data['executor_type'] = 'cypress'
        request_data['server_execution'] = True

        # Use the existing execution logic
        return execute_single_testcase(testcase_name, request_data)

    except Exception as e:
        print(f"[ERROR] Cypress test execution failed: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'testcase_name': testcase_name,
            'executor_type': 'cypress'
        }), 500

@app.route('/api/executors/available', methods=['GET'])
def get_available_executors():
    """Get list of available test executors"""
    try:
        executors = []
        
        # Check Selenium availability
        try:
            from selenium_executor import SeleniumTestExecutor
            executors.append({
                'name': 'selenium',
                'display_name': 'Selenium WebDriver',
                'description': 'Traditional Selenium WebDriver for cross-browser testing',
                'available': True,
                'browser_support': ['Chrome', 'Firefox', 'Edge', 'Safari'],
                'features': ['Cross-browser', 'Mature ecosystem', 'Wide language support']
            })
        except ImportError as e:
            executors.append({
                'name': 'selenium',
                'display_name': 'Selenium WebDriver',
                'description': 'Traditional Selenium WebDriver for cross-browser testing',
                'available': False,
                'error': str(e),
                'browser_support': [],
                'features': []
            })
        
        # Check Playwright availability
        try:
            from playwright_executor import PlaywrightTestExecutor
            executors.append({
                'name': 'playwright',
                'display_name': 'Playwright',
                'description': 'Modern browser automation with faster execution and better reliability',
                'available': True,
                'browser_support': ['Chromium', 'Firefox', 'WebKit'],
                'features': ['Fast execution', 'Auto-wait', 'Network interception', 'Mobile testing']
            })
        except ImportError as e:
            executors.append({
                'name': 'playwright',
                'display_name': 'Playwright',
                'description': 'Modern browser automation with faster execution and better reliability',
                'available': False,
                'error': str(e),
                'browser_support': [],
                'features': []
            })
        
        # Check Cypress availability
        try:
            from cypress_executor import CypressTestExecutor
            executors.append({
                'name': 'cypress',
                'display_name': 'Cypress',
                'description': 'Cypress E2E testing (runs via Node/NPM and Cypress runner)',
                'available': True,
                'browser_support': ['Chrome', 'Electron', 'Edge'],
                'features': ['Fast local runs', 'Time travel debugging', 'Network stubbing']
            })
        except ImportError as e:
            executors.append({
                'name': 'cypress',
                'display_name': 'Cypress',
                'description': 'Cypress E2E testing (runs via Node/NPM and Cypress runner)',
                'available': False,
                'error': str(e),
                'browser_support': [],
                'features': []
            })
        
        return jsonify({
            'success': True,
            'executors': executors,
            'default_executor': 'selenium'
        })
        
    except Exception as e:
        print(f"[ERROR] Error getting available executors: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/executors/test-connection', methods=['POST'])
def test_executor_connection():
    """Test connection to a specific executor"""
    try:
        data = request.get_json()
        executor_type = data.get('executor_type', 'selenium').lower()

        print(f"[TEST_CONNECTION] Testing {executor_type} executor connection...")

        if executor_type == 'playwright':
            try:
                from playwright_executor import PlaywrightTestExecutor
                executor = PlaywrightTestExecutor()

                # Test browser launch
                success = executor.launch_browser()
                if success:
                    executor.close_browser()
                    return jsonify({
                        'success': True,
                        'executor_type': 'playwright',
                        'message': 'Playwright executor connection successful',
                        'browser_info': 'Chromium browser launched and closed successfully'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'executor_type': 'playwright',
                        'error': 'Failed to launch Playwright browser'
                    }), 500

            except Exception as e:
                return jsonify({
                    'success': False,
                    'executor_type': 'playwright',
                    'error': f'Playwright executor error: {str(e)}'
                }), 500

        elif executor_type == 'selenium':
            try:
                from selenium_executor import SeleniumTestExecutor
                executor = SeleniumTestExecutor()

                # Test browser launch
                success = executor.launch_browser()
                if success:
                    executor.close_browser()
                    return jsonify({
                        'success': True,
                        'executor_type': 'selenium',
                        'message': 'Selenium executor connection successful',
                        'browser_info': 'Chrome browser launched and closed successfully'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'executor_type': 'selenium',
                        'error': 'Failed to launch Selenium browser'
                    }), 500

            except Exception as e:
                return jsonify({
                    'success': False,
                    'executor_type': 'selenium',
                    'error': f'Selenium executor error: {str(e)}'
                }), 500
        elif executor_type == 'cypress':
            try:
                # Quick check: ensure Cypress CLI is available via npx
                cmd = ["npx", "cypress", "--version"]
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)

                if proc.returncode == 0:
                    return jsonify({
                        'success': True,
                        'executor_type': 'cypress',
                        'message': 'Cypress CLI available via npx',
                        'browser_info': proc.stdout.strip()
                    })
                else:
                    return jsonify({
                        'success': False,
                        'executor_type': 'cypress',
                        'error': f'Cypress CLI returned non-zero status: {proc.stderr or proc.stdout}'
                    }), 500

            except Exception as e:
                return jsonify({
                    'success': False,
                    'executor_type': 'cypress',
                    'error': f'Cypress executor error: {str(e)}'
                }), 500
        else:
            return jsonify({
                'success': False,
                'error': f'Unknown executor type: {executor_type}'
            }), 400

    except Exception as e:
        print(f"[ERROR] Error testing executor connection: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/execute/server', methods=['POST'])
def execute_server():
    """Execute tests on server with optional live streaming"""
    try:
        print("[SERVER_EXECUTE] Starting server execution...")

        data = request.get_json() or {}
        user_email = request.headers.get('X-User-Email')

        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        test_cases = data.get('test_cases', [])
        selected_suites = data.get('selected_suites', [])
        executor_type = data.get('executor_type', 'selenium')
        enable_isolation = data.get('enable_isolation', True)
        enable_parallel = data.get('enable_parallel', False)
        max_concurrent = data.get('max_concurrent', 3)
        enable_streaming = data.get('enable_streaming', True)

        if not test_cases:
            return jsonify({'error': 'No test cases provided'}), 400

        execution_id = f"server_exec_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

        print(f"[SERVER_EXECUTE] Params:")
        print(f"  execution_id={execution_id}")
        print(f"  executor={executor_type}")
        print(f"  streaming={enable_streaming}")
        print(f"  user={user_email}")
        
        enriched_test_cases = []
        for tc in test_cases:
            enriched_tc = tc.copy()
            testcase_name = enriched_tc.get('name')
            # Normalize value-set flags for server execution payloads from UI
            if 'value_set_index' not in enriched_tc and 'valueSetIndex' in enriched_tc:
                enriched_tc['value_set_index'] = enriched_tc.get('valueSetIndex')
            if 'with_values' not in enriched_tc:
                execution_mode = str(enriched_tc.get('executionMode', '') or '').lower()
                enriched_tc['with_values'] = execution_mode == 'with_value'
            # FIX: Use actual suite_type from test case, don't default to "regression" unless truly missing
            suite_type = enriched_tc.get('suite_type') or enriched_tc.get('testsuitename')
            if not suite_type:
                # Only default to regression if no suite type is provided at all
                suite_type = "regression"
                print(f"[SERVER_EXEC] No suite_type provided for {testcase_name}, defaulting to 'regression'")
            else:
                print(f"[SERVER_EXEC] Using suite_type from test case: '{suite_type}' for {testcase_name}")
            
            if not enriched_tc.get('testcase_id'):
                enriched_tc['testcase_id'] = f"TC_{testcase_name}_001"
            
            if not enriched_tc.get('testrun_id'):
                try:
                    enriched_tc['testrun_id'] = generate_testrun_id(suite_type, testcase_name)
                except Exception as e:
                    print(f"[SERVER_EXECUTE] Error generating testrun_id: {e}")
                    enriched_tc['testrun_id'] = f"{suite_type}_{testcase_name}_TR001"
            
            if not enriched_tc.get('result_id') and enriched_tc.get('testrun_id'):
                try:
                    enriched_tc['result_id'] = generate_result_id(enriched_tc['testcase_id'], enriched_tc['testrun_id'])
                except Exception as e:
                    print(f"[SERVER_EXECUTE] Error generating result_id: {e}")
                    enriched_tc['result_id'] = "TC001_TR001"
            
            enriched_test_cases.append(enriched_tc)
            print(f"[SERVER_EXECUTE] - {testcase_name}: TC_ID={enriched_tc['testcase_id']}, TR_ID={enriched_tc.get('testrun_id')}, Result_ID={enriched_tc.get('result_id')}")
        
        test_cases = enriched_test_cases

        vnc_session_info = None
        
        if enable_streaming and user_email:
            print(f"[VNC] Creating VNC session for user: {user_email}")
            try:
                # Retry VNC session creation with exponential backoff
                max_attempts = 3
                for attempt in range(max_attempts):
                    print(f"[VNC] Attempt {attempt + 1}/{max_attempts} to create VNC session")
                    
                    vnc_session_info = vnc_manager.start_streaming_session(user_email, execution_id)
                    if vnc_session_info:
                        print(f"[VNC] Session created on attempt {attempt + 1}: {vnc_session_info.get('novnc_url')}")
                        break
                    else:
                        print(f"[VNC] Failed to create VNC session on attempt {attempt + 1}")
                        if attempt < max_attempts - 1:
                            retry_delay = 2 ** attempt  # 1s, 2s, 4s
                            print(f"[VNC] Retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                
                if not vnc_session_info:
                    print(f"[VNC] Failed to create VNC session after {max_attempts} attempts")
                    
            except Exception as vnc_error:
                print(f"[VNC] Error creating VNC session: {str(vnc_error)}")
                vnc_session_info = None

        server_manager = ServerExecutionManager(
            execution_id=execution_id,
            test_cases=test_cases,
            selected_suites=selected_suites,
            executor_type=executor_type,
            enable_isolation=enable_isolation,
            enable_parallel=enable_parallel,
            max_concurrent=max_concurrent,
            enable_streaming=enable_streaming,
            user_email=user_email,
            vnc_session_info=vnc_session_info,
        )

        def run_execution():
            try:
                print(f"[SERVER_EXECUTE] Background execution started: {execution_id}")
                results = server_manager.execute()
                print(f"[SERVER_EXECUTE] Background execution completed: {execution_id}")

                if results:
                    for result in results:
                        try:
                            store_selenium_results(
                                result.get('testcase_name', 'Unknown'),
                                result,
                                user_email
                            )
                        except Exception as store_err:
                            print(f"[SERVER_STORE] Error storing result: {store_err}")

                try:
                    auto_generate_allure_report()
                except Exception as report_err:
                    print(f"[ALLURE] Report generation failed: {report_err}")

            except Exception as e:
                print(f"[SERVER_EXECUTE] Execution failed: {e}")
                import traceback
                traceback.print_exc()

        execution_thread = threading.Thread(
            target=run_execution,
            daemon=True
        )
        execution_thread.start()

        novnc_url = ""
        session_id = ""
        if vnc_session_info:
            novnc_url = vnc_session_info.get("novnc_url", "")
            session_id = vnc_session_info.get("session_id", "")

        status = server_manager.get_status()
        response = {
            "success": True,
            "execution_id": execution_id,
            "execution_mode": "server",
            "executor_type": executor_type,
            "test_cases_count": len(test_cases),
            "parallel_execution": enable_parallel,
            "max_concurrent": max_concurrent if enable_parallel else 1,
            "streaming_active": enable_streaming,
            "vnc_status": status.get("vnc_status", {
                "vnc_failed": False,
                "running_headless": False,
                "execution_mode": "vnc"
            })
        }

        if novnc_url:
            response["novnc_url"] = novnc_url
        if session_id:
            response["session_id"] = session_id

        return jsonify(response), 200

    except Exception as e:
        print(f"[SERVER_EXECUTE_ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# Test Execution API - This will integrate with both Selenium and Playwright
@app.route('/api/execute/<testcase_name>', methods=['POST'])
def execute_testcase(testcase_name):
    try:
        print(f"[ROCKET] Starting test execution for: {testcase_name}")
        print(f"[REQUEST] Request method: {request.method}")

        # Handle requests with or without JSON body
        request_data = None
        try:
            request_data = request.get_json()
            print(f"[REQUEST] Request data: {request_data}")
        except Exception as e:
            print(f"[REQUEST] No JSON body in request (this is OK): {e}")
            request_data = {}

        # Extract user information from headers
        user_email = request.headers.get('X-User-Email')
        print(f"[USER_TRACKING] User email from headers: {user_email}")

        # Add user information to request data
        if request_data is None:
            request_data = {}
        request_data['user_email'] = user_email

        # Check if multiple suites are requested
        suite_types = request_data.get('suite_types', []) if request_data else []
        single_suite_type = request_data.get('suite_type') if request_data else None

        # If multiple suites are specified, execute for each suite
        if suite_types and len(suite_types) > 1:
            print(f"[MULTI_SUITE] Executing test case for multiple suites: {suite_types}")

            all_results = []
            overall_success = True

            for suite_type in suite_types:
                print(f"[MULTI_SUITE] Executing for suite: {suite_type}")

                # Create a modified request data for this specific suite
                suite_request_data = request_data.copy() if request_data else {}
                suite_request_data['suite_type'] = suite_type
                suite_request_data['suite_types'] = [suite_type]  # Single suite for this execution

                # Execute the test case for this specific suite
                try:
                    result = execute_single_testcase(testcase_name, suite_request_data)
                    all_results.append({
                        'suite_type': suite_type,
                        'result': result,
                        'success': result.get('success', False)
                    })

                    if not result.get('success', False):
                        overall_success = False

                except Exception as e:
                    print(f"[MULTI_SUITE] Error executing for suite {suite_type}: {str(e)}")
                    all_results.append({
                        'suite_type': suite_type,
                        'result': {'success': False, 'error': str(e)},
                        'success': False
                    })
                    overall_success = False

            return jsonify({
               'success': overall_success,
                 'multi_suite_execution': True,
                 'suite_results': all_results,
                 'total_suites': len(suite_types),
                 'successful_suites': sum(1 for r in all_results if r['success']),
                 'testcase_name': testcase_name
            })

        else:
            # Single suite execution (existing logic)
            return execute_single_testcase(testcase_name, request_data)
    except Exception as e:
        print(f"[ERROR] Test execution failed: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': str(e),
            'testcase_name': testcase_name
        }), 500

def execute_single_testcase(testcase_name, request_data=None):
    """Execute a single test case for a single suite"""
    try:
        print(f"[SINGLE_SUITE] Executing test case: {testcase_name}")
        if request_data:
            print(f"[SINGLE_SUITE] Request data: {request_data}")

        # Extract user information for tracking
        user_email = None
        if request_data and 'user_email' in request_data:
            user_email = request_data['user_email']
        elif hasattr(request, 'headers') and request.headers.get('X-User-Email'):
            user_email = request.headers.get('X-User-Email')

        print(f"[SINGLE_SUITE] User email for tracking: {user_email}")

        vnc_session = None
        
        # Load test steps from database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get project and module info for the testcase to generate correct table name
        cursor.execute("""
            SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                   COALESCE(m.module_name, 'Unknown') as module_name
            FROM TestCases tc
            LEFT JOIN Modules m ON tc.module_id = m.id
            LEFT JOIN Projects p1 ON tc.project_id = p1.id
            LEFT JOIN Projects p2 ON m.project_id = p2.id
            WHERE tc.name = ?
        """, (testcase_name,))

        metadata = cursor.fetchone()
        if metadata:
            project_name = metadata[0]
            module_name = metadata[1]
            table_name = generate_unique_table_name(project_name, module_name, testcase_name)
        else:
            # Get project and module info for generating unique table name
            cursor.execute("""
                SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                       COALESCE(m.module_name, 'Unknown') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.name = ?
            """, (testcase_name,))

            metadata = cursor.fetchone()
            if metadata:
                project_name = metadata[0]
                module_name = metadata[1]
                table_name = generate_unique_table_name(project_name, module_name, testcase_name)
            else:
                # Fallback to old naming for backward compatibility
                table_name = sanitize_table_name(testcase_name)

        print(f"[SEARCH] Looking for test steps in table: {table_name}")

        # Check if table exists
        cursor.execute(f"SELECT COUNT(*) FROM sysobjects WHERE name='{table_name}' AND xtype='U'")
        if cursor.fetchone()[0] == 0:
            conn.close()
            print(f"[ERROR] Test case table '{table_name}' not found")
            return {
                'success': False,
                'error': f'Test case table "{table_name}" does not exist. Please create test steps first.',
                'testcase_name': testcase_name
            }

        cursor.execute(f"SELECT tc_id, step_no, test_step_description, element_name, action_type, xpath, [values] FROM [{table_name}] ORDER BY step_no")

        test_steps = []
        for row in cursor.fetchall():
            test_steps.append({
                'tc_id': row[0],
                'step_no': row[1],
                'test_step_description': row[2],
                'element_name': row[3],
                'action_type': row[4],
                'xpath': row[5],
                'values': row[6]
            })

        cursor.close()  # Close cursor before closing connection
        conn.close()
        
        if not test_steps:
           return {'success': False, 'error': 'No test steps found', 'testcase_name': testcase_name}
        
        print(f"[INFO] Found {len(test_steps)} test steps")
        
        # Check if this is a WITH_VALUES execution and fetch Excel data
        with_values = request_data.get('with_values', False) if request_data else False
        value_set_index = request_data.get('value_set_index') if request_data else None
        
        print(f"[WITH_VALUES] Execution mode: with_values={with_values}, value_set_index={value_set_index}")
        
        if with_values and value_set_index is not None:
            print(f"[EXCEL_FETCH] Attempting to fetch Excel data for test case: {testcase_name}")
            try:
                try:
                    value_set_index = int(value_set_index)
                except Exception:
                    print(f"[EXCEL_FETCH] ERROR: Invalid value_set_index '{value_set_index}'")
                    value_set_index = None

                if value_set_index is None:
                    raise ValueError("value_set_index is not a valid integer")

                # Get the mapped Excel file name from database
                conn_excel = get_db_connection()
                cursor_excel = conn_excel.cursor()
                cursor_excel.execute("""
                    SELECT mapped_excel_file_name, mapped_excel_sheet_name
                    FROM TestCases
                    WHERE name = ?
                """, (testcase_name,))
                result = cursor_excel.fetchone()
                if not result:
                    cursor_excel.execute("""
                        SELECT mapped_excel_file_name, mapped_excel_sheet_name
                        FROM TestCases
                        WHERE LOWER(name) = LOWER(?)
                    """, (testcase_name,))
                    result = cursor_excel.fetchone()
                mapped_excel_name = result[0] if result and result[0] else None
                mapped_sheet_name = result[1] if result and len(result) > 1 and result[1] else None
                cursor_excel.close()
                conn_excel.close()
                
                if not mapped_excel_name:
                    print(f"[EXCEL_FETCH] WARNING: No Excel file mapped for test case: {testcase_name}")
                else:
                    print(f"[EXCEL_FETCH] Found mapped Excel file: {mapped_excel_name}")
                    
                    # Try to find and read the Excel file
                    conn_file = get_db_connection()
                    cursor_file = conn_file.cursor()
                    fallback_sheet_name = None
                    cursor_file.execute("""
                        SELECT TOP 1 file_path
                        FROM [Values]
                        WHERE original_name = ? AND status = 'Active'
                        ORDER BY id DESC
                    """, (mapped_excel_name,))
                    file_result = cursor_file.fetchone()
                    if not file_result:
                        cursor_file.execute("""
                            SELECT TOP 1 file_path
                            FROM [Values]
                            WHERE LOWER(original_name) = LOWER(?) AND status = 'Active'
                            ORDER BY id DESC
                        """, (mapped_excel_name,))
                        file_result = cursor_file.fetchone()
                    # Fallback: mapped value might be a sheet name instead of file name
                    if not file_result:
                        cursor_file.execute("""
                            SELECT TOP 1 file_path, original_name
                            FROM [Values]
                            WHERE status = 'Active'
                            ORDER BY id DESC
                        """)
                        latest_file = cursor_file.fetchone()
                        if latest_file and latest_file[0] and os.path.exists(latest_file[0]):
                            try:
                                import pandas as pd
                                latest_excel = pd.read_excel(latest_file[0], sheet_name=None, header=0)
                                if latest_excel:
                                    target_sheet = mapped_sheet_name or mapped_excel_name
                                    if target_sheet and target_sheet in latest_excel:
                                        file_result = (latest_file[0],)
                                        fallback_sheet_name = target_sheet
                                        print(f"[EXCEL_FETCH] Fallback matched sheet '{target_sheet}' in latest file '{latest_file[1]}'")
                            except Exception as fallback_err:
                                print(f"[EXCEL_FETCH] Fallback sheet lookup failed: {fallback_err}")
                    cursor_file.close()
                    conn_file.close()
                    
                    if file_result:
                        file_path = file_result[0]
                        print(f"[EXCEL_FETCH] Found file path: {file_path}")
                        
                        if os.path.exists(file_path):
                            try:
                                import pandas as pd
                                
                                # Read Excel file
                                excel_data = pd.read_excel(file_path, sheet_name=None, header=0)
                                if excel_data:
                                    if fallback_sheet_name and fallback_sheet_name in excel_data:
                                        sheet_name = fallback_sheet_name
                                    elif mapped_sheet_name and mapped_sheet_name in excel_data:
                                        sheet_name = mapped_sheet_name
                                    else:
                                        sheet_name = list(excel_data.keys())[0]
                                    df = excel_data[sheet_name]
                                    
                                    # Determine Excel layout and map accordingly.
                                    # Two supported layouts:
                                    # 1) Field-columns with rows as datasets (legacy behavior)
                                    #    - headers = column names (placeholders like {{field}} expected)
                                    #    - each row is a dataset; value_set_index selects the row
                                    # 2) Datasets-as-columns with rows mapping to test steps (requested behavior)
                                    #    - columns are datasets; each column contains values for steps (row i -> step i)
                                    headers = df.columns.tolist()
                                    num_rows = len(df)
                                    num_cols = df.shape[1] if hasattr(df, 'shape') else len(headers)
                                    selected_header = str(headers[value_set_index]) if value_set_index < len(headers) else ''
                                    # Pandas appends .1/.2 to duplicate headers; normalize URL headers back.
                                    selected_header_clean = re.sub(r'\.\d+$', '', selected_header.strip())
                                    header_is_url = bool(re.match(r'^https?://', selected_header_clean, re.IGNORECASE))

                                    print(f"[EXCEL_FETCH] Excel structure: {num_cols} columns, {num_rows} rows")
                                    print(f"[EXCEL_FETCH] Field names (column headers): {headers}")

                                    # Detect if step.values contain placeholders like {{field}} anywhere
                                    placeholder_pattern = re.compile(r"\{\{(\w+)\}\}")
                                    has_placeholders = any(
                                        bool(placeholder_pattern.search(str(step.get('values', ''))))
                                        for step in test_steps
                                    )

                                    # Always use column-as-dataset mapping: columns are datasets, rows map to test steps
                                    mapped_test_steps = []
                                    print("[EXCEL_FETCH] Using column-as-dataset mapping (columns = datasets, rows -> steps)")

                                    if value_set_index < num_cols:
                                        for step_index, step in enumerate(test_steps):
                                            mapped_step = step.copy()
                                            cell_value = ''
                                            try:
                                                if step_index == 0 and header_is_url:
                                                    # Excel has URL in header cell (first visual row) for this column.
                                                    cell_value = selected_header_clean
                                                else:
                                                    row_index = step_index - 1 if header_is_url else step_index
                                                    if row_index < num_rows:
                                                        cell_value = df.iat[row_index, value_set_index]
                                                    if pd.isna(cell_value):
                                                        cell_value = ''
                                                    elif hasattr(cell_value, 'item'):
                                                        cell_value = cell_value.item()
                                                    cell_value = str(cell_value)
                                            except Exception as cell_err:
                                                print(f"[EXCEL_FETCH] Warning reading cell (row={step_index}, col={value_set_index}): {cell_err}")
                                                cell_value = ''

                                            # Set the step's values to the cell content
                                            mapped_step['values'] = cell_value
                                            print(f"[EXCEL_MAPPING] Step {step.get('step_no')}: values set to '{cell_value}' from cell (row={step_index}, col={value_set_index})")

                                            # Map element_name placeholders from cell if present
                                            if step.get('element_name') and '{{' in str(step.get('element_name', '')):
                                                mapped_element = re.sub(r"\{\{\s*\w+\s*\}\}", cell_value, str(step['element_name']))
                                                mapped_step['element_name'] = mapped_element

                                            mapped_test_steps.append(mapped_step)
                                    else:
                                        print(f"[EXCEL_FETCH] ERROR: value_set_index {value_set_index} exceeds data column count {num_cols}")

                                    if mapped_test_steps:
                                        test_steps = mapped_test_steps
                                        print(f"[EXCEL_MAPPING] Applied Excel mapping for data set index {value_set_index} to {len(mapped_test_steps)} test steps")
                            except Exception as excel_error:
                                print(f"[EXCEL_FETCH] ERROR reading Excel file: {str(excel_error)}")
                                import traceback
                                traceback.print_exc()
                        else:
                            print(f"[EXCEL_FETCH] ERROR: File not found at path: {file_path}")
                    else:
                        print(f"[EXCEL_FETCH] ERROR: Excel file '{mapped_excel_name}' not found in database")
            except Exception as e:
                print(f"[EXCEL_FETCH] ERROR: Failed to fetch Excel data: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # Debug: Print first few test steps
        print("[DEBUG] Sample test steps from database:")
        for i, step in enumerate(test_steps[:3], 1):  # Show first 3 steps
            print(f"  Step {i}: action_type='{step.get('action_type', 'N/A')}', description='{step.get('test_step_description', 'N/A')[:50]}...'")
        if len(test_steps) > 3:
            print(f"  ... and {len(test_steps) - 3} more steps")
        
        # Get test case info to generate IDs
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get test case details including testcase_id, suite_type, module_id, and project_id
        # Use COALESCE to get project info from either testcase.project_id or module.project_id
        cursor.execute("""
            SELECT tc.testcase_id, tc.suite_type, tc.module_id, tc.project_id,
                   COALESCE(m.module_name, 'Unknown Module') as module_name, 
                   m.project_id as module_project_id,
                   COALESCE(p1.name, p2.name, 'Unknown Project') as project_name,
                   COALESCE(tc.project_id, m.project_id) as resolved_project_id
            FROM TestCases tc 
            LEFT JOIN Modules m ON tc.module_id = m.id 
            LEFT JOIN Projects p1 ON tc.project_id = p1.id 
            LEFT JOIN Projects p2 ON m.project_id = p2.id
            WHERE tc.name = ?
        """, (testcase_name,))
        testcase_info = cursor.fetchone()
        
        # Debug: Log the testcase info query result
        print(f"[DEBUG] Testcase info query result for '{testcase_name}':")
        if testcase_info:
            print(f"  testcase_id: {testcase_info[0]}")
            print(f"  suite_type: {testcase_info[1]}")
            print(f"  module_id: {testcase_info[2]}")
            print(f"  testcase_project_id: {testcase_info[3]}")
            print(f"  module_name: {testcase_info[4]}")
            print(f"  module_project_id: {testcase_info[5]}")
            print(f"  project_name: {testcase_info[6]}")
            print(f"  resolved_project_id: {testcase_info[7]}")
        else:
            print(f"  No testcase info found for '{testcase_name}'")
        
        # Close cursor to avoid "Connection is busy" error
        cursor.close()
        
        if testcase_info:
            testcase_id = testcase_info[0] if testcase_info[0] else f"TC_{testcase_name}_001"
            # Use suite_type from request data (UI selection) if provided, otherwise fallback to database
            suite_type_from_request = request_data.get('suite_type') if request_data else None
            suite_type_from_db = testcase_info[1] if testcase_info[1] else "regression"
            
            if suite_type_from_request:
                suite_type = suite_type_from_request
                print(f"[SUITE_TYPE] Using suite_type from UI request: '{suite_type}'")
            else:
                suite_type = suite_type_from_db
                print(f"[SUITE_TYPE] Using suite_type from database: '{suite_type}'")
            
            module_id = testcase_info[2]
            testcase_project_id = testcase_info[3]
            module_name = testcase_info[4]  # Already handled by COALESCE in SQL
            module_project_id = testcase_info[5]
            project_name = testcase_info[6]  # Already handled by COALESCE in SQL
            resolved_project_id = testcase_info[7]  # Already handled by COALESCE in SQL
            
            # Use the resolved project_id from the COALESCE
            project_id = resolved_project_id;
            
            print(f"[DEBUG] Final metadata values:")
            print(f"  project_name: '{project_name}'")
            print(f"  module_name: '{module_name}'")
            print(f"  suite_type: '{suite_type}'")
            
        else:
            testcase_id = f"TC_{testcase_name}_001"
            # Use suite_type from request data (UI selection) if provided, otherwise default to regression
            suite_type_from_request = request_data.get('suite_type') if request_data else None
            
            # Define suite name mapping - only allow sanity, smoke, regression
            suite_name_mapping = {
                'sanity': 'sanity',
                'smoke': 'smoke',
                'regression': 'regression',
                # Legacy mappings for any old incorrect values
                'functional': 'sanity',
                'development': 'regression',
                'general': 'sanity',
                'unknown': 'regression'
            }
            
            if suite_type_from_request:
                # Map the suite type to ensure only correct values are used
                # Allow custom suite names - only map legacy values, use others as-is
                suite_type_lower = suite_type_from_request.lower()
                if suite_type_lower in suite_name_mapping:
                    suite_type = suite_name_mapping[suite_type_lower]
                else:
                    # Use custom suite name as-is
                    suite_type = suite_type_lower
                print(f"[SUITE_TYPE] Mapped UI request '{suite_type_from_request}' -> '{suite_type}'")
            else:
                suite_type = "regression"
                print(f"[SUITE_TYPE] Using default suite_type: '{suite_type}'")
            module_id = None
            project_id = None
            module_name = "Unknown Module"
            project_name = "Unknown Project"
        
        # Generate TestRun_id and Result_id
        testrun_id = generate_testrun_id(suite_type, testcase_name, conn)
        result_id = generate_result_id(testcase_id, testrun_id)
        
        conn.close()
        
        # Determine which executor to use (default to playwright)
        executor_type = request_data.get('executor_type', 'playwright').lower()

        # Determine if this is server execution (affects headless mode for Playwright)
        is_server_execution = request_data.get('server_execution', False) if request_data else False
        print(f"[EXECUTION_MODE] Server execution mode: {is_server_execution}")

        execution_id = str(uuid.uuid4())
        if user_email and is_server_execution:
            print(f"[VNC] Starting VNC session for user: {user_email}")
            try:
                vnc_session = vnc_manager.start_streaming_session(user_email, execution_id)
                if vnc_session:
                    print(f"[VNC] Session started: {vnc_session.get('novnc_url')}")
                else:
                    print(f"[VNC] Failed to start streaming session")
            except Exception as vnc_error:
                print(f"[VNC] Error starting VNC session: {str(vnc_error)}")
                vnc_session = None

        # Get user information for Allure results
        user_info = {'username': '', 'role': ''}
        if user_email:
            try:
                # Get user details from Authentication table
                conn_user = get_db_connection()
                cursor_user = conn_user.cursor()
                cursor_user.execute("""
                    SELECT username, role FROM Authentication
                    WHERE email = ? AND status = 'Approved'
                """, (user_email,))
                user_data = cursor_user.fetchone()
                if user_data:
                    user_info['username'] = user_data[0] or ''
                    user_info['role'] = user_data[1] or ''
                conn_user.close()
            except Exception as e:
                print(f"[WARNING] Could not retrieve user info for Allure results: {str(e)}")

        # Prepare metadata to pass to executor
        test_metadata = {
            'testcase_id': testcase_id,
            'testrun_id': testrun_id,
            'result_id': result_id,
            'suite_type': suite_type,
            'module_name': module_name,
            'project_name': project_name,
            'module_id': module_id,
            'project_id': project_id,
            'username': user_info['username'],
            'role': user_info['role']
        }

        if executor_type == 'playwright':
            print("[PLAYWRIGHT] Creating PlaywrightTestExecutor instance...")
            from playwright_executor import PlaywrightTestExecutor
            display_id = vnc_session.get('display') if vnc_session else None
            executor = PlaywrightTestExecutor(server_execution=is_server_execution, vnc_session=vnc_session, display_id=display_id)
            print(f"[PLAYWRIGHT] Starting test case execution (server_execution={is_server_execution})...")
            result = executor.execute_test_case(testcase_name, test_steps, test_metadata)
            print(f"[ALLURE_DEBUG] PlaywrightTestExecutor result status: {result.get('status')}")

        elif executor_type == 'cypress':
            print("[CYPRESS] Creating CypressTestExecutor instance...")
            from cypress_executor import CypressTestExecutor
            # Get headless setting from request data, default to False (window opens)
            headless = request_data.get('headless', False) if request_data else False
            print(f"[CYPRESS] Headless mode: {headless} (Window will {'NOT ' if not headless else ''}open)")
            executor = CypressTestExecutor(server_execution=is_server_execution, headless=headless)
            print(f"[CYPRESS] Starting test case execution (server_execution={is_server_execution})...")
            result = executor.execute_test_case(testcase_name, test_steps, test_metadata)
            print(f"[ALLURE_DEBUG] CypressTestExecutor result status: {result.get('status')}")
            print(f"[CYPRESS] Test execution completed")

        else: # Default to selenium
            # Execute test steps using your Selenium code
            from selenium_executor import SeleniumTestExecutor
            print("[SELENIUM] Creating SeleniumTestExecutor instance...")
            executor = SeleniumTestExecutor()

            print("[SELENIUM] Starting test case execution...")
            result = executor.execute_test_case(testcase_name, test_steps, test_metadata)
            print(f"[ALLURE_DEBUG] SeleniumTestExecutor result status: {result.get('status')}")
            print(f"[ALLURE_DEBUG] SeleniumTestExecutor result suite_type: {result.get('suite_type')}")

        if not result:
            raise Exception(f"{executor_type.capitalize()}TestExecutor returned null/undefined result")

        # Add executor_type to result for proper storage
        result['executor_type'] = executor_type

        # Metadata is already included in result from executor

        # Store results in selenium_results table
        store_selenium_results(testcase_name, result, user_email)
        
        # Auto-generate Allure report after test execution
        try:
            print("[ALLURE] Auto-generating Allure report after test execution...")
            success = auto_generate_allure_report()
            if success:
                print("[ALLURE] Auto-generation completed successfully")
            else:
                print("[ALLURE] Auto-generation failed or skipped")
        except Exception as e:
            print(f"[WARNING] Failed to auto-generate Allure report: {str(e)}")
            traceback.print_exc()
        
        # Transform result to match frontend expectations
        api_result = {
            'success': result.get('status') == 'PASS',
            'status': result.get('status'),
            'execution_id': result.get('execution_id'),
            'testcase_name': result.get('testcase_name'),
            'total_steps': result.get('total_steps'),
            'passed_steps': result.get('passed_steps'),
            'failed_steps': result.get('failed_steps'),
            'skipped_steps': result.get('skipped_steps'),
            'execution_time': result.get('execution_time'),
            'start_time': result.get('start_time'),
            'end_time': result.get('end_time'),
            'error_message': result.get('error_message'),
            'step_results': result.get('step_results'),
            'browser_info': result.get('browser_info')
        }

        if vnc_session:
            api_result['vnc_url'] = vnc_session.get('novnc_url')
            api_result['vnc_port'] = vnc_session.get('vnc_port')
            api_result['session_id'] = vnc_session.get('session_id')
            print(f"[VNC] VNC URL included in response: {vnc_session.get('novnc_url')}")

        # Add user information to the result
        if user_email:
            try:
                # Get user details from Authentication table
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT username, role FROM Authentication
                    WHERE email = ? AND status = 'Approved'
                """, (user_email,))
                user_data = cursor.fetchone()
                if user_data:
                    api_result['username'] = user_data[0] or ''
                    api_result['role'] = user_data[1] or ''
                    print(f"[USER_INFO] Added user info to result: username='{api_result['username']}', role='{api_result['role']}'")
                else:
                    api_result['username'] = ''
                    api_result['role'] = ''
                    print(f"[USER_INFO] No user data found for email: {user_email}")
                conn.close()
            except Exception as e:
                print(f"[WARNING] Could not retrieve user info for result: {str(e)}")
                api_result['username'] = ''
                api_result['role'] = ''
        else:
            api_result['username'] = ''
            api_result['role'] = ''
            print(f"[USER_INFO] No user_email provided")

        print(f"[SUCCESS] Test execution completed for: {testcase_name}")
        return api_result
        
    except Exception as e:
        print(f"[ERROR] Single test execution failed: {str(e)}")
        traceback.print_exc()
        return {'success': False, 'error': str(e), 'testcase_name': testcase_name}
    finally:
        # VNC session cleanup removed - keep VNC alive for remote viewing
        # Users must explicitly stop VNC or it will timeout after idle period
        # if vnc_session:
        #     print(f"[VNC] Cleaning up VNC session: {vnc_session.get('session_id')}")
        #     try:
        #         vnc_manager.stop_user_vnc_session(vnc_session.get('session_id'))
        #         print(f"[VNC] Session cleaned up successfully")
        #     except Exception as e:
        #         print(f"[VNC] Error during cleanup: {str(e)}")
        pass



@app.route('/api/results', methods=['GET'])
def get_all_results():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Ensure selenium_results table exists
        create_selenium_results_table()
        
        cursor.execute("""
            SELECT id, testcase_name, projectname, modulename, testsuitename, testcasename, status,
                   total_steps, passed_steps, failed_steps, skipped_steps, execution_time,
                   start_time, end_time, error_message, step_details, browser_info, created_date,
                   testcase_id, testrun_id, result_id, username, role, executor_type
            FROM selenium_results
            ORDER BY created_date DESC
        """)
        
        results = []
        for row in cursor.fetchall():
            results.append({
                'id': row[0],
                'testcase_name': row[1],
                'projectname': row[2],  # Add project name
                'modulename': row[3],   # Add module name
                'testsuitename': row[4], # Add test suite name
                'testcasename': row[5],  # Add test case name
                'execution_id': row[20] if row[20] else f"EXEC_{row[0]}",
                'status': row[6],
                'total_steps': row[7],
                'passed_steps': row[8],
                'failed_steps': row[9],
                'skipped_steps': row[10],
                'execution_time': row[11],
                'start_time': format_timestamp(row[12]) if row[12] else None,
                'end_time': format_timestamp(row[13]) if row[13] else None,
                'error_message': row[14],
                'step_details': row[15],  # Add step details
                'browser_info': row[16],
                'created_date': format_timestamp(row[17]) if row[17] else None,
                'testcase_id': row[18],   # Add testcase_id
                'testrun_id': row[19],    # Add testrun_id
                'result_id': row[20],     # Add result_id
                'username': row[21] or '',  # Add username
                'role': row[22] or '',       # Add role
                'executor_type': row[23] or 'selenium'  # Add executor_type
            })
        
        conn.close()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Results API (Updated to match old working version)
@app.route('/api/results/<testcase_name>', methods=['GET'])
def get_results(testcase_name):
    try:
        print(f"[API] Getting results for testcase: {testcase_name}")
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Add cache-busting and force fresh data
        cursor.execute("""
            SELECT id, testcase_name, projectname, modulename, testsuitename, testcasename, status,
                   total_steps, passed_steps, failed_steps, skipped_steps, execution_time,
                   start_time, end_time, error_message, step_details, browser_info, created_date,
                   testcase_id, testrun_id, result_id, username, role, executor_type
            FROM selenium_results
            WHERE testcase_name = ?
            ORDER BY created_date DESC
        """, (testcase_name,))
        
        results = []
        for row in cursor.fetchall():
            step_details = []
            try:
                if row[15]:  # step_details index
                    step_details = json.loads(row[15])
            except:
                step_details = []
                
            results.append({
                'id': row[0],  # Database ID
                'testcase_id': row[18] if row[18] else 'TC001',  # Generated testcase ID
                'testrun_id': row[19] if row[19] else 'TR001',  # Generated testrun ID
                'result_id': row[20] if row[20] else 'R001',  # Generated result ID
                'testcase_name': row[1],
                'tc_id': row[18] if row[18] else 'TC001',  # For frontend compatibility
                'test_mode': 'Automated',  # Added for frontend compatibility
                'status': row[6],
                'total_steps': row[7],
                'passed_steps': row[8],
                'failed_steps': row[9],
                'skipped_steps': row[10],
                'execution_time': row[11],
                'test_data': f"Browser: {row[16]}" if row[16] else "Browser: Chrome",  # Added for frontend compatibility
                'step_results': step_details,  # Frontend expects step_results, not step_details
                'error_message': row[14],
                'execution_date': format_timestamp(row[17]) if row[17] else None,  # Changed from 'created_date' to 'execution_date' for frontend compatibility
                'username': row[21] or '',  # Add username
                'role': row[22] or '',         # Add role
                'executor_type': row[23] or 'selenium'  # Add executor_type
            })
        
        conn.close()
        
        print(f"[API] Returning {len(results)} results for {testcase_name}")
        
        # Create response with cache-busting headers
        response = jsonify(results)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        response.headers['X-Timestamp'] = str(int(time.time()))
        
        return response
    except Exception as e:
        print(f"[API_ERROR] Error getting results for {testcase_name}: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/execution-details/<execution_id>', methods=['GET'])
def get_execution_details(execution_id: str):
    """Get detailed execution results by execution_id, result_id, or database ID"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if execution_id is a numeric database ID
        is_numeric_id = execution_id.isdigit()
        
        if is_numeric_id:
            # Query by database ID
            cursor.execute("""
                SELECT
                    id,
                    testcase_id,
                    testrun_id,
                    result_id,
                    testcase_name,
                    testcase_id as tc_id,
                    testsuitename as test_mode,
                    status,
                    total_steps,
                    passed_steps,
                    failed_steps,
                    execution_time,
                    step_details as test_data,
                    error_message,
                    created_date as execution_date,
                    start_time,
                    end_time,
                    browser_info,
                    page,
                    username,
                    role,
                    executor_type
                FROM selenium_results
                WHERE id = ?
                ORDER BY created_date DESC
            """, (int(execution_id),))
        else:
            # Query by result_id or execution_id
            cursor.execute("""
                SELECT
                    id,
                    testcase_id,
                    testrun_id,
                    result_id,
                    testcase_name,
                    testcase_id as tc_id,
                    testsuitename as test_mode,
                    status,
                    total_steps,
                    passed_steps,
                    failed_steps,
                    execution_time,
                    step_details as test_data,
                    error_message,
                    created_date as execution_date,
                    start_time,
                    end_time,
                    browser_info,
                    page,
                    username,
                    role
                FROM selenium_results
                WHERE result_id = ? OR COALESCE(result_id, CONCAT('EXEC_', CAST(id AS NVARCHAR(10)))) = ?
                ORDER BY created_date DESC
            """, (execution_id, execution_id))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({'error': 'Execution not found'}), 404
        
        # Parse step_details JSON if it exists
        step_results = []
        if row[12]:  # test_data/step_details
            try:
                import json
                step_data = json.loads(row[12])
                if isinstance(step_data, list):
                    step_results = step_data
                elif isinstance(step_data, dict) and 'steps' in step_data:
                    step_results = step_data['steps']
            except:
                step_results = []
        
        result = {
            'id': row[0],
            'testcase_id': row[1] or '',
            'testrun_id': row[2] or '',
            'result_id': row[3] or '',
            'testcase_name': row[4],
            'tc_id': row[5] or '',
            'test_mode': row[6] or 'Regression',
            'status': row[7],
            'total_steps': row[8] or 0,
            'passed_steps': row[9] or 0,
            'failed_steps': row[10] or 0,
            'execution_time': row[11] or '0s',
            'test_data': row[12] or '',
            'step_results': step_results,
            'step_details': step_results,  # Alias for compatibility
            'error_message': row[13] or '',
            'execution_date': format_timestamp(row[14]) if row[14] else '',
            'start_time': format_timestamp(row[15]) if row[15] else '',
            'end_time': format_timestamp(row[16]) if row[16] else '',
            'browser_info': row[17] or '',
            'page': row[18] or '',
            'username': row[19] or '',
            'role': row[20] or ''
        }
        
        conn.close()
        return jsonify(result)
        
    except Exception as e:
        print(f"[ERROR] Error fetching execution details for {execution_id}: {str(e)}")
        return jsonify({
            'error': str(e)
        }), 500

# Allure Integration API Endpoints
@app.route('/api/allure/status', methods=['GET'])
def allure_status():
    """Check if Allure results are available"""
    try:
        # Get the project root directory (parent of new_backend)
        current_dir = os.getcwd()
        if current_dir.endswith('new_backend'):
            project_root = os.path.dirname(current_dir)
        else:
            project_root = current_dir
            
        allure_results_path = os.path.join(project_root, 'allure-results-new')
        allure_report_path = os.path.join(project_root, 'allure-report')
        
        if not os.path.exists(allure_results_path):
            return jsonify({
                'available': False,
                'report_ready': False,
                'message': 'No allure-results-new directory found'
            })
        
        # Check if there are any result files
        result_files = [f for f in os.listdir(allure_results_path) if f.endswith('.json')]
        
        # Check if report has been generated
        report_ready = os.path.exists(allure_report_path) and os.path.exists(os.path.join(allure_report_path, 'index.html'))
        
        return jsonify({
            'available': len(result_files) > 0,
            'report_ready': report_ready,
            'result_files': len(result_files),
            'report_url': f"http://{get_allure_report_host()}/allure-report/index.html" if report_ready else None,
            'path': allure_results_path
        })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/allure/force-regenerate', methods=['POST'])
def force_regenerate_allure():
    """Force regeneration of Allure report (bypasses timestamp check)"""
    try:
        print("[ALLURE] Force regenerating Allure report...")

        # Detect OS and use appropriate executable
        import platform
        is_windows = platform.system() == 'Windows'
        print(f"[ALLURE] Detected OS: {platform.system()}, is_windows: {is_windows}")

        # Get the project root directory (parent of new_backend)
        current_dir = os.getcwd()
        if current_dir.endswith('new_backend'):
            project_root = os.path.dirname(current_dir)
        else:
            project_root = current_dir

        allure_results_path = os.path.join(project_root, 'allure-results-new')
        allure_report_path = os.path.join(project_root, 'allure-report')

        if not os.path.exists(allure_results_path):
            return jsonify({
                'success': False,
                'error': 'No test results available. Please run tests first.'
            }), 400

        # Check if there are any result files
        result_files = [f for f in os.listdir(allure_results_path) if f.endswith('.json')]
        if not result_files:
            return jsonify({
                'success': False,
                'error': 'No test results available. Please run tests first.'
            }), 400

        # Clean previous report (force regeneration)
        if os.path.exists(allure_report_path):
            shutil.rmtree(allure_report_path)

        # Create report directory
        os.makedirs(allure_report_path, exist_ok=True)

        # Try multiple possible Allure CLI locations
        # Prioritize local repo path first and choose executable based on OS
        if is_windows:
            local_allure_path = os.path.join(project_root, 'allure-2.24.0', 'bin', 'allure.bat')
            possible_allure_commands = [
                local_allure_path,  # Local repo path first (now available)
                r'C:\allure\allure-2.24.0\bin\allure.bat',
                r'C:\allure\bin\allure.bat',
                'allure.bat',
                'allure'
            ]
        else:
            possible_allure_commands = [
                local_allure_path,
                'allure',  # Local repo path first (now available)
                '/usr/local/bin/allure',
                '/usr/bin/allure'
                
            ]

        allure_cli_worked = False

        for allure_cmd in possible_allure_commands:
            try:
                print(f"[ALLURE] Trying CLI: {allure_cmd}")
                # Check if the executable exists and is executable
                if os.path.exists(allure_cmd):
                    print(f"[ALLURE] Found executable at: {allure_cmd}")
                    # Check if it's executable (for Unix systems)
                    if not is_windows and not os.access(allure_cmd, os.X_OK):
                        print(f"[ALLURE] {allure_cmd} is not executable, trying with executable permissions")
                        try:
                            os.chmod(allure_cmd, 0o755)
                            print(f"[ALLURE] Made {allure_cmd} executable")
                        except Exception as perm_error:
                            print(f"[ALLURE] Could not make {allure_cmd} executable: {str(perm_error)}")
                            continue
                else:
                    print(f"[ALLURE] Executable not found at: {allure_cmd}")
                    continue

                # Run Allure generate command
                result = subprocess.run([
                    allure_cmd, 'generate', allure_results_path,
                    '-o', allure_report_path, '--clean'
                ], check=True, capture_output=True, text=True, timeout=30)

                print(f"[SUCCESS] Auto-generated Allure report with: {allure_cmd}")
                print(f"[OUTPUT] {result.stdout}")
                allure_cli_worked = True
                break

            except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
                print(f"[ALLURE] Auto-generation failed with {allure_cmd}: {str(e)}")
                continue

        if not allure_cli_worked:
            print("[FALLBACK] All Allure CLI attempts failed, using HTML fallback")
            # Fall back to simple HTML report
            html_report = generate_html_report(allure_results_path, result_files)
            report_file = os.path.join(allure_report_path, 'index.html')
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(html_report)
            print("[FALLBACK] Generated simple HTML report")

        print(f"[SUCCESS] Allure report force-regenerated at: {allure_report_path}")

        # Return the HTTP URL to serve the report
        report_url = f"http://{get_allure_report_host()}/allure-report/index.html"

        return jsonify({
            'success': True,
            'report_url': report_url,
            'message': 'Allure report force-regenerated successfully',
            'result_files_processed': len(result_files)
        })
        
    except Exception as e:
        print(f"[ERROR] Failed to force-regenerate Allure report: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def find_allure_binary():
    cmds = ["allure", "/usr/local/bin/allure", "/usr/bin/allure"]
    for cmd in cmds:
        try:
            subprocess.run([cmd, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return cmd
        except Exception:
            continue
    raise RuntimeError("Allure not installed")

@app.route('/api/allure/generate', methods=['POST'])
def allure_generate():
    """Generate Allure report and return the URL"""
    try:
        print("[ALLURE] Generating Allure report...")

        # Check if allure-results directory exists
        current_dir = os.getcwd()
        # If running from new_backend directory, go up one level
        if current_dir.endswith('new_backend'):
            project_root = os.path.dirname(current_dir)
        else:
            project_root = current_dir
        allure_results_path = os.path.join(project_root, 'allure-results-new')

        print(f"[DEBUG] Looking for allure results in: {allure_results_path}")

        if not os.path.exists(allure_results_path):
            return jsonify({
                'success': False,
                'error': f'No test results available in {allure_results_path}. Please run tests first.'
            }), 400

        # Check if there are any result files
        result_files = [f for f in os.listdir(allure_results_path) if f.endswith('.json')]
        if not result_files:
            return jsonify({
                'success': False,
                'error': 'No test results available. Please run tests first.'
            }), 400

        # Generate simple HTML report from JSON results
        allure_report_path = os.path.join(project_root, 'allure-report')

        # Clean previous report
        if os.path.exists(allure_report_path):
            shutil.rmtree(allure_report_path)

        # Create report directory
        os.makedirs(allure_report_path, exist_ok=True)

        # Use the new allure binary finder
        try:
            ALLURE_CMD = find_allure_binary()
            print(f"[INFO] Found Allure CLI: {ALLURE_CMD}")
            
            # Run Allure generate command
            result = subprocess.run([
                ALLURE_CMD,
                "generate",
                allure_results_path,
                "-o",
                allure_report_path,
                "--clean"
            ], check=True, capture_output=True, text=True, timeout=30)

            print(f"[SUCCESS] Allure CLI generated report successfully with: {ALLURE_CMD}")
            print(f"[OUTPUT] {result.stdout}")
            allure_cli_worked = True

        except RuntimeError as e:
            print(f"[ERROR] {str(e)}")
            allure_cli_worked = False
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"[ERROR] Failed to generate Allure report: {str(e)}")
            allure_cli_worked = False

        if not allure_cli_worked:
            print("[FALLBACK] All Allure CLI attempts failed, using HTML fallback")
            # Fall back to simple HTML report
            html_report = generate_html_report(allure_results_path, result_files)
            report_file = os.path.join(allure_report_path, 'index.html')
            with open(report_file, 'w', encoding='utf-8') as f:
                                f.write(html_report)
            print("[FALLBACK] Generated simple HTML report")

        print(f"[SUCCESS] Allure report generated at: {allure_report_path}")

        # Return the HTTP URL to serve the report
        report_url = f"http://{get_allure_report_host()}/allure-report/index.html"

        return jsonify({
            'success': True,
            'report_url': report_url,
            'message': 'Allure report generated successfully'
        })

    except Exception as e:
        print(f"[ERROR] Allure generation failed: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/allure/open', methods=['POST'])
def allure_open():
    """Generate and open Allure report in browser"""
    try:
        # Generate report first
        generate_response = allure_generate()

        if generate_response.status_code != 200:
            return generate_response

        # Get the report URL from the response
        response_data = generate_response.get_json()
        report_url = response_data.get('report_url')

        # Open in browser
        if report_url:
            import webbrowser
            webbrowser.open(report_url)

        return jsonify({
            'success': True,
            'message': 'Allure report opened in browser',
            'report_url': report_url
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/monitor/dashboard', methods=['GET'])
def get_monitor_dashboard():
    """Get monitor dashboard with active streaming sessions"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        # Get active streaming sessions for this user
        active_sessions = []
        for session_id, session in remote_viewing_sessions.items():
            if session.user_email == current_user_email and session.status == 'active':
                active_sessions.append({
                    'session_id': session_id,
                    'testcase_name': session.testcase_name,
                    'novnc_url': session.novnc_url,
                    'execution_id': session.execution_id,
                    'execution_mode': session.execution_mode,
                    'created_at': format_timestamp(session.created_at),
                    'viewer_count': len(session.viewers)
                })

        isolated_sessions = []
        for session_info in vnc_manager.list_active_sessions():
            if session_info.get('user_email') == current_user_email and session_info.get('status') == 'active':
                isolated_sessions.append({
                    'session_id': session_info['session_id'],
                    'novnc_url': session_info['novnc_url'],
                    'display_id': session_info['display_num'],
                    'vnc_port': session_info['vnc_port'],
                    'novnc_port': session_info['novnc_port'],
                    'execution_id': session_info['execution_id'],
                    'start_time': format_timestamp(session_info['started_at'])
                })

        return jsonify({
            'success': True,
            'active_sessions': active_sessions,
            'isolated_sessions': isolated_sessions,
            'total_active_streams': len(active_sessions) + len(isolated_sessions),
            'message': f'Found {len(active_sessions)} remote sessions and {len(isolated_sessions)} isolated streams'
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/monitor/recorded-videos', methods=['GET'])
def get_recorded_videos():
    """Get list of recorded videos from noVNC sessions"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        # Check if user is authorized for test-lab function
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, role FROM Authentication WHERE email = ?", (current_user_email,))
        user_result = cursor.fetchone()
        if not user_result:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        user_status, user_role = user_result

        # Check if user is approved
        if user_status != 'Approved':
            conn.close()
            return jsonify({'error': 'User not approved'}), 403

        # Admin users have access to all functions
        if user_role == 'Admin':
            conn.close()
        else:
            # Check if user is assigned to test-lab function
            cursor.execute("""
                SELECT id FROM FunctionAssignments
                WHERE function_name = 'test-lab' AND user_email = ?
            """, (current_user_email,))
            assignment = cursor.fetchone()
            conn.close()

            if not assignment:
                return jsonify({'error': 'User not authorized for test-lab function'}), 403

        # For now, return empty list as video recording implementation would need additional setup
        # In a real implementation, this would query a videos table or scan a recordings directory
        recorded_videos = []

        return jsonify(recorded_videos)

    except Exception as e:
        print(f"[ERROR] Failed to get recorded videos: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/monitor/cleanup-sessions', methods=['POST'])
def cleanup_monitor_sessions():
    """Clean up orphaned or inactive monitor sessions"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        cleaned_sessions = []
        cleaned_isolated = []

        # Clean up remote viewing sessions
        for session_id in list(remote_viewing_sessions.keys()):
            session = remote_viewing_sessions[session_id]
            if session.user_email == current_user_email:
                # Check if session is old or inactive
                time_diff = (datetime.now(pytz.timezone('Asia/Kolkata')) - session.last_activity).total_seconds()
                if time_diff > 3600:  # 1 hour timeout
                    try:
                        cleanup_isolated_session(session_id)
                        cleaned_sessions.append(session_id)
                        del remote_viewing_sessions[session_id]
                    except Exception as e:
                        print(f"[CLEANUP] Error cleaning session {session_id}: {str(e)}")

        # Clean up idle VNC sessions (>1 hour inactive)
        for session_info in vnc_manager.list_active_sessions():
            if session_info.get('user_email') == current_user_email:
                time_diff = (datetime.now(pytz.timezone('Asia/Kolkata')) - session_info['started_at']).total_seconds()
                if time_diff > 3600:  # 1 hour timeout
                    try:
                        cleanup_isolated_session(session_info['session_id'])
                        cleaned_isolated.append(session_info['session_id'])
                    except Exception as e:
                        print(f"[CLEANUP] Error cleaning isolated session {session_info['session_id']}: {str(e)}")

        return jsonify({
            'success': True,
            'cleaned_sessions': len(cleaned_sessions),
            'cleaned_isolated': len(cleaned_isolated),
            'message': f'Cleaned up {len(cleaned_sessions)} remote sessions and {len(cleaned_isolated)} isolated sessions'
        })

    except Exception as e:
        print(f"[ERROR] Failed to cleanup sessions: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Static file serving for Allure reports
@app.route('/allure-report/<path:filename>')
def serve_allure_report(filename):
    """Serve Allure report files"""
    try:
        # Get the project root directory (parent of new_backend)
        current_dir = os.getcwd()
        if current_dir.endswith('new_backend'):
            project_root = os.path.dirname(current_dir)
        else:
            project_root = current_dir
            
        allure_report_path = os.path.join(project_root, 'allure-report')
        response = send_from_directory(allure_report_path, filename)
        
        # Add proper headers for different file types
        if filename.endswith('.html'):
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        elif filename.endswith('.js'):
            response.headers['Content-Type'] = 'application/javascript'
        elif filename.endswith('.css'):
            response.headers['Content-Type'] = 'text/css'
        elif filename.endswith('.json'):
            response.headers['Content-Type'] = 'application/json'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        elif filename.endswith('.csv'):
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        return jsonify({'error': f'File not found: {str(e)}'}), 404

# Remote Viewing API Endpoints
@app.route('/api/remote-viewing/start', methods=['POST'])
def start_remote_viewing():
    """Start a remote viewing session for test execution"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        # Check if user is authorized for test-lab function
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, role FROM Authentication WHERE email = ?", (current_user_email,))
        user_result = cursor.fetchone()
        if not user_result:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        user_status, user_role = user_result

        # Check if user is approved
        if user_status != 'Approved':
            conn.close()
            return jsonify({'error': 'User not approved'}), 403

        # Admin users have access to all functions
        if user_role == 'Admin':
            conn.close()
        else:
            # Check if user is assigned to test-lab function
            cursor.execute("""
                SELECT id FROM FunctionAssignments
                WHERE function_name = 'test-lab' AND user_email = ?
            """, (current_user_email,))
            assignment = cursor.fetchone()
            conn.close()

            if not assignment:
                return jsonify({'error': 'User not authorized for test-lab function'}), 403

        # Get request data
        data = request.get_json() or {}
        testcase_name = data.get('testcase_name')
        executor_type = data.get('executor_type', 'selenium')

        # Generate session ID
        session_id = str(uuid.uuid4())

        # Create remote viewing session
        session = RemoteViewingSession(session_id, current_user_email, testcase_name)
        remote_viewing_sessions[session_id] = session

        print(f"[REMOTE_VIEWING] Started session {session_id} for user {current_user_email}")

        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': 'Remote viewing session started',
            'stream_url': f'/api/remote-viewing/stream/{session_id}',
            'status_url': f'/api/remote-viewing/status/{session_id}'
        }), 201

    except Exception as e:
        print(f"[ERROR] Failed to start remote viewing: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/server-execution/start', methods=['POST'])
def start_server_execution():
    """Start server execution with isolated noVNC streaming and automatic VNC session creation"""
    import uuid
    import json
    from datetime import datetime, timezone

    # Import the new VNC Session Manager
    from vnc_session_manager import VNCSessionManager

    try:
        # Get request data
        request_data = request.get_json()
        current_user_email = request_data.get('user_email', 'anonymous@local')

        # Extract test execution parameters
        test_cases = request_data.get('test_cases', [])
        selected_suites = request_data.get('selected_suites', [])
        executor_type = request_data.get('executor_type', 'selenium')
        enable_isolation = request_data.get('enable_isolation', True)
        enable_parallel = request_data.get('enable_parallel', False)
        max_concurrent = request_data.get('max_concurrent', 3)

        # Generate unique execution ID
        execution_id = str(uuid.uuid4())

        print(f"[SERVER_EXEC] Starting execution {execution_id} for user {current_user_email}")

        # Create automatic noVNC session for this execution
        print(f"[SERVER_EXEC] Creating automatic VNC session for execution {execution_id}")
        session_info = vnc_manager.start_streaming_session(
            current_user_email,
            execution_id
        )

        if not session_info:
            return jsonify({
                'success': False,
                'error': 'Failed to create VNC session'
            }), 500

        # Get noVNC URL from session info
        novnc_url = session_info['novnc_url']

        print(f"[SERVER_EXEC] VNC session created: {session_info}")
        print(f"[SERVER_EXEC] Generated noVNC URL: {novnc_url}")

        # Create server execution manager
        from server_execution_manager import ServerExecutionManager

        server_manager = ServerExecutionManager(
            execution_id=execution_id,
            test_cases=test_cases,
            selected_suites=selected_suites,
            executor_type=executor_type,
            enable_isolation=enable_isolation,
            enable_parallel=enable_parallel,
            max_concurrent=max_concurrent,
            enable_streaming=True,  # Always enable streaming
            user_email=current_user_email,
            vnc_session_info=session_info  # Pass already-created VNC session
        )

        # Execute tests in background thread
        def execute_tests_async():
            try:
                print(f"[SERVER_EXEC] Starting test execution for {execution_id}")
                results = server_manager.execute()

                # Store execution results
                execution_results[execution_id] = {
                    'results': results,
                    'completed_at': format_timestamp(datetime.now(pytz.timezone('Asia/Kolkata'))),
                    'status': 'completed',
                    'novnc_url': novnc_url,
                    'vnc_session_info': session_info
                }

                # VNC session cleanup removed - keep VNC alive for remote viewing
                # print(f"[SERVER_EXEC] Cleaning up VNC session after execution {execution_id}")
                # vnc_manager.stop_user_vnc_session(session_info['session_id'])

            except Exception as e:
                print(f"[SERVER_EXEC] Test execution failed for {execution_id}: {str(e)}")
                execution_results[execution_id] = {
                    'error': str(e),
                    'completed_at': format_timestamp(datetime.now(pytz.timezone('Asia/Kolkata'))),
                    'status': 'failed',
                    'novnc_url': novnc_url,
                    'vnc_session_info': session_info
                }

                # VNC session cleanup removed - keep VNC alive for remote viewing
                # try:
                #     vnc_manager.stop_user_vnc_session(session_info['session_id'])
                # except:
                #     pass

        # Store execution results globally
        execution_results[execution_id] = {
            'status': 'running',
            'started_at': format_timestamp(datetime.now(pytz.timezone('Asia/Kolkata'))),
            'novnc_url': novnc_url,
            'vnc_session_info': session_info
        }

        # Start execution in background
        execution_thread = threading.Thread(target=execute_tests_async)
        execution_thread.daemon = True
        execution_thread.start()

        # Return execution details with noVNC URL for frontend to open in new tab
        print(f"[SERVER_EXEC] Returning execution response with noVNC URL: {novnc_url}")
        return jsonify({
            'success': True,
            'execution_id': execution_id,
            'message': 'Server execution started with live streaming',
            'novnc_url': novnc_url,
            'vnc_session_id': session_info['session_id'],
            'streaming_active': True
        }), 200

    except Exception as e:
        print(f"[SERVER_EXEC] Failed to start server execution: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/execute-test-lab', methods=['POST'])
def execute_test_lab():
    """Start server execution with isolated noVNC streaming"""
    try:
        # Get current user from session/token
        current_user_email = request.headers.get('X-User-Email')
        if not current_user_email:
            return jsonify({'error': 'Authentication required'}), 401

        # Check if user is authorized for test-lab function
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, role FROM Authentication WHERE email = ?", (current_user_email,))
        user_result = cursor.fetchone()
        if not user_result:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        user_status, user_role = user_result

        # Check if user is approved
        if user_status != 'Approved':
            conn.close()
            return jsonify({'error': 'User not approved'}), 403

        # Admin users have access to all functions
        if user_role == 'Admin':
            conn.close()
        else:
            # Check if user is assigned to test-lab function
            cursor.execute("""
                SELECT id FROM FunctionAssignments
                WHERE function_name = 'test-lab' AND user_email = ?
            """, (current_user_email,))
            assignment = cursor.fetchone()
            conn.close()

            if not assignment:
                return jsonify({'error': 'User not authorized for test-lab function'}), 403

        # Get request data
        data = request.get_json() or {}
        execution_id = data.get('execution_id')
        test_cases = data.get('test_cases', [])
        selected_suites = data.get('selected_suites', [])
        enable_parallel = data.get('enable_parallel', False)

        if not execution_id:
            return jsonify({'error': 'execution_id is required'}), 400

        # Generate unique session ID
        session_id = f"server_exec_{execution_id}_{uuid.uuid4().hex[:8]}"

        # Check if this is a single test case or multiple test cases
        if len(test_cases) == 1:
            # Single test case - create one isolated session
            test_case = test_cases[0]
            test_name = test_case.get('name', 'Unknown')

            session_result = start_isolated_novnc_session(session_id, current_user_email, test_name)
            novnc_url = session_result['novnc_url']

            # Create remote viewing session for tracking
            session = RemoteViewingSession(session_id, current_user_email, test_name)
            session.execution_id = execution_id
            session.execution_mode = 'server'
            session.test_cases = test_cases
            session.selected_suites = selected_suites
            session.novnc_url = novnc_url
            remote_viewing_sessions[session_id] = session

            print(f"[SERVER_EXECUTION] Started single test execution session {session_id}")
            print(f"[SERVER_EXECUTION] noVNC URL: {novnc_url}")

            return jsonify({
                'success': True,
                'session_id': session_id,
                'execution_id': execution_id,
                'novnc_url': novnc_url,
                'message': 'Server execution started with isolated streaming.',
                'execution_mode': 'server',
                'parallel_execution': False,
                'test_count': 1
            }), 200

        else:
            # Multiple test cases - create isolated sessions for each
            streams = []
            session_ids = []

            for i, test_case in enumerate(test_cases):
                test_session_id = f"{session_id}_test_{i}"
                test_name = test_case.get('name', f'Test_{i+1}')

                try:
                    session_result = start_isolated_novnc_session(test_session_id, current_user_email, test_name)
                    novnc_url = session_result['novnc_url']

                    streams.append({
                        'test_name': test_name,
                        'url': novnc_url,
                        'session_id': test_session_id
                    })

                    session_ids.append(test_session_id)

                    # Create remote viewing session for tracking
                    session = RemoteViewingSession(test_session_id, current_user_email, test_name)
                    session.execution_id = execution_id
                    session.execution_mode = 'server'
                    session.test_cases = [test_case]
                    session.selected_suites = selected_suites
                    session.novnc_url = novnc_url
                    remote_viewing_sessions[test_session_id] = session

                except Exception as e:
                    print(f"[SERVER_EXECUTION] Failed to create session for {test_name}: {str(e)}")
                    # Continue with other tests, but log the failure

            if not streams:
                return jsonify({'error': 'Failed to create any streaming sessions'}), 500

            print(f"[SERVER_EXECUTION] Started multi-test execution with {len(streams)} isolated streams")

            return jsonify({
                'success': True,
                'execution_id': execution_id,
                'streams': streams,
                'session_ids': session_ids,
                'message': f'Server execution started with {len(streams)} isolated streams.',
                'execution_mode': 'server',
                'parallel_execution': enable_parallel,
                'test_count': len(test_cases),
                'active_streams': len(streams)
            }), 200

    except Exception as e:
        print(f"[ERROR] Failed to start server execution: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/remote-viewing/status/<session_id>', methods=['GET'])
def get_remote_viewing_status(session_id):
    """Get status of a remote viewing session"""
    try:
        if session_id not in remote_viewing_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = remote_viewing_sessions[session_id]

        # Update session activity
        session.update_activity()

        streaming_status = None
        if session.execution_mode == 'server' and session.novnc_url:
            streaming_status = {
                'active': True,
                'novnc_url': session.novnc_url
            }

        return jsonify({
            'session_id': session_id,
            'status': session.status,
            'viewer_count': len(session.viewers),
            'testcase_name': session.testcase_name,
            'current_step': session.current_step,
            'total_steps': session.total_steps,
            'stream_url': session.stream_url,
            'novnc_url': session.novnc_url,
            'streaming_active': session.novnc_url is not None,
            'execution_id': session.execution_id,
            'execution_mode': session.execution_mode,
            'streaming_status': streaming_status,
            'last_activity': format_timestamp(session.last_activity),
            'created_at': format_timestamp(session.created_at)
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to get session status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/remote-viewing/stop/<session_id>', methods=['POST'])
def stop_remote_viewing(session_id):
    """Stop a remote viewing session"""
    try:
        if session_id not in remote_viewing_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = remote_viewing_sessions[session_id]

        # Stop the session
        session.status = 'stopped'

        # IMPORTANT: VNC session cleanup removed - keep VNC alive for remote viewing
        # VNC cleanup should only happen on:
        # 1. Explicit user stop via separate endpoint, OR
        # 2. Idle timeout expires (>1 hour)
        # This allows browser to close while keeping VNC/noVNC streaming active

        # Close browser if executor exists
        if session.executor:
            try:
                session.executor.close_browser()
            except Exception as e:
                print(f"[WARNING] Error closing browser for session {session_id}: {str(e)}")

        # Notify all viewers
        socketio.emit('session_stopped', {
            'session_id': session_id,
            'message': 'Remote viewing session stopped'
        }, room=session_id)

        # Clean up session after a delay
        def cleanup_session():
            time.sleep(5)  # Give time for final messages
            if session_id in remote_viewing_sessions:
                del remote_viewing_sessions[session_id]
                print(f"[REMOTE_VIEWING] Cleaned up session {session_id}")

        threading.Thread(target=cleanup_session, daemon=True).start()

        return jsonify({
            'success': True,
            'message': 'Remote viewing session stopped'
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to stop remote viewing: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/remote-viewing/stop-vnc/<session_id>', methods=['POST'])
def stop_vnc_streaming(session_id):
    """Explicitly stop VNC/noVNC streaming for a remote viewing session"""
    try:
        if session_id not in remote_viewing_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = remote_viewing_sessions[session_id]

        # Stop noVNC streaming if active
        if session.execution_mode == 'server' and session.novnc_url:
            try:
                cleanup_isolated_session(session_id)
                print(f"[SERVER_EXECUTION] Stopped isolated noVNC streaming for session {session_id}")
            except Exception as novnc_error:
                print(f"[WARNING] Error stopping noVNC streaming for session {session_id}: {str(novnc_error)}")

        return jsonify({
            'success': True,
            'message': 'VNC/noVNC streaming stopped'
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to stop VNC streaming: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/remote-viewing/stream/<session_id>')
def stream_remote_viewing(session_id):
    """Stream video feed for remote viewing (placeholder for WebRTC implementation)"""
    try:
        if session_id not in remote_viewing_sessions:
            return jsonify({'error': 'Session not found'}), 404

        session = remote_viewing_sessions[session_id]

        if session.status != 'active':
            return jsonify({'error': 'Session not active'}), 400

        # For now, return a placeholder response
        # In a full implementation, this would establish WebRTC connection
        return jsonify({
            'session_id': session_id,
            'status': 'streaming',
            'message': 'Video streaming endpoint (WebRTC implementation needed)'
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to stream remote viewing: {str(e)}")
        return jsonify({'error': str(e)}), 500

# noVNC Streaming Functions
def start_isolated_novnc_session(execution_id, user_email, test_name=None):
    """Start an isolated noVNC session for a specific execution using VNC manager"""
    try:
        print(f"[ISOLATED_NOVNC] Starting isolated session for {user_email}, execution={execution_id}")
        
        session_info = vnc_manager.start_streaming_session(
            user_email,
            execution_id
        )
        if not session_info:
            raise Exception("Failed to start VNC streaming session")
        
        print(f"[ISOLATED_NOVNC] Session {session_info['session_id']} started successfully")
        
        return {
            'session_id': session_info['session_id'],
            'novnc_url': session_info['novnc_url'],
            'display_id': session_info['display_num'],
            'vnc_port': session_info['vnc_port'],
            'novnc_port': session_info['novnc_port'],
            'execution_id': execution_id,
            'test_name': test_name
        }
    
    except Exception as e:
        print(f"[ISOLATED_NOVNC] Failed to start isolated session: {str(e)}")
        raise e

def cleanup_isolated_session(session_id):
    """Clean up an isolated noVNC session"""
    try:
        print(f"[CLEANUP] Cleaning up isolated session {session_id}")
        vnc_manager.stop_user_vnc_session(session_id)
        print(f"[CLEANUP] Isolated session {session_id} cleaned up successfully")
    except Exception as e:
        print(f"[CLEANUP] Error during cleanup: {str(e)}")

def start_novnc_server():
    """Legacy function - kept for backward compatibility"""
    return start_isolated_novnc_session('legacy_session', 'system', 'legacy')

def find_novnc_installation():
    """Find noVNC installation path"""
    try:
        # Common installation paths - prioritize system installation
        possible_paths = [
            '/usr/share/novnc',  # Linux system installation (Ubuntu/Debian)
            '/usr/share/novnc',  # Alternative system path
            '/opt/novnc',        # Alternative Linux path
            './novnc',           # Local directory
            '../novnc',          # Parent directory
        ]

        for path in possible_paths:
            if os.path.exists(path) and os.path.exists(os.path.join(path, 'vnc.html')):
                print(f"[NOVNC] Found noVNC installation at: {path}")
                return os.path.abspath(path)

        # Try to find in current environment
        current_dir = os.getcwd()
        if current_dir.endswith('new_backend'):
            project_root = os.path.dirname(current_dir)
            novnc_path = os.path.join(project_root, 'novnc')
            if os.path.exists(novnc_path):
                print(f"[NOVNC] Found noVNC in project root: {novnc_path}")
                return novnc_path

        print("[NOVNC] noVNC installation not found in common locations")
        return None

    except Exception as e:
        print(f"[NOVNC] Error finding noVNC installation: {str(e)}")
        return None

# Socket.IO event handlers for real-time communication
@socketio.on('join_session')
def handle_join_session(data):
    """Handle viewer joining a remote viewing session"""
    try:
        session_id = data.get('session_id')
        viewer_id = data.get('viewer_id', request.sid)

        if session_id not in remote_viewing_sessions:
            emit('error', {'message': 'Session not found'})
            return

        session = remote_viewing_sessions[session_id]
        session.add_viewer(viewer_id)
        join_room(session_id)

        print(f"[SOCKET] Viewer {viewer_id} joined session {session_id}")

        # Notify all viewers in the session
        emit('viewer_joined', {
            'viewer_id': viewer_id,
            'viewer_count': len(session.viewers)
        }, room=session_id)

        # Send current session status to the new viewer
        emit('session_status', session.to_dict())

    except Exception as e:
        print(f"[SOCKET_ERROR] Error joining session: {str(e)}")
        emit('error', {'message': str(e)})

@socketio.on('leave_session')
def handle_leave_session(data):
    """Handle viewer leaving a remote viewing session"""
    try:
        session_id = data.get('session_id')
        viewer_id = data.get('viewer_id', request.sid)

        if session_id in remote_viewing_sessions:
            session = remote_viewing_sessions[session_id]
            session.remove_viewer(viewer_id)
            leave_room(session_id)

            print(f"[SOCKET] Viewer {viewer_id} left session {session_id}")

            # Notify remaining viewers
            emit('viewer_left', {
                'viewer_id': viewer_id,
                'viewer_count': len(session.viewers)
            }, room=session_id)

            # If no viewers left, consider stopping the session
            if len(session.viewers) == 0:
                print(f"[SOCKET] No viewers left in session {session_id}, stopping...")
                session.status = 'stopped'

    except Exception as e:
        print(f"[SOCKET_ERROR] Error leaving session: {str(e)}")

@socketio.on('start_test_execution')
def handle_start_test_execution(data):
    """Handle starting test execution in a remote viewing session"""
    try:
        session_id = data.get('session_id')
        testcase_name = data.get('testcase_name')
        executor_type = data.get('executor_type', 'selenium')

        if session_id not in remote_viewing_sessions:
            emit('error', {'message': 'Session not found'})
            return

        session = remote_viewing_sessions[session_id]

        # Update session status
        session.status = 'executing'
        session.testcase_name = testcase_name

        # Emit status update to all viewers
        emit('session_status_update', session.to_dict(), room=session_id)

        # Start test execution in a separate thread
        def execute_test():
            try:
                print(f"[REMOTE_EXEC] Starting test execution for {testcase_name} in session {session_id}")

                # Get test steps from database
                conn = get_db_connection()
                cursor = conn.cursor()

                # Get project and module info for generating unique table name
                cursor.execute("""
                    SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                           COALESCE(m.module_name, 'Unknown') as module_name
                    FROM TestCases tc
                    LEFT JOIN Modules m ON tc.module_id = m.id
                    LEFT JOIN Projects p1 ON tc.project_id = p1.id
                    LEFT JOIN Projects p2 ON m.project_id = p2.id
                    WHERE tc.name = ?
                """, (testcase_name,))

                metadata = cursor.fetchone()
                if metadata:
                    project_name = metadata[0]
                    module_name = metadata[1]
                    table_name = generate_unique_table_name(project_name, module_name, testcase_name)
                else:
                    # Fallback to old naming for backward compatibility
                    table_name = sanitize_table_name(testcase_name)

                cursor.execute(f"SELECT tc_id, step_no, test_step_description, element_name, action_type, xpath, [values] FROM [{table_name}] ORDER BY step_no")

                test_steps = []
                for row in cursor.fetchall():
                    test_steps.append({
                        'tc_id': row[0],
                        'step_no': row[1],
                        'test_step_description': row[2],
                        'element_name': row[3],
                        'action_type': row[4],
                        'xpath': row[5],
                        'values': row[6]
                    })

                cursor.close()
                conn.close()

                if not test_steps:
                    emit('execution_error', {'message': 'No test steps found'}, room=session_id)
                    return

                session.total_steps = len(test_steps)

                # Create executor
                if executor_type == 'playwright':
                    from playwright_executor import PlaywrightTestExecutor
                    executor = PlaywrightTestExecutor()
                else:
                    executor = SeleniumTestExecutor()

                session.executor = executor

                # Execute test with real-time updates
                for i, step in enumerate(test_steps, 1):
                    session.current_step = i

                    # Emit step start
                    emit('step_started', {
                        'step_number': i,
                        'description': step.get('test_step_description', ''),
                        'total_steps': session.total_steps
                    }, room=session_id)

                    try:
                        # Execute the step (this would need modification to the executor)
                        # For now, simulate execution
                        time.sleep(2)  # Simulate step execution time

                        # Emit step completion
                        emit('step_completed', {
                            'step_number': i,
                            'status': 'PASS',
                            'description': step.get('test_step_description', ''),
                            'execution_time': '2.0s'
                        }, room=session_id)

                    except Exception as e:
                        emit('step_failed', {
                            'step_number': i,
                            'error': str(e),
                            'description': step.get('test_step_description', '')
                        }, room=session_id)
                        break

                # Emit test completion
                emit('test_completed', {
                    'status': 'PASS',
                    'total_steps': session.total_steps,
                    'passed_steps': session.total_steps,
                    'failed_steps': 0
                }, room=session_id)

                # Close browser
                try:
                    executor.close_browser()
                except:
                    pass

                session.status = 'completed'

            except Exception as e:
                print(f"[REMOTE_EXEC_ERROR] Test execution failed: {str(e)}")
                emit('execution_error', {'message': str(e)}, room=session_id)
                session.status = 'error'

        # Start execution thread
        execution_thread = threading.Thread(target=execute_test, daemon=True)
        execution_thread.start()

    except Exception as e:
        print(f"[SOCKET_ERROR] Error starting test execution: {str(e)}")
        emit('error', {'message': str(e)})

# Static file serving for screenshots and attachments
@app.route('/allure-results/<path:filename>')
def serve_allure_results(filename):
    """Serve Allure result files and attachments (screenshots)"""
    try:
        # Get the working directory - should be the project root
        current_dir = os.getcwd()
        # If running from new_backend directory, go up one level
        if current_dir.endswith('new_backend'):
            project_root = os.path.dirname(current_dir)
        else:
            project_root = current_dir
        allure_results_path = os.path.join(project_root, 'allure-results-new')

        print(f"[DEBUG] Current directory: {current_dir}")
        print(f"[DEBUG] Allure results path: {allure_results_path}")
        print(f"[DEBUG] Requested filename: {filename}")
        print(f"[DEBUG] File exists: {os.path.exists(os.path.join(allure_results_path, filename))}")

        # Check if directory exists
        if not os.path.exists(allure_results_path):
            print(f"[ERROR] Allure results directory not found: {allure_results_path}")
            return jsonify({'error': f'Allure results directory not found: {allure_results_path}'}), 404

        # Check if file exists
        full_file_path = os.path.join(allure_results_path, filename)
        if not os.path.exists(full_file_path):
            print(f"[ERROR] File not found: {full_file_path}")
            return jsonify({'error': f'File not found: {full_file_path}'}), 404

        response = send_from_directory(allure_results_path, filename)

        # Add proper headers for different file types
        if filename.endswith('.png'):
            response.headers['Content-Type'] = 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            response.headers['Content-Type'] = 'image/jpeg'
        elif filename.endswith('.json'):
            response.headers['Content-Type'] = 'application/json'

        return response
    except Exception as e:
        print(f"[ERROR] Exception in serve_allure_results: {str(e)}")
        return jsonify({'error': f'File not found: {str(e)}'}), 404

@app.route('/api/populate-missing-testcase-metadata', methods=['POST'])
def populate_missing_testcase_metadata():
    """Populate missing project_id and module_id in TestCases table by parsing testcase_id"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("[POPULATE_METADATA] Starting population of missing project_id and module_id...")
        
        # Get all TestCases that have testcase_id but missing project_id or module_id
        cursor.execute("""
            SELECT id, name, testcase_id, project_id, module_id
            FROM TestCases
            WHERE testcase_id IS NOT NULL 
            AND testcase_id != ''
            AND (project_id IS NULL OR module_id IS NULL)
        """)
        
        testcases_to_fix = cursor.fetchall()
        
        fix_summary = {
            'total_testcases_checked': len(testcases_to_fix),
            'project_ids_populated': 0,
            'module_ids_populated': 0,
            'fixes_applied': []
        }
        
        for testcase in testcases_to_fix:
            testcase_db_id, testcase_name, testcase_id, current_project_id, current_module_id = testcase
            
            print(f"[POPULATE_METADATA] Processing testcase: {testcase_name} (ID: {testcase_id})")
            
            # Parse project and module names from testcase_id
            # Format: projectname_modulename_testcasename_TC001
            if testcase_id and '_TC' in testcase_id:
                # Remove the _TC### part to get the base
                base_id = testcase_id.rsplit('_TC', 1)[0]
                # Split by underscores and assume first two parts are project and module
                parts = base_id.split('_')
                if len(parts) >= 2:
                    project_name_from_id = parts[0]
                    module_name_from_id = parts[1]
                    
                    print(f"[POPULATE_METADATA] Parsed from ID: Project='{project_name_from_id}', Module='{module_name_from_id}'")
                    
                    populated_project_id = current_project_id
                    populated_module_id = current_module_id
                    
                    # Find or create project if missing
                    if not current_project_id:
                        cursor.execute("SELECT id FROM Projects WHERE name = ?", (project_name_from_id,))
                        project_result = cursor.fetchone()
                        if project_result:
                            populated_project_id = project_result[0]
                            print(f"[POPULATE_METADATA] Found existing project: {project_name_from_id} (ID: {populated_project_id})")
                        else:
                            # Create new project
                            cursor.execute("""
                                INSERT INTO Projects (name, description, status)
                                VALUES (?, ?, ?)
                            """, (project_name_from_id, f"Auto-created from testcase_id parsing", "Active"))
                            populated_project_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                            print(f"[POPULATE_METADATA] Created new project: {project_name_from_id} (ID: {populated_project_id})")
                        
                        fix_summary['project_ids_populated'] += 1
                    
                    # Find or create module if missing
                    if not current_module_id and populated_project_id:
                        cursor.execute("SELECT id FROM Modules WHERE module_name = ? AND project_id = ?", (module_name_from_id, populated_project_id))
                        module_result = cursor.fetchone()
                        if module_result:
                            populated_module_id = module_result[0]
                            print(f"[POPULATE_METADATA] Found existing module: {module_name_from_id} (ID: {populated_module_id})")
                        else:
                            # Create new module
                            cursor.execute("""
                                INSERT INTO Modules (module_name, description, project_id)
                                VALUES (?, ?, ?)
                            """, (module_name_from_id, f"Auto-created from testcase_id parsing", populated_project_id))
                            populated_module_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]
                            print(f"[POPULATE_METADATA] Created new module: {module_name_from_id} (ID: {populated_module_id})")
                        
                        fix_summary['module_ids_populated'] += 1
                    
                    # Update the testcase with the populated IDs
                    update_needed = False
                    if not current_project_id and populated_project_id:
                        update_needed = True
                    if not current_module_id and populated_module_id:
                        update_needed = True
                    
                    if update_needed:
                        cursor.execute("""
                            UPDATE TestCases 
                            SET project_id = COALESCE(project_id, ?), 
                                module_id = COALESCE(module_id, ?)
                            WHERE id = ?
                        """, (populated_project_id, populated_module_id, testcase_db_id))
                        
                        fix_summary['fixes_applied'].append({
                            'testcase_name': testcase_name,
                            'testcase_id': testcase_id,
                            'project_name': project_name_from_id,
                            'module_name': module_name_from_id,
                            'populated_project_id': populated_project_id,
                            'populated_module_id': populated_module_id
                        })
                        
                        print(f"[POPULATE_METADATA] Updated testcase {testcase_name} with project_id={populated_project_id}, module_id={populated_module_id}")
                else:
                    print(f"[POPULATE_METADATA] Could not parse project/module from testcase_id: {testcase_id}")
            else:
                print(f"[POPULATE_METADATA] Invalid testcase_id format: {testcase_id}")
        
        conn.commit()
        conn.close()
        
        print(f"[SUCCESS] Metadata population completed. Projects: {fix_summary['project_ids_populated']}, Modules: {fix_summary['module_ids_populated']}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully populated {fix_summary["project_ids_populated"]} project_ids and {fix_summary["module_ids_populated"]} module_ids',
            'fix_summary': fix_summary
        })
        
    except Exception as e:
        print(f"[ERROR] Error populating testcase metadata: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/fix-project-module-names', methods=['POST'])
def fix_project_module_names():
    """Fix missing/incorrect project and module names in existing test execution results"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        print("[FIX_METADATA] Starting project/module name fix for execution results...")
        
        # Get all selenium_results that have missing or 'Unknown' project/module names
        cursor.execute("""
            SELECT DISTINCT sr.testcase_name
            FROM selenium_results sr
            WHERE sr.projectname IS NULL OR sr.projectname = '' OR sr.projectname = 'Unknown Project'
               OR sr.modulename IS NULL OR sr.modulename = '' OR sr.modulename = 'Unknown Module'
        """)
        
        problem_testcases = cursor.fetchall()
        
        fix_summary = {
            'total_testcases_checked': len(problem_testcases),
            'total_results_updated': 0,
            'fixes_applied': []
        }
        
        for (testcase_name,) in problem_testcases:
            print(f"[FIX_METADATA] Processing testcase: {testcase_name}")
            
            # Get the correct project and module info from TestCases table
            cursor.execute("""
                SELECT COALESCE(p1.name, p2.name, 'Unknown Project') as project_name,
                       COALESCE(m.module_name, 'Unknown Module') as module_name
                FROM TestCases tc
                LEFT JOIN Modules m ON tc.module_id = m.id
                LEFT JOIN Projects p1 ON tc.project_id = p1.id
                LEFT JOIN Projects p2 ON m.project_id = p2.id
                WHERE tc.name = ?
            """, (testcase_name,))
            
            testcase_metadata = cursor.fetchone()
            
            if testcase_metadata:
                correct_project_name = testcase_metadata[0]
                correct_module_name = testcase_metadata[1]
                
                # Count how many results need updating
                cursor.execute("""
                    SELECT COUNT(*) FROM selenium_results
                    WHERE testcase_name = ? AND (
                        projectname IS NULL OR projectname = '' OR projectname = 'Unknown Project' OR
                        modulename IS NULL OR modulename = '' OR modulename = 'Unknown Module'
                    )
                """, (testcase_name,))
                
                results_to_update = cursor.fetchone()[0]
                
                if results_to_update > 0:
                    # Update the execution results with correct metadata
                    cursor.execute("""
                        UPDATE selenium_results 
                        SET projectname = ?, modulename = ?
                        WHERE testcase_name = ? AND (
                            projectname IS NULL OR projectname = '' OR projectname = 'Unknown Project' OR
                            modulename IS NULL OR modulename = '' OR modulename = 'Unknown Module'
                        )
                    """, (correct_project_name, correct_module_name, testcase_name))
                    
                    fix_summary['total_results_updated'] += results_to_update
                    fix_summary['fixes_applied'].append({
                        'testcase_name': testcase_name,
                        'correct_project_name': correct_project_name,
                        'correct_module_name': correct_module_name,
                        'results_updated': results_to_update
                    })
                    
                    print(f"[FIX_METADATA] Fixed {results_to_update} results for {testcase_name}: Project='{correct_project_name}', Module='{correct_module_name}'")
            else:
                print(f"[FIX_METADATA] No metadata found in TestCases table for: {testcase_name}")
        
        conn.commit()
        conn.close()
        
        print(f"[SUCCESS] Project/Module name fix completed. Updated {fix_summary['total_results_updated']} results across {len(fix_summary['fixes_applied'])} test cases.")
        
        return jsonify({
            'success': True,
            'message': f'Successfully fixed project/module names for {fix_summary["total_results_updated"]} execution results',
            'fix_summary': fix_summary
        })
        
    except Exception as e:
        print(f"[ERROR] Error fixing project/module names: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/brd/upload', methods=['POST'])
def upload_brd_file():
    """Upload BRD file and store in database"""
    try:
        # Ensure BRD table exists
        create_brd_table_if_not_exists()
        
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # Get file type from form data
        file_type = request.form.get('file_type', 'document')
        if file_type not in ['document', 'pdf', 'excel']:
            return jsonify({'error': 'Invalid file type'}), 400

        # Get name and description from form data
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()

        if not name:
            return jsonify({'error': 'Name is required'}), 400

        # Validate file extension based on type
        allowed_extensions = {
            'document': ['.doc', '.docx'],
            'pdf': ['.pdf'],
            'excel': ['.xlsx', '.xls']
        }

        file_ext = '.' + file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions[file_type]:
            return jsonify({'error': f'Invalid file extension for {file_type} type'}), 400

        # Generate unique filename
        import uuid
        unique_filename = f"{uuid.uuid4()}_{file.filename}"

        # Create uploads directory if it doesn't exist
        uploads_dir = os.path.join(os.getcwd(), 'uploads', 'brd')
        os.makedirs(uploads_dir, exist_ok=True)

        # Save file
        file_path = os.path.join(uploads_dir, unique_filename)
        file.save(file_path)

        # Get file size
        file_size = os.path.getsize(file_path)

        # Store in database
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO BRD (file_name, file_type, original_name, file_path, file_size, uploaded_by, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, file_type, file.filename, file_path, file_size, user_email, description))

        brd_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        conn.commit()
        conn.close()

        return jsonify({
            'success': True,
            'message': 'BRD file uploaded successfully',
            'brd_id': brd_id,
            'file_name': name,
            'original_name': file.filename,
            'file_type': file_type,
            'file_size': file_size
        }), 201

    except Exception as e:
        print(f"[ERROR] BRD upload failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/brd/files', methods=['GET'])
def get_brd_files():
    """Get list of uploaded BRD files"""
    try:
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, file_name, file_type, original_name, file_size, uploaded_by, uploaded_at, status
            FROM BRD
            WHERE uploaded_by = ?
            ORDER BY uploaded_at DESC
        """, (user_email,))

        files = []
        for row in cursor.fetchall():
            files.append({
                'id': row[0],
                'file_name': row[1],
                'file_type': row[2],
                'original_name': row[3],
                'file_size': row[4],
                'uploaded_by': row[5],
                'uploaded_at': format_timestamp(row[6]) if row[6] else None,
                'status': row[7]
            })

        conn.close()
        return jsonify({'files': files}), 200

    except Exception as e:
        print(f"[ERROR] Get BRD files failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/brd/download/<int:file_id>', methods=['GET'])
def download_brd_file(file_id):
    """Download BRD file"""
    try:
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT file_path, original_name, uploaded_by
            FROM BRD
            WHERE id = ? AND uploaded_by = ?
        """, (file_id, user_email))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'error': 'File not found or access denied'}), 404

        file_path, original_name, uploaded_by = row

        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found on disk'}), 404

        return send_from_directory(
            os.path.dirname(file_path),
            os.path.basename(file_path),
            as_attachment=True,
            download_name=original_name
        )

    except Exception as e:
        print(f"[ERROR] BRD download failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/brd/delete/<int:file_id>', methods=['DELETE'])
def delete_brd_file(file_id):
    """Delete BRD file"""
    try:
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()

        # Get file info and verify ownership
        cursor.execute("""
            SELECT file_path, original_name, uploaded_by
            FROM BRD
            WHERE id = ? AND uploaded_by = ?
        """, (file_id, user_email))

        row = cursor.fetchone()

        if not row:
            conn.close()
            return jsonify({'error': 'File not found or access denied'}), 404

        file_path, original_name, uploaded_by = row

        # Delete file from disk if it exists
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[BRD_DELETE] Deleted file from disk: {file_path}")
            except Exception as e:
                print(f"[WARNING] Could not delete file from disk: {str(e)}")

        # Delete record from database
        cursor.execute("DELETE FROM BRD WHERE id = ?", (file_id,))
        conn.commit()
        conn.close()

        print(f"[SUCCESS] BRD file deleted: {original_name} (ID: {file_id})")

        return jsonify({
            'success': True,
            'message': 'BRD file deleted successfully',
            'file_id': file_id,
            'file_name': original_name
        }), 200

    except Exception as e:
        print(f"[ERROR] BRD delete failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-testcases-from-brd', methods=['POST'])
def generate_testcases_from_brd():
    """Generate test cases from BRD documents using OpenAI"""
    # Import required modules at the top of the function
    from groq import Groq
    import httpx
    import json

    try:
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        brd_files = data.get('brd_files', [])
        project_id = data.get('project_id')
        module_id = data.get('module_id')

        if not brd_files:
            return jsonify({'error': 'No BRD files selected'}), 400

        if not project_id or not module_id:
            return jsonify({'error': 'Project and module information required'}), 400

        # Get project and module details
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT p.name as project_name, m.module_name
            FROM Projects p
            JOIN Modules m ON p.id = m.project_id
            WHERE p.id = ? AND m.id = ?
        """, (project_id, module_id))

        project_module = cursor.fetchone()
        if not project_module:
            conn.close()
            return jsonify({'error': 'Invalid project or module'}), 400

        project_name, module_name = project_module

        # Read BRD files content
        brd_content = ""
        excel_files = []  # Initialize here to collect Excel file data
        for brd_file in brd_files:
            file_id = brd_file.get('id')
            if not file_id:
                continue

            cursor.execute("""
                SELECT file_path, original_name, file_type
                FROM BRD
                WHERE id = ? AND uploaded_by = ?
            """, (file_id, user_email))

            file_row = cursor.fetchone()
            if file_row:
                file_path, original_name, file_type = file_row

                if os.path.exists(file_path):
                    try:
                        # Read file content based on type
                        if file_type == 'pdf':
                            import PyPDF2
                            with open(file_path, 'rb') as f:
                                pdf_reader = PyPDF2.PdfReader(f)
                                for page in pdf_reader.pages:
                                    brd_content += page.extract_text() + "\n"
                        elif file_type == 'document':
                            import docx
                            doc = docx.Document(file_path)
                            for para in doc.paragraphs:
                                brd_content += para.text + "\n"
                        elif file_type == 'excel':
                            print(f"[EXCEL] Processing Excel file: {original_name}")
                            # Parse Excel file directly to extract test cases
                            try:
                                import pandas as pd
                                print(f"[EXCEL] Reading Excel file with pandas...")
                                excel_data = pd.read_excel(file_path, sheet_name=None)  # Read all sheets
                                print(f"[EXCEL] Successfully read {len(excel_data)} sheets from Excel file")
                            except Exception as excel_error:
                                print(f"[EXCEL] Error reading Excel file: {str(excel_error)}")
                                continue

                            # Store Excel data for direct processing instead of text conversion
                            excel_testcases = []
                            for sheet_name, df in excel_data.items():
                                print(f"[EXCEL] Processing sheet: {sheet_name}")
                                print(f"[EXCEL] Columns found: {list(df.columns)}")

                                # Skip empty sheets
                                if df.empty:
                                    print(f"[EXCEL] Skipping empty sheet: {sheet_name}")
                                    continue

                                # Convert DataFrame to list of dicts for processing, skip header row
                                # Since the first row contains headers like "Test Case Name", skip it
                                sheet_data = df.to_dict('records')
                                print(f"[EXCEL] Initial sheet_data length: {len(sheet_data)}")
                                if sheet_data:
                                    print(f"[EXCEL] First row keys: {list(sheet_data[0].keys())}")
                                    print(f"[EXCEL] First row values: {sheet_data[0]}")

                                # Temporarily disable header detection to debug
                                print(f"[EXCEL] Temporarily disabling header detection for debugging")
                                print(f"[EXCEL] Processing all {len(sheet_data)} rows including potential headers")
                                # if sheet_data and len(sheet_data) > 0:
                                #     # Check if first row looks like headers
                                #     first_row = sheet_data[0]
                                #     header_keywords = ['test case name', 'description', 'test steps']
                                #     is_header = any(
                                #         any(keyword in str(first_row.get(col, '')).lower() for keyword in header_keywords)
                                #         for col in [tc_column, tc_desc_column, step_desc_column]
                                #         if col in first_row
                                #     )

                                #     print(f"[EXCEL] Header detection - tc_column: {tc_column}, tc_desc_column: {tc_desc_column}, step_desc_column: {step_desc_column}")
                                #     print(f"[EXCEL] Header keywords check: {header_keywords}")
                                #     print(f"[EXCEL] Is header detected: {is_header}")

                                #     if is_header:
                                #         print(f"[EXCEL] Skipping header row")
                                #         sheet_data = sheet_data[1:]
                                #     else:
                                #         print(f"[EXCEL] No header detected, processing all {len(sheet_data)} rows")
                                # else:
                                #     print(f"[EXCEL] No data rows found in sheet")

                                # Identify columns more flexibly - handle both named and numeric columns
                                tc_column = None
                                tc_desc_column = None
                                step_desc_column = None
                                expected_result_column = None

                                print(f"[EXCEL] Available columns: {list(df.columns)}")

                                def _is_non_empty_cell(value):
                                    return value is not None and not pd.isna(value) and str(value).strip() != ''

                                # First, try to find columns by name (for properly formatted Excel files)
                                for col in df.columns:
                                    col_lower = str(col).lower().strip()
                                    # Keep this strict; matching bare 'tc' causes false positives
                                    if any(keyword in col_lower for keyword in ['testcase', 'test_case', 'test case', 'tc name', 'testcasename', 'test case name', 'test name', 'casename']):
                                        tc_column = col
                                        print(f"[EXCEL] Found test case column: '{col}' (col_lower: '{col_lower}')")
                                        break

                                # Find test case description column
                                for col in df.columns:
                                    col_lower = str(col).lower().strip()
                                    # Look for description column that doesn't contain step/action keywords
                                    if ('description' in col_lower or 'desc' in col_lower) and \
                                       not ('step' in col_lower or 'action' in col_lower):
                                        tc_desc_column = col
                                        print(f"[EXCEL] Found test case description column: '{col}'")
                                        break

                                # Find test step description column
                                for col in df.columns:
                                    col_lower = str(col).lower().strip()
                                    # Look for step/action columns, or description columns that might contain steps
                                    if (('step' in col_lower or 'action' in col_lower) and \
                                       ('description' in col_lower or 'desc' in col_lower or 'detail' in col_lower)) or \
                                       (col_lower == 'description' and tc_desc_column and col != tc_desc_column) or \
                                       ('test step' in col_lower) or \
                                       ('step' in col_lower and 'test' in col_lower):
                                        step_desc_column = col
                                        print(f"[EXCEL] Found test step description column: '{col}'")
                                        break

                                # Find expected result column
                                for col in df.columns:
                                    col_lower = str(col).lower().strip()
                                    if 'expected' in col_lower and ('result' in col_lower or 'outcome' in col_lower):
                                        expected_result_column = col
                                        print(f"[EXCEL] Found expected result column: '{col}'")
                                        break

                                # Fallback: if columns not detected, assume positions based on user's format
                                # User's format: Test Case Name | Description | Test Steps Description
                                # This handles both named columns and numeric columns (0, 1, 2)
                                if not tc_column and len(df.columns) >= 1:
                                    tc_column = df.columns[0]
                                    print(f"[EXCEL] Fallback: Assuming first column '{tc_column}' is test case column")

                                if not tc_desc_column and len(df.columns) >= 2:
                                    tc_desc_column = df.columns[1]
                                    print(f"[EXCEL] Fallback: Assuming second column '{tc_desc_column}' is test case description column")

                                if not step_desc_column and len(df.columns) >= 3:
                                    step_desc_column = df.columns[2]
                                    print(f"[EXCEL] Fallback: Assuming third column '{step_desc_column}' is test step description column")

                                print(f"[EXCEL] Final column mapping: TC='{tc_column}', Desc='{tc_desc_column}', Steps='{step_desc_column}'")

                                if not tc_column:
                                    print(f"[EXCEL] ERROR: No test case column found in sheet {sheet_name}. Available columns: {list(df.columns)}")
                                    continue

                                if not step_desc_column:
                                    print(f"[EXCEL] ERROR: No test step description column found in sheet {sheet_name}. Available columns: {list(df.columns)}")
                                    continue

                                # Group by test case - handle multi-row format where test case name only appears in first row
                                testcase_groups = {}
                                current_tc_name = None
                                current_tc_rows = []

                                print(f"[EXCEL] Processing {len(sheet_data)} rows for test case grouping")

                                for row_idx, row in enumerate(sheet_data):
                                    print(f"[EXCEL] Processing row {row_idx}: {row}")

                                    # Temporarily disable empty row detection for debugging
                                    print(f"  [EXCEL] Temporarily disabling empty row detection")
                                    # # Skip completely empty rows (rows where all key columns are empty/NaN)
                                    # is_empty_row = True
                                    # for col in [tc_column, tc_desc_column, step_desc_column]:
                                    #     print(f"  [EXCEL] Checking column {col}: in row = {col in row}")
                                    #     if col and col in row:
                                    #         cell_value = row.get(col)
                                    #         print(f"    [EXCEL] Cell value: '{cell_value}' (type: {type(cell_value)})")
                                    #         # Be more lenient with empty cell detection
                                    #         cell_str = str(cell_value).strip() if cell_value is not None else ''
                                    #         is_valid_value = cell_str != '' and cell_str.lower() not in ['nan', 'none']
                                    #         print(f"    [EXCEL] Is valid value: {is_valid_value}")
                                    #         if is_valid_value:
                                    #             is_empty_row = False
                                    #             break

                                    # print(f"  [EXCEL] Row {row_idx} is_empty_row: {is_empty_row}")
                                    # if is_empty_row:
                                    #     print(f"[EXCEL] Skipping empty row {row_idx}")
                                    #     continue

                                    # Get the raw value from the test case column
                                    raw_tc_value = row.get(tc_column)
                                    print(f"[EXCEL] Row {row_idx} - TC column value: '{raw_tc_value}' (type: {type(raw_tc_value)})")

                                    # Check if it's a valid test case name (not NaN and not empty)
                                    is_valid_tc_name = (raw_tc_value is not None and
                                                       not (pd.isna(raw_tc_value)) and
                                                       str(raw_tc_value).strip() != '')

                                    print(f"[EXCEL] Row {row_idx} - is_valid_tc_name: {is_valid_tc_name}")

                                    if is_valid_tc_name:
                                        tc_name = str(raw_tc_value).strip()
                                        print(f"[EXCEL] Row {row_idx} - Found test case name: '{tc_name}'")

                                        # Save previous group if it exists
                                        if current_tc_name and current_tc_rows:
                                            if current_tc_name not in testcase_groups:
                                                testcase_groups[current_tc_name] = []
                                            testcase_groups[current_tc_name].extend(current_tc_rows)
                                            print(f"[EXCEL] Saved previous group '{current_tc_name}' with {len(current_tc_rows)} rows")

                                        # Start new group
                                        current_tc_name = tc_name
                                        current_tc_rows = [row]
                                        print(f"[EXCEL] Started new test case group: '{tc_name}'")
                                    else:
                                        # Continue adding to current group if we have a current test case
                                        if current_tc_name:
                                            current_tc_rows.append(row)
                                            print(f"[EXCEL] Added row {row_idx} to existing test case group: '{current_tc_name}' (now {len(current_tc_rows)} rows)")
                                        else:
                                            print(f"[EXCEL] WARNING: Row {row_idx} has no test case name but no current group exists - skipping")

                                # Don't forget the last group
                                if current_tc_name and current_tc_rows:
                                    if current_tc_name not in testcase_groups:
                                        testcase_groups[current_tc_name] = []
                                    testcase_groups[current_tc_name].extend(current_tc_rows)
                                    print(f"[EXCEL] Saved final group '{current_tc_name}' with {len(current_tc_rows)} rows")

                                print(f"[EXCEL] Final grouping result: {len(testcase_groups)} test cases")
                                for tc_name, rows in testcase_groups.items():
                                    print(f"  - '{tc_name}': {len(rows)} rows")

                                print(f"[EXCEL] Found {len(testcase_groups)} unique test cases in sheet {sheet_name}")

                                # Process each test case in the same order they appear in Excel
                                for tc_name, rows in testcase_groups.items():
                                    print(f"[EXCEL] Processing test case '{tc_name}' with {len(rows)} rows")
                                    for i, row in enumerate(rows):
                                        tc_val = str(row.get(tc_column, '')).strip() if tc_column else ''
                                        desc_val = str(row.get(tc_desc_column, '')).strip() if tc_desc_column else ''
                                        step_val = str(row.get(step_desc_column, '')).strip() if step_desc_column else ''
                                        print(f"  [EXCEL] Grouped row {i}: tc='{tc_val}', desc='{desc_val}', step='{step_val}'")

                                    # Debug: Check for duplicate steps within this test case
                                    all_steps_in_group = []
                                    for row in rows:
                                        step_val = row.get(step_desc_column)
                                        if _is_non_empty_cell(step_val):
                                            all_steps_in_group.append(str(step_val).strip())

                                    print(f"[EXCEL] Unique steps in '{tc_name}': {len(set(all_steps_in_group))} out of {len(all_steps_in_group)} total")
                                    if len(set(all_steps_in_group)) != len(all_steps_in_group):
                                        print(f"[EXCEL] WARNING: Duplicate steps detected in '{tc_name}'!")
                                        from collections import Counter
                                        step_counts = Counter(all_steps_in_group)
                                        duplicates = [step for step, count in step_counts.items() if count > 1]
                                        print(f"[EXCEL] Duplicate steps: {duplicates}")

                                    # Skip empty test case names
                                    if not tc_name or str(tc_name).lower() in ['nan', 'none', '']:
                                        continue

                                    testcase_data = {
                                        'name': tc_name,
                                        'description': '',
                                        'priority': 'Medium',  # Default priority
                                        'suite_type': 'regression',  # Default suite type
                                        'test_steps': []
                                    }

                                    # Extract test case description from the first row
                                    if tc_desc_column:
                                        desc_value = rows[0].get(tc_desc_column)
                                        if desc_value is not None and not pd.isna(desc_value) and str(desc_value).strip():
                                            testcase_data['description'] = str(desc_value).strip()
                                            print(f"[EXCEL] Test case description: '{testcase_data['description']}'")
                                        else:
                                            print(f"[EXCEL] No valid description found, using default")

                                    # Extract test steps from all rows
                                    step_no = 1
                                    max_steps_per_testcase = 50  # Safety limit to prevent runaway processing

                                    for i, row in enumerate(rows):
                                        if step_no > max_steps_per_testcase:
                                            print(f"[EXCEL] WARNING: Reached maximum steps limit ({max_steps_per_testcase}) for test case '{tc_name}', stopping processing")
                                            break

                                        # Primary source: mapped step column; fallback: description/other non-empty columns.
                                        raw_step_value = row.get(step_desc_column)
                                        step_source = f"step column '{step_desc_column}'"
                                        if not _is_non_empty_cell(raw_step_value):
                                            if tc_desc_column and _is_non_empty_cell(row.get(tc_desc_column)):
                                                raw_step_value = row.get(tc_desc_column)
                                                step_source = f"description column '{tc_desc_column}'"
                                            else:
                                                for col in df.columns:
                                                    if col == tc_column:
                                                        continue
                                                    candidate = row.get(col)
                                                    if _is_non_empty_cell(candidate):
                                                        raw_step_value = candidate
                                                        step_source = f"fallback column '{col}'"
                                                        break

                                        is_valid_step = _is_non_empty_cell(raw_step_value)
                                        step_desc = str(raw_step_value).strip() if is_valid_step else ''
                                        print(f"[EXCEL] Row {i}: raw_step='{raw_step_value}', source={step_source}, is_valid={is_valid_step}, step_desc='{step_desc}'")

                                        # Check if step_desc is valid
                                        if step_desc and step_desc.lower() not in ['nan', 'none', '']:

                                            expected_result = ''
                                            if expected_result_column:
                                                exp_value = row.get(expected_result_column, '')
                                                if _is_non_empty_cell(exp_value):
                                                    expected_result = str(exp_value).strip()

                                            testcase_data['test_steps'].append({
                                                'step_no': step_no,
                                                'description': step_desc,
                                                'expected_result': expected_result
                                            })
                                            print(f"[EXCEL] Added step {step_no}: '{step_desc}'")
                                            step_no += 1
                                        else:
                                            print(f"[EXCEL] Skipped step {step_no}: step_desc='{step_desc}', is_empty={not step_desc}, is_nan_like={step_desc.lower() in ['nan', 'none', '']}")

                                    # Only add test case if it has steps
                                    if testcase_data['test_steps']:
                                        # Remove duplicate steps (same description)
                                        seen_descriptions = set()
                                        deduplicated_steps = []

                                        for step in testcase_data['test_steps']:
                                            step_desc = step['description'].strip()
                                            if step_desc not in seen_descriptions:
                                                seen_descriptions.add(step_desc)
                                                deduplicated_steps.append(step)
                                            else:
                                                print(f"[EXCEL] Removed duplicate step: '{step_desc}'")

                                        # Update step numbers after deduplication
                                        for i, step in enumerate(deduplicated_steps, 1):
                                            step['step_no'] = i

                                        testcase_data['test_steps'] = deduplicated_steps

                                        # Debug: Check for duplicates in final test steps
                                        step_descriptions = [step['description'] for step in testcase_data['test_steps']]
                                        unique_steps = len(set(step_descriptions))
                                        total_steps = len(step_descriptions)
                                        print(f"[EXCEL] Final test case '{tc_name}' has {total_steps} steps ({unique_steps} unique) after deduplication")

                                        excel_testcases.append(testcase_data)
                                        print(f"[EXCEL] Successfully added test case '{tc_name}' with {len(testcase_data['test_steps'])} steps")
                                    else:
                                        print(f"[EXCEL] Skipped test case '{tc_name}' - no valid steps found")

                            # Store Excel data for later processing
                            excel_files.append({
                                'file_name': original_name,
                                'testcases': excel_testcases
                            })

                            print(f"[EXCEL] Successfully processed {len(excel_testcases)} test cases from {original_name}")
                            brd_content += f"\n--- Excel file {original_name} processed with {len(excel_testcases)} test cases ---\n\n"
                        else:
                            # For other file types, try to read as text
                            with open(file_path, 'r', encoding='utf-8') as f:
                                brd_content += f.read() + "\n"

                        brd_content += f"\n--- End of {original_name} ---\n\n"

                    except Exception as e:
                        print(f"[WARNING] Could not read file {original_name}: {str(e)}")
                        continue

        conn.close()

        # Check if we have Excel files with direct test case data
        print(f"[DEBUG] Excel files found: {len(excel_files)}")
        if excel_files:
            print(f"[EXCEL] Found {len(excel_files)} Excel files with direct test case data")
            # Use Excel data directly instead of AI generation
            all_testcases = []
            for excel_file in excel_files:
                all_testcases.extend(excel_file['testcases'])

            if all_testcases:
                print(f"[EXCEL] Using {len(all_testcases)} test cases directly from Excel files")
                testcases = all_testcases
            else:
                return jsonify({'error': 'No valid test cases found in Excel files. Please ensure your Excel has columns for Test Case names and Test Step descriptions.'}), 400
        else:
            # Use traditional BRD processing with AI for non-Excel files
            if not brd_content.strip():
                return jsonify({'error': 'No readable content found in BRD files'}), 400

            # Use Groq to generate test cases
            groq_api_key = "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"
            if not groq_api_key:
                return jsonify({'error': 'Groq API key not configured.'}), 500

            # Initialize Groq client - compatible with both old and new httpx versions
            try:
                # Try newer httpx version first
                http_client = httpx.Client()
                client = Groq(api_key=groq_api_key, http_client=http_client)
            except TypeError:
                # Fallback for older httpx versions - don't pass http_client
                client = Groq(api_key=groq_api_key)

            prompt = f"""
            Based on the following Business Requirements Document (BRD) content, generate comprehensive test cases for software testing.

            BRD Content:
            {brd_content[:10000]}  # Limit content to avoid token limits

            Please generate test cases in the following JSON format:
            {{
                "testcases": [
                    {{
                        "name": "Test case name (clear and descriptive)",
                        "description": "Detailed description of what this test case validates",
                        "priority": "High/Medium/Low",
                        "suite_type": "smoke/sanity/regression/general/automation/development",
                        "test_steps": [
                            {{
                                "step_no": 1,
                                "description": "Step description",
                                "expected_result": "Expected outcome"
                            }}
                        ]
                    }}
                ]
            }}

            Requirements:
            1. Generate 5-15 test cases depending on the complexity of the BRD
            2. Each test case should have a clear, descriptive name
            3. Include detailed descriptions
            4. Set appropriate priority levels (High for critical functionality, Medium for important features, Low for nice-to-have)
            5. Assign appropriate suite_type based on test nature:
               - 'smoke': Critical path tests, basic functionality validation
               - 'sanity': Quick validation of essential features
               - 'regression': Comprehensive testing, integration tests
               - 'general': Standard functional tests
               - 'automation': Tests specifically for automation framework
               - 'development': Tests for development phase validation
            6. Each test case should have 3-8 detailed test steps
            7. Focus on functional testing, edge cases, and error scenarios
            8. Ensure test cases are atomic and independent where possible

            Return only valid JSON, no additional text.
            """

            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": "You are an expert QA engineer who creates comprehensive test cases from business requirements."},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=4000,
                    temperature=0.3
                )

                ai_response = response.choices[0].message.content

                # Check if response is None or empty
                if not ai_response:
                    print("[ERROR] Groq API returned empty response")
                    raise Exception("Groq API returned an empty response")

                ai_response = ai_response.strip()

                # Handle potential empty response after stripping
                if not ai_response:
                    print("[ERROR] Groq API returned only whitespace")
                    raise Exception("Groq API returned only whitespace")

                print(f"[DEBUG] Raw AI response length: {len(ai_response)}")
                print(f"[DEBUG] AI response starts with: {ai_response[:200]}...")

                # Clean up the response to ensure it's valid JSON
                if ai_response.startswith('```json'):
                    ai_response = ai_response[7:]
                if ai_response.endswith('```'):
                    ai_response = ai_response[:-3]
                ai_response = ai_response.strip()

                # Final check for empty response after cleanup
                if not ai_response:
                    print("[ERROR] Groq API response became empty after cleanup")
                    raise Exception("Groq API response became empty after cleanup")

                # Try to parse JSON, with better error handling
                try:
                    generated_data = json.loads(ai_response)
                    print("[SUCCESS] Successfully parsed JSON response from Groq API")
                except json.JSONDecodeError as json_error:
                    print(f"[ERROR] JSON parsing failed: {str(json_error)}")
                    print(f"[DEBUG] Cleaned AI response: {ai_response[:500]}...")

                    # Try to extract JSON from response if it contains extra text
                    json_start = ai_response.find('{')
                    json_end = ai_response.rfind('}') + 1
                    if json_start != -1 and json_end > json_start:
                        try:
                            json_content = ai_response[json_start:json_end]
                            generated_data = json.loads(json_content)
                            print("[INFO] Successfully extracted JSON from response")
                        except json.JSONDecodeError as extract_error:
                            print(f"[ERROR] Failed to extract JSON: {str(extract_error)}")
                            print(f"[DEBUG] Extracted content: {json_content[:200]}...")
                            raise Exception(f"Failed to parse JSON response after extraction: {ai_response[:200]}...")
                    else:
                        print("[ERROR] No JSON structure found in response")
                        raise Exception(f"Invalid JSON response from Groq API - no JSON structure found: {ai_response[:200]}...")

                testcases = generated_data.get('testcases', [])

                if not testcases:
                    return jsonify({'error': 'No test cases generated'}), 500

            except Exception as e:
                print(f"[ERROR] Groq API error: {str(e)}")
                return jsonify({'error': f'Groq API error: {str(e)}'}), 500

        # Save generated test cases to database (for both Excel and AI-generated test cases)
        print(f"[SAVE] Starting to save {len(testcases) if 'testcases' in locals() else 'undefined'} test cases to database")
        if 'testcases' not in locals():
            print("[ERROR] testcases variable is not defined!")
            return jsonify({'error': 'testcases variable not defined'}), 500
        print(f"[SAVE] testcases content: {testcases[:2] if testcases else 'empty'}")  # Show first 2 items
        conn = get_db_connection()
        cursor = conn.cursor()

        generated_testcases = []

        for tc_data in testcases:
                # Generate testcase_id
                testcase_id = generate_testcase_id(project_name, module_name, tc_data['name'], conn)

                # Set defaults for Excel files (which may not have priority/suite_type)
                priority = tc_data.get('priority', 'Medium')  # Default to Medium
                suite_type = tc_data.get('suite_type', 'regression')  # Default to regression

                # Create test case
                cursor.execute("""
                    INSERT INTO TestCases (
                        testcase_id, name, description, project_id, module_id,
                        priority, status, suite_type, created_date
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'Active', ?, GETDATE())
                """, (
                    testcase_id,
                    tc_data['name'],
                    tc_data['description'],
                    project_id,
                    module_id,
                    priority,
                    suite_type
                ))

                # Get the inserted test case ID
                cursor.execute("SELECT @@IDENTITY")
                tc_db_id = cursor.fetchone()[0]

                # Create test steps table and insert steps
                table_name = generate_unique_table_name(project_name, module_name, tc_data['name'])

                cursor.execute(f"""
                    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='{table_name}' AND xtype='U')
                    CREATE TABLE [{table_name}] (
                        id INT IDENTITY(1,1) PRIMARY KEY,
                        tc_id NVARCHAR(255),
                        step_no INT,
                        test_step_description NVARCHAR(500),
                        element_name NVARCHAR(255),
                        action_type NVARCHAR(100),
                        xpath NVARCHAR(1000),
                        [values] NVARCHAR(500),
                        expected_result NVARCHAR(500),
                        actual_result NVARCHAR(500),
                        status NVARCHAR(20) DEFAULT 'Not Executed',
                        page NVARCHAR(255) NULL
                    )
                """)

                # Insert test steps
                for step in tc_data.get('test_steps', []):
                    cursor.execute(f"""
                        INSERT INTO [{table_name}] (
                            tc_id, step_no, test_step_description, expected_result
                        )
                        VALUES (?, ?, ?, ?)
                    """, (
                        testcase_id,
                        step['step_no'],
                        step['description'],
                        step.get('expected_result', '')
                    ))

                generated_testcases.append({
                    'id': tc_db_id,
                    'testcase_id': testcase_id,
                    'name': tc_data['name'],
                    'description': tc_data['description'],
                    'priority': tc_data['priority'],
                    'steps_count': len(tc_data.get('test_steps', []))
                })

        conn.commit()
        conn.close()

        return jsonify({
                'success': True,
                'message': f'Successfully generated {len(generated_testcases)} test cases from BRD documents',
                'generated_testcases': generated_testcases,
                'brd_files_processed': len(brd_files)
            }), 200

    except Exception as e:
        print(f"[ERROR] Generate testcases from BRD failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/testcases/filtered', methods=['GET'])
def get_testcases_filtered():
    """Get test cases with optional suite_type and module_id filters"""
    try:
        suite_type = request.args.get('suite_type')
        module_id = request.args.get('module_id')

        if not module_id:
            return jsonify({'error': 'module_id parameter is required'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # Build query based on parameters
        query = """
            SELECT id, testcase_id, name, description, project_id, module_id, created_date, status, priority, suite_type
            FROM TestCases
            WHERE module_id = ?
        """
        params = [module_id]

        if suite_type:
            if suite_type.lower() == 'null':
                # Handle NULL suite_type
                query += " AND suite_type IS NULL"
            else:
                query += " AND suite_type = ?"
                params.append(suite_type)

        query += " ORDER BY id ASC"

        cursor.execute(query, params)

        testcases = []
        for row in cursor.fetchall():
            testcases.append({
                'id': row[0],
                'testcase_id': row[1],
                'name': row[2],
                'description': row[3],
                'project_id': row[4],
                'module_id': row[5],
                'created_date': format_timestamp(row[6]) if row[6] else None,
                'status': row[7],
                'priority': row[8],
                'suite_type': row[9]
            })

        conn.close()

        return jsonify({
            'test_cases': testcases,
            'total_count': len(testcases),
            'filters': {
                'module_id': module_id,
                'suite_type': suite_type
            }
        })

    except Exception as e:
        print(f"[ERROR] Get testcases filtered error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup-orphaned-data', methods=['POST'])
def cleanup_orphaned_data():
    """Clean up orphaned test execution data that no longer has corresponding test cases"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get all existing test case names from TestCases table
        cursor.execute("SELECT name FROM TestCases")
        existing_testcases = {row[0] for row in cursor.fetchall()}

        # Get all test case names from selenium_results
        cursor.execute("SELECT DISTINCT testcase_name FROM selenium_results WHERE testcase_name IS NOT NULL")
        results_testcases = {row[0] for row in cursor.fetchall()}

        # Find orphaned test case names (exist in results but not in TestCases)
        orphaned_testcases = results_testcases - existing_testcases

        deletion_details = {
            'total_deleted': 0,
            'orphaned_testcases': list(orphaned_testcases),
            'deleted_records': []
        }

        # Delete orphaned records
        for orphaned_testcase in orphaned_testcases:
            # Count records before deletion
            cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_name = ?", (orphaned_testcase,))
            record_count = cursor.fetchone()[0]

            # Delete the orphaned records
            cursor.execute("DELETE FROM selenium_results WHERE testcase_name = ?", (orphaned_testcase,))

            deletion_details['total_deleted'] += record_count
            deletion_details['deleted_records'].append({
                'testcase_name': orphaned_testcase,
                'records_deleted': record_count
            })

            print(f"[CLEANUP] Deleted {record_count} orphaned records for test case: {orphaned_testcase}")

        # Also clean up records where testcase_name is NULL or empty
        cursor.execute("SELECT COUNT(*) FROM selenium_results WHERE testcase_name IS NULL OR testcase_name = ''")
        null_records = cursor.fetchone()[0]

        if null_records > 0:
            cursor.execute("DELETE FROM selenium_results WHERE testcase_name IS NULL OR testcase_name = ''")
            deletion_details['total_deleted'] += null_records
            deletion_details['deleted_records'].append({
                'testcase_name': 'NULL/Empty records',
                'records_deleted': null_records
            })
            print(f"[CLEANUP] Deleted {null_records} records with NULL/empty testcase_name")

        conn.commit()
        conn.close()

        print(f"[SUCCESS] Cleanup completed. Total deleted: {deletion_details['total_deleted']} records")

        return jsonify({
            'success': True,
            'message': f'Successfully cleaned up {deletion_details["total_deleted"]} orphaned records',
            'details': deletion_details
        })

    except Exception as e:
        print(f"[ERROR] Cleanup orphaned data error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Excel Files API for Test Value Management
@app.route('/api/excel-files/upload', methods=['POST'])
def upload_excel_file():
    """Upload Excel file and store in Values table"""
    try:
        # Get user email from form data or headers
        user_email = request.form.get('user_email') or request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        # No user authentication required for Excel upload
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_excel_mapping_infrastructure(conn)

        # Check if file is present
        if 'file' not in request.files:
            conn.close()
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            conn.close()
            return jsonify({'error': 'No file selected'}), 400

        # Validate file extension
        allowed_extensions = ['.xlsx', '.xls']
        file_ext = '.' + file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            conn.close()
            return jsonify({'error': 'Invalid file type. Only .xlsx and .xls files are allowed'}), 400

        # Generate unique filename
        import uuid
        unique_filename = f"{uuid.uuid4()}_{file.filename}"

        # Create uploads directory if it doesn't exist
        uploads_dir = os.path.join(os.getcwd(), 'uploads', 'excel_values')
        os.makedirs(uploads_dir, exist_ok=True)

        # Save file
        file_path = os.path.join(uploads_dir, unique_filename)
        file.save(file_path)

        # Get file size
        file_size = os.path.getsize(file_path)

        # Store in Values table
        cursor.execute("""
            INSERT INTO [Values] (file_name, original_name, file_path, file_size, uploaded_by)
            VALUES (?, ?, ?, ?, ?)
        """, (unique_filename, file.filename, file_path, file_size, user_email))

        file_id = cursor.execute("SELECT @@IDENTITY").fetchone()[0]

        conn.commit()
        conn.close()

        print(f"[EXCEL_UPLOAD] File uploaded: {file.filename} (ID: {file_id}) by {user_email}")

        return jsonify({
            'success': True,
            'message': 'Excel file uploaded successfully',
            'file_id': file_id,
            'file_name': unique_filename,
            'original_name': file.filename,
            'file_size': file_size
        }), 201

    except Exception as e:
        print(f"[ERROR] Excel file upload failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/excel-files', methods=['GET'])
def get_excel_files():
    """Get list of uploaded Excel files for the current user"""
    try:
        # Get user email from query params or headers
        user_email = request.args.get('user_email') or request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_excel_mapping_infrastructure(conn)

        cursor.execute("""
            SELECT id, file_name, original_name, file_size, uploaded_by, uploaded_at, status
            FROM [Values]
            WHERE uploaded_by = ? AND status = 'Active'
            ORDER BY uploaded_at DESC
        """, (user_email,))

        files = []
        for row in cursor.fetchall():
            files.append({
                'id': row[0],
                'file_name': row[1],
                'original_name': row[2],
                'file_size': row[3],
                'uploaded_by': row[4],
                'uploaded_at': format_timestamp(row[5]) if row[5] else None,
                'status': row[6]
            })

        conn.close()

        return jsonify({'files': files}), 200

    except Exception as e:
        print(f"[ERROR] Get Excel files failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/excel-files/<int:file_id>/parse', methods=['GET'])
def parse_excel_file(file_id):
    """Parse Excel file and extract values for test execution"""
    try:
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_excel_mapping_infrastructure(conn)

        # Get file info and verify ownership
        cursor.execute("""
            SELECT file_path, original_name, uploaded_by
            FROM [Values]
            WHERE id = ? AND status = 'Active'
        """, (file_id,))

        file_row = cursor.fetchone()
        conn.close()

        if not file_row:
            return jsonify({'error': 'File not found'}), 404

        file_path, original_name, uploaded_by = file_row

        # Verify ownership
        if uploaded_by != user_email:
            return jsonify({'error': 'Access denied'}), 403

        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found on disk'}), 404

        # Parse Excel file
        try:
            import pandas as pd

            # Read Excel file with first row as column headers
            excel_data = pd.read_excel(file_path, sheet_name=None, header=0)  # Read all sheets with first row as header

            if not excel_data:
                return jsonify({'error': 'No sheets found in Excel file'}), 400

            # Use the first sheet
            sheet_name = list(excel_data.keys())[0]
            df = excel_data[sheet_name]

            if df.empty:
                return jsonify({'error': 'Excel sheet is empty'}), 400

            # Get column headers (field names for test data)
            headers = df.columns.tolist()
            
            if len(headers) < 1:
                return jsonify({'error': 'No columns found in Excel file'}), 400

            # Convert each ROW to a data set (each row = one test iteration)
            # Headers are field names (e.g., "Username", "Password", "URL")
            # Each row is ONE complete data set
            values = []
            
            # Iterate through each COLUMN - each column is ONE complete data set (iteration)
            # Each ROW within the column represents a step value
            # Row 1 = Step 1, Row 2 = Step 2, etc.
            for col_idx in range(len(headers)):
                col_dict = {}
                col_name = headers[col_idx]
                
                # Each row becomes a step value for this column
                for row_idx in range(len(df)):
                    step_key = f"step_{row_idx + 1}"  # Row 1 = Step 1, Row 2 = Step 2
                    cell_value = df.iloc[row_idx, col_idx]
                    
                    if pd.isna(cell_value):
                        cell_value = ''
                    elif hasattr(cell_value, 'item'):
                        cell_value = cell_value.item()
                    
                    col_dict[step_key] = cell_value
                
                values.append(col_dict)

            if len(values) < 1:
                return jsonify({'error': 'No data columns found in Excel file'}), 400

            print(f"[EXCEL_PARSE] Successfully parsed {len(values)} columns (data sets) from {original_name}")
            print(f"[EXCEL_PARSE] Headers (Column Names): {headers}")
            print(f"[EXCEL_PARSE] Data Sets (Columns) Count: {len(values)}")
            print(f"[EXCEL_PARSE] Steps per Data Set: {len(df)} (rows in Excel)")

            return jsonify({
                'success': True,
                'file_id': file_id,
                'file_name': original_name,
                'sheet_name': sheet_name,
                'headers': headers,
                'values': values,
                'total_rows': len(df),
                'parsing_mode': 'columns',
                'data_sets': len(values),
                'field_count': len(headers),
                'steps_per_set': len(df)
            }), 200

        except ImportError:
            return jsonify({'error': 'Excel parsing libraries not available'}), 500
        except Exception as parse_error:
            print(f"[EXCEL_PARSE_ERROR] Failed to parse {original_name}: {str(parse_error)}")
            return jsonify({'error': f'Failed to parse Excel file: {str(parse_error)}'}), 400

    except Exception as e:
        print(f"[ERROR] Parse Excel file failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/excel-files/<int:file_id>', methods=['DELETE'])
def delete_excel_file(file_id):
    """Delete an uploaded Excel file"""
    try:
        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_excel_mapping_infrastructure(conn)

        # Get file info and verify ownership
        cursor.execute("""
            SELECT file_path, original_name, uploaded_by
            FROM [Values]
            WHERE id = ? AND status = 'Active'
        """, (file_id,))

        file_row = cursor.fetchone()

        if not file_row:
            conn.close()
            return jsonify({'error': 'File not found'}), 404

        file_path, original_name, uploaded_by = file_row

        # Verify ownership
        if uploaded_by != user_email:
            conn.close()
            return jsonify({'error': 'Access denied'}), 403

        # Mark file as inactive in database
        cursor.execute("""
            UPDATE [Values]
            SET status = 'Inactive'
            WHERE id = ?
        """, (file_id,))

        conn.commit()

        # Try to delete physical file if it exists
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"[EXCEL_DELETE] Physical file deleted: {file_path}")
        except Exception as file_error:
            print(f"[WARNING] Failed to delete physical file {file_path}: {str(file_error)}")
            # Continue anyway since database record is marked inactive

        conn.close()

        print(f"[EXCEL_DELETE] File deleted: {original_name} (ID: {file_id}) by {user_email}")

        return jsonify({
            'success': True,
            'message': 'File deleted successfully',
            'file_id': file_id
        }), 200

    except Exception as e:
        print(f"[ERROR] Delete Excel file failed: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/execute-with-excel-values', methods=['POST'])
def execute_with_excel_values():
    """Execute test case with values from Excel file"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        testcase_name = data.get('testcase_name')
        excel_values = data.get('excel_values', [])
        executor_type = data.get('executor_type', 'selenium')

        if not testcase_name:
            return jsonify({'error': 'testcase_name is required'}), 400

        if not excel_values or len(excel_values) == 0:
            return jsonify({'error': 'excel_values array must contain at least one data set'}), 400

        # Get user email from headers
        user_email = request.headers.get('X-User-Email')
        if not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        print(f"[EXCEL_EXECUTE] Starting execution of {testcase_name} with {len(excel_values)} data sets")

        # Execute with each data set from Excel
        execution_results = []

        for i, data_set in enumerate(excel_values):
            print(f"[EXCEL_EXECUTE] Executing data set {i+1}/{len(excel_values)}")

            try:
                # Create a modified request data for execution
                execution_data = {
                    'executor_type': executor_type,
                    'user_email': user_email,
                    'excel_data': data_set,  # Pass the current Excel data set for mapping
                    'data_set_index': i + 1,
                    'total_data_sets': len(excel_values)
                }

                # Execute the test case with this data set
                result = execute_single_testcase_with_excel_data(testcase_name, execution_data)

                # If result is a Response object (from Flask), extract JSON
                if hasattr(result, 'get_json'):
                    result_data = result.get_json()
                else:
                    result_data = result

                execution_results.append({
                    'data_set_index': i + 1,
                    'data_set': data_set,
                    'result': result_data,
                    'success': result_data.get('success', False)
                })

            except Exception as dataset_error:
                print(f"[EXCEL_EXECUTE] Error executing data set {i+1}: {str(dataset_error)}")
                execution_results.append({
                    'data_set_index': i + 1,
                    'data_set': data_set,
                    'result': {'success': False, 'error': str(dataset_error)},
                    'success': False
                })

        # Calculate overall success
        successful_executions = sum(1 for r in execution_results if r['success'])
        total_executions = len(execution_results)

        print(f"[EXCEL_EXECUTE] Completed execution: {successful_executions}/{total_executions} successful")

        return jsonify({
            'success': successful_executions > 0,
            'message': f'Executed {total_executions} data sets, {successful_executions} successful',
            'total_data_sets': total_executions,
            'successful_executions': successful_executions,
            'execution_results': execution_results
        }), 200

    except Exception as e:
        print(f"[ERROR] Execute with Excel values failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def execute_single_testcase_with_excel_data(testcase_name, request_data=None):
    """Execute a single test case with Excel data mapping"""
    try:
        print(f"[EXCEL_SINGLE] Executing test case: {testcase_name} with Excel data")
        if request_data:
            print(f"[EXCEL_SINGLE] Request data: {request_data}")

        # Extract Excel data
        excel_data = request_data.get('excel_data', {}) if request_data else {}
        data_set_index = request_data.get('data_set_index', 1) if request_data else 1
        total_data_sets = request_data.get('total_data_sets', 1) if request_data else 1

        # Extract user information for tracking
        user_email = None
        if request_data and 'user_email' in request_data:
            user_email = request_data['user_email']
        elif hasattr(request, 'headers') and request.headers.get('X-User-Email'):
            user_email = request.headers.get('X-User-Email')

        print(f"[EXCEL_SINGLE] User email for tracking: {user_email}")
        print(f"[EXCEL_SINGLE] Excel data keys: {list(excel_data.keys()) if excel_data else 'None'}")

        # Load test steps from database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get project and module info for the testcase to generate correct table name
        cursor.execute("""
            SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                    COALESCE(m.module_name, 'Unknown') as module_name
            FROM TestCases tc
            LEFT JOIN Modules m ON tc.module_id = m.id
            LEFT JOIN Projects p1 ON tc.project_id = p1.id
            LEFT JOIN Projects p2 ON m.project_id = p2.id
            WHERE tc.name = ?
        """, (testcase_name,))

        metadata = cursor.fetchone()
        if metadata:
            project_name = metadata[0]
            module_name = metadata[1]
            table_name = generate_unique_table_name(project_name, module_name, testcase_name)
        else:
            # Fallback to old naming for backward compatibility
            table_name = sanitize_table_name(testcase_name)

        print(f"[EXCEL_SINGLE] Looking for test steps in table: {table_name}")

        # Check if table exists
        cursor.execute(f"SELECT COUNT(*) FROM sysobjects WHERE name='{table_name}' AND xtype='U'")
        if cursor.fetchone()[0] == 0:
            conn.close()
            print(f"[ERROR] Test case table '{table_name}' not found")
            return {
                'success': False,
                'error': f'Test case table "{table_name}" does not exist. Please create test steps first.',
                'testcase_name': testcase_name
            }

        cursor.execute(f"SELECT tc_id, step_no, test_step_description, element_name, action_type, xpath, [values] FROM [{table_name}] ORDER BY step_no")

        test_steps = []
        for row in cursor.fetchall():
            test_steps.append({
                'tc_id': row[0],
                'step_no': row[1],
                'test_step_description': row[2],
                'element_name': row[3],
                'action_type': row[4],
                'xpath': row[5],
                'values': row[6]
            })

        cursor.close()
        conn.close()

        if not test_steps:
           return {'success': False, 'error': 'No test steps found', 'testcase_name': testcase_name}

        print(f"[EXCEL_SINGLE] Found {len(test_steps)} test steps")

        # Apply Excel data mapping to test steps
        # Now excel_data contains: {'step_1': 'value_for_row1', 'step_2': 'value_for_row2', ...}
        # Each step_no in test_steps should match the step_X format
        mapped_test_steps = []
        for step in test_steps:
            mapped_step = step.copy()

            # Map values field - replace {{step_X}} with Excel data
            # The step_no in test_steps (1-based) maps to step_X in excel_data
            if step.get('values'):
                original_values = str(step['values'])
                mapped_values = original_values

                # For new format: {{step_X}} where X is the row/step number
                # Also support legacy format: {{column_name}} for backward compatibility
                for excel_key, excel_value in excel_data.items():
                    # Support both {{step_1}} and {{column_name}} formats
                    if excel_key.startswith('step_'):
                        # New format: {{step_1}}, {{step_2}}, etc.
                        placeholder = '{{' + str(excel_key) + '}}'
                    else:
                        # Legacy format: {{column_name}}
                        placeholder = '{{' + str(excel_key) + '}}'
                    
                    replacement = str(excel_value) if excel_value is not None else ''
                    mapped_values = mapped_values.replace(placeholder, replacement)

                mapped_step['values'] = mapped_values
                print(f"[EXCEL_MAPPING] Step {step['step_no']}: '{original_values}' -> '{mapped_values}'")

            # Also map element_name if it contains placeholders
            if step.get('element_name'):
                original_element = str(step['element_name'])
                mapped_element = original_element

                for excel_key, excel_value in excel_data.items():
                    if excel_key.startswith('step_'):
                        placeholder = '{{' + str(excel_key) + '}}'
                    else:
                        placeholder = '{{' + str(excel_key) + '}}'
                    
                    replacement = str(excel_value) if excel_value is not None else ''
                    mapped_element = mapped_element.replace(placeholder, replacement)

                mapped_step['element_name'] = mapped_element

            mapped_test_steps.append(mapped_step)

        print(f"[EXCEL_SINGLE] Applied Excel data mapping to {len(mapped_test_steps)} test steps")

        # Get test case info to generate IDs
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get test case details including testcase_id, suite_type, module_id, and project_id
        cursor.execute("""
            SELECT tc.testcase_id, tc.suite_type, tc.module_id, tc.project_id,
                    COALESCE(m.module_name, 'Unknown Module') as module_name,
                    m.project_id as module_project_id,
                    COALESCE(p1.name, p2.name, 'Unknown Project') as project_name,
                    COALESCE(tc.project_id, m.project_id) as resolved_project_id
            FROM TestCases tc
            LEFT JOIN Modules m ON tc.module_id = m.id
            LEFT JOIN Projects p1 ON tc.project_id = p1.id
            LEFT JOIN Projects p2 ON m.project_id = p2.id
            WHERE tc.name = ?
        """, (testcase_name,))

        testcase_info = cursor.fetchone()
        cursor.close()
        conn.close()

        if testcase_info:
            testcase_id = testcase_info[0] if testcase_info[0] else f"TC_{testcase_name}_001"
            suite_type = testcase_info[1] if testcase_info[1] else "regression"
            module_id = testcase_info[2]
            testcase_project_id = testcase_info[3]
            module_name = testcase_info[4]
            module_project_id = testcase_info[5]
            project_name = testcase_info[6]
            resolved_project_id = testcase_info[7]
            project_id = resolved_project_id
        else:
            testcase_id = f"TC_{testcase_name}_001"
            suite_type = "regression"
            module_id = None
            project_id = None
            module_name = "Unknown Module"
            project_name = "Unknown Project"

        # Generate TestRun_id and Result_id with Excel data set indicator
        testrun_id = generate_testrun_id(suite_type, testcase_name, conn)
        # Modify testrun_id to include data set index
        if total_data_sets > 1:
            testrun_id = f"{testrun_id}_DS{data_set_index}"

        result_id = generate_result_id(testcase_id, testrun_id)

        conn.close()

        # Determine which executor to use
        executor_type = request_data.get('executor_type', 'selenium').lower()

        # Prepare metadata to pass to executor
        test_metadata = {
            'testcase_id': testcase_id,
            'testrun_id': testrun_id,
            'result_id': result_id,
            'suite_type': suite_type,
            'module_name': module_name,
            'project_name': project_name,
            'module_id': module_id,
            'project_id': project_id,
            'username': '',  # Will be set from user info
            'role': '',      # Will be set from user info
            'excel_data_set': data_set_index,
            'total_excel_data_sets': total_data_sets
        }

        # Get user information for Allure results
        user_info = {'username': '', 'role': ''}
        if user_email:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT username, role FROM Authentication
                    WHERE email = ? AND status = 'Approved'
                """, (user_email,))
                user_data = cursor.fetchone()
                if user_data:
                    user_info['username'] = user_data[0] or ''
                    user_info['role'] = user_data[1] or ''
                conn.close()
            except Exception as e:
                print(f"[WARNING] Could not retrieve user info for Allure results: {str(e)}")

        test_metadata.update(user_info)

        # Execute with the appropriate executor
        if executor_type == 'playwright':
            print("[EXCEL_PLAYWRIGHT] Creating PlaywrightTestExecutor instance...")
            from playwright_executor import PlaywrightTestExecutor
            executor = PlaywrightTestExecutor()
            print("[EXCEL_PLAYWRIGHT] Starting test case execution...")
            result = executor.execute_test_case(testcase_name, mapped_test_steps, test_metadata)
            print(f"[EXCEL_ALLURE_DEBUG] PlaywrightTestExecutor result status: {result.get('status')}")

        elif executor_type == 'cypress':
            print("[EXCEL_CYPRESS] Creating CypressTestExecutor instance...")
            from cypress_executor import CypressTestExecutor
            executor = CypressTestExecutor()
            print("[EXCEL_CYPRESS] Starting test case execution...")
            result = executor.execute_test_case(testcase_name, mapped_test_steps, test_metadata)
            print(f"[EXCEL_ALLURE_DEBUG] CypressTestExecutor result status: {result.get('status')}")
            print("[EXCEL_CYPRESS] Test execution completed")

        else: # Default to selenium
            from selenium_executor import SeleniumTestExecutor
            print("[EXCEL_SELENIUM] Creating SeleniumTestExecutor instance...")
            executor = SeleniumTestExecutor()
            print("[EXCEL_SELENIUM] Starting test case execution...")
            result = executor.execute_test_case(testcase_name, mapped_test_steps, test_metadata)
            print(f"[EXCEL_ALLURE_DEBUG] SeleniumTestExecutor result status: {result.get('status')}")
            print(f"[EXCEL_ALLURE_DEBUG] SeleniumTestExecutor result suite_type: {result.get('suite_type')}")

        if not result:
            raise Exception(f"{executor_type.capitalize()}TestExecutor returned null/undefined result")

        # Add executor_type to result for proper storage
        result['executor_type'] = executor_type
        result['excel_data_set'] = data_set_index
        result['total_excel_data_sets'] = total_data_sets

        # Store results in selenium_results table
        store_selenium_results(testcase_name, result, user_email)

        # Auto-generate Allure report after test execution
        try:
            print("[EXCEL_ALLURE] Auto-generating Allure report after Excel test execution...")
            success = auto_generate_allure_report()
            if success:
                print("[EXCEL_ALLURE] Auto-generation completed successfully")
            else:
                print("[EXCEL_ALLURE] Auto-generation failed or skipped")
        except Exception as e:
            print(f"[WARNING] Failed to auto-generate Allure report: {str(e)}")

        # Transform result to match frontend expectations
        api_result = {
            'success': result.get('status') == 'PASS',
            'status': result.get('status'),
            'execution_id': result.get('execution_id'),
            'testcase_name': result.get('testcase_name'),
            'total_steps': result.get('total_steps'),
            'passed_steps': result.get('passed_steps'),
            'failed_steps': result.get('failed_steps'),
            'skipped_steps': result.get('skipped_steps'),
            'execution_time': result.get('execution_time'),
            'start_time': result.get('start_time'),
            'end_time': result.get('end_time'),
            'error_message': result.get('error_message'),
            'step_results': result.get('step_results'),
            'browser_info': result.get('browser_info'),
            'excel_data_set': data_set_index,
            'total_excel_data_sets': total_data_sets
        }

        # Add user information to the result
        if user_email:
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT username, role FROM Authentication
                    WHERE email = ? AND status = 'Approved'
                """, (user_email,))
                user_data = cursor.fetchone()
                if user_data:
                    api_result['username'] = user_data[0] or ''
                    api_result['role'] = user_data[1] or ''
                conn.close()
            except Exception as e:
                print(f"[WARNING] Could not retrieve user info for result: {str(e)}")
                api_result['username'] = ''
                api_result['role'] = ''

        print(f"[EXCEL_SUCCESS] Test execution completed for: {testcase_name} (Data set {data_set_index}/{total_data_sets})")
        return api_result

    except Exception as e:
        print(f"[ERROR] Excel single test execution failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': str(e), 'testcase_name': testcase_name}

@app.route('/api/testcases/<testcase_name>/mapped-excel', methods=['GET'])
def get_mapped_excel_sheet(testcase_name):
    """Get the mapped Excel sheet name for a test case"""
    try:
        # URL decode the testcase_name
        testcase_name = unquote(testcase_name).strip()
        print(f"[GET_EXCEL] Fetching mapped Excel for test case: '{testcase_name}'")
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_excel_mapping_infrastructure(conn)
        
        # First, try exact match
        cursor.execute("""
            SELECT id
            FROM [dbo].[TestCases]
            WHERE name = ?
        """, (testcase_name,))
        
        result = cursor.fetchone()
        
        # If not found, try case-insensitive match
        if not result:
            print(f"[GET_EXCEL] Exact match not found, trying case-insensitive search...")
            cursor.execute("""
                SELECT id
                FROM [dbo].[TestCases]
                WHERE LOWER(name) = LOWER(?)
            """, (testcase_name,))
            result = cursor.fetchone()
            
            if result:
                print(f"[GET_EXCEL] Found via case-insensitive match")
        
        # If still not found, list all test case names for debugging
        if not result:
            cursor.execute("SELECT TOP 20 id, name FROM [dbo].[TestCases]")
            all_cases = cursor.fetchall()
            print(f"[GET_EXCEL] No test case found for '{testcase_name}'")
            print(f"[GET_EXCEL] Available test cases: {[(tc[1]) for tc in all_cases]}")
        
        if result:
            testcase_id = result[0]
            cursor.execute("""
                SELECT em.excel_file_id, em.sheet_name, em.data_sets, v.original_name
                FROM [dbo].[ExcelMapping] em
                LEFT JOIN [dbo].[Values] v ON v.id = em.excel_file_id
                WHERE em.testcase_id = ?
            """, (testcase_id,))
            mapping_row = cursor.fetchone()
            if mapping_row:
                excel_file_id = mapping_row[0]
                mapped_sheet_name = mapping_row[1] or ''
                data_sets = mapping_row[2] if mapping_row[2] is not None else 0
                mapped_file = mapping_row[3] or ''
                print(f"[GET_EXCEL] [OK] Found mapping: file_id='{excel_file_id}', sheet='{mapped_sheet_name}'")
            else:
                print(f"[GET_EXCEL] [FAIL] No Excel mapping found for testcase_id: {testcase_id}")
                conn.close()
                return jsonify({'excelSheetName': '', 'found': False, 'dataSets': 0}), 200
            
            # Also attempt to detect configured value sets stored in the test steps (non-placeholder literal values)
            configured_values_list = []
            try:
                # Attempt to resolve project/module for table name
                cursor_meta = get_db_connection().cursor()
                cursor_meta.execute("""
                    SELECT COALESCE(p1.name, p2.name, 'Unknown') as project_name,
                           COALESCE(m.module_name, 'Unknown') as module_name
                    FROM [dbo].[TestCases] tc
                    LEFT JOIN [dbo].[Modules] m ON tc.module_id = m.id
                    LEFT JOIN [dbo].[Projects] p1 ON tc.project_id = p1.id
                    LEFT JOIN [dbo].[Projects] p2 ON m.project_id = p2.id
                    WHERE tc.name = ?
                """, (testcase_name,))
                meta = cursor_meta.fetchone()
                if meta:
                    proj_name = meta[0]
                    mod_name = meta[1]
                    table_name = generate_unique_table_name(proj_name, mod_name, testcase_name)
                    try:
                        cursor_meta.execute(f"SELECT [values] FROM [{table_name}] WHERE [values] IS NOT NULL AND LTRIM(RTRIM([values])) <> '' ORDER BY step_no")
                        step_rows = cursor_meta.fetchall()
                        # If there are literal values (without placeholders) assume at least one configured dataset
                        for r in step_rows:
                            val = r[0] or ''
                            if isinstance(val, str) and ('{{' not in val and '}}' not in val):
                                configured_values_list = ['configured']
                                break
                    except Exception as step_err:
                        print(f"[GET_EXCEL] Could not read test steps for configured values: {step_err}")
                cursor_meta.close()
            except Exception as cfg_err:
                print(f"[GET_EXCEL] Error detecting configured values: {cfg_err}")

            excel_sheet_to_return = mapped_sheet_name if (mapped_sheet_name and mapped_sheet_name.strip() != '') else mapped_file
            conn.close()
            return jsonify({
                'excelSheetName': excel_sheet_to_return,
                'found': True,
                'dataSets': data_sets,
                'configuredValues': configured_values_list
            }), 200
        else:
            print(f"[GET_EXCEL] [FAIL] No test case found with name: '{testcase_name}'")
            conn.close()
            return jsonify({'excelSheetName': '', 'found': False, 'dataSets': 0}), 200
            
    except Exception as e:
        print(f"[ERROR] Failed to get mapped Excel sheet: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'found': False}), 500

@app.route('/api/testcases/<testcase_name>/mapped-excel', methods=['POST'])
def update_mapped_excel_sheet(testcase_name):
    """Update the mapped Excel sheet name for a test case"""
    try:
        # URL decode the testcase_name
        testcase_name = unquote(testcase_name).strip()
        print(f"[UPDATE_EXCEL] Received POST request for testcase_name: '{testcase_name}'")
        
        data = request.get_json()
        excel_file_id = data.get('excelFileId')
        sheet_name = data.get('sheetName') or data.get('excelSheetName') or ''
        data_sets = data.get('dataSets')
        
        print(f"[UPDATE_EXCEL] Updating test case '{testcase_name}' with Excel file_id: '{excel_file_id}', sheet: '{sheet_name}'")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_excel_mapping_infrastructure(conn)
        if not table_exists(cursor, 'TestCases'):
            conn.close()
            return jsonify({'error': "Table [dbo].[TestCases] does not exist or is not accessible."}), 500
        
        # First check if test case exists (exact match)
        cursor.execute("""
            SELECT id, name FROM [dbo].[TestCases] WHERE name = ?
        """, (testcase_name,))
        
        existing_testcase = cursor.fetchone()
        
        # If not found, try case-insensitive match
        if not existing_testcase:
            print(f"[UPDATE_EXCEL] Exact match not found, trying case-insensitive search...")
            cursor.execute("""
                SELECT id, name FROM [dbo].[TestCases] WHERE LOWER(name) = LOWER(?)
            """, (testcase_name,))
            existing_testcase = cursor.fetchone()
            
            if existing_testcase:
                print(f"[UPDATE_EXCEL] Found via case-insensitive match: '{existing_testcase[1]}'")
        
        if not existing_testcase:
            print(f"[UPDATE_EXCEL] Test case '{testcase_name}' not found in any form - Creating new test case")
            # Create the test case if it doesn't exist
            cursor.execute("""
                INSERT INTO [dbo].[TestCases] (name, status)
                VALUES (?, ?)
            """, (testcase_name, 'Active'))
            conn.commit()
            print(f"[UPDATE_EXCEL] [OK] Created new test case '{testcase_name}'")
            cursor.execute("SELECT id FROM [dbo].[TestCases] WHERE name = ?", (testcase_name,))
            existing_testcase = cursor.fetchone()
        else:
            actual_testcase_id = existing_testcase[0]
            actual_testcase_name = existing_testcase[1]
            print(f"[UPDATE_EXCEL] [OK] Test case found with id: {actual_testcase_id}, actual name: '{actual_testcase_name}'")

        actual_testcase_id = existing_testcase[0]
        if not excel_file_id or not sheet_name:
            conn.close()
            return jsonify({'error': 'excelFileId and sheetName are required'}), 400

        # Upsert mapping (one per testcase)
        cursor.execute("""
            IF EXISTS (SELECT 1 FROM [dbo].[ExcelMapping] WHERE testcase_id = ?)
            BEGIN
                UPDATE [dbo].[ExcelMapping]
                SET excel_file_id = ?, sheet_name = ?, data_sets = ?, updated_at = GETDATE()
                WHERE testcase_id = ?
            END
            ELSE
            BEGIN
                INSERT INTO [dbo].[ExcelMapping] (testcase_id, excel_file_id, sheet_name, data_sets)
                VALUES (?, ?, ?, ?)
            END
        """, (actual_testcase_id, excel_file_id, sheet_name, data_sets, actual_testcase_id, actual_testcase_id, excel_file_id, sheet_name, data_sets))
        conn.commit()
        
        # Verify the update - use case-insensitive query
        cursor.execute("""
            SELECT em.testcase_id, em.excel_file_id, em.sheet_name
            FROM [dbo].[ExcelMapping] em
            WHERE em.testcase_id = ?
        """, (actual_testcase_id,))
        
        verify_result = cursor.fetchone()
        if verify_result:
            verified_id = verify_result[0]
            verified_file_id = verify_result[1]
            verified_sheet = verify_result[2]
            print(f"[UPDATE_EXCEL] [OK] Verification - Test case ID: {verified_id}, File ID: '{verified_file_id}', Sheet: '{verified_sheet}'")
        else:
            print(f"[UPDATE_EXCEL] [FAIL] Verification - Could not find test case after update")
        
        conn.close()
        
        return jsonify({'success': True, 'message': 'Excel mapping updated successfully', 'excelFileId': excel_file_id, 'sheetName': sheet_name}), 200
            
    except Exception as e:
        print(f"[ERROR] Failed to update mapped Excel sheet: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/testcases/<testcase_name>/mapped-excel', methods=['DELETE'])
def delete_mapped_excel_sheet(testcase_name):
    """Delete the mapped Excel sheet mapping for a test case"""
    try:
        # URL decode the testcase_name
        testcase_name = unquote(testcase_name).strip()
        print(f"[DELETE_EXCEL] Received DELETE request for testcase_name: '{testcase_name}'")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        ensure_excel_mapping_infrastructure(conn)
        if not table_exists(cursor, 'TestCases'):
            conn.close()
            return jsonify({'success': False, 'error': "Table [dbo].[TestCases] does not exist or is not accessible."}), 500
        
        # First check if test case exists (exact match)
        cursor.execute("""
            SELECT id, name FROM [dbo].[TestCases] WHERE name = ?
        """, (testcase_name,))
        
        existing_testcase = cursor.fetchone()
        
        # If not found, try case-insensitive match
        if not existing_testcase:
            print(f"[DELETE_EXCEL] Exact match not found, trying case-insensitive search...")
            cursor.execute("""
                SELECT id, name FROM [dbo].[TestCases] WHERE LOWER(name) = LOWER(?)
            """, (testcase_name,))
            existing_testcase = cursor.fetchone()
            
            if existing_testcase:
                print(f"[DELETE_EXCEL] Found via case-insensitive match: '{existing_testcase[1]}'")
        
        if not existing_testcase:
            print(f"[DELETE_EXCEL] Test case '{testcase_name}' not found")
            conn.close()
            return jsonify({'success': False, 'error': 'Test case not found'}), 404
        
        actual_testcase_id = existing_testcase[0]
        actual_testcase_name = existing_testcase[1]
        
        print(f"[DELETE_EXCEL] [OK] Test case found with id: {actual_testcase_id}, actual name: '{actual_testcase_name}'")
        
        # Delete mapping
        cursor.execute("""
            DELETE FROM [dbo].[ExcelMapping] WHERE testcase_id = ?
        """, (actual_testcase_id,))
        
        rows_affected = cursor.rowcount
        print(f"[DELETE_EXCEL] Rows affected: {rows_affected}")
        conn.commit()
        
        # Verify the deletion
        cursor.execute("""
            SELECT testcase_id FROM [dbo].[ExcelMapping] WHERE testcase_id = ?
        """, (actual_testcase_id,))
        
        verify_result = cursor.fetchone()
        if verify_result:
            print(f"[DELETE_EXCEL] [FAIL] Verification - Excel mapping still exists for testcase_id: '{actual_testcase_id}'")
        else:
            print(f"[DELETE_EXCEL] [OK] Verification - Excel mapping removed for testcase_id: '{actual_testcase_id}'")
        
        conn.close()
        
        return jsonify({'success': True, 'message': 'Excel mapping deleted successfully'}), 200
            
    except Exception as e:
        print(f"[ERROR] Failed to delete mapped Excel sheet: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create selenium_results table on startup
    create_selenium_results_table()

    def create_authentication_table():
        """Create Authentication table if it doesn't exist"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Authentication' AND xtype='U')
                CREATE TABLE Authentication (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    username NVARCHAR(255) NOT NULL UNIQUE,
                    email NVARCHAR(255) NOT NULL UNIQUE,
                    password_hash NVARCHAR(255) NOT NULL,
                    status NVARCHAR(50) DEFAULT 'Pending',
                    role NVARCHAR(50) DEFAULT NULL,
                    is_active BIT DEFAULT 1,
                    created_at DATETIME DEFAULT GETDATE(),
                    last_login DATETIME NULL
                )
                """
            )
            conn.commit()
            conn.close()
            print("[SUCCESS] Authentication table created/verified")
        except Exception as e:
            print(f"[ERROR] Error creating Authentication table: {str(e)}")

    def create_functions_table():
        """Create Functions table and populate with default functions if it doesn't exist"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # Create Functions table
            cursor.execute(
                """
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Functions' AND xtype='U')
                CREATE TABLE Functions (
                    id NVARCHAR(50) PRIMARY KEY,
                    name NVARCHAR(255) NOT NULL,
                    description NVARCHAR(500),
                    icon NVARCHAR(50) DEFAULT 'Settings',
                    color NVARCHAR(50) DEFAULT 'bg-gray-500',
                    created_at DATETIME DEFAULT GETDATE()
                )
                """
            )

            # Insert default functions if they don't exist
            default_functions = [
                ('requirements', 'Requirements & Feasibility Analysis', 'Analyze requirements and assess feasibility', 'FileText', 'bg-blue-500'),
                ('planning', 'Automation Planning', 'Plan automation strategy and timeline', 'Calendar', 'bg-green-500'),
                ('development', 'Automation Development', 'Develop automated test scripts', 'Code', 'bg-purple-500'),
                ('test-lab', 'Test Lab', 'Execute and monitor test runs', 'TestTube', 'bg-orange-500'),
                ('reporting', 'Reporting', 'Generate test reports and analytics', 'BarChart3', 'bg-red-500'),
                ('maintenance', 'Maintenance', 'Maintain and update test assets', 'Settings', 'bg-gray-500')
            ]

            for func_id, name, description, icon, color in default_functions:
                cursor.execute("""
                    IF NOT EXISTS (SELECT 1 FROM Functions WHERE id = ?)
                    INSERT INTO Functions (id, name, description, icon, color) VALUES (?, ?, ?, ?, ?)
                """, (func_id, func_id, name, description, icon, color))

            conn.commit()
            conn.close()
            print("[SUCCESS] Functions table created/verified and populated with default functions")
        except Exception as e:
            print(f"[ERROR] Error creating Functions table: {str(e)}")
    
    print("[START] Starting Flask API Server with Selenium & Playwright Integration")
    print("[DATABASE] Database: Ixigo_TestAutomation on LPT2084-B1")
    print("[SERVER] Server: http://localhost:5000")
    print("[INFO] API Endpoints:")
    print("   - Health Check: /api/health")
    print("   - Projects: /api/projects")
    print("   - Test Cases: /api/testcases")
    print("   - Update Test Case: /api/testcases/<id> (PUT)")
    print("   - Delete Test Case: /api/testcases/<id> (DELETE)")
    print("   - Test Steps: /api/teststeps")
    print("   - Test Execution: /api/execute/<testcase_name>")
    print("   - Playwright Execution: /api/playwright/execute/<testcase_name>")
    print("   - Selenium Execution: /api/selenium/execute/<testcase_name>")
    print("   - Available Executors: /api/executors/available")
    print("   - Test Executor Connection: /api/executors/test-connection")
    print("   - Test Results: /api/results")
    print("   - Reports: /api/allure/generate")
    print("   - Allure Force Regenerate: /api/allure/force-regenerate")
    print("   - Allure Status: /api/allure/status")
    print("   - Allure Open: /api/allure/open")
    print("   - Allure Report Access: /allure-report/index.html")
    print("   - Allure Screenshots: /allure-results/<filename>")
    print("   - Pages Master: /api/page-names (GET, POST)")
    print("   - Pages: /api/pages (POST), /api/pages/bulk (POST), /api/pages/<page_name> (GET)")
    print("   - Fix Project/Module Names: /api/fix-project-module-names (POST)")
    print("   - Populate Missing Metadata: /api/populate-missing-testcase-metadata (POST)")
    print("   - Cleanup Orphaned Data: /api/cleanup-orphaned-data (POST)")
    print("   - Remote Viewing Start: /api/remote-viewing/start (POST)")
    print("   - Remote Viewing Start Server Execution: /api/remote-viewing/start-server-execution (POST)")
    print("   - Server Execution Start: /api/server-execution/start (POST)")
    print("   - Remote Viewing Status: /api/remote-viewing/status/<session_id> (GET)")
    print("   - Remote Viewing Stop: /api/remote-viewing/stop/<session_id> (POST)")
    print("   - Remote Viewing Stream: /api/remote-viewing/stream/<session_id> (GET)")
    print("   - Monitor Dashboard: /api/monitor/dashboard (GET)")
    print("   - Recorded Videos: /api/monitor/recorded-videos (GET)")
    print("   - Socket.IO: Real-time communication enabled")
    print("   - noVNC Streaming: Integrated for server execution monitoring")

    # Ensure tables exist at startup
    def create_function_assignments_table():
        """Create FunctionAssignments table if it doesn't exist"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='FunctionAssignments' AND xtype='U')
                CREATE TABLE FunctionAssignments (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    function_name NVARCHAR(100) NOT NULL,
                    user_email NVARCHAR(255) NOT NULL,
                    assigned_by NVARCHAR(255),
                    assigned_on DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (user_email) REFERENCES Authentication(email),
                    UNIQUE(function_name, user_email)
                )
                """
            )
            conn.commit()
            conn.close()
            print("[SUCCESS] FunctionAssignments table created/verified")
        except Exception as e:
            print(f"[ERROR] Error creating FunctionAssignments table: {str(e)}")
    
    def create_pages_master_table():
        """Create pages_master table if it doesn't exist"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='pages_master' AND xtype='U')
                CREATE TABLE pages_master (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    page_name NVARCHAR(255) NOT NULL UNIQUE,
                    created_date DATETIME DEFAULT GETDATE()
                )
                """
            )
            conn.commit()
            conn.close()
            print("[SUCCESS] pages_master table created/verified")
        except Exception as e:
            print(f"[ERROR] Error creating pages_master table: {str(e)}")

    def create_brd_table():
        """Create BRD table if it doesn't exist"""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='BRD' AND xtype='U')
                CREATE TABLE BRD (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    file_name NVARCHAR(255) NOT NULL,
                    file_type NVARCHAR(50) NOT NULL,
                    original_name NVARCHAR(255) NOT NULL,
                    file_path NVARCHAR(500) NOT NULL,
                    file_size BIGINT NOT NULL,
                    uploaded_by NVARCHAR(255) NOT NULL,
                    uploaded_at DATETIME DEFAULT GETDATE(),
                    description NVARCHAR(1000) NULL,
                    status NVARCHAR(50) DEFAULT 'Active',
                    FOREIGN KEY (uploaded_by) REFERENCES Authentication(email) ON DELETE CASCADE
                )
                """
            )
            
            # Create indexes if they don't exist
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_BRD_FileType')
                CREATE INDEX IX_BRD_FileType ON BRD(file_type)
            """)
            
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name = 'IX_BRD_UploadedBy')
                CREATE INDEX IX_BRD_UploadedBy ON BRD(uploaded_by)
            """)
            
            conn.commit()
            conn.close()
            print("[SUCCESS] BRD table created/verified")
        except Exception as e:
            print(f"[ERROR] Error creating BRD table: {str(e)}")

    create_authentication_table()
    create_functions_table()
    create_function_assignments_table()
    create_pages_master_table()
    create_pages_table()
    create_extension_xpaths_table()
    create_testcases_table_if_missing()
    create_values_table_if_missing()
    create_excel_mapping_table_if_missing()
    create_brd_table()
    
    # Setup system monitoring routes
    print("[SYSTEM] Setting up system monitoring routes...")
    setup_system_monitor_routes(app)
    print("[SYSTEM] System monitoring routes registered successfully")

    # Check if we're on Linux (for server deployment) or Windows (for development)
    import platform
    is_linux = platform.system() == 'Linux'
    
    # DISABLED: Global VNC/noVNC startup - comment out to prevent auto-starting
    # The user wants to disable VNC session per execution, so we disable the startup VNC server
    #
    # if is_linux:
    #     print("[STARTUP] Linux server detected, starting global noVNC server...")
    #     if start_global_novnc_server():
    #         print("[STARTUP] Global noVNC server started successfully")
    #         print("[STARTUP] Server monitor URL: http://10.30.3.85:6080/vnc.html")
    #     else:
    #         print("[STARTUP] Failed to start global noVNC server")
    # else:
    #     print("[STARTUP] Windows development environment detected")
    #     print("[STARTUP] VNC server expected on Linux server: http://10.30.3.85:6080/vnc.html")
    
    print("[STARTUP] Global VNC/noVNC server startup DISABLED")
    print("[STARTUP] VNC functionality available only when explicitly started by user")

    # Run Flask app directly without SocketIO process management
    if __name__ == "__main__":
        ssl_context = None
        
        cert_file = os.path.join(os.path.dirname(__file__), 'certs', 'cert.pem')
        key_file = os.path.join(os.path.dirname(__file__), 'certs', 'key.pem')
        
        if os.path.exists(cert_file) and os.path.exists(key_file):
            print("[SSL] Using SSL certificates for HTTPS")
            ssl_context = (cert_file, key_file)
        else:
            print("[SSL] WARNING: SSL certificates not found at", cert_file)
            print("[SSL] VNC connections may fail due to missing TLS")
            print("[SSL] Run: python generate_ssl_cert.py to generate self-signed certificates")
        
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
            threaded=True,
            ssl_context=ssl_context
        )
  #Working
