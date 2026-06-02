"""
Constants and endpoints for HourBoostr
Based on EndPoint.cs
"""
import os

# File paths
SETTINGS_FILE_PATH = "Settings.json"
GLOBAL_SETTINGS_FILE_PATH = "GlobalDB.hb"
SENTRY_FOLDER_PATH = "Sentryfiles"
LOG_FOLDER_PATH = "Logs"

# URLs
STEAM_GROUP_URL = "http://steamcommunity.com/gid/103582791455389825"
VERSION_FILE = "https://raw.githubusercontent.com/Ezzpify/HourBoostr/master/version.txt"

# App info - version will be read from git or package
VERSION = "1.0.0"
CONSOLE_TITLE = f"HourBoostr v{VERSION}"

# Ensure directories exist
os.makedirs(SENTRY_FOLDER_PATH, exist_ok=True)
os.makedirs(LOG_FOLDER_PATH, exist_ok=True)