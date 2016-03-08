#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
import logging
import queue
from PyQt5.QtWidgets import QDialog, QPlainTextEdit, QSpinBox, QHBoxLayout, QVBoxLayout, QComboBox, QCompleter, QLabel
from PyQt5.QtCore import Qt, QTimer
from . import CommitableComboBoxWithHistory, make_icon_button, get_monospace_font, LabelWithIcon, show_error


logger = logging.getLogger(__name__)


def _list_message_data_type_names_with_dtid():
    # Custom data type mappings must be configured in the library
    message_types = []
    for (dtid, kind), dtype in uavcan.DATATYPES.items():
        if dtid is not None and kind == uavcan.dsdl.CompoundType.KIND_MESSAGE:
            message_types.append(str(dtype))
    return list(sorted(message_types))


class SubscriberWindow(QDialog):
    WINDOW_NAME_PREFIX = 'Subscriber'

    def __init__(self, parent, node):
        super(SubscriberWindow, self).__init__(parent)
        self.setWindowTitle(self.WINDOW_NAME_PREFIX)

        self._node = node

        self._message_queue = queue.Queue(1000000)

        self._subscriber_handle = None

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(False)
        self._update_timer.timeout.connect(self._do_redraw)
        self._update_timer.start(100)

        self._log_viewer = QPlainTextEdit(self)
        self._log_viewer.setReadOnly(True)
        self._log_viewer.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._log_viewer.setFont(get_monospace_font())
        self._log_viewer.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        try:
            self._log_viewer.setPlaceholderText('Received messages will be printed here in YAML format')
        except AttributeError:      # Old PyQt
            pass

        self._history_length = QSpinBox(self)
        self._history_length.setToolTip('Number of rows to display; large number will impair performance')
        self._history_length.valueChanged.connect(
            lambda: self._log_viewer.setMaximumBlockCount(self._history_length.value()))
        self._history_length.setMinimum(1)
        self._history_length.setMaximum(1000000)
        self._history_length.setValue(100)

        self._num_received_messages = 0
        self._message_counter_label = LabelWithIcon('newspaper-o', '0', self)
        self._message_counter_label.setToolTip('Total number of received messages since last clear')

        self._type_selector = CommitableComboBoxWithHistory(self)
        self._type_selector.setToolTip('Name of the message type to subscribe to')
        self._type_selector.setInsertPolicy(QComboBox.NoInsert)
        completer = QCompleter(self._type_selector)
        completer.setCaseSensitivity(Qt.CaseSensitive)
        completer.setModel(self._type_selector.model())
        self._type_selector.setCompleter(completer)
        self._type_selector.on_commit = self._do_start
        self._type_selector.setFont(get_monospace_font())
        self._type_selector.addItems(_list_message_data_type_names_with_dtid())
        self._type_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._type_selector.setCurrentText('')

        self._clear_button = make_icon_button('trash-o', 'Clear output', self, on_clicked=self._do_clear,
                                              text='Clear')
        self._start_stop_button = make_icon_button('video-camera', 'Begin subscription', self, checkable=True,
                                                   on_clicked=self._toggle_start_stop, text='Capture')
        self._pause_button = make_icon_button('pause', 'Pause updates, non-displayed messages will be queued in memory',
                                              self, checkable=True, text='Pause')

        layout = QVBoxLayout(self)
        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._start_stop_button, 1)
        controls_layout.addWidget(self._pause_button, 1)
        controls_layout.addWidget(self._clear_button, 1)
        controls_layout.addWidget(QLabel('Rows:'))
        controls_layout.addWidget(self._history_length, 1)
        controls_layout.addWidget(self._message_counter_label, 1)
        layout.addWidget(self._type_selector)
        layout.addLayout(controls_layout)
        layout.addWidget(self._log_viewer, 1)
        self.setLayout(layout)

    def _on_message(self, e):
        try:
            self._message_queue.put_nowait(e)
            self._num_received_messages += 1
        except queue.Full:
            pass

    def _toggle_start_stop(self):
        try:
            if self._subscriber_handle is None:
                self._do_start()
            else:
                self._do_stop()
        finally:
            self._start_stop_button.setChecked(self._subscriber_handle is not None)

    def _do_stop(self):
        if self._subscriber_handle is not None:
            self._subscriber_handle.remove()
            self._subscriber_handle = None

        self._pause_button.setChecked(False)
        self.setWindowTitle(self.WINDOW_NAME_PREFIX)

    def _do_start(self):
        self._do_stop()
        self._do_clear()

        try:
            selected_type = self._type_selector.currentText().strip()
            if not selected_type:
                return
            data_type = uavcan.TYPENAMES[selected_type]
        except Exception as ex:
            show_error('Subscription error', 'Could not load requested data type', ex, self)
            return

        try:
            self._subscriber_handle = self._node.add_handler(data_type, self._on_message)
        except Exception as ex:
            show_error('Subscription error', 'Could not create requested subscription', ex, self)
            return

        self.setWindowTitle('%s [%s]' % (self.WINDOW_NAME_PREFIX, selected_type))
        self._start_stop_button.setChecked(True)

    def _do_redraw(self):
        self._message_counter_label.setText(str(self._num_received_messages))

        if self._pause_button.isChecked():
            return

        self._log_viewer.setUpdatesEnabled(False)
        while True:
            try:
                msg = self._message_queue.get_nowait()
            except queue.Empty:
                break

            try:
                yaml = uavcan.to_yaml(msg)
                self._log_viewer.appendPlainText(yaml + '\n')
            except Exception as ex:
                self._log_viewer.appendPlainText('YAML rendering failed: %r' % ex)

        self._log_viewer.setUpdatesEnabled(True)

    def _do_clear(self):
        self._log_viewer.clear()
        self._num_received_messages = 0
        self._message_counter_label.setText(str(self._num_received_messages))

    def closeEvent(self, qcloseevent):
        try:
            self._subscriber_handle.close()
        except Exception:
            pass
        super(SubscriberWindow, self).closeEvent(qcloseevent)

    @staticmethod
    def spawn(parent, node):
        SubscriberWindow(parent, node).show()
