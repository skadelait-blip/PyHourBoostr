#!/usr/bin/env python3
"""
HourBoostr GUI Launcher
Run with: python run_gui.py
"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui import main

if __name__ == "__main__":
    main()