#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
import datetime
from functools import partial
from PyQt5.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QGroupBox, QVBoxLayout, QHBoxLayout, QStatusBar,\
    QHeaderView
from PyQt5.QtCore import QTimer, Qt
from logging import getLogger
from . import get_monospace_font, make_icon_button, LabelWithIcon, BasicTable, show_error, request_confirmation
from helpers import UAVCANStructInspector


logger = getLogger(__name__)


REQUEST_PRIORITY = 30


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

    def clear(self):
        if not self.isEnabled():
            self.setEnabled(True)
        super(FieldValueWidget, self).clear()


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

        def make_field(name, field_stretch_ratios=None):
            row = layout.rowCount()
            layout.addWidget(QLabel(name, self), row, 0)
            if not field_stretch_ratios:
                field = FieldValueWidget(self)
                layout.addWidget(field, row, 1)
                return field
            else:
                fields = [FieldValueWidget(self) for _ in field_stretch_ratios]
                hbox = QHBoxLayout(self)
                hbox.setContentsMargins(0, 0, 0, 0)
                for f, stretch_ratio in zip(fields, field_stretch_ratios):
                    hbox.addWidget(f, stretch_ratio)
                layout.addLayout(hbox, row, 1)
                return fields

        self._node_id_name = make_field('Node ID / Name', field_stretch_ratios=(1, 8))
        self._node_id_name[0].set(target_node_id)

        self._mode_health_uptime = make_field('Mode / Health / Uptime', field_stretch_ratios=(1, 1, 1))
        self._vendor_status = make_field('Vendor-specific code', field_stretch_ratios=(1, 1, 2))

        self._sw_version_crc = make_field('Software version/CRC64', field_stretch_ratios=(1, 1))
        self._hw_version_uid = make_field('Hardware version/UID', field_stretch_ratios=(1, 6))
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

        self.setEnabled(True)

        if entry.status:        # Status should be always available...
            inspector = UAVCANStructInspector(entry.status)
            self._mode_health_uptime[0].set(inspector.field_to_string('mode', keep_literal=True))
            self._mode_health_uptime[1].set(inspector.field_to_string('health', keep_literal=True))
            self._mode_health_uptime[2].set(datetime.timedelta(days=0, seconds=entry.status.uptime_sec))

            vssc = entry.status.vendor_specific_status_code
            self._vendor_status[0].set(vssc)
            self._vendor_status[1].set('0x%04x' % vssc)
            self._vendor_status[2].set('0b' + bin((vssc >> 8) & 0xFF)[2:].zfill(8) +
                                       '_' + bin(vssc & 0xFF)[2:].zfill(8))

        if entry.info:
            inf = entry.info
            self._node_id_name[1].set(inf.name.decode())

            swver = '%d.%d' % (inf.software_version.major, inf.software_version.minor)
            if inf.software_version.optional_field_flags & inf.software_version.OPTIONAL_FIELD_FLAG_VCS_COMMIT:
                swver += '.%08x' % inf.software_version.vcs_commit
            self._sw_version_crc[0].set(swver)

            if inf.software_version.optional_field_flags & inf.software_version.OPTIONAL_FIELD_FLAG_IMAGE_CRC:
                self._sw_version_crc[1].set('0x%016x' % inf.software_version.image_crc)
            else:
                self._sw_version_crc[1].clear()

            self._hw_version_uid[0].set('%d.%d' % (inf.hardware_version.major, inf.hardware_version.minor))

            if not all([x == 0 for x in inf.hardware_version.unique_id]):
                self._hw_version_uid[1].set(' '.join(['%02x' % x for x in inf.hardware_version.unique_id]))
            else:
                self._hw_version_uid[1].clear()

            if len(inf.hardware_version.certificate_of_authenticity):
                self._cert_of_auth.set(' '.join(['%02x' % x for x in inf.hardware_version.certificate_of_authenticity]))
            else:
                self._cert_of_auth.clear()
        else:
            self._node_id_name[1].disable()
            self._sw_version_crc[0].disable()
            self._sw_version_crc[1].disable()
            self._hw_version_uid[0].disable()
            self._hw_version_uid[1].disable()
            self._cert_of_auth.disable()


class Controls(QGroupBox):
    def __init__(self, parent, node, target_node_id, file_server_widget):
        super(Controls, self).__init__(parent)
        self.setTitle('Node controls')

        self._node = node
        self._target_node_id = target_node_id

        self._restart_button = make_icon_button('power-off', 'Restart the node [uavcan.protocol.RestartNode]', self,
                                                text='Restart', on_clicked=self._do_restart)

        self._update_button = make_icon_button('bug',
                                               'Request firmware update [uavcan.protocol.file.BeginFirmwareUpdate]',
                                               self, text='Update firmware', on_clicked=self._do_firmware_update)

        layout = QHBoxLayout(self)
        layout.addWidget(self._restart_button, 1)
        layout.addWidget(self._update_button, 1)
        self.setLayout(layout)

    def _do_restart(self):
        request = uavcan.protocol.RestartNode.Request(magic_number=uavcan.protocol.RestartNode.Request().MAGIC_NUMBER)
        if not request_confirmation('Confirm node restart',
                                    'Do you really want to send request uavcan.protocol.RestartNode?', self):
            return

        def callback(e):
            if e is None:
                self.window().show_message('Restart request timed out')
            else:
                self.window().show_message('Restart request response: %s', e.response)

        try:
            self._node.request(request, self._target_node_id, callback, priority=REQUEST_PRIORITY)
            self.window().show_message('Restart requested')
        except Exception as ex:
            show_error('Node error', 'Could not send restart request', ex, self)

    def _do_firmware_update(self):
        self.window().show_message('TODO: not implemented!')


class ConfigParams(QGroupBox):
    @staticmethod
    def render_union(u):
        value = getattr(u, uavcan.get_active_union_field(u))
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return round(value, 9)
        if 'uavcan.protocol.param.Empty' in str(value):
            return ''
        return value

    def __init__(self, parent, node, target_node_id):
        super(ConfigParams, self).__init__(parent)
        self.setTitle('Configuration parameters')

        self._node = node
        self._target_node_id = target_node_id

        self._read_all_button = make_icon_button('refresh', 'Fetch all config parameters from the node', self,
                                                 text='Fetch', on_clicked=self._do_reload)

        opcodes = uavcan.protocol.param.ExecuteOpcode.Request()

        self._save_button = \
            make_icon_button('database', 'Commit configuration to the non-volatile storage [OPCODE_SAVE]', self,
                             text='Store', on_clicked=partial(self._do_execute_opcode, opcodes.OPCODE_SAVE))

        self._erase_button = \
            make_icon_button('eraser', 'Clear the non-volatile configuration storage [OPCODE_ERASE]', self,
                             text='Erase', on_clicked=partial(self._do_execute_opcode, opcodes.OPCODE_ERASE))

        self._param_count_label = LabelWithIcon('list', '0', self)
        self._param_count_label.setToolTip('Number of loaded configuration parameters')

        columns = [
            BasicTable.Column('Idx',
                              lambda m: m[0]),
            BasicTable.Column('Name',
                              lambda m: m[1].name,
                              resize_mode=QHeaderView.Stretch),
            BasicTable.Column('Type',
                              lambda m: uavcan.get_active_union_field(m[1].value).replace('_value', '')),
            BasicTable.Column('Value',
                              lambda m: self.render_union(m[1].value),
                              resize_mode=QHeaderView.Stretch),
            BasicTable.Column('Default',
                              lambda m: self.render_union(m[1].default_value)),
            BasicTable.Column('Min',
                              lambda m: self.render_union(m[1].min_value)),
            BasicTable.Column('Max',
                              lambda m: self.render_union(m[1].max_value)),
        ]

        self._table = BasicTable(self, columns, multi_line_rows=True, font=get_monospace_font())

        layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._read_all_button, 1)
        controls_layout.addWidget(self._save_button, 1)
        controls_layout.addWidget(self._erase_button, 1)
        controls_layout.addWidget(self._param_count_label, 0)
        layout.addLayout(controls_layout)
        layout.addWidget(self._table)
        self.setLayout(layout)

    def _on_fetch_response(self, index, e):
        if e is None:
            self.window().show_message('Param fetch failed: request timed out')
            return

        if len(e.response.name) == 0:
            self.window().show_message('%d params fetched successfully', index)
            return

        self._table.setRowCount(self._table.rowCount() + 1)
        self._table.set_row(self._table.rowCount() - 1, (index, e.response))
        self._param_count_label.setText(str(self._table.rowCount()))

        try:
            index += 1
            self.window().show_message('Requesting index %d', index)
            self._node.defer(0.1, lambda: self._node.request(uavcan.protocol.param.GetSet.Request(index=index),
                                                             self._target_node_id,
                                                             partial(self._on_fetch_response, index),
                                                             priority=REQUEST_PRIORITY))
        except Exception as ex:
            logger.error('Param fetch error', exc_info=True)
            self.window().show_message('Could not send param get request: %r', ex)

    def _do_reload(self):
        try:
            index = 0
            self._node.request(uavcan.protocol.param.GetSet.Request(index=index),
                               self._target_node_id,
                               partial(self._on_fetch_response, index),
                               priority=REQUEST_PRIORITY)
        except Exception as ex:
            show_error('Node error', 'Could not send param get request', ex, self)
        else:
            self.window().show_message('Param fetch request sent')
            self._table.setRowCount(0)

    def _do_execute_opcode(self, opcode):
        request = uavcan.protocol.param.ExecuteOpcode.Request(opcode=opcode)
        opcode_str = UAVCANStructInspector(request).field_to_string('opcode', keep_literal=True)

        if not request_confirmation('Confirm opcode execution',
                                    'Do you really want to execute param opcode %s?' % opcode_str, self):
            return

        def callback(e):
            if e is None:
                self.window().show_message('Opcode execution response for %s has timed out', opcode_str)
            else:
                self.window().show_message('Opcode execution response for %s: %s', opcode_str, e.response)

        try:
            self._node.request(request, self._target_node_id, callback, priority=REQUEST_PRIORITY)
            self.window().show_message('Param opcode %s requested', opcode_str)
        except Exception as ex:
            show_error('Node error', 'Could not send param opcode execution request', ex, self)


class NodePropertiesWindow(QDialog):
    def __init__(self, parent, node, target_node_id, file_server_widget, node_monitor):
        super(NodePropertiesWindow, self).__init__(parent)
        self.setWindowTitle('Node Properties [%d]' % target_node_id)
        self.setMinimumWidth(640)

        self._target_node_id = target_node_id
        self._node = node
        self._file_server_widget = file_server_widget

        self._info_box = InfoBox(self, target_node_id, node_monitor)
        self._controls = Controls(self, node, target_node_id, file_server_widget)
        self._config_params = ConfigParams(self, node, target_node_id)

        self._status_bar = QStatusBar(self)
        self._status_bar.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self._info_box)
        layout.addWidget(self._controls)
        layout.addWidget(self._config_params)
        layout.addWidget(self._status_bar)

        left, top, right, bottom = layout.getContentsMargins()
        bottom = 0
        layout.setContentsMargins(left, top, right, bottom)

        self.setLayout(layout)

    def show_message(self, text, *fmt, duration=0):
        self._status_bar.showMessage(text % fmt, duration * 1000)

    @property
    def target_node_id(self):
        return self._target_node_id
