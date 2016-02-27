#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import datetime
import uavcan
from . import BasicTable
from PyQt5.QtWidgets import QGroupBox, QVBoxLayout, QHeaderView
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from logging import getLogger
from helpers import UAVCANStructInspector


logger = getLogger(__name__)


def node_mode_to_color(mode):
    s = uavcan.protocol.NodeStatus()
    return {
        s.MODE_INITIALIZATION: Qt.cyan,
        s.MODE_MAINTENANCE: Qt.magenta,
        s.MODE_SOFTWARE_UPDATE: Qt.magenta,
        s.MODE_OFFLINE: Qt.red
    }.get(mode)


def node_health_to_color(health):
    s = uavcan.protocol.NodeStatus()
    return {
        s.HEALTH_WARNING: Qt.yellow,
        s.HEALTH_ERROR: Qt.magenta,
        s.HEALTH_CRITICAL: Qt.red,
    }.get(health)


class NodeTable(BasicTable):
    COLUMNS = [
        BasicTable.Column('Node ID',
                          lambda e: e.node_id),
        BasicTable.Column('Name',
                          lambda e: e.info.name if e.info else '?',
                          QHeaderView.Stretch),
        BasicTable.Column('Mode',
                          lambda e: (UAVCANStructInspector(e.status).field_to_string('mode'),
                                     node_mode_to_color(e.status.mode))),
        BasicTable.Column('Health',
                          lambda e: (UAVCANStructInspector(e.status).field_to_string('health'),
                                     node_health_to_color(e.status.health))),
        BasicTable.Column('Uptime',
                          lambda e: datetime.timedelta(days=0, seconds=e.status.uptime_sec)),
        BasicTable.Column('Vendor-specific status',
                          lambda e: '%d  0x%04x' % (e.status.vendor_specific_status_code,
                                                    e.status.vendor_specific_status_code))
    ]

    info_requested = pyqtSignal([int])

    def __init__(self, parent, node):
        super(NodeTable, self).__init__(parent, self.COLUMNS)

        self.doubleClicked.connect(self._on_double_click)

        self._monitor = uavcan.app.node_monitor.NodeMonitor(node)

        self._timer = QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._update)
        self._timer.start(500)

    @property
    def monitor(self):
        return self._monitor

    def close(self):
        self._monitor.close()

    def _on_double_click(self):
        sel = self.selectedIndexes()
        if not sel:
            return
        row = sel[0].row()
        nid = int(self.item(row, 0).text())
        self.info_requested.emit(nid)

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

        self._table = NodeTable(self, node)
        self._table.info_requested.connect(self._show_info_window)

        vbox = QVBoxLayout(self)
        vbox.addWidget(self._table)
        self.setLayout(vbox)

    @property
    def monitor(self):
        return self._table.monitor

    def close(self):
        self._table.close()

    def _show_info_window(self, node_id):
        print(node_id)
