import threading
import os
import subprocess
import signal
import logging
from datetime import datetime
from typing import Dict, Optional
from vnc_session_manager import vnc_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VNCLifecycleManager:
    """
    User-specific VNC lifecycle manager with proper cleanup
    - Tracks VNC sessions per user email
    - Manages dynamic display allocation
    - Handles graceful cleanup
    - Tracks PIDs for proper process management
    """

    def __init__(self):
        self.user_sessions: Dict[str, Dict] = {}
        self.session_lock = threading.Lock()

    def allocate_vnc_session(self, user_email: str, execution_id: str) -> Optional[Dict]:
        """
        Allocate a new VNC session for a user
        Returns session info with allocated display, ports, and PIDs
        """
        try:
            with self.session_lock:
                logger.info(f"[VNC_LIFECYCLE] Allocating VNC session for user: {user_email}")

                existing_session = self.user_sessions.get(user_email)
                if existing_session and self._is_session_active(existing_session):
                    logger.info(f"[VNC_LIFECYCLE] Reusing existing session for {user_email}")
                    return existing_session

                session = vnc_manager.start_streaming_session(user_email, execution_id)

                if session:
                    session_data = {
                        'user_email': user_email,
                        'execution_id': execution_id,
                        'session_id': session.get('session_id'),
                        'display': session.get('display'),
                        'vnc_port': session.get('vnc_port'),
                        'novnc_port': session.get('novnc_port'),
                        'novnc_url': session.get('novnc_url'),
                        'pids': session.get('pids', []),
                        'created_at': datetime.now().isoformat(),
                        'status': 'active'
                    }

                    self.user_sessions[user_email] = session_data
                    logger.info(f"[VNC_LIFECYCLE] Session allocated for {user_email}: {session_data['display']}")

                    return session_data

                logger.warning(f"[VNC_LIFECYCLE] Failed to allocate VNC session for {user_email}")
                return None

        except Exception as e:
            logger.error(f"[VNC_LIFECYCLE] Error allocating session: {e}")
            return None

    def cleanup_user_vnc_session(self, user_email: str) -> bool:
        """
        Backward-compatible cleanup method.
        Internally kills all sessions/ports mapped to this user.
        """
        result = self.cleanup_all_user_sessions(user_email)
        return bool(result.get('success'))

    def cleanup_all_user_sessions(self, user_email: str) -> Dict:
        """Force cleanup of all active VNC sessions and assigned ports for a user."""
        try:
            with self.session_lock:
                lifecycle_session = self.user_sessions.get(user_email)
                managed_sessions = []

                if vnc_manager:
                    with vnc_manager.session_lock:
                        for session_id, session in vnc_manager.active_sessions.items():
                            if session.get('user_email') == user_email:
                                managed_sessions.append((session_id, dict(session)))

                session_ids = {session_id for session_id, _ in managed_sessions if session_id}
                if lifecycle_session and lifecycle_session.get('session_id'):
                    session_ids.add(lifecycle_session.get('session_id'))

                ports_to_cleanup = set()
                pids_to_kill = []

                if lifecycle_session:
                    for key in ('vnc_port', 'novnc_port'):
                        value = lifecycle_session.get(key)
                        if isinstance(value, int):
                            ports_to_cleanup.add(value)
                    pids_to_kill.extend(lifecycle_session.get('pids', []))

                for _, session in managed_sessions:
                    for key in ('vnc_port', 'novnc_port'):
                        value = session.get(key)
                        if isinstance(value, int):
                            ports_to_cleanup.add(value)
                    for proc_name in ('xvfb', 'x11vnc', 'novnc_proxy'):
                        proc = session.get(proc_name)
                        if proc and hasattr(proc, 'pid'):
                            pids_to_kill.append(proc.pid)

                if not session_ids and not lifecycle_session:
                    logger.warning(f"[VNC_LIFECYCLE] No session found for user: {user_email}")
                    return {
                        'success': False,
                        'sessions_terminated': 0,
                        'ports_cleaned': [],
                        'message': f'No active VNC session found for {user_email}'
                    }

                sessions_terminated = 0
                for session_id in session_ids:
                    try:
                        stopped = vnc_manager.stop_user_vnc_session(session_id) if vnc_manager else False
                        if stopped:
                            sessions_terminated += 1
                    except Exception as err:
                        logger.warning(f"[VNC_LIFECYCLE] Error stopping session {session_id}: {err}")

                for pid in pids_to_kill:
                    try:
                        if isinstance(pid, int) and pid > 0:
                            os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except Exception as err:
                        logger.debug(f"[VNC_LIFECYCLE] Could not kill PID {pid}: {err}")

                for port in sorted(ports_to_cleanup):
                    self._cleanup_port(port)

                if lifecycle_session:
                    lifecycle_session['status'] = 'terminated'
                self.user_sessions.pop(user_email, None)

                return {
                    'success': sessions_terminated > 0 or bool(ports_to_cleanup),
                    'sessions_terminated': sessions_terminated,
                    'ports_cleaned': sorted(ports_to_cleanup),
                    'message': f'Terminated {sessions_terminated} VNC session(s) for {user_email}'
                }

        except Exception as e:
            logger.error(f"[VNC_LIFECYCLE] Error during cleanup: {e}")
            return {
                'success': False,
                'sessions_terminated': 0,
                'ports_cleaned': [],
                'message': str(e)
            }

    def get_user_vnc_session(self, user_email: str) -> Optional[Dict]:
        """Get current VNC session info for a user."""
        with self.session_lock:
            session = self.user_sessions.get(user_email)
            if session and self._is_session_active(session):
                return session

            if vnc_manager:
                with vnc_manager.session_lock:
                    for session_id, managed in vnc_manager.active_sessions.items():
                        if managed.get('user_email') == user_email:
                            return {
                                'user_email': user_email,
                                'session_id': session_id,
                                'display': managed.get('display'),
                                'vnc_port': managed.get('vnc_port'),
                                'novnc_port': managed.get('novnc_port'),
                                'novnc_url': managed.get('novnc_url'),
                                'created_at': managed.get('started_at'),
                                'status': 'active'
                            }
            return None

    def get_user_vnc_status(self, user_email: str) -> Dict:
        """Get VNC status for a user."""
        session = self.get_user_vnc_session(user_email)

        if not session:
            return {
                'has_active_session': False,
                'user_email': user_email,
                'message': 'No active VNC session'
            }

        active_count = 1
        if vnc_manager:
            with vnc_manager.session_lock:
                active_count = sum(
                    1 for s in vnc_manager.active_sessions.values()
                    if s.get('user_email') == user_email
                )

        return {
            'has_active_session': True,
            'user_email': user_email,
            'display': session.get('display'),
            'vnc_port': session.get('vnc_port'),
            'novnc_port': session.get('novnc_port'),
            'novnc_url': session.get('novnc_url'),
            'created_at': session.get('created_at'),
            'status': session.get('status'),
            'active_session_count': active_count
        }

    def _is_session_active(self, session: Dict) -> bool:
        """Check if a session is still active."""
        if not session:
            return False

        if session.get('status') == 'terminated':
            return False

        try:
            pids = session.get('pids', [])
            if pids:
                for pid in pids:
                    if isinstance(pid, int) and pid > 0:
                        os.kill(pid, 0)
                return True
        except ProcessLookupError:
            pass

        return True

    def _cleanup_port(self, port: int):
        """Cleanup processes using a specific port."""
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
                        os.kill(pid, signal.SIGKILL)
                        logger.info(f"[VNC_LIFECYCLE] Killed process {pid} on port {port}")
                    except (ValueError, ProcessLookupError):
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"[VNC_LIFECYCLE] Could not cleanup port {port}: {e}")


vnc_lifecycle_manager = VNCLifecycleManager()
