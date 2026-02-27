# vnc_manager.py
import subprocess
import time
import socket
import os
import signal
import uuid
import threading
from datetime import datetime
import requests
import websocket
import json
import shutil
import logging

BASE_VNC_PORT = 6000
BASE_NOVNC_PORT = 6100
BASE_DISPLAY = 20
MAX_PARALLEL_EXECUTIONS_PER_USER = 3


class VNCSessionManager:
    """
    Deterministic per-user VNC/noVNC session manager with global fallback.
    - Same user → same base ports
    - Parallel executions → incremental ports
    - Automatic fallback to global VNC server when individual sessions fail
    """

    def __init__(self, server_host="15.134.56.119", novnc_install_path="/home/ubuntu/Auto_Delta/noVNC"):
        self.server_host = server_host
        self.novnc_install_path = novnc_install_path

        self.global_vnc_port = 5900
        self.global_novnc_port = 6005
        self.global_vnc_url = f"http://{self.server_host}:5000/api/vnc/viewer/6005"
        self.global_vnc_started = False

        self.active_sessions = {}
        self.user_execution_count = {}
        self.execution_states = {}

        self.session_lock = threading.Lock()
        self.cleanup_interval = 30
        self.max_concurrent_sessions = 50  # Rate limiting: max sessions per server
        self.session_creation_count = {}  # Track session creation for rate limiting
        self._start_cleanup_thread()

        # Auto-setup dependencies and noVNC if not available
        self._check_system_requirements()
        self._ensure_dependencies_available()
        self._ensure_novnc_available()

        # Check if global VNC server is already running
        self._check_existing_global_vnc()

        # Try to start global VNC server on initialization only if not already running
        if not self.global_vnc_started:
            self._start_global_vnc_server()

        print("[VNC_MGR] Initialized (stable mode with global fallback)")
        print(
            f"[VNC_MGR] BASE_VNC_PORT={BASE_VNC_PORT}, "
            f"BASE_NOVNC_PORT={BASE_NOVNC_PORT}, BASE_DISPLAY={BASE_DISPLAY}"
        )
        print(f"[VNC_MGR] Global VNC URL: {self.global_vnc_url}")
        print(f"[VNC_MGR] Global VNC started: {self.global_vnc_started}")

    # -------------------------------------------------------
    # deterministic allocation
    # -------------------------------------------------------

    def _user_base_offset(self, email: str) -> int:
        return abs(hash(email)) % 50

    def _get_novnc_port_for_vnc_port(self, vnc_port: int) -> int:
        """Explicit mapping between VNC port and noVNC port.
        noVNC ports are offset by 100 from VNC ports.
        VNC Port 6000 → noVNC Port 6100
        VNC Port 6123 → noVNC Port 6223
        """
        return vnc_port + 100

    def _assign_ports(self, email: str, exec_index: int):
        """Assign unique ports for each parallel execution of the user.
        Parallel executions use incremental ports: user_base, user_base+3, user_base+6
        Each execution gets 3 ports: primary, auxiliary1, auxiliary2
        Returns: (primary_port, auxiliary_port1, auxiliary_port2, display)
        """
        base = self._user_base_offset(email)
        # Each parallel execution gets unique ports
        # Execution 0: base*3, base*3+1, base*3+2, display base
        # Execution 1: base*3+150, base*3+151, base*3+152, display base+50
        # Execution 2: base*3+300, base*3+151, base*3+302, display base+100
        execution_offset = exec_index * 150  # 150 port gaps per parallel execution
        display_offset = exec_index * 50     # 50 display gaps per parallel execution
        
        primary_port = BASE_VNC_PORT + base * 3 + execution_offset
        auxiliary_port1 = primary_port + 1
        auxiliary_port2 = primary_port + 2
        display = BASE_DISPLAY + base + display_offset

        return (primary_port, auxiliary_port1, auxiliary_port2, display)

    # -------------------------------------------------------
    # helpers
    # -------------------------------------------------------

    def _is_port_free(self, port):
        try:
            s = socket.socket()
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", port))
            s.close()
            return True
        except OSError:
            return False

    def _wait_for_ports_free(self, ports, max_retries=5, initial_wait=1):
        """Wait for multiple ports to become free"""
        for attempt in range(max_retries):
            if all(self._is_port_free(port) for port in ports):
                print(f"[VNC_MGR] All ports free on attempt {attempt + 1}: {ports}")
                return True

            if attempt < max_retries - 1:
                wait_time = initial_wait * (2 ** attempt)
                print(f"[VNC_MGR] Ports busy, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            elif attempt == max_retries - 1:
                print(f"[VNC_MGR] Last retry: attempting to cleanup stale processes")
                for port in ports:
                    self._cleanup_port_processes(port, port)  # Cleanup each port
                time.sleep(2)
                if all(self._is_port_free(port) for port in ports):
                    print(f"[VNC_MGR] All ports free after cleanup: {ports}")
                    return True

        return False

    def _cleanup_port_processes(self, vnc_port, novnc_port):
        for port in [vnc_port, novnc_port]:
            try:
                result = subprocess.run(
                    ["lsof", "-i", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                lines = result.stdout.strip().split('\n')[1:]
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            pid = int(parts[1])
                            print(f"[VNC_MGR] Killing process {pid} on port {port}")
                            os.kill(pid, signal.SIGKILL)
                        except (ValueError, ProcessLookupError):
                            pass
            except subprocess.TimeoutExpired:
                print(f"[VNC_MGR] Timeout checking port {port}")
            except FileNotFoundError:
                print(f"[VNC_MGR] lsof not available, skipping process cleanup")

    def _is_display_alive(self, display):
        return subprocess.run(
            ["xdpyinfo"],
            env={"DISPLAY": f":{display}"},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode == 0

    def _wait_for_vnc_port_ready(self, port, max_retries=8, initial_wait=0.5):
        for attempt in range(max_retries):
            if not self._is_port_free(port):
                print(f"[VNC_MGR] VNC port {port} ready on attempt {attempt + 1}")
                return True
            if attempt < max_retries - 1:
                wait_time = initial_wait * (2 ** attempt)
                time.sleep(wait_time)
        return False

    def _wait_for_novnc_http(self, port, retries=15, delay=0.5):
        for attempt in range(retries):
            try:
                s = socket.create_connection(("localhost", port), timeout=2)
                s.sendall(b"GET /vnc.html HTTP/1.1\r\nHost: localhost\r\n\r\n")
                data = s.recv(1024)
                s.close()
                if b"200" in data or b"<html" in data or b"<!doctype" in data or b"<!DOCTYPE" in data:
                    print(f"[VNC_MGR] noVNC HTTP check passed on port {port} (attempt {attempt + 1})")
                    return True
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(delay)
        print(f"[VNC_MGR] noVNC HTTP check failed on port {port} after {retries} retries")
        return False

    def _test_websocket_connection(self, host, port, max_retries=5, delay=1):
        """Test WebSocket connection to noVNC"""
        ws_url = f"ws://{host}:{port}/websockify"
        
        for attempt in range(max_retries):
            try:
                print(f"[VNC_CONN] Testing WebSocket connection: {ws_url} (attempt {attempt + 1})")
                
                # Create WebSocket connection with timeout
                ws = websocket.create_connection(
                    ws_url, 
                    timeout=5,
                    subprotocols=["binary"]
                )
                
                # Send a simple RFB handshake to test VNC connection
                # RFB version handshake - should get version response
                time.sleep(0.5)
                
                # Try to receive initial VNC handshake
                try:
                    response = ws.recv()
                    if response:
                        logging.info(f"[VNC_AUTO] WebSocket connected to: {ws_url}")
                        ws.close()
                        return True
                except Exception as recv_error:
                    print(f"[VNC_CONN] WebSocket connected but VNC handshake failed: {recv_error}")
                
                ws.close()
                return True  # WebSocket connected, VNC handshake issues are OK for now
                
            except Exception as e:
                print(f"[VNC_CONN] WebSocket connection failed (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(delay)
        
        print(f"[VNC_CONN] WebSocket connection failed after {max_retries} attempts")
        return False

    def _verify_vnc_session(self, novnc_url, vnc_port, max_retries=3):
        """Verify that VNC session is fully functional"""
        try:
            host = self.server_host
            
            # Extract novnc_port from URL
            # Handles two URL formats:
            # 1. Direct noVNC: http://15.134.56.119:6130/vnc.html (extract port from URL)
            # 2. Global VNC API: http://15.134.56.119:5000/api/vnc/viewer/6145 (extract from path)
            import re
            
            # Try to extract from /viewer/(\d+) pattern first (global VNC API)
            match = re.search(r'/viewer/(\d+)', novnc_url)
            if match:
                novnc_port = int(match.group(1))
            else:
                # Try to extract port from URL host:port pattern
                match = re.search(r':(\d+)/', novnc_url)
                if match:
                    novnc_port = int(match.group(1))
                else:
                    print(f"[VNC_VERIFY] Could not extract port from URL: {novnc_url}")
                    return False
            
            print(f"[VNC_VERIFY] Verifying VNC session: {host}:{novnc_port}")
            
            # Test HTTP access to websockify
            try:
                response = requests.get(
                    f"http://{host}:{novnc_port}/vnc.html",
                    timeout=5
                )
                if response.status_code != 200:
                    print(f"[VNC_VERIFY] noVNC HTTP failed: {response.status_code}")
                    return False
                    
                print("[VNC_VERIFY] noVNC HTTP interface accessible")
            except Exception as e:
                print(f"[VNC_VERIFY] noVNC HTTP test failed: {e}")
                return False
            
            # Test WebSocket connection
            if not self._test_websocket_connection(host, novnc_port):
                return False
            
            # Test direct VNC connection
            try:
                vnc_sock = socket.create_connection((host, vnc_port), timeout=3)
                vnc_sock.close()
                print("[VNC_VERIFY] Direct VNC connection test passed")
            except Exception as e:
                print(f"[VNC_VERIFY] Direct VNC connection failed: {e}")
                return False
            
            print("[VNC_VERIFY] VNC session verification successful")
            return True
            
        except Exception as e:
            print(f"[VNC_VERIFY] Session verification failed: {e}")
            return False

    def _create_connection_helper_page(self, novnc_port, vnc_port):
        """Create a custom HTML page with enhanced connection logic"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>VNC Session - Enhanced Connection</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 10px;
            background: #f0f0f0;
            overflow: hidden;
        }}
        .status {{
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
            font-size: 12px;
        }}
        .success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }}
        .warning {{ background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }}
        .error {{ background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }}
        .info {{ background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }}
        
        iframe {{
            width: 100%;
            height: calc(100vh - 100px);
            border: 2px solid #007bff;
            border-radius: 5px;
            background: #000;
        }}
        .controls {{
            margin: 5px 0;
            text-align: center;
        }}
        button {{
            padding: 8px 16px;
            margin: 3px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }}
        .btn-primary {{ background: #007bff; color: white; }}
        .btn-success {{ background: #28a745; color: white; }}
        .btn-warning {{ background: #ffc107; color: black; }}
        .btn-danger {{ background: #dc3545; color: white; }}
    </style>
</head>
<body>
    <div id="status" class="status info">Initializing automated connection...</div>
    
    <div class="controls">
        <button class="btn-primary" onclick="forceConnect()">Force Connect</button>
        <button class="btn-warning" onclick="testConnection()">Test WebSocket</button>
        <button class="btn-success" onclick="fullscreen()">Fullscreen</button>
        <button class="btn-danger" onclick="refreshFrame()">Refresh</button>
    </div>

    <iframe id="vncFrame" src="about:blank"></iframe>
    
    <script>
        const vncPort = {novnc_port};
        const rfbPort = {vnc_port};
        const serverHost = '{self.server_host}';
        
        let connectionAttempts = 0;
        const maxAttempts = 10;
        let autoConnectTimer;
        let forceConnectTimer;
        
        function updateStatus(message, type = 'warning') {{
            const statusDiv = document.getElementById('status');
            statusDiv.textContent = `[VNC] ${{message}}`;
            statusDiv.className = 'status ' + type;
            console.log(`[VNC_CLIENT] ${{message}}`);
        }}
        
        function testConnection() {{
            updateStatus('Testing WebSocket connection...', 'warning');
            
            const wsProtocol = (window.location.protocol === 'https:') ? 'wss' : 'ws';
            const wsUrl = `${{wsProtocol}}://${{serverHost}}:${{vncPort}}/websockify`;
            const ws = new WebSocket(wsUrl, ['binary']);
            
            const timeout = setTimeout(() => {{
                ws.close();
                updateStatus('WebSocket connection timeout', 'error');
            }}, 5000);
            
            ws.onopen = function() {{
                clearTimeout(timeout);
                updateStatus('WebSocket connection successful!', 'success');
                ws.close();
                
                // Auto-trigger connection after successful test
                setTimeout(forceConnect, 500);
            }};
            
            ws.onerror = function(error) {{
                clearTimeout(timeout);
                updateStatus(`WebSocket connection failed: ${{error}}`, 'error');
                setTimeout(() => {{
                    if (connectionAttempts < maxAttempts) {{
                        testConnection();
                    }}
                }}, 3000);
            }};
            
            ws.onclose = function() {{
                clearTimeout(timeout);
            }};
        }}
        
        function forceConnect() {{
            connectionAttempts++;
            updateStatus(`Force connecting to VNC (attempt ${{connectionAttempts}})...`, 'warning');
            
            // Clear any existing timers
            clearTimeout(autoConnectTimer);
            clearTimeout(forceConnectTimer);
            
            // Build enhanced URL with forced autoconnect
            const params = [
                'autoconnect=true',
                'resize=remote', 
                'path=websockify',
                'reconnect=true',
                'reconnect_delay=500',
                'logging=error',
                'quality=6',
                'compression=2',
                'view_only=false',
                'shared=true',
                'show_dot=false'
            ];
            
            const httpProtocol = (window.location.protocol === 'https:') ? 'https' : 'http';
            const vncUrl = `${{httpProtocol}}://${{serverHost}}:${{vncPort}}/vnc.html?${{params.join('&')}}`;
            console.log(`[VNC_CLIENT] Loading URL: ${{vncUrl}}`);
            
            const frame = document.getElementById('vncFrame');
            frame.src = vncUrl;
            
            // Monitor connection status
            setTimeout(() => {{
                updateStatus('VNC client loaded, establishing connection...', 'info');
                
                // Force trigger connection via postMessage to iframe
                setTimeout(() => {{
                    try {{
                        frame.contentWindow.postMessage({{
                            action: 'connect',
                            host: serverHost,
                            port: vncPort,
                            path: '/websockify'
                        }}, '*');
                    }} catch (e) {{
                        console.log('[VNC_CLIENT] PostMessage failed (normal for cross-origin)');
                    }}
                }}, 1000);
                
                setTimeout(() => {{
                    updateStatus('VNC session ready. If screen is black, click "Force Connect"', 'success');
                }}, 3000);
                
            }}, 2000);
            
            // Auto-retry mechanism
            if (connectionAttempts < maxAttempts) {{
                forceConnectTimer = setTimeout(() => {{
                    updateStatus('Auto-retry in progress...', 'warning');
                    forceConnect();
                }}, 15000);
            }}
        }}
        
        function refreshFrame() {{
            updateStatus('Refreshing VNC frame...', 'warning');
            const frame = document.getElementById('vncFrame');
            frame.src = frame.src;
        }}
        
        function fullscreen() {{
            const frame = document.getElementById('vncFrame');
            if (frame.requestFullscreen) {{
                frame.requestFullscreen();
            }} else if (frame.webkitRequestFullscreen) {{
                frame.webkitRequestFullscreen();
            }} else if (frame.msRequestFullscreen) {{
                frame.msRequestFullscreen();
            }}
        }}
        
        // Enhanced auto-connection sequence
        window.onload = function() {{
            updateStatus('Starting automated connection sequence...', 'info');
            
            // Step 1: Test WebSocket connection first
            autoConnectTimer = setTimeout(() => {{
                testConnection();
            }}, 500);
            
            // Step 2: Force connect as backup
            setTimeout(() => {{
                if (connectionAttempts === 0) {{
                    forceConnect();
                }}
            }}, 3000);
        }};
        
        // Listen for iframe load events
        document.getElementById('vncFrame').onload = function() {{
            updateStatus('noVNC client loaded, attempting connection...', 'info');
        }};
        
        // Handle window messages from noVNC
        window.addEventListener('message', function(event) {{
            if (event.data && event.data.type === 'vnc') {{
                updateStatus(`VNC Status: ${{event.data.message}}`, event.data.connected ? 'success' : 'warning');
            }}
        }});
        
        // Keep connection alive
        setInterval(() => {{
            if (connectionAttempts > 0 && connectionAttempts < 5) {{
                // Periodic connection health check
                testConnection();
            }}
        }}, 30000);
    </script>
</body>
</html>
"""
        return html_content

    def _create_autoconnect_page(self, novnc_port, vnc_port, session_id=None):
        """Create a minimal auto-connect page that forces VNC connection immediately"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>VNC Auto-Connect</title>
    <meta charset="utf-8">
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: Arial, sans-serif;
            color: white;
            text-align: center;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        .container {{
            background: rgba(0,0,0,0.7);
            padding: 40px;
            border-radius: 15px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            max-width: 500px;
        }}
        .spinner {{
            border: 4px solid rgba(255,255,255,0.3);
            border-top: 4px solid #fff;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 2s linear infinite;
            margin: 20px auto;
        }}
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
        .status {{
            font-size: 18px;
            margin: 20px 0;
        }}
        .details {{
            font-size: 14px;
            opacity: 0.8;
            margin: 15px 0;
        }}
        .btn {{
            display: inline-block;
            padding: 12px 24px;
            margin: 10px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 8px;
            font-size: 16px;
            transition: background 0.3s;
            border: none;
            cursor: pointer;
        }}
        .btn:hover {{
            background: #0056b3;
        }}
        .btn-danger {{
            background: #dc3545;
        }}
        .btn-danger:hover {{
            background: #c82333;
        }}
        .countdown {{
            font-size: 24px;
            font-weight: bold;
            color: #ffd700;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🖥️ VNC Auto-Connect</h1>
        <div class="spinner"></div>
        <div class="status">Connecting to VNC Server...</div>
        <div class="details">Server: {self.server_host}:{novnc_port}</div>
        <div class="countdown" id="countdown">Redirecting in <span id="timer">2</span> seconds...</div>
        
        <div style="margin-top: 30px;">
            <button class="btn" onclick="connectNow()">Connect Now</button>
            <button class="btn btn-danger" onclick="openDirect()">Direct Connection</button>
        </div>
        
        <div class="details" style="margin-top: 20px;">
            If auto-connection fails, try the manual connection options above.
        </div>
    </div>
    
    <script>
        const serverHost = '{self.server_host}';
        const vncPort = {novnc_port};
        const httpProtocol = (window.location.protocol === 'https:') ? 'https' : 'http';
        
        // Build the VNC URL - use custom VNC page if session_id available, otherwise default
        const useCustom = '{session_id}' && '{session_id}' !== 'None';
        const vncUrl = useCustom ?
            `${{httpProtocol}}://{self.server_host}:5000/api/vnc/custom/{session_id}` :
            `${{httpProtocol}}://${{serverHost}}:${{vncPort}}/vnc.html?` + [
                'autoconnect=true',
                'resize=remote',
                'path=websockify',
                'reconnect=true',
                'reconnect_delay=500',
                'logging=warn',
                'quality=6',
                'compression=2',
                'view_only=false',
                'shared=true'
            ].join('&');
        
        console.log('[VNC_AUTO] Target URL:', vncUrl);
        
        // Countdown timer
        let countdown = 2;
        const timerElement = document.getElementById('timer');
        
        const countdownInterval = setInterval(() => {{
            countdown--;
            timerElement.textContent = countdown;
            
            if (countdown <= 0) {{
                clearInterval(countdownInterval);
                connectNow();
            }}
        }}, 1000);
        
        function connectNow() {{
            console.log('[VNC_AUTO] Connecting now to:', vncUrl);
            clearInterval(countdownInterval);
            
            // First try to test WebSocket connectivity
            testWebSocket().then(wsWorking => {{
                if (wsWorking) {{
                    console.log('[VNC_AUTO] WebSocket test passed, redirecting...');
                    window.location.href = vncUrl;
                }} else {{
                    console.log('[VNC_AUTO] WebSocket test failed, trying direct connection...');
                    // Try direct connection anyway
                    window.location.href = vncUrl;
                }}
            }}).catch(e => {{
                console.log('[VNC_AUTO] WebSocket test error, trying direct connection...', e);
                window.location.href = vncUrl;
            }});
        }}
        
        function openDirect() {{
            console.log('[VNC_AUTO] Opening direct connection');
            window.open(vncUrl, '_blank');
        }}
        
        function testWebSocket() {{
            return new Promise((resolve) => {{
                try {{
                    console.log('[VNC_AUTO] Testing WebSocket connection...');
                    const wsProtocol = (window.location.protocol === 'https:') ? 'wss' : 'ws';
                    const ws = new WebSocket(`${{wsProtocol}}://${{serverHost}}:${{vncPort}}/websockify`, ['binary']);
                    
                    const timeout = setTimeout(() => {{
                        try {{ ws.close(); }} catch(e) {{}}
                        resolve(false);
                    }}, 2000);
                    
                    ws.onopen = function() {{
                        console.log('[VNC_AUTO] WebSocket connection successful');
                        clearTimeout(timeout);
                        try {{ ws.close(); }} catch(e) {{}}
                        resolve(true);
                    }};
                    
                    ws.onerror = function(error) {{
                        console.log('[VNC_AUTO] WebSocket connection failed:', error);
                        clearTimeout(timeout);
                        resolve(false);
                    }};
                    
                    ws.onclose = function() {{
                        console.log('[VNC_AUTO] WebSocket connection closed');
                    }};
                    
                }} catch(e) {{
                    console.log('[VNC_AUTO] WebSocket test exception:', e);
                    resolve(false);
                }}
            }});
        }}
        
        // Test connection on page load
        window.addEventListener('load', function() {{
            console.log('[VNC_AUTO] Page loaded, testing connection...');
            testWebSocket().then(working => {{
                if (working) {{
                    document.querySelector('.status').textContent = 'VNC Server is ready!';
                }} else {{
                    document.querySelector('.status').textContent = 'VNC Server detected, connecting...';
                }}
            }});
        }});
    </script>
</body>
</html>
"""
        return html_content

    def _create_custom_novnc_page(self, novnc_port, vnc_port, session_id):
        """Create a custom noVNC page that prevents DOM errors by ensuring all required elements exist"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>VNC Client - {session_id}</title>
    <meta charset="utf-8">
    <script>
        window.vncConfig = {{
            serverHost: '{self.server_host}',
            novncPort: {novnc_port},
            protocol: window.location.protocol === 'https:' ? 'https' : 'http',
            wsProtocol: window.location.protocol === 'https:' ? 'wss' : 'ws'
        }};
    </script>
    <script>
        document.addEventListener('DOMContentLoaded', function() {{
            const baseUrl = `${{window.vncConfig.protocol}}://${{window.vncConfig.serverHost}}:${{window.vncConfig.novncPort}}`;
            const head = document.head;
            
            const baseCss = document.createElement('link');
            baseCss.rel = 'stylesheet';
            baseCss.type = 'text/css';
            baseCss.href = baseUrl + '/app/styles/base.css';
            head.appendChild(baseCss);
            
            const uiCss = document.createElement('link');
            uiCss.rel = 'stylesheet';
            uiCss.type = 'text/css';
            uiCss.href = baseUrl + '/app/styles/ui.css';
            head.appendChild(uiCss);
        }});
    </script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #000;
            overflow: hidden;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
        }}
        #noVNC_container {{
            width: 100vw;
            height: 100vh;
            position: relative;
            background: #000;
        }}
        #noVNC_screen {{
            position: absolute;
            margin: 0;
            padding: 0;
            top: 0;
            left: 0;
            bottom: 0;
            right: 0;
            background: #000;
        }}
        #noVNC_canvas {{
            background: #000;
        }}
        .noVNC_loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #fff;
            font-size: 18px;
            z-index: 1000;
        }}
        /* Ensure touch-related elements exist to prevent DOM errors */
        #noVNC_control_bar,
        #noVNC_settings_button,
        #noVNC_disconnect_button,
        #noVNC_fullscreen_button {{
            display: none;
        }}
    </style>
</head>
<body>
    <div id="noVNC_container">
        <div id="noVNC_screen">
            <div class="noVNC_loading">Connecting to VNC server...</div>
            <canvas id="noVNC_canvas"></canvas>
        </div>
        
        <!-- Control elements to prevent DOM errors -->
        <div id="noVNC_control_bar" style="display: none;">
            <div id="noVNC_control_bar_anchor"></div>
            <button id="noVNC_settings_button"></button>
            <button id="noVNC_disconnect_button"></button>
            <button id="noVNC_fullscreen_button"></button>
            <button id="noVNC_clipboard_button"></button>
            <button id="noVNC_keyboard_button"></button>
            <div id="noVNC_control_bar_handle"></div>
        </div>
        
        <!-- Hidden elements to prevent touch handler errors -->
        <div style="display: none;">
            <div id="noVNC_touch_area"></div>
            <div id="noVNC_mobile_touch"></div>
            <div id="noVNC_keyboard_area"></div>
        </div>
    </div>

    <!-- Load noVNC scripts -->
    <script type="module">
        const baseUrl = `${{window.vncConfig.protocol}}://${{window.vncConfig.serverHost}}:${{window.vncConfig.novncPort}}`;
        
        const RFBModule = await import(baseUrl + '/core/rfb.js');
        const LoggingModule = await import(baseUrl + '/core/util/logging.js');
        
        const RFB = RFBModule.default || RFBModule.RFB;
        const setLogLevel = LoggingModule.setLogLevel;
        
        // Set minimal logging
        setLogLevel('warn');
        
        let rfb = undefined;
        let resizeTimeout;
        
        function updateDesktopSize() {{
            if (rfb) {{
                const canvas = document.getElementById('noVNC_canvas');
                const container = document.getElementById('noVNC_screen');
                const containerRect = container.getBoundingClientRect();
                canvas.style.width = containerRect.width + 'px';
                canvas.style.height = containerRect.height + 'px';
            }}
        }}
        
        function connected(e) {{
            console.log('[CUSTOM_VNC] Connected to VNC server');
            document.querySelector('.noVNC_loading').style.display = 'none';
            updateDesktopSize();
        }}
        
        function disconnected(e) {{
            console.log('[CUSTOM_VNC] Disconnected from VNC server');
            document.querySelector('.noVNC_loading').innerHTML = 'Disconnected. <button onclick="connect()">Reconnect</button>';
            document.querySelector('.noVNC_loading').style.display = 'block';
        }}
        
        function credentialsRequired(e) {{
            console.log('[CUSTOM_VNC] Credentials required');
            // For automation, typically no password is needed
        }}
        
        function connect() {{
            console.log('[CUSTOM_VNC] Attempting to connect...');
            document.querySelector('.noVNC_loading').textContent = 'Connecting...';
            document.querySelector('.noVNC_loading').style.display = 'block';
            
            try {{
                const canvas = document.getElementById('noVNC_canvas');
                const wsUrl = `${{window.vncConfig.wsProtocol}}://${{window.vncConfig.serverHost}}:${{window.vncConfig.novncPort}}/websockify`;
                
                rfb = new RFB(canvas, wsUrl, {{
                    shared: true,
                    repeaterID: '',
                    wsProtocols: ['binary']
                }});
                
                rfb.addEventListener("connect", connected);
                rfb.addEventListener("disconnect", disconnected);
                rfb.addEventListener("credentialsrequired", credentialsRequired);
                
                rfb.scaleViewport = true;
                rfb.resizeSession = true;
                
            }} catch (err) {{
                console.error('[CUSTOM_VNC] Connection error:', err);
                document.querySelector('.noVNC_loading').innerHTML = 'Connection failed. <button onclick="connect()">Retry</button>';
            }}
        }}
        
        window.connect = connect;
        
        // Auto-connect when page loads
        window.addEventListener('load', function() {{
            console.log('[CUSTOM_VNC] Page loaded, auto-connecting...');
            connect();
        }});
        
        // Handle window resize
        window.addEventListener('resize', function() {{
            clearTimeout(resizeTimeout);
            resizeTimeout = setTimeout(updateDesktopSize, 100);
        }});
        
    </script>
</body>
</html>
"""
        return html_content

    def _check_system_requirements(self):
        """Check that required system binaries are available"""
        try:
            print("[VNC_MGR] Checking system requirements...")
            
            required_binaries = {
                "Xvfb": "sudo apt-get install xvfb",
                "x11vnc": "sudo apt-get install x11vnc", 
                "python3": "sudo apt-get install python3",
                "tar": "sudo apt-get install tar",
                "wget": "sudo apt-get install wget (or curl)"
            }
            
            missing_binaries = []
            
            for binary, install_cmd in required_binaries.items():
                try:
                    result = subprocess.run([
                        "which", binary
                    ], capture_output=True, text=True, timeout=5)
                    
                    if result.returncode == 0:
                        print(f"[VNC_MGR] ✅ {binary} found: {result.stdout.strip()}")
                    else:
                        print(f"[VNC_MGR] ERROR: {binary} not found")
                        missing_binaries.append((binary, install_cmd))
                        
                except Exception as e:
                    print(f"[VNC_MGR] ERROR: Failed to check {binary}: {e}")
                    missing_binaries.append((binary, install_cmd))
            
            # Check websockify in venv
            websockify_path = "/home/ubuntu/.local/bin/websockify"
            if os.path.exists(websockify_path):
                print(f"[VNC_MGR] ✅ websockify found: {websockify_path}")
            else:
                print(f"[VNC_MGR] ERROR: websockify not found at {websockify_path}")
                print("[VNC_MGR] Run: pip install websockify")
            
            if missing_binaries:
                print(f"[VNC_MGR] ERROR: Missing system binaries detected!")
                for binary, install_cmd in missing_binaries:
                    print(f"[VNC_MGR] To install {binary}: {install_cmd}")
                print("[VNC_MGR] ⚠️  VNC functionality may not work properly without these binaries")
            else:
                print("[VNC_MGR] ✅ All system requirements satisfied")
                
        except Exception as e:
            print(f"[VNC_MGR] Error checking system requirements: {e}")

    def _ensure_dependencies_available(self):
        """Automatically install required Python packages if missing"""
        try:
            print("[VNC_MGR] Checking Python dependencies...")
            
            required_packages = [
                ("websocket-client", "websocket"),
                ("requests", "requests")
            ]
            
            for pip_name, import_name in required_packages:
                try:
                    __import__(import_name)
                    print(f"[VNC_MGR] ✅ {import_name} available")
                except ImportError:
                    print(f"[VNC_MGR] Installing missing package: {pip_name}")
                    try:
                        subprocess.run([
                            "pip", "install", pip_name
                        ], check=True, capture_output=True, text=True)
                        print(f"[VNC_MGR] ✅ Successfully installed {pip_name}")
                    except Exception as e:
                        print(f"[VNC_MGR] ❌ Failed to install {pip_name}: {e}")
                        
            print("[VNC_MGR] Dependency check complete")
            
        except Exception as e:
            print(f"[VNC_MGR] Error checking dependencies: {e}")

    def _ensure_novnc_available(self):
        """Automatically setup noVNC if not available"""
        try:
            print("[VNC_MGR] Checking noVNC installation...")
            
            # Check if noVNC is already installed and valid
            if os.path.exists(self.novnc_install_path):
                vnc_html_path = os.path.join(self.novnc_install_path, "vnc.html")
                core_dir_path = os.path.join(self.novnc_install_path, "core")
                
                if os.path.exists(vnc_html_path) and os.path.exists(core_dir_path):
                    print(f"[VNC_MGR] ✅ Valid noVNC installation found at {self.novnc_install_path}")
                    return True
                else:
                    print(f"[VNC_MGR] Invalid noVNC installation, removing...")
                    shutil.rmtree(self.novnc_install_path, ignore_errors=True)
            
            # Download and install noVNC
            print("[VNC_MGR] Installing noVNC automatically...")
            return self._download_and_install_novnc()
            
        except Exception as e:
            print(f"[VNC_MGR] Failed to ensure noVNC availability: {e}")
            return False

    def _download_and_install_novnc(self):
        """Download and install noVNC from GitHub"""
        try:
            temp_dir = "/tmp/novnc_auto_install"
            
            # Clean up any existing temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            
            os.makedirs(temp_dir, exist_ok=True)
            
            print("[VNC_MGR] Downloading noVNC from GitHub...")
            
            # Try git clone first, then fallback to wget
            download_success = False
            
            # Method 1: Try git clone
            try:
                result = subprocess.run([
                    "git", "clone", "--depth", "1", 
                    "https://github.com/novnc/noVNC.git",
                    os.path.join(temp_dir, "noVNC")
                ], capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print("[VNC_MGR] ✅ Downloaded noVNC using git")
                    download_success = True
                else:
                    print(f"[VNC_MGR] Git clone failed: {result.stderr}")
            except Exception as e:
                print(f"[VNC_MGR] Git clone failed: {e}")
            
            # Method 2: Fallback to wget/curl
            if not download_success:
                try:
                    print("[VNC_MGR] Trying wget download...")
                    wget_result = subprocess.run([
                        "wget", "-O", os.path.join(temp_dir, "novnc.tar.gz"),
                        "https://github.com/novnc/noVNC/archive/refs/heads/master.tar.gz"
                    ], capture_output=True, text=True, timeout=60)
                    
                    if wget_result.returncode == 0:
                        # Extract the tar.gz
                        subprocess.run([
                            "tar", "-xzf", os.path.join(temp_dir, "novnc.tar.gz"),
                            "-C", temp_dir
                        ], check=True)
                        
                        # Rename the extracted directory
                        extracted_dir = os.path.join(temp_dir, "noVNC-master")
                        target_dir = os.path.join(temp_dir, "noVNC")
                        
                        if os.path.exists(extracted_dir):
                            os.rename(extracted_dir, target_dir)
                            print("[VNC_MGR] ✅ Downloaded noVNC using wget")
                            download_success = True
                        
                except Exception as e:
                    print(f"[VNC_MGR] Wget download failed: {e}")
            
            # Method 3: Final fallback to curl
            if not download_success:
                try:
                    print("[VNC_MGR] Trying curl download...")
                    curl_result = subprocess.run([
                        "curl", "-L", "-o", os.path.join(temp_dir, "novnc.tar.gz"),
                        "https://github.com/novnc/noVNC/archive/refs/heads/master.tar.gz"
                    ], capture_output=True, text=True, timeout=60)
                    
                    if curl_result.returncode == 0:
                        # Extract the tar.gz
                        subprocess.run([
                            "tar", "-xzf", os.path.join(temp_dir, "novnc.tar.gz"),
                            "-C", temp_dir
                        ], check=True)
                        
                        # Rename the extracted directory
                        extracted_dir = os.path.join(temp_dir, "noVNC-master")
                        target_dir = os.path.join(temp_dir, "noVNC")
                        
                        if os.path.exists(extracted_dir):
                            os.rename(extracted_dir, target_dir)
                            print("[VNC_MGR] ✅ Downloaded noVNC using curl")
                            download_success = True
                        
                except Exception as e:
                    print(f"[VNC_MGR] Curl download failed: {e}")
            
            if not download_success:
                print("[VNC_MGR] ❌ All download methods failed")
                return False
            
            # Move to final location
            source_dir = os.path.join(temp_dir, "noVNC")
            if not os.path.exists(source_dir):
                print(f"[VNC_MGR] ❌ Source directory not found: {source_dir}")
                return False
            
            print(f"[VNC_MGR] Installing noVNC to {self.novnc_install_path}...")
            
            # Create parent directory if it doesn't exist
            os.makedirs(os.path.dirname(self.novnc_install_path), exist_ok=True)
            
            # Move the downloaded noVNC to the target location
            shutil.move(source_dir, self.novnc_install_path)
            
            # Verify installation
            vnc_html_path = os.path.join(self.novnc_install_path, "vnc.html")
            if os.path.exists(vnc_html_path):
                print(f"[VNC_MGR] ✅ noVNC installed successfully at {self.novnc_install_path}")
                
                # Set proper permissions (if running as admin user)
                try:
                    subprocess.run([
                        "chown", "-R", "admin:admin", self.novnc_install_path
                    ], check=False)  # Don't fail if chown doesn't work
                    subprocess.run([
                        "chmod", "-R", "755", self.novnc_install_path  
                    ], check=False)  # Don't fail if chmod doesn't work
                except:
                    pass  # Ignore permission errors
                
                # Cleanup temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                return True
            else:
                print(f"[VNC_MGR] ❌ Installation verification failed")
                return False
                
        except Exception as e:
            print(f"[VNC_MGR] Failed to download and install noVNC: {e}")
            return False

    # -------------------------------------------------------
    # global VNC server
    # -------------------------------------------------------

    def _start_global_vnc_server(self):
        """Start global VNC server for fallback connections"""
        try:
            print("[VNC_MGR] Attempting to start global VNC server...")
            
            # Check if we're on Windows and use the provided shell scripts
            import platform
            if platform.system() == "Windows":
                print("[VNC_MGR] Windows detected, starting VNC via shell script...")
                
                # Use the start_stream.sh script to start VNC
                script_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "start_stream.sh")
                
                try:
                    if os.path.exists(script_path):
                        # Run the VNC startup script with display ID 0 for global server
                        result = subprocess.run(
                            ["bash", script_path, "0"],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        
                        if result.returncode == 0:
                            print(f"[VNC_MGR] Global VNC server started successfully")
                            print(f"[VNC_MGR] Output: {result.stdout}")
                            self.global_vnc_started = True
                        else:
                            print(f"[VNC_MGR] Global VNC server failed to start: {result.stderr}")
                            self.global_vnc_started = False
                    else:
                        print(f"[VNC_MGR] VNC script not found at {script_path}")
                        self.global_vnc_started = False
                        
                except Exception as script_error:
                    print(f"[VNC_MGR] Error running VNC script: {script_error}")
                    self.global_vnc_started = False
            else:
                # Linux - try native VNC tools
                print("[VNC_MGR] Linux detected, starting native VNC...")
                self._start_linux_global_vnc()
            
            # If script-based approach fails, try direct command approach
            if not self.global_vnc_started:
                print("[VNC_MGR] Script-based approach failed, trying direct command approach...")
                self._start_direct_global_vnc()
                
        except Exception as e:
            print(f"[VNC_MGR] Failed to start global VNC server: {e}")
            self.global_vnc_started = False

    def _start_direct_global_vnc(self):
        """Start global VNC server using direct commands"""
        try:
            print("[VNC_MGR] Starting global VNC server with direct commands...")
            
            # Use Xvnc instead of Xvfb + x11vnc for simplicity
            display_num = 0
            vnc_port = self.global_vnc_port  # Standard VNC port
            novnc_port = self.global_novnc_port
            
            # Start Xvnc server
            xvnc_cmd = [
                "Xvnc", f":{display_num}",
                "-geometry", "1920x1080",
                "-depth", "24", 
                "-SecurityTypes", "None",
                "-AlwaysShared",
                "-DisconnectClients=0",
                "-MaxDisconnectionTime=0"
            ]
            
            print(f"[VNC_MGR] Starting Xvnc: {' '.join(xvnc_cmd)}")
            xvnc_proc = subprocess.Popen(
                xvnc_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            time.sleep(3)  # Wait for Xvnc to start
            
            if xvnc_proc.poll() is None:  # Still running
                print(f"[VNC_MGR] ✅ Xvnc started successfully on display :{display_num}")
                
                # Start websockify
                websockify_cmd = [
                    "/home/ubuntu/.local/bin/websockify",
                    "--web", self.novnc_install_path,
                    f"{self.server_host}:{novnc_port}",
                    f"localhost:{vnc_port}"
                ]
                
                print(f"[VNC_MGR] Starting websockify: {' '.join(websockify_cmd)}")
                websockify_proc = subprocess.Popen(
                    websockify_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                time.sleep(2)  # Wait for websockify to start
                
                if websockify_proc.poll() is None:  # Still running
                    print(f"[VNC_MGR] ✅ Global VNC server started successfully on port {novnc_port}")
                    self.global_vnc_started = True
                    return True
                else:
                    print("[VNC_MGR] ❌ websockify failed to start")
                    xvnc_proc.terminate()
            else:
                print("[VNC_MGR] ❌ Xvnc failed to start")
            
            return False
            
        except Exception as e:
            print(f"[VNC_MGR] Direct global VNC startup failed: {e}")
            return False

    def _start_linux_global_vnc(self):
        """Start global VNC server on Linux"""
        try:
            # This would be the Linux implementation
            # For now, just mark as failed since we're primarily on Windows
            print("[VNC_MGR] Linux VNC implementation not yet complete")
            self.global_vnc_started = False
        except Exception as e:
            print(f"[VNC_MGR] Linux VNC startup failed: {e}")
            self.global_vnc_started = False

    def _check_existing_global_vnc(self):
        """Check if global VNC server is already running"""
        try:
            print("[VNC_MGR] Checking for existing global VNC server...")

            # Check if the global noVNC port is accessible
            if not self._is_port_free(self.global_novnc_port):
                print(f"[VNC_MGR] Global noVNC port {self.global_novnc_port} is in use")

                # Test HTTP access to noVNC interface
                try:
                    response = requests.get(
                        f"http://{self.server_host}:{self.global_novnc_port}/vnc.html",
                        timeout=5
                    )
                    if response.status_code == 200:
                        print("[VNC_MGR] Global noVNC HTTP interface accessible")

                        # Test WebSocket connection
                        if self._test_websocket_connection(self.server_host, self.global_novnc_port):
                            print("[VNC_MGR] ✅ Global VNC server detected and working!")
                            self.global_vnc_started = True
                            return True
                        else:
                            print("[VNC_MGR] Global noVNC WebSocket test failed")
                    else:
                        print(f"[VNC_MGR] Global noVNC HTTP failed: {response.status_code}")
                except Exception as e:
                    print(f"[VNC_MGR] Global noVNC HTTP test failed: {e}")
            else:
                print(f"[VNC_MGR] Global noVNC port {self.global_novnc_port} is free")

            print("[VNC_MGR] No working global VNC server detected")
            self.global_vnc_started = False
            return False

        except Exception as e:
            print(f"[VNC_MGR] Error checking existing global VNC: {e}")
            self.global_vnc_started = False
            return False

    def _create_custom_vnc_html(self):
        """Create custom VNC HTML file with correct WebSocket configuration"""
        try:
            print("[VNC_MGR] Creating custom VNC HTML file...")
            
            custom_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Automation VNC Session</title>
    <meta charset="utf-8">
    <link rel="stylesheet" href="app/styles/base.css">
    <script type="module" crossorigin="anonymous" src="app/ui.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 0;
            background: #000;
            font-family: Arial, sans-serif;
        }}
        #noVNC_container {{
            width: 100vw;
            height: 100vh;
            overflow: hidden;
        }}
        .status {{
            position: fixed;
            top: 10px;
            left: 10px;
            background: rgba(0,0,0,0.8);
            color: white;
            padding: 5px 10px;
            border-radius: 3px;
            font-size: 12px;
            z-index: 1000;
        }}
    </style>
</head>
<body>
    <div class="status" id="status">Connecting...</div>
    <div id="noVNC_container">
        <div id="noVNC_canvas_container">
            <canvas id="noVNC_canvas"></canvas>
        </div>
    </div>
    
    <script>
        // Import RFB from noVNC
        import RFB from './core/rfb.js';
        
        let rfb;
        
        function updateStatus(text, isError = false) {{
            const status = document.getElementById('status');
            status.textContent = text;
            status.style.background = isError ? 'rgba(255,0,0,0.8)' : 'rgba(0,100,0,0.8)';
            console.log('[VNC]', text);
        }}
        
        function connected(e) {{
            updateStatus('Connected');
        }}
        
        function disconnected(e) {{
            updateStatus('Disconnected', true);
            // Auto-retry connection after 3 seconds
            setTimeout(connect, 3000);
        }}
        
        function credentialsRequired(e) {{
            updateStatus('Credentials required', true);
        }}
        
        function connect() {{
            try {{
                updateStatus('Connecting...');
                
                const canvas = document.getElementById('noVNC_canvas');
                const url = `ws://{self.server_host}:{self.global_novnc_port}/websockify`;
                
                console.log('[VNC] WebSocket URL:', url);
                
                rfb = new RFB(canvas, url, {{
                    shared: true,
                    repeaterID: '',
                    wsProtocols: ['binary']
                }});
                
                rfb.addEventListener("connect", connected);
                rfb.addEventListener("disconnect", disconnected); 
                rfb.addEventListener("credentialsrequired", credentialsRequired);
                
                rfb.scaleViewport = true;
                rfb.resizeSession = true;
                rfb.clipToWindow = false;
                
            }} catch (err) {{
                updateStatus('Connection failed: ' + err.message, true);
                console.error('[VNC] Connection error:', err);
                setTimeout(connect, 5000); // Retry after 5 seconds
            }}
        }}
        
        // Auto-connect when page loads
        window.addEventListener('load', function() {{
            console.log('[VNC] Page loaded, connecting...');
            connect();
        }});
        
        // Handle window resize
        window.addEventListener('resize', function() {{
            if (rfb) {{
                rfb.scaleViewport = true;
            }}
        }});
    </script>
</body>
</html>"""
            
            # Save the custom HTML file to noVNC directory
            custom_html_path = os.path.join(self.novnc_install_path, "custom_vnc.html")
            with open(custom_html_path, 'w', encoding='utf-8') as f:
                f.write(custom_html)
            
            print(f"[VNC_MGR] ✅ Custom VNC HTML created: {custom_html_path}")
            return True
            
        except Exception as e:
            print(f"[VNC_MGR] ❌ Failed to create custom VNC HTML: {e}")
            return False

    # -------------------------------------------------------
    # process starters
    # -------------------------------------------------------

    def _start_xvfb(self, display):
        disp = f":{display}"

        # cleanup stale locks
        for p in (f"/tmp/.X{display}-lock", f"/tmp/.X11-unix/X{display}"):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        cmd = ["Xvfb", disp, "-screen", "0", "1920x1080x24", "-ac", "-nolisten", "tcp"]

        print(f"[VNC_MGR] Starting Xvfb: {' '.join(cmd)}")

        p = subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        time.sleep(1.5)

        if p.poll() is None and self._is_display_alive(display):
            print(f"[VNC_MGR] Xvfb running on {disp}")
            return p

        print("[VNC_MGR] Xvfb failed to start")
        return None

    def _start_x11vnc(self, display, vnc_port):
        disp = f":{display}"
        cmd = [
            "x11vnc",
            "-display", disp,
            "-rfbport", str(vnc_port),
            "-forever",
            "-nopw",
            "-shared",
            "-threads",
            "-noxrecord",
            "-noxfixes",
            "-noxdamage",
        ]

        print(f"[VNC_MGR] Starting x11vnc: {' '.join(cmd)}")

        p = subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if not self._wait_for_vnc_port_ready(vnc_port, max_retries=8):
            print(f"[VNC_MGR] x11vnc failed to become ready on port {vnc_port}")
            return None

        if p.poll() is None:
            print(f"[VNC_MGR] x11vnc listening on {vnc_port}")
            return p

        print("[VNC_MGR] x11vnc failed")
        return None

    def _start_websockify(self, rfb_port, novnc_port, max_retries=3):
        for attempt in range(max_retries):
            print(f"[VNC_MGR] Starting websockify attempt {attempt + 1}/{max_retries}")
            
            cmd = [
                "/home/ubuntu/.local/bin/websockify",
                "--web", self.novnc_install_path,
                f"0.0.0.0:{novnc_port}",
                f"localhost:{rfb_port}",
            ]

            print(f"[VNC_MGR] Starting novnc_proxy: {' '.join(cmd)}")
            print(f"[VNC_MGR] websockify will bridge VNC port {rfb_port} to noVNC port {novnc_port} (listening on all interfaces)")

            p = subprocess.Popen(
                cmd,
                start_new_session=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            
            # Wait longer for websockify to start
            time.sleep(2)

            if not self._wait_for_novnc_http(novnc_port):
                print(f"[VNC_MGR] noVNC HTTP not ready on port {novnc_port}")
                stdout, stderr = p.communicate(timeout=3) if p.poll() is None else ("", "")
                if stdout:
                    print(f"[VNC_MGR] websockify stdout: {stdout}")
                if stderr:
                    print(f"[VNC_MGR] websockify stderr: {stderr}")
                    
                # Kill the failed process
                if p.poll() is None:
                    p.terminate()
                    time.sleep(1)
                    if p.poll() is None:
                        p.kill()
                        
                if attempt < max_retries - 1:
                    print(f"[VNC_MGR] Retrying websockify in 2 seconds...")
                    time.sleep(2)
                continue

            if p.poll() is None:
                print(f"[VNC_MGR] novnc_proxy running on {novnc_port}")
                return p

            print(f"[VNC_MGR] novnc_proxy failed on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                time.sleep(2)

        print("[VNC_MGR] All websockify attempts failed")
        return None

    # -------------------------------------------------------
    # public API
    # -------------------------------------------------------

    def start_streaming_session(self, email, execution_id):
        print(f"[VNC_MGR] Starting streaming session for {email}, execution: {execution_id}")

        # Prioritize individual sessions with dynamic port assignment
        print("[VNC_MGR] Attempting individual session with dynamic port allocation...")
        individual_session = self._try_individual_session(email, execution_id)
        if individual_session:
            print(f"[VNC_MGR] Individual session created successfully: {individual_session['novnc_url']}")
            print(f"[VNC_MGR] Dynamic ports assigned - VNC: {individual_session['vnc_port']}, noVNC: {individual_session['novnc_port']}")
            return individual_session

        # Fall back to global session if individual creation fails
        print("[VNC_MGR] Individual session failed, attempting global session as fallback...")
        if self.global_vnc_started:
            global_session = self._create_global_session(email, execution_id)
            if global_session:
                print(f"[VNC_MGR] Global session created successfully: {global_session['novnc_url']}")
                return global_session

        # Last resort: try to restart global and create session
        print("[VNC_MGR] Global session not available, attempting to restart global VNC server...")
        self._start_global_vnc_server()
        global_session = self._create_global_session(email, execution_id)
        if global_session:
            print(f"[VNC_MGR] Global session created after restart: {global_session['novnc_url']}")
            return global_session

        print("[VNC_MGR] All session creation methods failed")
        return None

    def _try_individual_session(self, email, execution_id, max_retries=2):
        """Try to create an individual VNC session for the user with retry logic"""
        for attempt in range(max_retries):
            try:
                print(f"[VNC_MGR] Creating individual session attempt {attempt + 1}/{max_retries}")
                
                with self.session_lock:
                    # Rate limiting: check total concurrent sessions
                    active_session_count = len(self.active_sessions)
                    if active_session_count >= self.max_concurrent_sessions:
                        print(f"[VNC_RATELIMIT] Server has reached max concurrent sessions ({active_session_count}/{self.max_concurrent_sessions})")
                        print(f"[VNC_RATELIMIT] Active sessions: {list(self.active_sessions.keys())[:5]}...")  # Show first 5
                        return None
                    
                    # Per-user parallel execution limit
                    count = self.user_execution_count.get(email, 0)
                    if count >= MAX_PARALLEL_EXECUTIONS_PER_USER:
                        print(f"[VNC_RATELIMIT] Parallel execution limit reached for {email} ({count}/{MAX_PARALLEL_EXECUTIONS_PER_USER})")
                        return None
                    self.user_execution_count[email] = count + 1

                exec_index = count % MAX_PARALLEL_EXECUTIONS_PER_USER
                primary_port, auxiliary_port1, auxiliary_port2, display = self._assign_ports(email, exec_index)

                # Use primary_port as the main VNC port
                vnc_port = primary_port
                # Use explicit mapping for noVNC port
                novnc_port = self._get_novnc_port_for_vnc_port(vnc_port)

                # Check if all required ports are free
                required_ports = [vnc_port, novnc_port, auxiliary_port1, auxiliary_port2]

                if not self._wait_for_ports_free(required_ports):
                    with self.session_lock:
                        self.user_execution_count[email] -= 1
                        if self.user_execution_count[email] <= 0:
                            del self.user_execution_count[email]
                    print(f"[VNC_MGR] Required ports not available: {required_ports}")
                    continue  # Try again

                print(
                    f"[VNC_MGR] Allocated for {email}: "
                    f"primary={primary_port}, aux1={auxiliary_port1}, aux2={auxiliary_port2}, "
                    f"novnc={novnc_port}, display={display}"
                )

                session_id = f"{execution_id}_{uuid.uuid4()}"

                try:
                    xvfb = self._start_xvfb(display)
                    if not xvfb:
                        raise RuntimeError("Xvfb failed")
                    print(f"[VNC_LOG] Xvfb started for display :{display} (PID: {xvfb.pid})")

                    x11vnc = self._start_x11vnc(display, vnc_port)
                    if not x11vnc:
                        raise RuntimeError("x11vnc failed")
                    print(f"[VNC_LOG] x11vnc started on port {vnc_port} (PID: {x11vnc.pid})")

                    novnc = self._start_websockify(vnc_port, novnc_port)
                    if not novnc:
                        raise RuntimeError("novnc_proxy failed")
                    print(f"[VNC_LOG] WebSockify started on noVNC port {novnc_port} (PID: {novnc.pid})")

                    time.sleep(2)  # Give services time to stabilize
                    print(f"[DEBUG] noVNC expected on port {novnc_port}")

                    # Force explicit host/port so noVNC does not reuse stale browser settings
                    direct_url = (
                        f"http://{self.server_host}:{novnc_port}/vnc.html?"
                        f"autoconnect=true&resize=remote&host={self.server_host}"
                        f"&port={novnc_port}&path=websockify&reconnect=true&reconnect_delay=500"
                    )

                    # Verify the session works before returning it
                    print(f"[VNC_MGR] Verifying session connectivity for session {session_id}...")
                    if not self._verify_vnc_session(direct_url, vnc_port):
                        print(f"[VNC_ERROR] Session verification failed for session {session_id} on attempt {attempt + 1}")
                        print(f"[VNC_ERROR] Details - Display: :{display}, VNC Port: {vnc_port}, noVNC Port: {novnc_port}")
                        print(f"[VNC_ERROR] Process PIDs - Xvfb: {xvfb.pid}, x11vnc: {x11vnc.pid}, WebSockify: {novnc.pid}")
                        try:
                            if novnc and novnc.poll() is None:
                                novnc.terminate()
                            if x11vnc and x11vnc.poll() is None:
                                x11vnc.terminate()
                            if xvfb and xvfb.poll() is None:
                                xvfb.terminate()
                        except:
                            pass
                        
                        with self.session_lock:
                            self.user_execution_count[email] -= 1
                            if self.user_execution_count[email] <= 0:
                                del self.user_execution_count[email]
                        
                        if attempt < max_retries - 1:
                            print(f"[VNC_MGR] Retrying session creation...")
                            time.sleep(2)
                            continue
                        else:
                            return None

                    session = {
                        "session_id": session_id,
                        "execution_id": execution_id,
                        "user_email": email,
                        "display": f":{display}",
                        "display_num": display,
                        "vnc_port": vnc_port,
                        "novnc_port": novnc_port,
                        "novnc_url": direct_url,
                        "direct_url": direct_url,
                        "xvfb": xvfb,
                        "x11vnc": x11vnc,
                        "novnc_proxy": novnc,
                        "started_at": datetime.utcnow(),
                        "session_type": "individual",
                        "verified": True
                    }

                    with self.session_lock:
                        self.active_sessions[session_id] = session

                    print(f"[VNC_SUCCESS] Session {session_id} created successfully")
                    print(f"[VNC_SUCCESS] User: {email}, Display: :{display}, VNC: {vnc_port}, noVNC: {novnc_port}")
                    print(f"[VNC_SUCCESS] URL: {direct_url}")
                    print(f"[VNC_SUCCESS] Active sessions on server: {len(self.active_sessions)}/{self.max_concurrent_sessions}")
                    return session

                except Exception as e:
                    print(f"[VNC_ERROR] Individual session failed for session {session_id}: {e}")
                    print(f"[VNC_ERROR] Details - User: {email}, Display: :{display}, VNC Port: {vnc_port}, noVNC Port: {novnc_port}")
                    import traceback
                    print(f"[VNC_ERROR] Traceback: {traceback.format_exc()}")
                    
                    with self.session_lock:
                        self.user_execution_count[email] -= 1
                        if self.user_execution_count[email] <= 0:
                            del self.user_execution_count[email]
                    
                    if attempt < max_retries - 1:
                        print(f"[VNC_MGR] Retrying after error (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(2)
                        continue
                    else:
                        return None
                        
            except Exception as e:
                print(f"[VNC_MGR] Individual session setup failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return None
        
        print(f"[VNC_MGR] Failed to create individual session after {max_retries} attempts")
        return None

    def _create_global_session(self, email, execution_id):
        """Create a global VNC session as fallback"""
        try:
            print(f"[VNC_MGR] Creating global session for {email}")
            
            # Restart global VNC if not running
            if not self.global_vnc_started:
                print("[VNC_MGR] Attempting to restart global VNC server...")
                self._start_global_vnc_server()
            
            # Create session info for global server
            session_id = f"global_{execution_id}_{uuid.uuid4()}"
            
            session = {
                "session_id": session_id,
                "execution_id": execution_id,
                "user_email": email,
                "display": ":0",  # Global display
                "display_num": 0,
                "vnc_port": self.global_vnc_port,  # Raw VNC port (5900)
                "novnc_port": self.global_novnc_port,  # noVNC HTTP port (6005)
                "novnc_url": self.global_vnc_url,
                "direct_url": self.global_vnc_url,
                "started_at": datetime.utcnow(),
                "session_type": "global"
            }
            
            with self.session_lock:
                self.active_sessions[session_id] = session
            
            print(f"[VNC_MGR] Global session created: {self.global_vnc_url}")
            return session
            
        except Exception as e:
            print(f"[VNC_MGR] Global session creation failed: {e}")
            return None

    def stop_user_vnc_session(self, session_id):
        with self.session_lock:
            session = self.active_sessions.pop(session_id, None)

        if not session:
            return False

        # Clean up processes
        for proc_name in ["xvfb", "x11vnc", "novnc_proxy"]:
            proc = session.get(proc_name)
            if proc and proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    pass

        email = session["user_email"]
        
        with self.session_lock:
            if email in self.user_execution_count:
                self.user_execution_count[email] -= 1
                if self.user_execution_count[email] <= 0:
                    del self.user_execution_count[email]

        print(f"[VNC_MGR] Session stopped: {session_id}")
        return True
    
    def list_active_sessions(self):
        """Return list of active VNC sessions with metadata"""
        with self.session_lock:
            sessions = []
            for session_id, session in self.active_sessions.items():
                sessions.append({
                    'session_id': session_id,
                    'execution_id': session.get('execution_id'),
                    'user_email': session.get('user_email'),
                    'started_at': session.get('started_at'),
                    'novnc_url': session.get('novnc_url'),
                    'display': session.get('display'),
                })
            return sessions

    def get_session_metrics(self):
        """Return detailed metrics about VNC session usage and rate limiting"""
        with self.session_lock:
            total_active = len(self.active_sessions)
            user_counts = {}
            port_usage = {}
            
            for session_id, session in self.active_sessions.items():
                user_email = session.get('user_email', 'unknown')
                user_counts[user_email] = user_counts.get(user_email, 0) + 1
                
                vnc_port = session.get('vnc_port')
                novnc_port = session.get('novnc_port')
                if vnc_port:
                    port_usage[vnc_port] = {'novnc': novnc_port, 'user': user_email}
            
            return {
                'total_active_sessions': total_active,
                'max_concurrent_sessions': self.max_concurrent_sessions,
                'sessions_available': self.max_concurrent_sessions - total_active,
                'usage_percent': (total_active / self.max_concurrent_sessions) * 100,
                'user_sessions': user_counts,
                'port_usage': port_usage,
                'user_parallel_counts': dict(self.user_execution_count),
                'max_parallel_per_user': MAX_PARALLEL_EXECUTIONS_PER_USER
            }

    # -------------------------------------------------------
    # cleanup thread
    # -------------------------------------------------------

    def _start_cleanup_thread(self):
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()

    def _cleanup_loop(self):
        while True:
            time.sleep(self.cleanup_interval)
            dead = []
            with self.session_lock:
                for sid, s in self.active_sessions.items():
                    # Check if xvfb exists and is not None before calling poll()
                    if "xvfb" in s and s["xvfb"] is not None and s["xvfb"].poll() is not None:
                        dead.append(sid)
            for sid in dead:
                print(f"[VNC_MGR] Cleaning dead session: {sid}")
                self.stop_user_vnc_session(sid)


# singleton
vnc_manager = VNCSessionManager(
    server_host="15.134.56.119",
    novnc_install_path="/home/ubuntu/Auto_Delta/noVNC",
)
