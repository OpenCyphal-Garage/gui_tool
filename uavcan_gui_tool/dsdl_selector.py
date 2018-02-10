import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QDialog, QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QFileDialog, QLineEdit


class ValidationButton(QPushButton):
    def __init__(self, parent, callback):
        super().__init__('OK', parent)
        self.clicked.connect(callback)

class DirectorySelectionWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.dir_selection = os.path.abspath(os.curdir)
        self.dir_textbox = QLineEdit(parent)
        self.dir_textbox.setText(self.dir_selection)

        self.dir_browser = QPushButton('Browse', parent)

        def on_browse():
            self.dir_selection = str(QFileDialog.getExistingDirectory(parent, "Select Directory"))
            self.dir_textbox.setText(self.dir_selection)

        self.dir_browser.clicked.connect(on_browse)

        layout = QHBoxLayout(parent)
        layout.addWidget(self.dir_textbox)
        layout.addWidget(self.dir_browser)

        self.setLayout(layout)

    def selection(self):
        return self.dir_selection

def run_dsdl_selection_window(icon):
    win = QDialog()
    win.setWindowTitle('UAVCAN DSDL Configuration')
    win.setWindowIcon(icon)
    win.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
    win.setAttribute(Qt.WA_DeleteOnClose)

    dir_selection = DirectorySelectionWidget(win)
    validation_button = ValidationButton(win, lambda: win.close())

    layout = QVBoxLayout(win)
    layout.addWidget(QLabel('Select custom DSDL messages'))
    layout.addWidget(dir_selection)
    layout.addWidget(validation_button)
    layout.setSizeConstraint(layout.SetFixedSize)

    win.setLayout(layout)

    win.exec()
    return dir_selection.selection()