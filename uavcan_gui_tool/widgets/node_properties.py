#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
import os
import datetime
from functools import partial
from PyQt5.QtWidgets import QDialog, QGridLayout, QLabel, QLineEdit, QGroupBox, QVBoxLayout, QHBoxLayout, QStatusBar,\
    QHeaderView, QSpinBox, QCheckBox, QFileDialog, QApplication, QPlainTextEdit
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QPalette
from logging import getLogger
from . import get_monospace_font, make_icon_button, BasicTable, show_error, request_confirmation
from .node_monitor import node_health_to_color, node_mode_to_color


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

    def set_background_color(self, color):
        if color is None:
            color = QApplication.palette().color(QPalette.Base)
        palette = QPalette()
        palette.setColor(QPalette.Base, color)
        self.setPalette(palette)


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
            self._mode_health_uptime[0].set(uavcan.value_to_constant_name(entry.status, 'mode', keep_literal=True))
            self._mode_health_uptime[1].set(uavcan.value_to_constant_name(entry.status, 'health', keep_literal=True))
            self._mode_health_uptime[2].set(datetime.timedelta(days=0, seconds=entry.status.uptime_sec))

            self._mode_health_uptime[0].set_background_color(node_mode_to_color(entry.status.mode))
            self._mode_health_uptime[1].set_background_color(node_health_to_color(entry.status.health))

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
    def __init__(self, parent, node, target_node_id, file_server_widget, dynamic_node_id_allocator_widget):
        super(Controls, self).__init__(parent)
        self.setTitle('Node controls')

        self._node = node
        self._target_node_id = target_node_id
        self._file_server_widget = file_server_widget
        self._dynamic_node_id_allocator_widget = dynamic_node_id_allocator_widget

        self._restart_button = make_icon_button('power-off', 'Restart the node [uavcan.protocol.RestartNode]', self,
                                                text='Restart', on_clicked=self._do_restart)

        self._transport_stats_button = make_icon_button('truck',
                                                        'Request transport stats [uavcan.protocol.GetTransportStats]',
                                                        self, text='Get Transport Stats',
                                                        on_clicked=self._do_get_transport_stats)

        self._update_button = make_icon_button('bug',
                                               'Request firmware update [uavcan.protocol.file.BeginFirmwareUpdate]',
                                               self, text='Update Firmware', on_clicked=self._do_firmware_update)

        layout = QHBoxLayout(self)
        layout.addWidget(self._restart_button, 1)
        layout.addWidget(self._transport_stats_button, 1)
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

    def _do_get_transport_stats(self):
        def callback(e):
            if e is None:
                self.window().show_message('Transport stats request timed out')
            else:
                text = uavcan.to_yaml(e.response)
                win = QDialog(self)
                view = QPlainTextEdit(win)
                view.setReadOnly(True)
                view.setFont(get_monospace_font())
                view.setPlainText(text)
                view.setLineWrapMode(QPlainTextEdit.NoWrap)
                layout = QVBoxLayout(win)
                layout.addWidget(view)
                win.setModal(True)
                win.setWindowTitle('Transport stats of node %r' % e.transfer.source_node_id)
                win.setLayout(layout)
                win.show()
        try:
            self._node.request(uavcan.protocol.GetTransportStats.Request(),
                               self._target_node_id, callback, priority=REQUEST_PRIORITY)
            self.window().show_message('Transport stats requested')
        except Exception as ex:
            show_error('Node error', 'Could not send stats request', ex, self)


    def _do_firmware_update(self):
        # Making sure the node is not anonymous
        if self._node.is_anonymous:
            show_error('Cannot request firmware update', 'Local node is anonymous',
                       'Assign a node ID to the local node in order to issue requests (see the main window)', self)
            return

        # Checking if the dynamic node ID allocator is running; warning the user if it doesn't
        if self._dynamic_node_id_allocator_widget.allocator is None:
            if not request_confirmation('Suspicious configuration',
                                        'The local dynamic node ID allocator is not running (see the main window).\n'
                                        'Some nodes will not be able to perform firmware update unless a dynamic node '
                                        'ID allocator is available on the bus.\n'
                                        'Do you want to continue anyway?', self):
                self.window().show_message('Cancelled')
                return

        # Requesting the firmware path
        fw_file = QFileDialog().getOpenFileName(self, 'Select firmware file', '',
                                                'Binary images (*.bin *.uavcan.bin);;All files (*.*)')
        if not fw_file[0]:
            self.window().show_message('Cancelled')
            return
        fw_file = os.path.normcase(os.path.abspath(fw_file[0]))

        # Making sure the file is readable by the process
        try:
            with open(fw_file, 'rb') as f:
                f.read(100)
        except Exception as ex:
            show_error('Bad file', 'Specified firmware file is not readable', ex, self)
            return

        # Configuring the file server
        try:
            self.window().show_message('Configuring the file server...')
            self._file_server_widget.add_path(fw_file)
            self._file_server_widget.force_start()
        except Exception as ex:
            show_error('File server error', 'Could not configure the file server', ex, self)
            return

        remote_fw_file = os.path.basename(fw_file)
        logger.info('Firmware file remote path: %r', remote_fw_file)

        # Sending update requests
        def on_response(e):
            if e is None:
                self.window().show_message('One of firmware update requests has timed out')
            else:
                logger.info('Firmware update response: %s', e.response)
                self.window().show_message('Firmware update response: %s', e.response)
            if e is None or e.response.error != e.response.ERROR_IN_PROGRESS:
                self._node.defer(2, send_request)

        num_remaining_requests = 4

        def send_request():
            nonlocal num_remaining_requests
            if num_remaining_requests > 0:
                num_remaining_requests -= 1
                request = uavcan.protocol.file.BeginFirmwareUpdate.Request(
                    source_node_id=self._node.node_id,
                    image_file_remote_path=uavcan.protocol.file.Path(path=remote_fw_file))
                self.window().show_message('Sending request (%d to go) %s', num_remaining_requests, request)
                try:
                    self._node.request(request, self._target_node_id, on_response, priority=REQUEST_PRIORITY)
                except Exception as ex:
                    show_error('Firmware update error', 'Could not send firmware update request', ex, self)

        send_request()  # Kickstarting the process, it will continue in the background


def get_union_value(u):
    return getattr(u, uavcan.get_active_union_field(u))


def round_float(x):
    return round(x, 9)


def render_union(u):
    value = get_union_value(u)
    if 'boolean' in uavcan.get_active_union_field(u):
        return bool(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round_float(value)
    if 'uavcan.protocol.param.Empty' in str(value):
        return ''
    return value


class ConfigParamEditWindow(QDialog):
    def __init__(self, parent, node, target_node_id, param_struct, update_callback):
        super(ConfigParamEditWindow, self).__init__(parent)
        self.setWindowTitle('Edit configuration parameter')
        self.setModal(True)

        self._node = node
        self._target_node_id = target_node_id
        self._param_struct = param_struct
        self._update_callback = update_callback

        min_val = get_union_value(param_struct.min_value)
        if 'uavcan.protocol.param.Empty' in str(min_val):
            min_val = None

        max_val = get_union_value(param_struct.max_value)
        if 'uavcan.protocol.param.Empty' in str(max_val):
            max_val = None

        value = get_union_value(param_struct.value)
        self._value_widget = None
        value_type = uavcan.get_active_union_field(param_struct.value)

        if value_type == 'integer_value':
            min_val = min_val if min_val is not None else -0x8000000000000000
            max_val = max_val if max_val is not None else 0x7FFFFFFFFFFFFFFF
            if min_val >= -0x800000 and max_val <= 0x7FFFFFFF:
                self._value_widget = QSpinBox(self)
                self._value_widget.setMaximum(max_val)
                self._value_widget.setMinimum(min_val)
                self._value_widget.setValue(value)
        if value_type == 'real_value':
            min_val = round_float(min_val) if min_val is not None else -3.4028235e+38
            max_val = round_float(max_val) if max_val is not None else 3.4028235e+38
            value = round_float(value)
        if value_type == 'boolean_value':
            self._value_widget = QCheckBox(self)
            self._value_widget.setChecked(bool(value))

        if self._value_widget is None:
            self._value_widget = QLineEdit(self)
            self._value_widget.setText(str(value))
        self._value_widget.setFont(get_monospace_font())

        layout = QGridLayout(self)

        def add_const_field(label, *values):
            row = layout.rowCount()
            layout.addWidget(QLabel(label, self), row, 0)
            if len(values) == 1:
                layout.addWidget(FieldValueWidget(self, values[0]), row, 1)
            else:
                sub_layout = QHBoxLayout(self)
                for idx, v in enumerate(values):
                    sub_layout.addWidget(FieldValueWidget(self, v))
                layout.addLayout(sub_layout, row, 1)

        add_const_field('Name', param_struct.name)
        add_const_field('Type', uavcan.get_active_union_field(param_struct.value).replace('_value', ''))
        add_const_field('Min/Max', min_val, max_val)
        add_const_field('Default', render_union(param_struct.default_value))

        layout.addWidget(QLabel('Value', self), layout.rowCount(), 0)
        layout.addWidget(self._value_widget, layout.rowCount() - 1, 1)

        fetch_button = make_icon_button('refresh', 'Read parameter from the node', self, text='Fetch',
                                        on_clicked=self._do_fetch)
        set_default_button = make_icon_button('fire-extinguisher', 'Restore default value', self, text='Restore',
                                              on_clicked=self._restore_default)
        send_button = make_icon_button('flash', 'Send parameter to the node', self, text='Send',
                                       on_clicked=self._do_send)
        cancel_button = make_icon_button('remove', 'Close this window; unsent changes will be lost', self,
                                         text='Cancel', on_clicked=self.close)

        controls_layout = QGridLayout(self)
        controls_layout.addWidget(fetch_button, 0, 0)
        controls_layout.addWidget(send_button, 0, 1)
        controls_layout.addWidget(set_default_button, 1, 0)
        controls_layout.addWidget(cancel_button, 1, 1)
        layout.addLayout(controls_layout, layout.rowCount(), 0, 1, 2)

        self._status_bar = QStatusBar(self)
        self._status_bar.setSizeGripEnabled(False)
        layout.addWidget(self._status_bar, layout.rowCount(), 0, 1, 2)

        left, top, right, bottom = layout.getContentsMargins()
        bottom = 0
        layout.setContentsMargins(left, top, right, bottom)

        self.setLayout(layout)

    def show_message(self, text, *fmt):
        self._status_bar.showMessage(text % fmt)

    def _assign(self, value_union):
        value = get_union_value(value_union)

        if uavcan.get_active_union_field(value_union) == 'real_value':
            value = round_float(value)

        if hasattr(self._value_widget, 'setValue'):
            self._value_widget.setValue(value)
            self._update_callback(value)
        elif hasattr(self._value_widget, 'setChecked'):
            self._value_widget.setChecked(bool(value))
            self._update_callback(bool(value))
        else:
            self._value_widget.setText(str(value))
            self._update_callback(value)

    def _on_response(self, e):
        if e is None:
            self.show_message('Request timed out')
        else:
            logger.info('Param get/set response: %s', e.response)
            self._assign(e.response.value)
            self.show_message('Response received')

    def _restore_default(self):
        self._assign(self._param_struct.default_value)

    def _do_fetch(self):
        try:
            request = uavcan.protocol.param.GetSet.Request(name=self._param_struct.name)
            self._node.request(request, self._target_node_id, self._on_response, priority=REQUEST_PRIORITY)
        except Exception as ex:
            show_error('Node error', 'Could not send param get request', ex, self)
        else:
            self.show_message('Fetch request sent')

    def _do_send(self):
        value_type = uavcan.get_active_union_field(self._param_struct.value)

        try:
            if value_type == 'integer_value':
                if hasattr(self._value_widget, 'value'):
                    value = int(self._value_widget.value())
                else:
                    value = int(self._value_widget.text())
                self._param_struct.value.integer_value = value
            elif value_type == 'real_value':
                value = float(self._value_widget.text())
                self._param_struct.value.real_value = value
            elif value_type == 'boolean_value':
                value = bool(self._value_widget.isChecked())
                self._param_struct.value.boolean_value = value
            elif value_type == 'string_value':
                value = self._value_widget.text()
                self._param_struct.value.string_value = value
            else:
                raise RuntimeError('This is not happening!')
        except Exception as ex:
            show_error('Format error', 'Could not parse value', ex, self)
            return

        try:
            request = uavcan.protocol.param.GetSet.Request(name=self._param_struct.name,
                                                           value=self._param_struct.value)
            logger.info('Sending param set request: %s', request)
            self._node.request(request, self._target_node_id, self._on_response, priority=REQUEST_PRIORITY)
        except Exception as ex:
            show_error('Node error', 'Could not send param set request', ex, self)
        else:
            self.show_message('Set request sent')


class ConfigParams(QGroupBox):
    VALUE_COLUMN = 3

    def __init__(self, parent, node, target_node_id):
        super(ConfigParams, self).__init__(parent)
        self.setTitle('Configuration parameters (double click to change)')

        self._node = node
        self._target_node_id = target_node_id

        self._read_all_button = make_icon_button('refresh', 'Fetch all config parameters from the node', self,
                                                 text='Fetch All', on_clicked=self._do_reload)

        opcodes = uavcan.protocol.param.ExecuteOpcode.Request()

        self._save_button = \
            make_icon_button('database', 'Commit configuration to the non-volatile storage [OPCODE_SAVE]', self,
                             text='Store All', on_clicked=partial(self._do_execute_opcode, opcodes.OPCODE_SAVE))

        self._erase_button = \
            make_icon_button('eraser', 'Clear the non-volatile configuration storage [OPCODE_ERASE]', self,
                             text='Erase All', on_clicked=partial(self._do_execute_opcode, opcodes.OPCODE_ERASE))

        columns = [
            BasicTable.Column('Idx',
                              lambda m: m[0]),
            BasicTable.Column('Name',
                              lambda m: m[1].name,
                              resize_mode=QHeaderView.Stretch),
            BasicTable.Column('Type',
                              lambda m: uavcan.get_active_union_field(m[1].value).replace('_value', '')),
            BasicTable.Column('Value',
                              lambda m: render_union(m[1].value),
                              resize_mode=QHeaderView.Stretch),
            BasicTable.Column('Default',
                              lambda m: render_union(m[1].default_value)),
            BasicTable.Column('Min',
                              lambda m: render_union(m[1].min_value)),
            BasicTable.Column('Max',
                              lambda m: render_union(m[1].max_value)),
        ]

        self._table = BasicTable(self, columns, multi_line_rows=True, font=get_monospace_font())
        self._table.cellDoubleClicked.connect(lambda row, col: self._do_edit_param(row))
        self._table.on_enter_pressed = self._on_cell_enter_pressed

        self._params = []

        layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._read_all_button, 1)
        controls_layout.addWidget(self._save_button, 1)
        controls_layout.addWidget(self._erase_button, 1)
        layout.addLayout(controls_layout)
        layout.addWidget(self._table)
        self.setLayout(layout)

    def _on_cell_enter_pressed(self, list_of_row_col_pairs):
        unique_rows = set([row for row, _col in list_of_row_col_pairs])
        if len(unique_rows) == 1:
            self._do_edit_param(list(unique_rows)[0])

    def _do_edit_param(self, index):
        def update_callback(value):
            self._table.item(index, self.VALUE_COLUMN).setText(str(value))

        win = ConfigParamEditWindow(self, self._node, self._target_node_id, self._params[index], update_callback)
        win.show()

    def _on_fetch_response(self, index, e):
        if e is None:
            self.window().show_message('Param fetch failed: request timed out')
            return

        if len(e.response.name) == 0:
            self.window().show_message('%d params fetched successfully', index)
            return

        self._params.append(e.response)
        self._table.setRowCount(self._table.rowCount() + 1)
        self._table.set_row(self._table.rowCount() - 1, (index, e.response))

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
            self._params = []

    def _do_execute_opcode(self, opcode):
        request = uavcan.protocol.param.ExecuteOpcode.Request(opcode=opcode)
        opcode_str = uavcan.value_to_constant_name(request, 'opcode', keep_literal=True)

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
    def __init__(self, parent, node, target_node_id, file_server_widget, node_monitor,
                 dynamic_node_id_allocator_widget):
        super(NodePropertiesWindow, self).__init__(parent)
        self.setWindowTitle('Node Properties [%d]' % target_node_id)
        self.setMinimumWidth(640)

        self._target_node_id = target_node_id
        self._node = node
        self._file_server_widget = file_server_widget

        self._info_box = InfoBox(self, target_node_id, node_monitor)
        self._controls = Controls(self, node, target_node_id, file_server_widget, dynamic_node_id_allocator_widget)
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
