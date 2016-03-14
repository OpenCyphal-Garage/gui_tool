#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from PyQt5.QtWidgets import QGroupBox, QLabel, QSpinBox, QHBoxLayout
from PyQt5.QtCore import QTimer
from logging import getLogger
from . import make_icon_button, flash

logger = getLogger(__name__)


NODE_ID_MIN = 1
NODE_ID_MAX = 127


class LocalNodeWidget(QGroupBox):
    def __init__(self, parent, node):
        super(LocalNodeWidget, self).__init__(parent)
        self.setTitle('Local node properties')

        self._node = node
        self._node_id_collector = uavcan.app.message_collector.MessageCollector(
            self._node, uavcan.protocol.NodeStatus, timeout=uavcan.protocol.NodeStatus().OFFLINE_TIMEOUT_MS * 1e-3)

        self._node_id_label = QLabel('Set local node ID:', self)

        self._node_id_spinbox = QSpinBox(self)
        self._node_id_spinbox.setMaximum(NODE_ID_MAX)
        self._node_id_spinbox.setMinimum(NODE_ID_MIN)
        self._node_id_spinbox.setValue(NODE_ID_MAX)
        self._node_id_spinbox.valueChanged.connect(self._update)

        self._node_id_apply = make_icon_button('check', 'Apply local node ID', self,
                                               on_clicked=self._on_node_id_apply_clicked)

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(False)
        self._update_timer.timeout.connect(self._update)
        self._update_timer.start(500)

        self._update()

        layout = QHBoxLayout(self)
        layout.addWidget(self._node_id_label)
        layout.addWidget(self._node_id_spinbox)
        layout.addWidget(self._node_id_apply)
        layout.addStretch(1)

        self.setLayout(layout)

        flash(self, 'Some functions will be unavailable unless local node ID is set')

    def close(self):
        self._node_id_collector.close()

    def _update(self):
        if not self._node.is_anonymous:
            self._node_id_spinbox.setEnabled(False)
            self._node_id_spinbox.setValue(self._node.node_id)
            self._node_id_apply.hide()
            self._node_id_label.setText('Local node ID:')
            self._update_timer.stop()
            flash(self, 'Local node ID set to %d, all functions should be available now', self._node.node_id)
        else:
            prohibited_node_ids = set(self._node_id_collector)
            while True:
                nid = int(self._node_id_spinbox.value())
                if not (set(range(nid, NODE_ID_MAX + 1)) - prohibited_node_ids):
                    self._node_id_spinbox.setValue(nid - 1)
                else:
                    break

            if nid in prohibited_node_ids:
                if self._node_id_apply.isEnabled():
                    self._node_id_apply.setEnabled(False)
                    flash(self, 'Selected node ID is used by another node, try different one', duration=3)
            else:
                self._node_id_apply.setEnabled(True)

    def _on_node_id_apply_clicked(self):
        nid = int(self._node_id_spinbox.value())
        if nid > 0:
            self._node.node_id = nid
            logger.info('Node ID: %s', self._node.node_id)
        self._update()
