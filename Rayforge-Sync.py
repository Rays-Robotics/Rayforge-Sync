#!/usr/bin/env python3

"""
Rayforge Sync
A cross-platform game save synchronization tool by Rays Robotics.
This script uses PySide6 for the GUI and QSettings for persistent,
cross-platform configuration.
"""

import sys
import os
import json
import pathlib
import uuid
import shutil
import datetime
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import Qt, QSettings, QStandardPaths
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QWidget, QMessageBox, QFileDialog,
    QListWidget, QListWidgetItem, QLineEdit, QDialogButtonBox,
    QFormLayout, QCheckBox
)

# --- Configuration Constants ---
# These are used by QSettings to automatically store config in the
# correct OS-specific location (Registry, .plist, .config)
ORGANIZATION_NAME = "RaysRobotics"
APPLICATION_NAME = "RayforgeSync"

# QSettings keys
CONFIG_SERVER_PATH = "server_path"
CONFIG_GAMES_PATHS = "local_game_paths" # This will store the local path map
CONFIG_SHOW_OVERWRITE_WARNING = "show_overwrite_warning"


class AddGameDialog(QDialog):
    """
    A dialog box to add a new game.
    It asks for the game's name and its local save directory.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add New Game")
        self.setMinimumWidth(400)

        self.layout = QFormLayout(self)
        
        self.game_name_edit = QLineEdit()
        self.game_name_edit.setPlaceholderText("e.g., Hollow Knight")
        
        self.local_path_edit = QLineEdit()
        self.local_path_edit.setReadOnly(True)
        
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self.browse_local_path)
        
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.local_path_edit)
        path_layout.addWidget(self.browse_button)
        
        self.layout.addRow(QLabel("Game Name:"), self.game_name_edit)
        self.layout.addRow(QLabel("Local Save Directory:"), path_layout)
        
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.validate_and_accept)
        self.button_box.rejected.connect(self.reject)
        
        self.layout.addRow(self.button_box)

        # Store the selected path
        self.local_path = None

    def browse_local_path(self):
        """Opens a dialog to select the local save game directory."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Local Save Directory"
        )
        if path:
            self.local_path = pathlib.Path(path)
            self.local_path_edit.setText(str(self.local_path))

    def validate_and_accept(self):
        """Ensures all fields are filled before closing the dialog."""
        if not self.game_name_edit.text().strip():
            QMessageBox.warning(self, "Missing Name", "Please enter a game name.")
            return
            
        if not self.local_path:
            QMessageBox.warning(self, "Missing Path", "Please select a local save directory.")
            return
            
        self.accept()

    def get_data(self):
        """Returns the collected data."""
        return self.game_name_edit.text().strip(), self.local_path


class WelcomeDialog(QDialog):
    """
    First-run dialog to configure the server path.
    Asks user to "Set Up New Server" or "Connect to Existing Server".
    """
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Welcome to Rayforge Sync")
        self.setModal(True)
        self.setMinimumWidth(400)
        
        self.layout = QVBoxLayout(self)
        
        title = QLabel("Welcome to Rayforge Sync")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        
        info = QLabel(
            "To get started, please connect to your sync server.\n"
            "This is typically a network share (e.g., a Samba folder)."
        )
        info.setWordWrap(True)
        
        self.new_server_button = QPushButton("Set Up New Server")
        self.new_server_button.setToolTip(
            "Choose an empty folder to initialize as a new server."
        )
        self.new_server_button.clicked.connect(self.setup_new_server)
        
        self.existing_server_button = QPushButton("Connect to Existing Server")
        self.existing_server_button.setToolTip(
            "Choose a folder that already contains a 'games.json' file."
        )
        self.existing_server_button.clicked.connect(self.connect_to_existing_server)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        self.layout.addWidget(title)
        self.layout.addWidget(info)
        self.layout.addSpacing(20)
        self.layout.addWidget(self.new_server_button)
        self.layout.addWidget(self.existing_server_button)
        self.layout.addSpacing(10)
        self.layout.addWidget(self.cancel_button)

    def setup_new_server(self):
        """
        Guides user through creating a new server structure.
        Selects a directory, checks if it's safe to use, and creates 'games.json'.
        """
        path_str = QFileDialog.getExistingDirectory(
            self, "Select a Directory for Your New Server"
        )
        if not path_str:
            return  # User cancelled

        server_path = pathlib.Path(path_str)
        games_json_path = server_path / "games.json"

        # Check if 'games.json' already exists
        if games_json_path.exists():
            QMessageBox.warning(
                self, 
                "Server Already Exists",
                f"'games.json' already found in this directory.\n\n"
                f"If you want to connect to this server, "
                f"please choose 'Connect to Existing Server' instead."
            )
            return

        # Check if directory is empty (safer to allow non-empty, just check for json)
        # We will just create the file.
        
        try:
            default_data = {"games": []}
            with open(games_json_path, 'w') as f:
                json.dump(default_data, f, indent=4)
                
            QMessageBox.information(
                self, 
                "Success!",
                f"New server successfully created at:\n{server_path}"
            )
            
            # Save the path and close the dialog
            self.settings.setValue(CONFIG_SERVER_PATH, str(server_path))
            self.accept()
            
        except PermissionError:
            QMessageBox.critical(
                self, 
                "Permission Error",
                "Could not write to this directory.\n\n"
                "If this is a network drive (e.g., Samba server), "
                "please ensure you are connected in your operating system "
                "and have write permissions."
            )
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error",
                f"An unexpected error occurred: {e}"
            )

    def connect_to_existing_server(self):
        """
        Connects to an existing server.
        Selects a directory and validates it by checking for 'games.json'.
        """
        path_str = QFileDialog.getExistingDirectory(
            self, "Select Your Existing Server Directory"
        )
        if not path_str:
            return  # User cancelled

        server_path = pathlib.Path(path_str)
        games_json_path = server_path / "games.json"

        # Validate by checking for 'games.json'
        try:
            if not games_json_path.is_file():
                QMessageBox.warning(
                    self, 
                    f"Please select the correct Rayforge Sync server folder."
                )
                return
                
            # Try to parse the JSON to be sure
            with open(games_json_path, 'r') as f:
                json.load(f)

        except PermissionError:
            QMessageBox.critical(
                self,
                "Permission Error",
                "Could not read from this directory.\n\n"
                "If this is a network drive (e.g., Samba server), "
                "please ensure you are connected in your operating system."
            )
            return
        except Exception as e:
            QMessageBox.warning(
                self,
                "File Corrupted",
                f"Found 'games.json', but it could not be read.\n"
                f"The file may be corrupted.\n\nError: {e}"
            )
            return

        QMessageBox.information(
            self, 
            "Success!",
            f"Successfully connected to server at:\n{server_path}"
        )
        
        # Save the path and close the dialog
        self.settings.setValue(CONFIG_SERVER_PATH, str(server_path))
        self.accept()


class MainWindow(QMainWindow):
    """
    The main application window.
    Displays the list of games and provides sync controls.
    """
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.server_path = pathlib.Path(self.settings.value(CONFIG_SERVER_PATH))
        self.games_json_path = self.server_path / "games.json"
        
        # This is the local map of {game_id: local_path_str}
        # Fixed TypeError: Removed 'dict' as a type parameter,
        # it's not supported. {} is a valid default value.
        self.local_game_paths = self.settings.value(CONFIG_GAMES_PATHS, {})

        # Get a cross-platform-safe path for local backups
        self.local_backup_root = pathlib.Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
        ) / "backups"
        
        self.setWindowTitle(f"Rayforge Sync - {self.server_path.name}")
        self.setGeometry(100, 100, 700, 500)
        
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QHBoxLayout(self.main_widget)
        
        # --- Left Panel (Game List) ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("Synced Games"))
        
        self.game_list_widget = QListWidget()
        self.game_list_widget.setStyleSheet("font-size: 16px;")
        self.game_list_widget.itemSelectionChanged.connect(self.update_ui_state)
        left_layout.addWidget(self.game_list_widget)
        
        self.add_game_button = QPushButton("Add New Game...")
        self.add_game_button.clicked.connect(self.add_new_game)
        left_layout.addWidget(self.add_game_button)

        # --- Right Panel (Controls) ---
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.status_label = QLabel("Select a game to see its status.")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.status_label.setStyleSheet("font-size: 14px; min-height: 60px;")
        right_layout.addWidget(self.status_label)
        
        self.upload_button = QPushButton("Upload Save to Server")
        self.upload_button.clicked.connect(self.upload_save)
        
        self.download_button = QPushButton("Download Save from Server")
        self.download_button.clicked.connect(self.download_save)
        
        # Button for the "New PC" scenario
        self.set_local_path_button = QPushButton("Set Local Path...")
        self.set_local_path_button.clicked.connect(self.set_local_path)
        
        self.upload_all_button = QPushButton("Upload All Games")
        self.download_all_button = QPushButton("Download All Games")
        
        # Add a "spacer" to push buttons down a bit
        right_layout.addSpacing(20) 
        
        right_layout.addWidget(self.upload_button)
        right_layout.addWidget(self.download_button)
        right_layout.addWidget(self.set_local_path_button)
        
        right_layout.addStretch(1) # Pushes bulk buttons to bottom
        
        right_layout.addWidget(self.upload_all_button)
        right_layout.addWidget(self.download_all_button)

        self.main_layout.addLayout(left_layout, 2)  # 2/3 of space
        self.main_layout.addLayout(right_layout, 1) # 1/3 of space
        
        self.load_games_from_json()
        self.update_ui_state()
        
    def load_games_from_json(self):
        """Reads the server 'games.json' and populates the list."""
        self.game_list_widget.clear()
        try:
            with open(self.games_json_path, 'r') as f:
                data = json.load(f)
            
            # Add validation for the JSON structure
            if not isinstance(data, dict):
                raise TypeError("JSON root is not an object/dictionary")
            
            games_list = data.get("games")
            
            if not isinstance(games_list, list):
                 raise TypeError("JSON 'games' key is not a list")

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Error Loading Games", f"'games.json' is corrupted and cannot be read.\n\nError: {e}")
            return
        except TypeError as e:
            QMessageBox.critical(self, "Error Loading Games", f"'games.json' has an invalid format.\n\nError: {e}")
            return
        except Exception as e:
            QMessageBox.critical(self, "Error Loading Games", f"Could not read 'games.json': {e}")
            return
            
        for game in games_list:
            if not isinstance(game, dict):
                print(f"Skipping invalid game entry: {game}")
                continue
                
            game_id = game.get("id")
            game_name = game.get("name")
            
            # Fixed IndentationError: This block was indented too far
            if not game_id or not game_name:
                continue
                
            item = QListWidgetItem(game_name)
            # Store the ID and Name right in the list item
            item.setData(Qt.ItemDataRole.UserRole, game) 
            
            # Check if we have a local path for this game
            if game_id not in self.local_game_paths:
                # This is the "New PC" scenario!
                item.setForeground(Qt.GlobalColor.gray)
                item.setToolTip(
                    "Local path not set for this PC. "
                    "Select this game and set path."
                )
            
            self.game_list_widget.addItem(item)
                
        # Removed stray 'except' block here that was causing a syntax error
            
        self.update_ui_state()

    def update_ui_state(self):
        """Enables/disables buttons based on selection."""
        selected_item = self.get_selected_game_item()
        
        if not selected_item:
            self.upload_button.setEnabled(False)
            self.download_button.setEnabled(False)
            self.set_local_path_button.setVisible(False)
            self.status_label.setText("Select a game from the list.")
            return

        game_data = selected_item.data(Qt.ItemDataRole.UserRole)
        game_id = game_data.get("id")
        game_name = game_data.get("name")

        if game_id not in self.local_game_paths:
            self.status_label.setText(
                f"{game_name} is not configured on this PC.\n\n"
                "Please set the local save directory."
            )
            # This is the "New PC" workflow
            self.upload_button.setEnabled(False)
            self.download_button.setEnabled(False)
            self.set_local_path_button.setVisible(True) # Show the "Set Path" button
        else:
            local_path = self.local_game_paths[game_id]
            self.status_label.setText(
                f"Game: {game_name}\n"
                f"Local Path: {local_path}"
            )
            self.upload_button.setEnabled(True)
            self.download_button.setEnabled(True)
            self.set_local_path_button.setVisible(False) # Hide the "Set Path" button
            
        # TODO: Logic for enabling/disabling bulk buttons
        self.upload_all_button.setEnabled(self.game_list_widget.count() > 0)
        self.download_all_button.setEnabled(self.game_list_widget.count() > 0)

    def get_selected_game_item(self) -> QListWidgetItem | None:
        """Helper to get the currently selected list item."""
        items = self.game_list_widget.selectedItems()
        if items:
            return items[0]
        return None

    def set_local_path(self):
        """
        Allows the user to set the local save path for a game
        that is already on the server (the "New PC" scenario).
        """
        selected_item = self.get_selected_game_item()
        if not selected_item:
            return
            
        game_data = selected_item.data(Qt.ItemDataRole.UserRole)
        game_id = game_data.get("id")
        game_name = game_data.get("name")
        
        path_str = QFileDialog.getExistingDirectory(
            self, f"Select Local Save Directory for {game_name}"
        )
        if not path_str:
            return

        # Save the new path to our local settings
        self.local_game_paths[game_id] = path_str
        self.settings.setValue(CONFIG_GAMES_PATHS, self.local_game_paths)
        
        # Reload the game list to remove the "greyed out" style
        # and update the UI to show the correct buttons
        self.load_games_from_json()
        
        # Reselect the item that was just configured
        for i in range(self.game_list_widget.count()):
            item = self.game_list_widget.item(i)
            if item.data(Qt.ItemDataRole.UserRole).get("id") == game_id:
                item.setSelected(True)
                break
                
        self.update_ui_state()

    def add_new_game(self):
        """
        Handles the "Add New Game" logic.
        1. Opens the AddGameDialog.
        2. On success, updates 'games.json' on the server.
        3. Creates server-side directories.
        4. Saves the local path to QSettings.
        5. Reloads the game list.
        """
        dialog = AddGameDialog(self)
        if dialog.exec() == QDialog.Accepted:
            game_name, local_path = dialog.get_data()
            game_id = str(uuid.uuid4()) # Generate a new unique ID
            new_game_data = {"id": game_id, "name": game_name}

            # --- 1. Create Server Directories FIRST ---
            # If this fails, we haven't touched the JSON file.
            try:
                game_server_dir = self.server_path / game_id
                (game_server_dir / "save_data").mkdir(parents=True, exist_ok=True)
                (game_server_dir / "backup").mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Server Error", f"Could not create server directories: {e}")
                return

            # --- 2. Update Server 'games.json' (Atomically) ---
            games_json_temp_path = self.games_json_path.with_suffix(".json.tmp")
            try:
                # Read existing data
                with open(self.games_json_path, 'r') as f:
                    server_data = json.load(f)
                
                # Check for duplicate game name (case-insensitive)
                existing_names = [g['name'].lower() for g in server_data.get("games", [])]
                if game_name.lower() in existing_names:
                    QMessageBox.warning(self, "Duplicate Game", f"A game named '{game_name}' already exists.")
                    # Rollback: delete the directories we just made
                    shutil.rmtree(game_server_dir)
                    return
                
                # Add new game
                server_data["games"].append(new_game_data)
                
                # Write to temp file
                with open(games_json_temp_path, 'w') as f:
                    json.dump(server_data, f, indent=4)
                
                # Atomic rename operation (safer)
                os.rename(games_json_temp_path, self.games_json_path)
                    
            except Exception as e:
                QMessageBox.critical(self, "Server Error", f"Could not update 'games.json': {e}")
                # Rollback: Try to delete the directories we just made
                try:
                    shutil.rmtree(game_server_dir)
                except Exception as e_roll:
                    QMessageBox.critical(self, "Rollback Error", f"Failed to update JSON and also failed to clean up directories: {e_roll}")
                return
                
            # --- 3. Save Local Path ---
    def _show_overwrite_warning(self, title, text):
        """
        Shows a confirmation dialog with a "Don't show again" checkbox.
        Returns True if user clicks OK, False if Cancel.
        """
        show_warning = self.settings.value(CONFIG_SHOW_OVERWRITE_WARNING, True, bool)
        
        if not show_warning:
            return True # User has already opted out of warnings

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        
        checkbox = QCheckBox("Don't show this warning again")
        msg_box.setCheckBox(checkbox)
        
        result = msg_box.exec()
        
        if checkbox.isChecked():
            self.settings.setValue(CONFIG_SHOW_OVERWRITE_WARNING, False)
            
        return result == QMessageBox.StandardButton.Ok

    def _clear_directory_contents(self, dir_path: pathlib.Path):
        """Helper to safely delete all contents of a directory."""
        if not dir_path.is_dir():
            return
        for item in dir_path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                os.remove(item)

    def upload_save(self):
        """
        Uploads the local save data to the server.
        1. Backs up the current server save.
        2. Copies the local save files to the server.
        """
        selected_item = self.get_selected_game_item()
        if not selected_item: return
            
        game_data = selected_item.data(Qt.ItemDataRole.UserRole)
        game_id = game_data["id"]
        game_name = game_data["name"]
        local_path_str = self.local_game_paths.get(game_id)
        
        if not local_path_str:
            QMessageBox.warning(self, "Error", "Local path not set.")
            return

        if not self._show_overwrite_warning(
            "Confirm Upload",
            f"This will overwrite the server save data for '{game_name}'.\n\n"
            "The existing server data will be backed up. Continue?"
        ):
            return # User cancelled

        try:
            local_path = pathlib.Path(local_path_str)
            server_save_path = self.server_path / game_id / "save_data"
            server_backup_path = self.server_path / game_id / "backup"
            
            # 1. Create timestamped backup on server
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_dest = server_backup_path / timestamp
            
            # Check if there's anything to back up
            if any(server_save_path.iterdir()):
                shutil.move(str(server_save_path), str(backup_dest))
                # Re-create the now-moved 'save_data' directory
                server_save_path.mkdir()
            
            # 2. Copy local files to server
            # We copy the *contents* of the local path
            shutil.copytree(str(local_path), str(server_save_path), dirs_exist_ok=True)

            QMessageBox.information(self, "Upload Complete", f"Successfully uploaded save for '{game_name}'.")

        except Exception as e:
            QMessageBox.critical(self, "Upload Failed", f"An error occurred: {e}")
        
    def download_save(self):
        """
        Downloads the server save data to the local machine.
        1. Backs up the current local save.
        2. Copies the server save files to the local machine.
        """
        selected_item = self.get_selected_game_item()
        if not selected_item: return
            
        game_data = selected_item.data(Qt.ItemDataRole.UserRole)
        game_id = game_data["id"]
        game_name = game_data["name"]
        local_path_str = self.local_game_paths.get(game_id)
        
        if not local_path_str:
            QMessageBox.warning(self, "Error", "Local path not set.")
            return
            
        if not self._show_overwrite_warning(
            "Confirm Download",
            f"This will overwrite your local save data for '{game_name}'.\n\n"
            "Your existing local data will be backed up. Continue?"
        ):
            return # User cancelled

        try:
            local_path = pathlib.Path(local_path_str)
            server_save_path = self.server_path / game_id / "save_data"
            
            # 1. Create timestamped local backup
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            # Use the app's config folder for its *own* backups
            backup_dest = self.local_backup_root / game_id / timestamp
            backup_dest.mkdir(parents=True, exist_ok=True)
            
            # Check if there's anything to back up
            if any(local_path.iterdir()):
                # Back up by copying, then delete contents
                shutil.copytree(str(local_path), str(backup_dest), dirs_exist_ok=True)
                self._clear_directory_contents(local_path)
            
            # 2. Copy server files to local machine
            shutil.copytree(str(server_save_path), str(local_path), dirs_exist_ok=True)

            QMessageBox.information(self, "Download Complete", f"Successfully downloaded save for '{game_name}'.")

        except Exception as e:
            QMessageBox.critical(self, "Download Failed", f"An error occurred: {e}")


def main():
    """
    Main entry point for the application.
    Initializes QSettings and decides whether to show
    the WelcomeDialog or the MainWindow.
    """
    # Fixes scaling on high-DPI monitors
    # Use environment variable for modern Qt6, fixes DeprecationWarning
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    
    app = QApplication(sys.argv)
    
    # Set up QSettings
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setApplicationName(APPLICATION_NAME)
    
    settings = QSettings()
    
    server_path = settings.value(CONFIG_SERVER_PATH)
    
    main_window = None
    
    if not server_path:
        # First run, or config is missing. Show Welcome dialog.
        welcome_dialog = WelcomeDialog(settings)
        
        if welcome_dialog.exec() == QDialog.Accepted:
            # User successfully configured a server.
            main_window = MainWindow(settings)
            main_window.show()
        else:
            # User cancelled setup.
            sys.exit()
    else:
        # We have a server path, proceed to main window.
        # We should also validate this path, in case the drive
        # is disconnected.
        try:
            server_path_obj = pathlib.Path(server_path)
            if not (server_path_obj / "games.json").is_file():
                QMessageBox.critical(
                    None, 
                    "Server Not Found",
                    f"Could not find 'games.json' at the configured path:\n{server_path}\n\n"
                    "The server may be disconnected or the file is missing.\n"
                    "Rayforge Sync will now exit."
                )
                settings.remove(CONFIG_SERVER_PATH) # Clear the bad path
                sys.exit(1)
        
        except PermissionError:
            QMessageBox.critical(
                None,
                "Permission Error",
                f"Could not access the server path:\n{server_path}\n\n"
                "If this is a network drive (e.g., Samba server), "
                "please ensure you are connected in your operating system.\n"
                "Rayforge Sync will now exit."
            )
            # We don't clear the path, as it might be a temporary connection issue
            sys.exit(1)
        except Exception as e:
            QMessageBox.critical(
                None,
                "Startup Error",
                f"An unexpected error occurred while accessing the server path:\n{e}\n"
                "Rayforge Sync will now exit."
            )
            sys.exit(1)
            
        main_window = MainWindow(settings)
        main_window.show()

    if main_window:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
