#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QHeaderView, QPushButton, QFileDialog, \
    QCompleter, QDirModel
from PyQt5.QtCore import QTimer
from logging import getLogger
from . import BasicTable, get_monospace_font, get_icon, show_error, CommitableComboBoxWithHistory, make_icon_button


logger = getLogger(__name__)


def unique_id_to_string(uid):
    return ' '.join(['%02X' % x for x in uid]) if uid else 'N/A'


class DynamicNodeIDAllocatorWidget(QGroupBox):
    DEFAULT_DATABASE_FILE = ':memory:'

    COLUMNS = [
        BasicTable.Column('Node ID',
                          lambda e: e[1]),
        BasicTable.Column('Unique ID',
                          lambda e: unique_id_to_string(e[0]),
                          resize_mode=QHeaderView.Stretch),
    ]

    def __init__(self, parent, node, node_monitor):
        super(DynamicNodeIDAllocatorWidget, self).__init__(parent)
        self.setTitle('Dynamic node ID allocation server (uavcan.protocol.dynamic_node_id.*)')

        self._node = node
        self._node_monitor = node_monitor
        self._allocator = None

        self._allocation_table = BasicTable(self, self.COLUMNS, font=get_monospace_font())

        self._allocation_table_update_timer = QTimer(self)
        self._allocation_table_update_timer.setSingleShot(False)
        self._allocation_table_update_timer.start(500)
        self._allocation_table_update_timer.timeout.connect(self._update_table)

        self._start_stop_button = make_icon_button('rocket', 'Launch/stop the dynamic node ID allocation server', self,
                                                   checkable=True)
        self._start_stop_button.clicked.connect(self._on_start_stop_button)

        self._database_file = CommitableComboBoxWithHistory(self)
        self._database_file.setAcceptDrops(True)
        self._database_file.setToolTip('Path to the allocation table file')
        self._database_file.setCurrentText(self.DEFAULT_DATABASE_FILE)
        self._database_file.addItem(self._database_file.currentText())
        self._database_file.on_commit = self._on_start_stop_button

        self._select_database_file = make_icon_button('folder-open-o', 'Open allocation table file', self,
                                                      on_clicked=self._on_select_database_file)

        db_file_completer = QCompleter()
        db_file_completer.setModel(QDirModel(db_file_completer))
        self._database_file.setCompleter(db_file_completer)

        self._sync_gui()

        layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._start_stop_button)
        controls_layout.addWidget(self._database_file, 1)
        controls_layout.addWidget(self._select_database_file)

        layout.addLayout(controls_layout)
        layout.addWidget(self._allocation_table, 1)
        self.setLayout(layout)

    def _on_select_database_file(self):
        # TODO: It would be nice to rename the 'Save' button into something more appropriate like 'Open'
        dbf = QFileDialog().getSaveFileName(self, 'Select existing database file, or create a new one',
                                            '', '', '', QFileDialog.DontConfirmOverwrite)
        self._database_file.setCurrentText(dbf[0])

    def _sync_gui(self):
        # Syncing the GUI state
        if self._allocator:
            self._start_stop_button.setChecked(True)
            self.setEnabled(True)
            self._database_file.setEnabled(False)
            self._select_database_file.setEnabled(False)
        else:
            self._database_file.setEnabled(True)
            self._select_database_file.setEnabled(True)
            self._start_stop_button.setChecked(False)
            self.setEnabled(not self._node.is_anonymous)

    def _on_start_stop_button(self):
        # Serving the start/stop request
        if self._allocator:
            self._allocator.close()
            self._allocator = None
        else:
            try:
                db_file = self._database_file.currentText()
                self._allocator = uavcan.app.dynamic_node_id.CentralizedServer(self._node, self._node_monitor,
                                                                               database_storage=db_file)
            except Exception as ex:
                show_error('Error', 'Could not start allocator', str(ex), parent=self)

        # Updating the combo box
        if self._database_file.findText(self._database_file.currentText()) < 0:
            self._database_file.addItem(self._database_file.currentText())

        self._sync_gui()

    def _update_table(self):
        self._sync_gui()

        # Redrawing the table
        self._allocation_table.setUpdatesEnabled(False)

        if self._allocator is None:
            self._allocation_table.setRowCount(0)
        else:
            known_entries = [] if self._allocator is None else self._allocator.get_allocation_table()
            displayed_entries = set()

            for row in range(self._allocation_table.rowCount()):
                nid_str = self._allocation_table.item(row, 0).text()
                uid_str = self._allocation_table.item(row, 1).text()
                displayed_entries.add((uid_str, nid_str))

            def find_insertion_pos_for_node_id(target_nid):
                for row in range(self._allocation_table.rowCount()):
                    nid = int(self._allocation_table.item(row, 0).text())
                    if nid > target_nid:
                        return row
                return self._allocation_table.rowCount()

            for uid, nid in known_entries:
                if (unique_id_to_string(uid), str(nid)) in displayed_entries:
                    continue
                row = find_insertion_pos_for_node_id(nid)
                self._allocation_table.insertRow(row)
                self._allocation_table.set_row(row, (uid, nid))

        self._allocation_table.setUpdatesEnabled(True)

    @property
    def allocator(self):
        return self._allocator
