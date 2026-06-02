"""
Bot class for HourBoostr
Based on Bot.cs
"""
import time
import threading
import getpass
import random
import traceback
from typing import List, Optional, Dict
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta

from config import AccountSettings
from steam_client import SteamConnection, create_sentry_path
from logger import Logger, LogLevel
from endpoints import LOG_FOLDER_PATH
from settings_manager import update_account_login_key


class BotState(Enum):
    """Bot state enumeration"""
    LOGGED_OUT = "logged_out"
    LOGGED_IN = "logged_in"
    LOGGED_IN_WEB = "logged_in_web"


@dataclass
class ChatMessageData:
    """Data for chat message"""
    account_id: int
    date_received: datetime


class Bot:
    """Main bot class for a single Steam account"""
    
    def __init__(self, account_settings: AccountSettings):
        self.account_settings = account_settings
        
        # Get password if not set
        if not account_settings.details.password and not account_settings.details.login_key:
            print(f"Enter password for account '{account_settings.details.username}'")
            account_settings.details.password = getpass.getpass("Password: ")
        
        # Create sentry path
        sentry_path = create_sentry_path(account_settings.details.username)
        
        # Initialize Steam connection
        self.steam = SteamConnection(
            username=account_settings.details.username,
            password=account_settings.details.password,
            login_key=account_settings.details.login_key,
            games=account_settings.games,
            sentry_path=sentry_path
        )
        
        # State tracking
        self.state = BotState.LOGGED_OUT
        self.has_connected_once = False
        self.playing_blocked = False
        self.is_running = False
        self.disconnected_counter = 0
        self.max_disconnects_before_pause = 5
        
        # Chat blocklist
        self.chat_blocklist: List[ChatMessageData] = []
        
        # Loggers
        self.log = Logger(
            account_settings.details.username,
            f"{LOG_FOLDER_PATH}/{account_settings.details.username}.txt"
        )
        self.log_chat = Logger(
            f"{account_settings.details.username} Chat",
            f"{LOG_FOLDER_PATH}/{account_settings.details.username} steam chat.txt"
        )
        
        # Timers
        self.restart_games_timer: Optional[threading.Timer] = None
        self.community_timer: Optional[threading.Timer] = None
        
        # Set up callbacks
        self._setup_callbacks()
    
    def _setup_callbacks(self):
        """Set up Steam connection callbacks"""
        # Bridge all steam_client log messages to our Logger
        self.steam.set_callback('log', self._on_steam_log)
        self.steam.set_callback('connected', self._on_connected)
        self.steam.set_callback('disconnected', self._on_disconnected)
        self.steam.set_callback('logged_on', self._on_logged_on)
        self.steam.set_callback('logged_off', self._on_logged_off)
        self.steam.set_callback('login_key', self._on_login_key)
        self.steam.set_callback('error', self._on_error)
        self.steam.set_callback('auth_needed', self._on_auth_needed)
    
    def _on_steam_log(self, message: str):
        """Bridge steam_client log messages to our Logger"""
        self.log.info(message)
    
    def start(self):
        """Start the bot"""
        self.is_running = True
        self.steam.connect()
    
    def _on_connected(self):
        """Handle connected event"""
        pass  # steam_client logs this already
    
    def _on_disconnected(self):
        """Handle disconnected event"""
        self.disconnected_counter += 1
        self.state = BotState.LOGGED_OUT
        
        if self.is_running and self.disconnected_counter >= self.max_disconnects_before_pause:
            self.log.warn(f"Too many disconnects ({self.disconnected_counter}). Sleeping for 15 minutes...")
            time.sleep(15 * 60)
            self.disconnected_counter = 0
    
    def _on_logged_off(self):
        """Handle logged off event"""
        self.state = BotState.LOGGED_OUT
        self.log.warn("Logged off from Steam")
    
    def _on_logged_on(self, *args):
        """Handle logged on event"""
        self.log.success("Successfully logged in!")
        self.state = BotState.LOGGED_IN
        self.has_connected_once = True
        self.disconnected_counter = 0
        self.playing_blocked = False
        
        # Start games
        self._set_games_playing(True)
        self._log_on_success()
    
    def _on_auth_needed(self, auth_type: str):
        """Handle authentication needed (SteamGuard/2FA)"""
        if auth_type == 'email':
            self.log.text("Enter the SteamGuard code from your email:")
            code = input("SteamGuard code: ")
            self.steam.submit_email_code(code)
        elif auth_type == '2fa':
            self.log.text("Enter your two-way authentication code:")
            code = input("2FA code: ")
            self.steam.submit_twofactor_code(code)
    
    def _on_login_key(self, login_key: str):
        """Handle login key received"""
        self.log.info("Received LoginKey from Steam")
        self.account_settings.details.login_key = login_key
        update_account_login_key(self.account_settings.details.username, login_key)
        
        if self.account_settings.connect_to_steam_community:
            self.log.info("Authenticating user...")
            self._user_web_logon()
    
    def _on_error(self, error):
        """Handle error event"""
        err = str(error).lower()
        
        if err == 'invalidpassword':
            self.log.warn("The password was not accepted.")
            if self.account_settings.details.login_key:
                self.log.info("Login key expired or invalid - clearing it to use password")
                self.account_settings.details.login_key = ""
                update_account_login_key(self.account_settings.details.username, "")
            if not self.account_settings.details.password.strip():
                self.log.text("Re-enter your Steam password:")
                self.account_settings.details.password = getpass.getpass("Password: ").strip()
            self.steam.password = self.account_settings.details.password.strip()
            self.steam.login_key = ""  # force password use
            self.steam.retry_login()
        elif err == 'passwordunset':
            self.log.warn("Password not set for this account.")
        elif err == 'loggedinelsewhere':
            self.log.warn("Account logged in elsewhere.")
        elif err == 'invalidloginauthcode':
            self.log.warn("Invalid Steam Guard code. Will retry.")
        elif err == 'twofactorcodemismatch':
            self.log.warn("Invalid 2FA code. Will retry.")
        elif err == 'tryanothercm':
            pass  # steam_client handles this
        else:
            self.log.warn(f"Error: {err}")
    
    def _log_on_success(self):
        """Called when bot is fully logged on"""
        # Set up restart games timer if enabled
        if self.account_settings.restart_games_every_three_hours:
            extra_time = random.randint(20, 60)
            restart_interval = 180 + extra_time
            self._start_restart_games_timer(restart_interval * 60)  # Convert to seconds
    
    def _start_restart_games_timer(self, interval_seconds: int):
        """Start timer to restart games periodically"""
        if self.restart_games_timer:
            self.restart_games_timer.cancel()
        
        self.restart_games_timer = threading.Timer(interval_seconds, self._restart_games)
        self.restart_games_timer.daemon = True
        self.restart_games_timer.start()
        self.log.info(f"Games restart timer: {interval_seconds // 60} minutes")
    
    def _restart_games(self):
        """Restart games (stop for 5 min, then start again)"""
        self._set_games_playing(False)
        self.log.info("Stopping games for 5 minutes...")
        time.sleep(5 * 60)  # 5 minutes
        self.log.info("Starting games again!")
        self._set_games_playing(True)
        
        # Reschedule
        if self.account_settings.restart_games_every_three_hours:
            extra_time = random.randint(20, 60)
            interval = (180 + extra_time) * 60
            self._start_restart_games_timer(interval)
    
    def _set_games_playing(self, state: bool):
        """Set the game currently playing"""
        game_list = self.account_settings.games if state else []
        
        if not self.playing_blocked:
            self.steam.set_games_playing(game_list)
        
        action = "Playing" if state else "Stopped"
        self.log.info(f"{action} {len(game_list)} games.")
    
    def _user_web_logon(self):
        """Authenticate user to Steam Community"""
        try:
            if self.steam.web.authenticate(
                self.steam.data.unique_id,
                self.steam.data.steam_id,
                self.steam.login_key if hasattr(self.steam, 'login_key') else ""
            ):
                self.log.success("User authenticated!")
                self.state = BotState.LOGGED_IN_WEB
                
                # Set online status if enabled
                if self.account_settings.show_online_status:
                    self.steam.set_persona_state(1)  # Online
                
                # Join Steam group if enabled
                if self.account_settings.join_steam_group:
                    pass
                
                # Start community connection timer
                self._start_community_timer()
        except Exception as e:
            self.log.error(f"Error on UserWebLogon: {e}")
            self.log.error(traceback.format_exc())
    
    def _start_community_timer(self):
        """Start timer to verify community connection"""
        if self.community_timer:
            self.community_timer.cancel()
        
        interval = 15 * 60
        self.community_timer = threading.Timer(interval, self._verify_community_connection)
        self.community_timer.daemon = True
        self.community_timer.start()
        self.log.info(f"Community timer: {interval // 60} minutes")
    
    def _verify_community_connection(self):
        """Verify and refresh community connection"""
        if self.state != BotState.LOGGED_IN_WEB:
            self.community_timer.cancel()
            return
        
        if not self.steam.web.verify_cookies():
            self.log.warn("Cookies were out of date, requesting new user nonce...")
            self.state = BotState.LOGGED_IN
    
    def stop(self):
        """Stop the bot"""
        self.is_running = False
        if self.restart_games_timer:
            self.restart_games_timer.cancel()
        if self.community_timer:
            self.community_timer.cancel()
        self.steam.stop()
        self.log.warn("Bot has stopped running!")
