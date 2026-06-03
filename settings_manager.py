"""
Settings management for HourBoostr
Based on Settings.cs
"""
import json
import os
from typing import Optional
from config import Settings, AccountSettings, AccountDetails


def get_settings() -> Optional[Settings]:
    """Read the settings for the application"""
    from endpoints import SETTINGS_FILE_PATH
    
    if not os.path.exists(SETTINGS_FILE_PATH):
        # Create default settings
        settings = Settings()
        settings.accounts = [
            AccountSettings(games=[730, 10]),
            AccountSettings(games=[730, 10]),
            AccountSettings(games=[730, 10])
        ]
        
        with open(SETTINGS_FILE_PATH, 'w') as f:
            json.dump({
                "check_for_updates": True,
                "hide_to_tray": True,
                "steam_api_key": "",
                "accounts": [
                    {"games": [730, 10]},
                    {"games": [730, 10]},
                    {"games": [730, 10]}
                ]
            }, f, indent=4)
        
        print(f"Settings file has been written at {SETTINGS_FILE_PATH}")
        print("Please close the program and edit the settings.")
        return None
    
    try:
        with open(SETTINGS_FILE_PATH, 'r') as f:
            data = json.load(f)
        
        settings = Settings()
        settings.check_for_updates = data.get('check_for_updates', True)
        settings.hide_to_tray = data.get('hide_to_tray', True)
        settings.steam_api_key = data.get('steam_api_key', '')
        
        # Parse accounts
        for acc_data in data.get('accounts', []):
            details_data = acc_data.get('details', {})
            details = AccountDetails(
                username=details_data.get('username', '').strip(),
                password=details_data.get('password', '').strip(),
                login_key=details_data.get('login_key', '').strip()
            )
            
            account = AccountSettings(
                details=details,
                show_online_status=acc_data.get('show_online_status', True),
                connect_to_steam_community=acc_data.get('connect_to_steam_community', True),
                restart_games_every_three_hours=acc_data.get('restart_games_every_three_hours', True),
                join_steam_group=acc_data.get('join_steam_group', True),
                ignore_account=acc_data.get('ignore_account', False),
                chat_response=acc_data.get('chat_response', ''),
                games=acc_data.get('games', [])
            )
            settings.accounts.append(account)
        
        # Filter out accounts with empty usernames and remove duplicates
        settings.accounts = [a for a in settings.accounts if a.details.username.strip()]
        
        # Remove duplicates by username
        seen = set()
        unique_accounts = []
        for acc in settings.accounts:
            if acc.details.username not in seen:
                seen.add(acc.details.username)
                unique_accounts.append(acc)
        settings.accounts = unique_accounts
        
        return settings
        
    except Exception as e:
        print(f"Error reading settings file: {e}")
        return None


def save_settings(settings: Settings) -> bool:
    """Writes settings to file"""
    from endpoints import SETTINGS_FILE_PATH
    
    data = {
        "check_for_updates": settings.check_for_updates,
        "hide_to_tray": settings.hide_to_tray,
        "steam_api_key": settings.steam_api_key,
        "accounts": []
    }
    
    for acc in settings.accounts:
        acc_data = {
            "details": {
                "username": acc.details.username.strip(),
                "password": acc.details.password.strip(),
                "login_key": acc.details.login_key.strip()
            },
            "show_online_status": acc.show_online_status,
            "connect_to_steam_community": acc.connect_to_steam_community,
            "restart_games_every_three_hours": acc.restart_games_every_three_hours,
            "join_steam_group": acc.join_steam_group,
            "ignore_account": acc.ignore_account,
            "chat_response": acc.chat_response,
            "games": acc.games
        }
        data["accounts"].append(acc_data)
    
    with open(SETTINGS_FILE_PATH, 'w') as f:
        json.dump(data, f, indent=4)
    
    return True


def update_account_login_key(username: str, login_key: str):
    """Update login key for a specific account"""
    settings = get_settings()
    if settings:
        for acc in settings.accounts:
            if acc.details.username == username:
                acc.details.login_key = login_key
                save_settings(settings)
                break