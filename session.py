"""
Session management for HourBoostr
Based on Session.cs - manages multiple bot accounts
"""
import sys
import threading
import time
from typing import List, Optional

from config import Settings
from bot import Bot, BotState
from logger import Logger
from settings_manager import get_settings


class Session:
    """Manages multiple bot accounts"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.active_bots: List[Bot] = []
        self.running = False
        self.status_thread: Optional[threading.Thread] = None
        
        # Check for updates
        if settings.check_for_updates:
            self._check_updates()
    
    def _check_updates(self):
        """Check if update is available"""
        # Simplified - would fetch from VERSION_FILE
        pass
    
    def start(self):
        """Start all bots"""
        self.running = True
        
        print("Starting bots...")
        
        # Start each account as a bot
        for account in self.settings.accounts:
            if account.ignore_account:
                print(f"{account.details.username} has been ignored.")
                continue
            
            bot = Bot(account)
            bot.start()
            self.active_bots.append(bot)
            
            # Wait for bot to log in before starting next bot
            while bot.state == BotState.LOGGED_OUT:
                time.sleep(0.1)
        
        # Print banner
        self._print_banner()
        
        # Start status thread
        self.status_thread = threading.Thread(target=self._status_loop, daemon=True)
        self.status_thread.start()
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop()
    
    def _print_banner(self):
        """Print ASCII banner"""
        print("\n" + "=" * 45)
        print("   _____             _               _       ")
        print("  |  |  |___ _ _ ___| |_ ___ ___ ___| |_ ___ ")
        print("  |     | . | | |  _| . | . | . |_ -|  _|  _|")
        print("  |__|__|___|___|_| |___|___|___|___|_| |_|  ")
        print("=" * 45)
        print(f"  Source: https://github.com/Ezzpify/HourBoostr")
        print(f"  Version: 1.0.0 (Python)")
        print("\n  ----------------------------------------")
        print(f"\n  Loaded {len(self.active_bots)} accounts\n\n  Account list:")
        
        for bot in self.active_bots:
            print(f"      {bot.account_settings.details.username} | {len(bot.account_settings.games)} Games")
        
        print("\n\n  Log:")
        print("  ----------------------------------------\n")
    
    def _status_loop(self):
        """Update console title with uptime"""
        start_time = time.time()
        
        # Import here to avoid circular import
        from endpoints import CONSOLE_TITLE
        
        while self.running:
            elapsed = int(time.time() - start_time)
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            seconds = elapsed % 60
            
            title = f"{CONSOLE_TITLE} | Online for: {hours}h {minutes}m {seconds}s"
            
            # Set console title (works on Linux/Windows)
            try:
                import sys
                if sys.platform == 'win32':
                    import ctypes
                    ctypes.windll.kernel32.SetConsoleTitleW(title)
                else:
                    sys.stdout.write(f"\033]0;{title}\007")
                    sys.stdout.flush()
            except:
                pass
            
            time.sleep(0.5)
    
    def stop(self):
        """Stop all bots"""
        self.running = False
        
        for bot in self.active_bots:
            bot.stop()
        
        print("All bots stopped.")