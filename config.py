"""
Config data classes for HourBoostr
Based on Config.cs
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AccountDetails:
    """Holds account login information"""
    username: str = ""
    password: str = ""
    login_key: str = ""  # Saving this means we don't have to enter code twice


@dataclass
class AccountSettings:
    """Class for account settings"""
    details: AccountDetails = field(default_factory=AccountDetails)
    
    # Options
    show_online_status: bool = True
    connect_to_steam_community: bool = True
    restart_games_every_three_hours: bool = True
    join_steam_group: bool = True
    ignore_account: bool = False
    chat_response: str = ""
    
    # List of games we should set as playing
    games: List[int] = field(default_factory=list)


@dataclass
class Settings:
    """Application settings"""
    check_for_updates: bool = True
    hide_to_tray: bool = True
    steam_api_key: str = ""
    accounts: List[AccountSettings] = field(default_factory=list)