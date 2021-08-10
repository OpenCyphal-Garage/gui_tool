#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import datetime
import pyuavcan_v0
from . import BasicTable, get_monospace_font
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHeaderView, QLabel
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from logging import getLogger


logger = getLogger(__name__)


def node_mode_to_color(mode):
    s = pyuavcan_v0.protocol.NodeStatus()
    return {
        s.MODE_INITIALIZATION: Qt.cyan,
        s.MODE_MAINTENANCE: Qt.magenta,
        s.MODE_SOFTWARE_UPDATE: Qt.magenta,
        s.MODE_OFFLINE: Qt.red
    }.get(mode)


def node_health_to_color(health):
    s = pyuavcan_v0.protocol.NodeStatus()
    return {
        s.HEALTH_WARNING: Qt.yellow,
        s.HEALTH_ERROR: Qt.magenta,
        s.HEALTH_CRITICAL: Qt.red,
    }.get(health)


def render_vendor_specific_status_code(s):
    out = '%-5d     0x%04x\n' % (s, s)
    binary = bin(s)[2:].rjust(16, '0')

    def high_nibble(s):
        return s.replace('0', '\u2070').replace('1', '\u00B9')  # Unicode 0/1 superscript

    def low_nibble(s):
        return s.replace('0', '\u2080').replace('1', '\u2081')  # Unicode 0/1 subscript

    nibbles = [
        high_nibble(binary[:4]),
        low_nibble(binary[4:8]),
        high_nibble(binary[8:12]),
        low_nibble(binary[12:]),
    ]

    out += ''.join(nibbles)
    return out


class NodeTable(BasicTable):
    COLUMNS = [
        BasicTable.Column('NID',
                          lambda e: e.node_id),
        BasicTable.Column('Name',
                          lambda e: e.info.name if e.info else '?',
                          QHeaderView.Stretch),
        BasicTable.Column('Mode',
                          lambda e: (pyuavcan_v0.value_to_constant_name(e.status, 'mode'),
                                     node_mode_to_color(e.status.mode))),
        BasicTable.Column('Health',
                          lambda e: (pyuavcan_v0.value_to_constant_name(e.status, 'health'),
                                     node_health_to_color(e.status.health))),
        BasicTable.Column('Uptime',
                          lambda e: datetime.timedelta(days=0, seconds=e.status.uptime_sec)),
        BasicTable.Column('VSSC',
                          lambda e: render_vendor_specific_status_code(e.status.vendor_specific_status_code))
    ]

    info_requested = pyqtSignal([int])

    def __init__(self, parent, node):
        super(NodeTable, self).__init__(parent, self.COLUMNS, font=get_monospace_font())

        self.cellDoubleClicked.connect(lambda row, col: self._call_info_requested_callback_on_row(row))
        self.on_enter_pressed = self._on_enter

        self._monitor = pyuavcan_v0.app.node_monitor.NodeMonitor(node)

        self._timer = QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._update)
        self._timer.start(500)

        self.setMinimumWidth(600)

        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    @property
    def monitor(self):
        return self._monitor

    def close(self):
        self._monitor.close()

    def _call_info_requested_callback_on_row(self, row):
        nid = int(self.item(row, 0).text())
        self.info_requested.emit(nid)

    def _on_enter(self, list_of_row_col_pairs):
        unique_rows = set([row for row, _col in list_of_row_col_pairs])
        if len(unique_rows) == 1:
            self._call_info_requested_callback_on_row(list(unique_rows)[0])

    def _update(self):
        known_nodes = {e.node_id: e for e in self._monitor.find_all(lambda _: True)}
        displayed_nodes = set()
        rows_to_remove = []

        # Updating existing entries
        for row in range(self.rowCount()):
            nid = int(self.item(row, 0).text())
            displayed_nodes.add(nid)
            if nid not in known_nodes:
                rows_to_remove.append(row)
            else:
                self.set_row(row, known_nodes[nid])

        # Removing nonexistent entries
        for row in rows_to_remove[::-1]:     # It is important to traverse from end
            logger.info('Removing row %d', row)
            self.removeRow(row)

        # Adding new entries
        def find_insertion_pos_for_node_id(target_nid):
            for row in range(self.rowCount()):
                nid = int(self.item(row, 0).text())
                if nid > target_nid:
                    return row
            return self.rowCount()

        for nid in set(known_nodes.keys()) - displayed_nodes:
            row = find_insertion_pos_for_node_id(nid)
            logger.info('Adding new row %d for node %d', row, nid)
            self.insertRow(row)
            self.set_row(row, known_nodes[nid])


class NodeMonitorWidget(QGroupBox):
    def __init__(self, parent, node):
        super(NodeMonitorWidget, self).__init__(parent)
        self.setTitle('Online nodes (double click for more options)')

        self._node = node
        self.on_info_window_requested = lambda *_: None

        self._status_update_timer = QTimer(self)
        self._status_update_timer.setSingleShot(False)
        self._status_update_timer.timeout.connect(self._update_status)
        self._status_update_timer.start(500)

        self._table = NodeTable(self, node)
        self._table.info_requested.connect(self._show_info_window)

        self._monitor_handle = self._table.monitor.add_update_handler(lambda _: self._update_status())

        self._status_label = QLabel(self)

        vbox = QVBoxLayout(self)
        vbox.addWidget(self._table)
        vbox.addWidget(self._status_label)
        self.setLayout(vbox)

    @property
    def monitor(self):
        return self._table.monitor

    def close(self):
        self._table.close()
        self._monitor_handle.remove()
        self._status_update_timer.stop()

    def _update_status(self):
        if self._node.is_anonymous:
            self._status_label.setText('Discovery is not possible - local node is configured in anonymous mode')
        else:
            num_undiscovered = len(list(self.monitor.find_all(lambda e: not e.discovered)))
            if num_undiscovered > 0:
                self._status_label.setText('Node discovery is in progress, %d left...' % num_undiscovered)
            else:
                self._status_label.setText('All nodes are discovered')

    def _show_info_window(self, node_id):
        self.on_info_window_requested(node_id)
