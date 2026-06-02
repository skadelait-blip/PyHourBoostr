#!/usr/bin/env python3
"""
HourBoostr - Steam Hour Booster
Cross-platform Python implementation

Main entry point
Supports both CLI and GUI modes
"""
import os
import sys
import argparse

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Settings
from session import Session
from settings_manager import get_settings
from endpoints import (
    GLOBAL_SETTINGS_FILE_PATH, 
    SENTRY_FOLDER_PATH, 
    LOG_FOLDER_PATH, 
    CONSOLE_TITLE
)


class GlobalDB:
    """Global database for cell ID storage"""
    def __init__(self):
        self.cell_id = 0
    
    @staticmethod
    def load(path: str):
        """Load global database"""
        if not os.path.exists(path):
            return GlobalDB()
        
        try:
            db = GlobalDB()
            db.cell_id = 66  # Default cell ID
            return db
        except Exception as e:
            print(f"Error loading global db at {path}: {e}")
            return None


def run_cli():
    """Run in CLI mode"""
    # Set console title (Windows)
    try:
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.kernel32.SetConsoleTitleW(CONSOLE_TITLE)
    except:
        pass
    
    # Create required directories
    os.makedirs(SENTRY_FOLDER_PATH, exist_ok=True)
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)
    
    # Load global database
    global_db = GlobalDB.load(GLOBAL_SETTINGS_FILE_PATH)
    if global_db is None:
        print(f"Error loading global db at {GLOBAL_SETTINGS_FILE_PATH}")
    
    if global_db and global_db.cell_id == 0:
        global_db.cell_id = 66
    
    # Load settings
    settings = get_settings()
    
    if settings is not None:
        if len(settings.accounts) > 0:
            session = Session(settings)
            session.start()
        else:
            print("No accounts were loaded from settings. Press Enter to exit.")
            try:
                input()
            except:
                pass
    else:
        print("Failed to load settings. Press Enter to exit.")
        try:
            input()
        except:
            pass


def run_gui():
    """Run in GUI mode"""
    from gui import main as gui_main
    gui_main()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="HourBoostr - Steam Hour Booster")
    parser.add_argument(
        '--cli', 
        action='store_true',
        help='Run in CLI mode instead of GUI'
    )
    parser.add_argument(
        '--gui',
        action='store_true', 
        help='Run in GUI mode (default)'
    )
    
    args = parser.parse_args()
    
    if args.cli:
        run_cli()
    else:
        # Default to GUI
        run_gui()


if __name__ == "__main__":
    main()