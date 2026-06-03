"""
Main GUI Window for HourBoostr
Using PyQt6
"""
import sys
import os
import json
import re
import urllib.request
import urllib.parse
from typing import Optional
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFormLayout, QLineEdit, QSpinBox, QCheckBox, QTextEdit,
    QMessageBox, QDialog, QDialogButtonBox, QTabWidget, QListWidget,
    QListWidgetItem, QProgressBar, QStatusBar, QMenuBar, QMenu,
    QFrame, QSplitter, QComboBox, QSystemTrayIcon, QProgressDialog,
    QInputDialog, QToolButton
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QAction, QIcon, QColor, QFont, QPixmap, QPainter, QBrush

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Settings, AccountSettings, AccountDetails
from settings_manager import get_settings, save_settings
from endpoints import SETTINGS_FILE_PATH, LOG_FOLDER_PATH


class BotWorker(QThread):
    """Worker thread for running a bot with real Steam connection"""
    log_signal = pyqtSignal(str, str)  # account_name, message
    status_signal = pyqtSignal(str, str)  # account_name, status
    error_signal = pyqtSignal(str, str)  # account_name, error
    auth_signal = pyqtSignal(str, str)  # account_name, auth_type (email/2fa)
    success_signal = pyqtSignal(str)  # account_name
    
    def __init__(self, account_settings: AccountSettings):
        super().__init__()
        self.account_settings = account_settings
        self._running = False
        self.steam = None
        self._pending_auth_code = None
        self._pending_auth_type = None
    
    def run(self):
        """Run the bot with real Steam client"""
        self._running = True
        
        from steam_client import SteamConnection, create_sentry_path
        import time
        
        username = self.account_settings.details.username
        self.status_signal.emit(username, "Connecting...")
        self.log_signal.emit(username, "Initializing Steam client...")
        
        # Create sentry path
        sentry_path = create_sentry_path(username)
        
        # Initialize Steam connection with ValvePython library
        self.steam = SteamConnection(
            username=username,
            password=self.account_settings.details.password,
            login_key=self.account_settings.details.login_key,
            games=self.account_settings.games,
            sentry_path=sentry_path
        )
        
        # Set up callbacks
        self.steam.set_callback('log', self._on_bot_log)
        self.steam.set_callback('logged_on', self._on_logged_on)
        self.steam.set_callback('error', self._on_error)
        self.steam.set_callback('auth_needed', self._on_auth_needed)
        self.steam.set_callback('login_key', self._on_login_key)
        
        # Start connection
        self.steam.connect()
        
        # Run callbacks in loop (use gevent.sleep to let hub process I/O)
        while self._running and self.steam.is_running:
            # Process pending auth code (set from main thread via submit_auth_code)
            self._process_pending_auth()
            self.steam.client.sleep(0.5)
        
        if self._running:
            self.status_signal.emit(username, "Running")
        else:
            self.status_signal.emit(username, "Stopped")
    
    def _on_logged_on(self, *args):
        """Handle successful login"""
        import time
        username = self.account_settings.details.username
        self.log_signal.emit(username, "✓ Logged in to Steam!")
        self.status_signal.emit(username, "Running")
        self.success_signal.emit(username)
        
        # Verify session with a small delay
        time.sleep(1)
        try:
            if self.steam.client.web.verify_cookies():
                self.log_signal.emit(username, "Session verified ✓")
            else:
                self.log_signal.emit(username, "Session needs refresh")
        except Exception as e:
            self.log_signal.emit(username, f"Session check: {e}")
    
    def _on_login_key(self, login_key: str):
        """Handle login key received"""
        username = self.account_settings.details.username
        self.account_settings.details.login_key = login_key
    
    def _on_error(self, error):
        """Handle error"""
        username = self.account_settings.details.username
        self.error_signal.emit(username, error)
        self.status_signal.emit(username, "Error")
    
    def _on_auth_needed(self, auth_type: str, *args):
        """Handle SteamGuard authentication needed"""
        username = self.account_settings.details.username
        self.auth_signal.emit(username, auth_type)
    
    def _on_bot_log(self, message: str):
        """Handle log messages from steam_client"""
        username = self.account_settings.details.username
        self.log_signal.emit(username, message)
    
    def submit_auth_code(self, code: str, auth_type: str):
        """Submit SteamGuard code (called from main thread)"""
        self._pending_auth_code = code
        self._pending_auth_type = auth_type
    
    def _process_pending_auth(self):
        """Process pending auth code (called from BotWorker thread loop)"""
        code = self._pending_auth_code
        auth_type = self._pending_auth_type
        if code and auth_type:
            self._pending_auth_code = None
            self._pending_auth_type = None
            if auth_type == 'email':
                self.steam.submit_email_code(code)
            elif auth_type == '2fa':
                self.steam.submit_twofactor_code(code)
    
    def stop(self):
        """Stop the bot"""
        self._running = False
        if self.steam:
            self.steam.stop()
        self.status_signal.emit(self.account_settings.details.username, "Stopped")


class AccountDialog(QDialog):
    """Dialog for adding/editing an account"""
    
    def __init__(self, account: Optional[AccountSettings] = None, parent=None):
        super().__init__(parent)
        self.account = account or AccountSettings()
        self.setup_ui()
    
    def setup_ui(self):
        self.setWindowTitle("Account Settings" if self.account.details.username else "Add Account")
        self.setMinimumWidth(400)
        
        layout = QFormLayout(self)
        
        # Username
        self.username_edit = QLineEdit()
        self.username_edit.setText(self.account.details.username)
        layout.addRow("Username:", self.username_edit)
        
        # Password (only for new accounts)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setText(self.account.details.password)
        layout.addRow("Password:", self.password_edit)
        
        # Games
        games_layout = QHBoxLayout()
        self.games_edit = QLineEdit()
        self.games_edit.setText(", ".join(map(str, self.account.games)))
        self.games_edit.setPlaceholderText("730, 10, 440  (comma or space separated)")
        games_layout.addWidget(self.games_edit)
        import_btn = QPushButton("📦 Import")
        import_btn.setToolTip("Import games from Steam library")
        import_btn.clicked.connect(self._import_games)
        games_layout.addWidget(import_btn)
        layout.addRow("Games (App IDs):", games_layout)
        
        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()
        
        self.online_check = QCheckBox("Show Online Status")
        self.online_check.setChecked(self.account.show_online_status)
        options_layout.addWidget(self.online_check)
        
        self.community_check = QCheckBox("Connect to Steam Community")
        self.community_check.setChecked(self.account.connect_to_steam_community)
        options_layout.addWidget(self.community_check)
        
        self.restart_check = QCheckBox("Restart Games Every 3 Hours")
        self.restart_check.setChecked(self.account.restart_games_every_three_hours)
        options_layout.addWidget(self.restart_check)
        
        self.group_check = QCheckBox("Join Steam Group")
        self.group_check.setChecked(self.account.join_steam_group)
        options_layout.addWidget(self.group_check)
        
        self.ignore_check = QCheckBox("Ignore Account")
        self.ignore_check.setChecked(self.account.ignore_account)
        options_layout.addWidget(self.ignore_check)
        
        options_group.setLayout(options_layout)
        layout.addRow(options_group)
        
        # Chat Response
        self.chat_edit = QLineEdit()
        self.chat_edit.setText(self.account.chat_response)
        layout.addRow("Chat Response:", self.chat_edit)
        
        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
    
    def get_account(self) -> AccountSettings:
        """Get the account settings from the dialog"""
        self.account.details.username = self.username_edit.text()
        self.account.details.password = self.password_edit.text()
        
        # Parse games: comma, space, or mixed
        games_text = self.games_edit.text()
        self.account.games = list(dict.fromkeys(
            int(g) for g in re.split(r'[,\s]+', games_text.strip()) if g.isdigit()
        ))
        
        # Options
        self.account.show_online_status = self.online_check.isChecked()
        self.account.connect_to_steam_community = self.community_check.isChecked()
        self.account.restart_games_every_three_hours = self.restart_check.isChecked()
        self.account.join_steam_group = self.group_check.isChecked()
        self.account.ignore_account = self.ignore_check.isChecked()
        self.account.chat_response = self.chat_edit.text()
        
        return self.account
    
    def _import_games(self):
        """Import games from Steam library via Web API"""
        from endpoints import STEAM_RESOLVE_VANITY, STEAM_GET_OWNED_GAMES
        
        api_key, ok = QInputDialog.getText(
            self, "Steam Web API Key",
            "Paste your Steam Web API key:\n(Get one at https://steamcommunity.com/dev/apikey)",
            text=self._get_api_key()
        )
        if not ok or not api_key.strip():
            return
        api_key = api_key.strip()
        
        profile_url, ok = QInputDialog.getText(
            self, "Steam Profile",
            "Paste your Steam profile URL or SteamID64:\n"
            "Examples:\n"
            "  https://steamcommunity.com/id/yourname\n"
            "  https://steamcommunity.com/profiles/7656119...\n"
            "  76561197960287930"
        )
        if not ok or not profile_url.strip():
            return
        
        try:
            steamid = self._resolve_steamid(profile_url.strip(), api_key)
            if not steamid:
                QMessageBox.warning(self, "Error", "Could not resolve Steam ID from that URL")
                return
            
            games = self._fetch_owned_games(steamid, api_key)
            if not games:
                QMessageBox.information(self, "No Games", "No games found or library is private")
                return
            
            self._show_game_picker(games)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import games:\n{e}")
    
    def _get_api_key(self):
        """Get Steam API key from parent MainWindow settings"""
        parent = self.parent()
        if parent and hasattr(parent, 'settings') and parent.settings:
            return parent.settings.steam_api_key
        return ""
    
    def _resolve_steamid(self, input_str: str, api_key: str) -> Optional[str]:
        """Resolve a profile URL or raw SteamID to steamID64"""
        # Already a steamID64 (17 digits)
        m = re.match(r'^(\d{17})$', input_str)
        if m:
            return m.group(1)
        
        # https://steamcommunity.com/profiles/76561197960287930
        m = re.search(r'steamcommunity\.com/profiles/(\d{17})', input_str)
        if m:
            return m.group(1)
        
        # https://steamcommunity.com/id/customname
        m = re.search(r'steamcommunity\.com/id/([a-zA-Z0-9_-]+)', input_str)
        if m:
            vanity = m.group(1)
            url = f"{STEAM_RESOLVE_VANITY}?key={api_key}&vanityurl={vanity}"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            result = data.get('response', {})
            if result.get('success') == 1:
                return result.get('steamid')
            return None
        
        return None
    
    def _fetch_owned_games(self, steamid: str, api_key: str) -> list:
        """Fetch owned games from Steam library"""
        url = f"{STEAM_GET_OWNED_GAMES}?key={api_key}&steamid={steamid}&include_appinfo=true&format=json"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        games = data.get('response', {}).get('games', [])
        return sorted(games, key=lambda g: g.get('name', '').lower())
    
    def _show_game_picker(self, games: list):
        """Show dialog to select games to import"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Select Games to Import")
        dialog.setMinimumSize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        search_edit = QLineEdit()
        search_edit.setPlaceholderText("Search games...")
        layout.addWidget(search_edit)
        
        list_widget = QListWidget()
        all_checkboxes = []
        for game in games:
            appid = game.get('appid')
            name = game.get('name', f'Unknown ({appid})')
            playtime = game.get('playtime_forever', 0)
            hours = round(playtime / 60, 1)
            item = QListWidgetItem(f"[{appid}] {name}  ({hours}h)")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, appid)
            all_checkboxes.append(item)
            list_widget.addItem(item)
        
        layout.addWidget(list_widget)
        
        # Filter
        def on_search(text):
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                item.setHidden(text.lower() not in item.text().lower() if text else False)
        search_edit.textChanged.connect(on_search)
        
        # Buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        def select_all():
            for item in all_checkboxes:
                item.setCheckState(Qt.CheckState.Checked)
        select_all_btn.clicked.connect(select_all)
        btn_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("Deselect All")
        def deselect_all():
            for item in all_checkboxes:
                item.setCheckState(Qt.CheckState.Unchecked)
        deselect_all_btn.clicked.connect(deselect_all)
        btn_layout.addWidget(deselect_all_btn)
        
        btn_layout.addStretch()
        
        ok_btn = QPushButton("Import Selected")
        btn_layout.addWidget(ok_btn)
        
        cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        result_games = []
        def accept():
            nonlocal result_games
            for item in all_checkboxes:
                if item.checkState() == Qt.CheckState.Checked:
                    result_games.append(item.data(Qt.ItemDataRole.UserRole))
            dialog.accept()
        ok_btn.clicked.connect(accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        if dialog.exec() == QDialog.DialogCode.Accepted and result_games:
            current = set(self.account.games)
            merged = list(current | set(result_games))
            self.games_edit.setText(", ".join(map(str, sorted(merged))))
            
            # Save API key to parent settings
            parent = self.parent()
            if parent and hasattr(parent, 'settings') and parent.settings:
                parent.settings.steam_api_key = api_key
                from settings_manager import save_settings
                save_settings(parent.settings)


class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.settings: Optional[Settings] = None
        self.bot_workers = {}  # username -> BotWorker
        self.account_status = {}  # username -> status
        self.tray_icon: Optional[QSystemTrayIcon] = None
        
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        """Set up the user interface"""
        self.setWindowTitle("HourBoostr v1.0.0")
        self.setMinimumSize(900, 600)
        
        # Apply dark theme
        self._apply_dark_theme()
        
        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # Main layout
        main_layout = QVBoxLayout(central)
        
        # Create menu bar
        self._create_menu_bar()
        
        # Create toolbar
        toolbar = self._create_toolbar()
        main_layout.addLayout(toolbar)
        
        # Main content - splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - Account list
        left_panel = self._create_account_panel()
        splitter.addWidget(left_panel)
        
        # Right panel - Logs and details
        right_panel = self._create_details_panel()
        splitter.addWidget(right_panel)
        
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Create tray icon
        self._create_tray_icon()
        self.tray_icon.show()
    
    def _create_menu_bar(self):
        """Create the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        reload_action = QAction("Reload Settings", self)
        reload_action.triggered.connect(self.load_settings)
        file_menu.addAction(reload_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _create_toolbar(self):
        """Create the toolbar"""
        toolbar = QHBoxLayout()
        
        self.start_btn = QPushButton("▶ Start All")
        self.start_btn.clicked.connect(self.start_all_bots)
        toolbar.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("■ Stop All")
        self.stop_btn.clicked.connect(self.stop_all_bots)
        self.stop_btn.setEnabled(False)
        toolbar.addWidget(self.stop_btn)
        
        toolbar.addStretch()
        
        # Status indicator
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
        toolbar.addWidget(self.status_indicator)
        
        self.status_label = QLabel("Idle")
        toolbar.addWidget(self.status_label)
        
        return toolbar
    
    def _apply_dark_theme(self):
        """Apply dark theme to the application"""
        dark_stylesheet = """
        QMainWindow {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        QWidget {
            background-color: #1e1e1e;
            color: #e0e0e0;
        }
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #555;
            padding: 5px 15px;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #4a4a4a;
        }
        QPushButton:pressed {
            background-color: #2a2a2a;
        }
        QTableWidget {
            background-color: #252525;
            alternate-background-color: #2a2a2a;
            gridline-color: #3a3a3a;
            border: 1px solid #3a3a3a;
        }
        QTableWidget::item {
            padding: 5px;
        }
        QTableWidget::item:selected {
            background-color: #0d47a1;
        }
        QHeaderView::section {
            background-color: #2a2a2a;
            color: #e0e0e0;
            padding: 5px;
            border: 1px solid #3a3a3a;
        }
        QTabWidget::pane {
            border: 1px solid #3a3a3a;
            background-color: #252525;
        }
        QTabBar::tab {
            background-color: #2a2a2a;
            color: #a0a0a0;
            padding: 8px 15px;
            border: 1px solid #3a3a3a;
        }
        QTabBar::tab:selected {
            background-color: #3a3a3a;
            color: #ffffff;
        }
        QTextEdit {
            background-color: #1a1a1a;
            color: #d0d0d0;
            border: 1px solid #3a3a3a;
        }
        QLineEdit {
            background-color: #2a2a2a;
            color: #e0e0e0;
            border: 1px solid #3a3a3a;
            padding: 5px;
            border-radius: 3px;
        }
        QLineEdit:focus {
            border: 1px solid #1976d2;
        }
        QCheckBox {
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 3px;
            border: 1px solid #555;
            background-color: #2a2a2a;
        }
        QCheckBox::indicator:checked {
            background-color: #1976d2;
        }
        QGroupBox {
            border: 1px solid #3a3a3a;
            border-radius: 5px;
            margin-top: 10px;
            padding-top: 10px;
        }
        QGroupBox::title {
            color: #a0a0a0;
        }
        QMenuBar {
            background-color: #252525;
            color: #e0e0e0;
        }
        QMenuBar::item:selected {
            background-color: #3a3a3a;
        }
        QMenu {
            background-color: #2a2a2a;
            color: #e0e0e0;
            border: 1px solid #3a3a3a;
        }
        QMenu::item:selected {
            background-color: #3a3a3a;
        }
        QStatusBar {
            background-color: #252525;
            color: #a0a0a0;
        }
        QLabel {
            color: #e0e0e0;
        }
        QScrollBar:vertical {
            background-color: #1a1a1a;
            width: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background-color: #4a4a4a;
            border-radius: 5px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background-color: #5a5a5a;
        }
        """
        self.setStyleSheet(dark_stylesheet)
    
    def _create_tray_icon(self):
        """Create system tray icon"""
        # Create a simple icon using QPixmap
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#1e88e5")))
        painter.drawEllipse(8, 8, 48, 48)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.drawEllipse(20, 20, 24, 24)
        painter.end()
        
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("HourBoostr")
        
        # Create tray menu
        tray_menu = QMenu(self)
        
        show_action = QAction("Show Window", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        start_action = QAction("Start All", self)
        start_action.triggered.connect(self.start_all_bots)
        tray_menu.addAction(start_action)
        
        stop_action = QAction("Stop All", self)
        stop_action.triggered.connect(self.stop_all_bots)
        tray_menu.addAction(stop_action)
        
        tray_menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
    
    def _on_tray_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
    
    def _create_account_panel(self) -> QWidget:
        """Create the account list panel"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Title
        title = QLabel("Accounts")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)
        
        # Account table
        self.account_table = QTableWidget()
        self.account_table.setColumnCount(4)
        self.account_table.setHorizontalHeaderLabels(["Username", "Games", "Status", "Online"])
        self.account_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.account_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.account_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.account_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self.account_table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_account)
        btn_layout.addWidget(add_btn)
        
        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self.edit_account)
        btn_layout.addWidget(edit_btn)
        
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self.remove_account)
        btn_layout.addWidget(remove_btn)
        
        layout.addLayout(btn_layout)
        
        return panel
    
    def _create_details_panel(self) -> QWidget:
        """Create the details panel with tabs"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # Tabs
        tabs = QTabWidget()
        
        # Log tab
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        log_layout.addWidget(self.log_text)
        
        tabs.addTab(log_tab, "Logs")
        
        # Global Settings tab
        settings_tab = QWidget()
        settings_layout = QFormLayout(settings_tab)
        
        self.updates_check = QCheckBox("Check for Updates")
        settings_layout.addRow(self.updates_check)
        
        self.tray_check = QCheckBox("Hide to Tray")
        settings_layout.addRow(self.tray_check)
        
        save_settings_btn = QPushButton("Save Settings")
        save_settings_btn.clicked.connect(self.save_global_settings)
        settings_layout.addRow(save_settings_btn)
        
        tabs.addTab(settings_tab, "Global Settings")
        
        # Account Details tab
        self.details_tab = QWidget()
        self.details_layout = QFormLayout(self.details_tab)
        
        self.details_layout.addRow(QLabel("Select an account to view details"))
        
        tabs.addTab(self.details_tab, "Account Details")
        
        layout.addWidget(tabs)
        
        return panel
    
    def load_settings(self):
        """Load settings from file"""
        self.settings = get_settings()
        
        if self.settings is None:
            # Create default settings
            self.settings = Settings()
            save_settings(self.settings)
            self.log_message("System", "Created default settings file")
        
        # Update UI
        self._populate_account_table()
        self._update_global_settings()
        
        self.log_message("System", f"Loaded {len(self.settings.accounts)} accounts")
        self.status_bar.showMessage(f"Loaded {len(self.settings.accounts)} accounts")
    
    def _populate_account_table(self):
        """Populate the account table"""
        self.account_table.setRowCount(0)
        
        for i, account in enumerate(self.settings.accounts):
            self.account_table.insertRow(i)
            
            # Username
            username_item = QTableWidgetItem(account.details.username)
            username_item.setData(Qt.ItemDataRole.UserRole, account)
            self.account_table.setItem(i, 0, username_item)
            
            # Games
            games_text = ", ".join(map(str, account.games))
            self.account_table.setItem(i, 1, QTableWidgetItem(games_text))
            
            # Status
            status_item = QTableWidgetItem("Idle")
            status_item.setForeground(QColor("gray"))
            self.account_table.setItem(i, 2, status_item)
            
            # Online indicator
            online_item = QTableWidgetItem("○")
            if account.show_online_status:
                online_item.setText("●")
                online_item.setForeground(QColor("green"))
            else:
                online_item.setForeground(QColor("gray"))
            self.account_table.setItem(i, 3, online_item)
        
        # Connect selection
        self.account_table.selectionModel().selectionChanged.connect(self.on_account_selected)
    
    def _update_global_settings(self):
        """Update global settings controls"""
        if self.settings:
            self.updates_check.setChecked(self.settings.check_for_updates)
            self.tray_check.setChecked(self.settings.hide_to_tray)
    
    def on_account_selected(self, selected, deselected):
        """Handle account selection"""
        # Clear details
        while self.details_layout.count():
            child = self.details_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Get selected account
        current_row = self.account_table.currentRow()
        if current_row < 0:
            self.details_layout.addRow(QLabel("Select an account to view details"))
            return
        
        item = self.account_table.item(current_row, 0)
        account: AccountSettings = item.data(Qt.ItemDataRole.UserRole)
        
        # Show details
        self.details_layout.addRow("Username:", QLabel(account.details.username))
        self.details_layout.addRow("Games:", QLabel(", ".join(map(str, account.games))))
        self.details_layout.addRow("Online Status:", 
            QLabel("Yes" if account.show_online_status else "No"))
        self.details_layout.addRow("Steam Community:", 
            QLabel("Yes" if account.connect_to_steam_community else "No"))
        self.details_layout.addRow("Restart Games:", 
            QLabel("Yes" if account.restart_games_every_three_hours else "No"))
        self.details_layout.addRow("Ignore:", 
            QLabel("Yes" if account.ignore_account else "No"))
        
        if account.chat_response:
            self.details_layout.addRow("Chat Response:", QLabel(account.chat_response))
    
    def add_account(self):
        """Add a new account"""
        dialog = AccountDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            account = dialog.get_account()
            self.settings.accounts.append(account)
            save_settings(self.settings)
            self._populate_account_table()
            self.log_message("System", f"Added account: {account.details.username}")
    
    def edit_account(self):
        """Edit selected account"""
        current_row = self.account_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select an account to edit")
            return
        
        item = self.account_table.item(current_row, 0)
        account: AccountSettings = item.data(Qt.ItemDataRole.UserRole)
        
        dialog = AccountDialog(account, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated_account = dialog.get_account()
            self.settings.accounts[current_row] = updated_account
            save_settings(self.settings)
            self._populate_account_table()
            self.log_message("System", f"Updated account: {updated_account.details.username}")
    
    def remove_account(self):
        """Remove selected account"""
        current_row = self.account_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "No Selection", "Please select an account to remove")
            return
        
        item = self.account_table.item(current_row, 0)
        account: AccountSettings = item.data(Qt.ItemDataRole.UserRole)
        
        reply = QMessageBox.question(
            self, "Remove Account",
            f"Remove account '{account.details.username}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            username = account.details.username
            del self.settings.accounts[current_row]
            save_settings(self.settings)
            self._populate_account_table()
            self.log_message("System", f"Removed account: {username}")
    
    def save_global_settings(self):
        """Save global settings"""
        if self.settings:
            self.settings.check_for_updates = self.updates_check.isChecked()
            self.settings.hide_to_tray = self.tray_check.isChecked()
            save_settings(self.settings)
            self.log_message("System", "Global settings saved")
            QMessageBox.information(self, "Saved", "Settings saved successfully")
    
    def start_all_bots(self):
        """Start all bots"""
        if not self.settings or not self.settings.accounts:
            QMessageBox.warning(self, "No Accounts", "No accounts configured")
            return
        
        for account in self.settings.accounts:
            if account.ignore_account:
                continue
            
            username = account.details.username
            if username in self.bot_workers:
                continue
            
            # Create and start worker
            worker = BotWorker(account)
            worker.log_signal.connect(self.on_bot_log)
            worker.status_signal.connect(self.on_bot_status)
            worker.error_signal.connect(self.on_bot_error)
            worker.auth_signal.connect(self.on_auth_needed)
            worker.success_signal.connect(self.on_success)
            
            self.bot_workers[username] = worker
            worker.start()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._update_overall_status("Running")
        self.log_message("System", "Started all bots")
    
    def stop_all_bots(self):
        """Stop all bots"""
        for worker in self.bot_workers.values():
            worker.stop()
            worker.wait()
        
        self.bot_workers.clear()
        self._update_account_statuses("Stopped")
        
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._update_overall_status("Idle")
        self.log_message("System", "Stopped all bots")
    
    def on_bot_log(self, username: str, message: str):
        """Handle bot log message"""
        self.log_message(username, message)
    
    def on_bot_status(self, username: str, status: str):
        """Handle bot status change"""
        self.account_status[username] = status
        self._update_account_status(status)
    
    def on_bot_error(self, username: str, error: str):
        """Handle bot error"""
        self.log_message(username, f"ERROR: {error}", is_error=True)
    
    def on_auth_needed(self, username: str, auth_type: str):
        """Handle SteamGuard authentication needed"""
        self.log_message(username, f"SteamGuard required: {auth_type}")
        
        if auth_type == 'email':
            self._show_auth_dialog(username, 'email')
        elif auth_type == '2fa':
            self._show_auth_dialog(username, '2fa')
    
    def _show_auth_dialog(self, username: str, auth_type: str):
        """Show dialog to input SteamGuard code"""
        # Find the worker for this account
        worker = self.bot_workers.get(username)
        if not worker:
            return
        
        # Create input dialog
        dialog = QInputDialog(self)
        dialog.setWindowTitle("SteamGuard Required")
        
        if auth_type == 'email':
            dialog.setLabelText(f"Enter SteamGuard code from email for {username}:")
            dialog.setOkButtonText("Submit")
        else:
            dialog.setLabelText(f"Enter 2FA code from mobile app for {username}:")
            dialog.setOkButtonText("Submit")
        
        dialog.setInputMode(QInputDialog.InputMode.TextInput)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            code = dialog.textValue()
            if code:
                self.log_message(username, f"Submitting {auth_type} code...")
                worker.submit_auth_code(code, auth_type)
    
    def on_success(self, username: str):
        """Handle successful login"""
        # Save login key to settings
        worker = self.bot_workers.get(username)
        if worker and worker.steam and worker.steam.login_key:
            for account in self.settings.accounts:
                if account.details.username == username:
                    account.details.login_key = worker.steam.login_key
                    save_settings(self.settings)
                    self.log_message("System", f"Saved login key for {username}")
                    break
    
    def _update_account_status(self, status: str):
        """Update status in table for current row"""
        current_row = self.account_table.currentRow()
        if current_row >= 0:
            status_item = self.account_table.item(current_row, 2)
            if status_item:
                status_item.setText(status)
                
                # Color based on status
                if status == "Running":
                    status_item.setForeground(QColor("green"))
                elif status == "Error":
                    status_item.setForeground(QColor("red"))
                else:
                    status_item.setForeground(QColor("gray"))
    
    def _update_account_statuses(self, status: str):
        """Update all account statuses"""
        for i in range(self.account_table.rowCount()):
            status_item = self.account_table.item(i, 2)
            if status_item:
                status_item.setText(status)
                if status == "Running":
                    status_item.setForeground(QColor("green"))
                else:
                    status_item.setForeground(QColor("gray"))
    
    def _update_overall_status(self, status: str):
        """Update overall status indicator"""
        if status == "Running":
            self.status_indicator.setText("●")
            self.status_indicator.setStyleSheet("color: green; font-size: 16px;")
            self.status_label.setText("Running")
        else:
            self.status_indicator.setText("●")
            self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
            self.status_label.setText("Idle")
    
    def log_message(self, source: str, message: str, is_error: bool = False):
        """Add message to log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        color = "red" if is_error else "black"
        html = f'<span style="color: gray;">[{timestamp}]</span> '
        html += f'<span style="color: blue;">{source}</span>: '
        html += f'<span style="color: {color};">{message}</span>'
        
        self.log_text.append(html)
        
        # Auto-scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def _show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self, "About HourBoostr",
            "<h3>HourBoostr v1.0.0</h3>"
            "<p>Cross-platform Steam Hour Booster</p>"
            "<p>Originally by Ezzpify</p>"
            "<p>Python port by Kiro</p>"
        )
    
    def closeEvent(self, event):
        """Handle window close"""
        # Check if hide to tray is enabled
        if self.settings and self.settings.hide_to_tray and self.tray_icon:
            # Hide to tray instead of closing
            self.hide()
            event.ignore()
            return
        
        if self.bot_workers:
            reply = QMessageBox.question(
                self, "Running Bots",
                "Bots are still running. Stop them and exit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_all_bots()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    """Main entry point for GUI"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Modern style
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()