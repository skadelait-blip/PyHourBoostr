"""
Steam client wrapper for HourBoostr
Using ValvePython steam library (like original C# SteamKit2)
"""
import os
import time
import threading
from typing import Optional, List

# Patch time.sleep and socket/ssl to work with gevent (so IO doesn't block the hub)
import gevent.monkey
gevent.monkey.patch_time()
gevent.monkey.patch_socket()
gevent.monkey.patch_ssl()

from steam.client import SteamClient
from steam.enums import EResult
from steam.exceptions import SteamError

# Monkey-patch: Fix CMClient.__init__ not calling super().__init__
# (bug in steam 1.4.4 with eventemitter 0.2.0)
# Also provide a sync loop so callbacks fire immediately (not via asyncio)
import steam.core.cm as _cm
import steam.client as _steamclient
import collections
import gevent

class _SyncLoop:
    """Synchronous loop that executes callbacks immediately"""
    def call_soon(self, callback, *args, **context):
        callback(*args)

_original_cm_init = _cm.CMClient.__init__
def _patched_cm_init(self, protocol=_cm.CMClient.PROTOCOL_TCP):
    self._listeners = collections.defaultdict(list)
    self._once = collections.defaultdict(list)
    self._max_listeners = 10
    self._loop = _SyncLoop()
    _original_cm_init(self, protocol)
_cm.CMClient.__init__ = _patched_cm_init

# Add missing methods removed in eventemitter 0.2.0
def _wait_event(self, event, timeout=None, raises=False):
    """Wait for an event to fire using gevent"""
    e = gevent.event.AsyncResult()
    def handler(*args):
        e.set(args)
    self.once(event, handler)
    try:
        return e.get(timeout=timeout)
    except gevent.Timeout:
        if raises:
            raise
        return None
_cm.CMClient.wait_event = _wait_event

def _count_listeners(self, event):
    """Renamed to count() in eventemitter 0.2.0"""
    return self.count(event)
_cm.CMClient.count_listeners = _count_listeners

# Patch SteamClient.login to log exact auth payload
_original_login = _steamclient.SteamClient.login
def _patched_login(self, username, password='', login_key=None, auth_code=None, two_factor_code=None, login_id=None):
    import logging
    log = logging.getLogger('SteamClient')
    log.debug("=== login() called ===")
    log.debug("username=%s password=***%s (len=%d) login_key=%s auth_code=%s two_factor_code=%s",
              username,
              password[-4:] if len(password) >= 4 else '',
              len(password),
              'set' if login_key else 'None',
              'set' if auth_code else 'None',
              'set' if two_factor_code else 'None')
    log.debug("password repr: %r", password)
    return _original_login(self, username, password, login_key, auth_code, two_factor_code, login_id)
_steamclient.SteamClient.login = _patched_login


class SteamConnection:
    """Main Steam connection handler using SteamClient"""
    
    def __init__(self, username: str, password: str, login_key: str = "", 
                 games: List[int] = None, sentry_path: str = ""):
        self.username = username.strip()
        self.login_key = login_key.strip()
        self.games = games or []
        
        # Auth codes
        self.auth_code = None
        self.twofactor_code = None
        
        # Strip password and warn if whitespace was present
        self._password_was_stripped = bool(password != password.strip())
        if self._password_was_stripped:
            print(f"[{username}] WARNING: Password had whitespace stripped (original len={len(password)}, stripped len={len(password.strip())})")
        self.password = password.strip()
        self.sentry_path = sentry_path
        
        # Create Steam client
        self.client = SteamClient()
        sentry_dir = os.path.dirname(sentry_path) if sentry_path else "."
        self.client.set_credential_location(sentry_dir)
        
        # Register event handlers once
        self.client.on(self.client.EVENT_CONNECTED, self._on_connected)
        self.client.on(self.client.EVENT_DISCONNECTED, self._on_disconnected)
        self.client.on(self.client.EVENT_LOGGED_ON, self._on_logged_on)
        self.client.on(self.client.EVENT_ERROR, self._on_error)
        self.client.on(self.client.EVENT_AUTH_CODE_REQUIRED, self._on_auth_required)
        
        self.connected = False
        self.logged_on = False
        self.is_running = False
        self._reconnect_count = 0
        self._invalid_password_count = 0
        self._start_time = 0.0
        
        # Callbacks
        self._callbacks = {
            'connected': [], 'disconnected': [], 'logged_on': [],
            'error': [], 'login_key': [], 'auth_needed': [], 'log': []
        }
        
        # Internal state tracking (not affected by SteamClient._reset_attributes)
        self._channel_secured_logged = False
        self._auth_pending = False  # True when waiting for SteamGuard code
        self._skip_auto_login = False  # True when submit_email_code/twofactor_code is handling login
    
    def set_callback(self, event: str, callback):
        if event in self._callbacks:
            self._callbacks[event].append(callback)
    
    def _trigger(self, event: str, *args):
        for cb in self._callbacks.get(event, []):
            try:
                cb(*args)
            except:
                pass
    
    def _do_login_attempt(self):
        """Single login attempt with clear auth method logging"""
        if self.login_key:
            lk_preview = self.login_key[:16] + "..." if len(self.login_key) > 16 else self.login_key
            self._trigger('log', f"Logging in using login_key (key: {lk_preview})")
        else:
            pw_status = "set" if self.password else "EMPTY"
            pw_head = self.password[:2] if self.password else "--"
            pw_tail = self.password[-2:] if len(self.password) >= 2 else "--"
            pw_hex = " ".join(f"{b:02x}" for b in self.password.encode('utf-8')[:6]) if self.password else "empty"
            pw_has_special = any(ord(c) > 127 for c in self.password)
            stripped_warn = " [STRIPPED]" if self._password_was_stripped else ""
            self._trigger('log', f"Logging in using password ({pw_status}, len={len(self.password)}, [{pw_head}...{pw_tail}], hex_start={pw_hex}, has_unicode={pw_has_special}{stripped_warn})")
            if self._password_was_stripped:
                self._trigger('log', "WARNING: Password had leading/trailing whitespace - stripped for this attempt. Fix settings.json!")
        
        self.client.login(
            username=self.username,
            password=self.password,
            login_key=self.login_key or None,
            auth_code=self.auth_code,
            two_factor_code=self.twofactor_code,
        )
    
    def connect(self, timeout=30):
        """Connect to Steam"""
        self.is_running = True
        self._start_time = time.time()
        self._reconnect_count = 0
        
        # Log sentry info
        if self.sentry_path:
            sentry_exists = os.path.exists(self.sentry_path)
            self._trigger('log', f"Sentry file: {self.sentry_path} (exists: {sentry_exists})")
        else:
            self._trigger('log', "Sentry file: not configured")
        
        self._trigger('log', "Connecting to Steam...")
        try:
            import gevent
            with gevent.Timeout(timeout, TimeoutError(f"Steam connection timed out after {timeout}s")):
                self.client.connect(retry=3)
        except TimeoutError as e:
            self._trigger('error', str(e))
            self.is_running = False
        except Exception as e:
            self._trigger('error', f"Connection error: {e}")
            self.is_running = False
    
    def _on_connected(self):
        """Connected to Steam server"""
        self._channel_secured_logged = False
        self._trigger('log', f"Connected! Logging in...")
        self._trigger('log', "Channel encryption handshake in progress...")
        
        # Listen for channel secured event for accurate state tracking
        self.client.once('channel_secured', lambda: setattr(self, '_channel_secured_logged', True))
        
        # Don't spawn auto-login greenlet if submit_email_code/twofactor_code is handling it
        if self._skip_auto_login:
            return
        
        def _do_login():
            try:
                self._do_login_attempt()
            except Exception as e:
                self._trigger('error', f"Login error: {e}")
        
        gevent.spawn(_do_login)
    
    def _on_disconnected(self):
        """Disconnected from Steam"""
        self.connected = False
        
        if self.logged_on:
            self._trigger('log', "Disconnected from Steam (was logged on)")
        elif self._channel_secured_logged:
            self._trigger('log', "Disconnected from Steam (channel was secured, login failed)")
        else:
            self._trigger('log', "Disconnected from Steam (channel not secured)")
        
        self.logged_on = False
        self._channel_secured_logged = False
        
        if self.is_running:
            if self._auth_pending:
                return  # wait for SteamGuard code, don't reconnect
            
            if self._invalid_password_count >= 3:
                self._trigger('log', "Too many invalid password errors. Stopping - check your credentials in settings.json")
                self.is_running = False
                return
            
            self._reconnect_count += 1
            self._trigger('log', f"Reconnecting in 5s (attempt #{self._reconnect_count})...")
            time.sleep(5)
            self.client.connect()
    
    def _on_logged_on(self, *args):
        """Successfully logged on"""
        elapsed = time.time() - self._start_time
        self._trigger('log', f"Logged on! SteamID: {self.client.steam_id} (took {elapsed:.1f}s)")
        self.logged_on = True
        self.connected = True
        self._reconnect_count = 0
        self._invalid_password_count = 0
        self._auth_pending = False
        
        # Extract login key from Steam if available
        if hasattr(self.client, 'login_key') and self.client.login_key:
            self.login_key = self.client.login_key
            self._trigger('login_key', self.login_key)
            self._trigger('log', "Received login key from Steam")
        
        self._trigger('logged_on')
        
        # Set games playing
        if self.games:
            self.set_games_playing(self.games)
    
    def _on_error(self, error):
        """Error occurred"""
        err_str = error.name if hasattr(error, 'name') else str(error)
        err_lower = err_str.lower()
        
        # If SteamGuard code is needed, don't auto-reconnect (wait for code)
        if err_lower in ('accountlogondenied', 'accountlogindeniedneedtwofactor', 
                          'invalidloginauthcode', 'twofactorcodemismatch'):
            self._auth_pending = True
        
        # Track invalid password errors, stop retrying after 3
        if err_lower == 'invalidpassword':
            self._invalid_password_count += 1
            self._trigger('log', f"Invalid password error #{self._invalid_password_count}")
            # Clear any stale login_key so password is used
            if self.login_key:
                self._trigger('log', "Login key expired, will retry with password")
                self.login_key = ""
        
        # Map common errors to user-friendly messages
        friendly = {
            'invalidpassword': "Invalid password - check credentials",
            'passwordunset': "Password not set for this account",
            'loggedinelsewhere': "Account logged in elsewhere",
            'invalidloginauthcode': "Invalid Steam Guard email code",
            'twofactorcodemismatch': "Invalid 2FA code",
            'accountlogondenied': "Steam Guard email code required",
            'accountlogindeniedneedtwofactor': "2FA code required",
            'cannotuseoldpassword': "Password cannot be reused",
            'servicunavailable': "Steam service unavailable, retrying...",
            'tryanothercm': "Steam CM server busy, trying another...",
        }
        
        msg = friendly.get(err_str.lower(), err_str.lower())
        self._trigger('log', f"Steam error: {msg}")
        self._trigger('error', err_str.lower())
    
    def _on_auth_required(self, is_2fa, code_mismatch=False):
        """SteamGuard required"""
        self._auth_pending = True
        if is_2fa:
            hint = " (code mismatch, try again)" if code_mismatch else ""
            self._trigger('log', f"2FA code required{hint}!")
            self._trigger('auth_needed', '2fa')
        else:
            hint = " (code mismatch, try again)" if code_mismatch else ""
            self._trigger('log', f"SteamGuard email code required{hint}!")
            self._trigger('auth_needed', 'email')
    
    def submit_email_code(self, code: str):
        """Submit SteamGuard email code"""
        self._auth_pending = False
        self._trigger('log', f"Submitting email code...")
        self.auth_code = code
        self.twofactor_code = None
        self._skip_auto_login = True
        try:
            self.client.login(
                username=self.username,
                password=self.password,
                login_key=None,
                auth_code=code
            )
        finally:
            self._skip_auto_login = False
    
    def submit_twofactor_code(self, code: str):
        """Submit 2FA code"""
        self._auth_pending = False
        self._trigger('log', f"Submitting 2FA code...")
        self.twofactor_code = code
        self.auth_code = None
        self._skip_auto_login = True
        try:
            self.client.login(
                username=self.username,
                password=self.password,
                login_key=None,
                two_factor_code=code
            )
        finally:
            self._skip_auto_login = False
    
    def set_games_playing(self, game_ids: List[int]):
        """Set games as playing"""
        self.games = game_ids
        if self.logged_on:
            try:
                self.client.games_played(game_ids)
                self._trigger('log', f"Games set to play: {game_ids}")
            except Exception as e:
                self._trigger('log', f"Error setting games: {e}")
        else:
            self._trigger('log', f"Not logged in - games not set: {game_ids}")
    
    def set_persona_state(self, state: int):
        """Set online status"""
        states = {0: "Offline", 1: "Online", 2: "Busy", 3: "Away", 4: "Snooze", 5: "LookingToTrade", 6: "LookingToPlay"}
        state_name = states.get(state, f"Unknown({state})")
        if self.logged_on:
            try:
                self.client.change_status(persona_state=state)
                self._trigger('log', f"Persona state set to: {state_name}")
            except Exception as e:
                self._trigger('log', f"Error setting persona state: {e}")
        else:
            self._trigger('log', f"Cannot set persona state - not logged in")
    
    def retry_login(self):
        """Retry login with current credentials"""
        self._trigger('log', "Retrying login...")
        def _do_login():
            try:
                self._do_login_attempt()
            except Exception as e:
                self._trigger('error', f"Login error: {e}")
        gevent.spawn(_do_login)

    def run_callbacks(self):
        """Process client callbacks - call this in a loop"""
        try:
            self.client.sleep(0)
        except Exception as e:
            self._trigger('error', f"Callback error: {e}")
    
    def stop(self):
        """Stop the client"""
        self.is_running = False
        self.logged_on = False
        try:
            self.client.logout()
        except:
            pass
        try:
            self.client.disconnect()
        except:
            pass
        self._trigger('disconnected')
        self._trigger('log', "Bot stopped")


def create_sentry_path(username: str) -> str:
    from endpoints import SENTRY_FOLDER_PATH
    os.makedirs(SENTRY_FOLDER_PATH, exist_ok=True)
    return os.path.join(SENTRY_FOLDER_PATH, f"{username}.sentry")
