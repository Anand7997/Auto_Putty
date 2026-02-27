import threading
import os
import subprocess
import signal
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
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
                    logger.info(f"[VNC_LIFECYCLE] ✓ Session allocated for {user_email}: {session_data['display']}")
                    
                    return session_data
                else:
                    logger.warning(f"[VNC_LIFECYCLE] Failed to allocate VNC session for {user_email}")
                    return None
                    
        except Exception as e:
            logger.error(f"[VNC_LIFECYCLE] Error allocating session: {e}")
            return None
    
    def cleanup_user_vnc_session(self, user_email: str) -> bool:
        """
        Kill/cleanup VNC session for a specific user
        Only affects the logged-in user's assigned VNC port
        """
        try:
            with self.session_lock:
                session = self.user_sessions.get(user_email)
                
                if not session:
                    logger.warning(f"[VNC_LIFECYCLE] No session found for user: {user_email}")
                    return False
                
                logger.info(f"[VNC_LIFECYCLE] Cleaning up VNC session for {user_email}")
                logger.info(f"[VNC_LIFECYCLE] Session details: {session}")
                
                cleaned = False
                
                if session.get('session_id') and vnc_manager:
                    try:
                        vnc_manager.stop_user_vnc_session(session['session_id'])
                        logger.info(f"[VNC_LIFECYCLE] ✓ Stopped VNC session via manager")
                        cleaned = True
                    except Exception as e:
                        logger.warning(f"[VNC_LIFECYCLE] Error stopping via manager: {e}")
                
                if session.get('pids'):
                    for pid in session.get('pids', []):
                        try:
                            if isinstance(pid, int) and pid > 0:
                                os.kill(pid, signal.SIGKILL)
                                logger.info(f"[VNC_LIFECYCLE] ✓ Killed PID: {pid}")
                                cleaned = True
                        except ProcessLookupError:
                            logger.info(f"[VNC_LIFECYCLE] PID {pid} already terminated")
                        except Exception as e:
                            logger.warning(f"[VNC_LIFECYCLE] Error killing PID {pid}: {e}")
                
                if session.get('vnc_port'):
                    self._cleanup_port(session['vnc_port'])
                    
                if session.get('novnc_port'):
                    self._cleanup_port(session['novnc_port'])
                
                session['status'] = 'terminated'
                logger.info(f"[VNC_LIFECYCLE] ✓ Cleanup completed for {user_email}")
                
                return cleaned
                
        except Exception as e:
            logger.error(f"[VNC_LIFECYCLE] Error during cleanup: {e}")
            return False
    
    def get_user_vnc_session(self, user_email: str) -> Optional[Dict]:
        """Get current VNC session info for a user"""
        with self.session_lock:
            session = self.user_sessions.get(user_email)
            if session and self._is_session_active(session):
                return session
            return None
    
    def get_user_vnc_status(self, user_email: str) -> Dict:
        """Get VNC status for a user"""
        session = self.get_user_vnc_session(user_email)
        
        if not session:
            return {
                'has_active_session': False,
                'user_email': user_email,
                'message': 'No active VNC session'
            }
        
        return {
            'has_active_session': True,
            'user_email': user_email,
            'display': session.get('display'),
            'vnc_port': session.get('vnc_port'),
            'novnc_port': session.get('novnc_port'),
            'novnc_url': session.get('novnc_url'),
            'created_at': session.get('created_at'),
            'status': session.get('status')
        }
    
    def _is_session_active(self, session: Dict) -> bool:
        """Check if a session is still active"""
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
        """Cleanup processes using a specific port"""
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
                        logger.info(f"[VNC_LIFECYCLE] ✓ Killed process {pid} on port {port}")
                    except (ValueError, ProcessLookupError):
                        pass
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"[VNC_LIFECYCLE] Could not cleanup port {port}: {e}")
    
    def cleanup_all_user_sessions(self, user_email: str) -> bool:
        """Force cleanup all sessions for a user (even old ones)"""
        return self.cleanup_user_vnc_session(user_email)


vnc_lifecycle_manager = VNCLifecycleManager()
