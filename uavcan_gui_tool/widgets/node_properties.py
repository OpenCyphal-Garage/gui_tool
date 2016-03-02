#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
import datetime
from PyQt5.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QGroupBox, QFrame, QVBoxLayout, QHBoxLayout
from PyQt5.QtCore import QTimer, Qt
from logging import getLogger
from . import get_monospace_font
from helpers import UAVCANStructInspector


logger = getLogger(__name__)


class FieldValueWidget(QLineEdit):
    def __init__(self, parent, initial_value=None):
        super(FieldValueWidget, self).__init__(parent)
        self.setFont(get_monospace_font())
        self.setReadOnly(True)
        if initial_value is None:
            self.setEnabled(False)
        else:
            self.setText(str(initial_value))

    def disable(self):
        self.setEnabled(False)

    def set(self, value):
        if not self.isEnabled():
            self.setEnabled(True)
        value = str(value)
        if self.text() != value:
            self.setText(value)


class InfoBox(QGroupBox):
    def __init__(self, parent, target_node_id, node_monitor):
        super(InfoBox, self).__init__(parent)
        self.setTitle('Node info')

        self._target_node_id = target_node_id
        self._node_monitor = node_monitor

        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update)
        self._update_timer.setSingleShot(False)
        self._update_timer.start(1000)

        layout = QGridLayout(self)

        def make_field(name, initial_value=None, multiple_field_stretch_ratios=None):
            row = layout.rowCount()
            layout.addWidget(QLabel(name, self), row, 0)
            if not multiple_field_stretch_ratios:
                field = FieldValueWidget(self, initial_value)
                layout.addWidget(field, row, 1)
                return field
            else:
                fields = [FieldValueWidget(self, initial_value) for _ in multiple_field_stretch_ratios]
                hbox = QHBoxLayout(self)
                hbox.setContentsMargins(0, 0, 0, 0)
                for f, stretch_ratio in zip(fields, multiple_field_stretch_ratios):
                    hbox.addWidget(f, stretch_ratio)
                layout.addLayout(hbox, row, 1)
                return fields

        def add_separator():
            f = QFrame(self)
            f.setFrameShape(QFrame.HLine)
            f.setFrameShadow(QFrame.Sunken)
            layout.addWidget(f, layout.rowCount(), 0, 1, 2)

        self._node_id = make_field('Node ID', target_node_id)
        self._name = make_field('Name')

        self._mode = make_field('Mode')
        self._health = make_field('Health')
        self._vendor_status = make_field('Vendor-specific code', multiple_field_stretch_ratios=(1, 1, 2))
        self._uptime = make_field('Uptime')

        self._sw_version = make_field('Software version')
        self._sw_crc = make_field('Software CRC-64-WE')
        self._hw_version = make_field('Hardware version')
        self._unique_id = make_field('Unique ID')
        self._cert_of_auth = make_field('Cert. of authenticity')

        self.setLayout(layout)

        self._update()

    def _update(self):
        # noinspection PyBroadException
        try:
            entry = self._node_monitor.get(self._target_node_id)
        except Exception:
            self.setEnabled(False)
            return

        if entry.status:        # Status should be always available...
            inspector = UAVCANStructInspector(entry.status)
            self._mode.set(inspector.field_to_string('mode', keep_literal=True))
            self._health.set(inspector.field_to_string('health', keep_literal=True))

            vssc = entry.status.vendor_specific_status_code
            self._vendor_status[0].set(vssc)
            self._vendor_status[1].set('0x%04x' % vssc)
            self._vendor_status[2].set('0b' + bin((vssc >> 8) & 0xFF)[2:].zfill(8) +
                                       '_' + bin(vssc & 0xFF)[2:].zfill(8))

            self._uptime.set(datetime.timedelta(days=0, seconds=entry.status.uptime_sec))

        if entry.info:
            inf = entry.info
            self._name.set(inf.name.decode())

            swver = '%d.%d' % (inf.software_version.major, inf.software_version.minor)
            if inf.software_version.optional_field_flags & inf.software_version.OPTIONAL_FIELD_FLAG_VCS_COMMIT:
                swver += '.%08x' % inf.software_version.vcs_commit
            self._sw_version.set(swver)

            if inf.software_version.optional_field_flags & inf.software_version.OPTIONAL_FIELD_FLAG_IMAGE_CRC:
                self._sw_crc.set('0x%016x' % inf.software_version.image_crc)
            else:
                self._sw_crc.disable()

            self._hw_version.set('%d.%d' % (inf.hardware_version.major, inf.hardware_version.minor))

            uid = inf.hardware_version.unique_id
            if not all([x == 0 for x in uid]):
                self._unique_id.set(' '.join(['%02x' % x for x in uid]))
            else:
                self._unique_id.disable()

            if len(inf.hardware_version.certificate_of_authenticity):
                self._cert_of_auth.set(' '.join(['%02x' % x
                                                     for x in inf.hardware_version.certificate_of_authenticity]))
            else:
                self._cert_of_auth.disable()
        else:
            self._name.disable()
            self._sw_version.disable()
            self._sw_crc.disable()
            self._hw_version.disable()
            self._unique_id.disable()
            self._cert_of_auth.disable()


class NodePropertiesWindow(QDialog):
    def __init__(self, parent, node, target_node_id, file_server_widget, node_monitor):
        super(NodePropertiesWindow, self).__init__(parent)
        self.setWindowTitle('Node Properties [%d]' % target_node_id)
        self.setMinimumWidth(480)

        self._target_node_id = target_node_id
        self._node = node
        self._file_server_widget = file_server_widget

        self._info_box = InfoBox(self, target_node_id, node_monitor)

        layout = QVBoxLayout(self)
        layout.addWidget(self._info_box)
        self.setLayout(layout)

    @property
    def target_node_id(self):
        return self._target_node_id
