import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QDialog, QPushButton, QLabel, QHBoxLayout, QVBoxLayout, QFileDialog, QLineEdit


def run_dsdl_selection_window(icon):
    win = QDialog()
    win.setWindowTitle('UAVCAN DSDL Configuration')
    win.setWindowIcon(icon)
    win.setWindowFlags(Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
    win.setAttribute(Qt.WA_DeleteOnClose)

    dsdl_directory = os.path.abspath(os.curdir)
    dsdl_textbox = QLineEdit()
    dsdl_textbox.setText(dsdl_directory)
    dsdl_browse = QPushButton('Browse', win)

    def on_browse():
        nonlocal dsdl_directory
        dsdl_directory = str(QFileDialog.getExistingDirectory(win, "Select Directory"))
        dsdl_textbox.setText(dsdl_directory)

    dsdl_browse.clicked.connect(on_browse)

    ok = QPushButton('OK', win)

    def on_ok():
        win.close()

    ok.clicked.connect(on_ok)

    dsdl_layout = QHBoxLayout(win)
    dsdl_layout.addWidget(dsdl_textbox)
    dsdl_layout.addWidget(dsdl_browse)
    dsdl_widget = QWidget()
    dsdl_widget.setLayout(dsdl_layout)

    layout = QVBoxLayout(win)
    layout.addWidget(QLabel('Select custom DSDL messages'))
    layout.addWidget(dsdl_widget)
    layout.addWidget(ok)
    layout.setSizeConstraint(layout.SetFixedSize)
    win.setLayout(layout)

    win.exec()

    return dsdl_directory
