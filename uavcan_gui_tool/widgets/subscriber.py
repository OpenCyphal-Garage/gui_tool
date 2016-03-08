#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import time
import uavcan
import logging
import queue
from PyQt5.QtWidgets import QWidget, QDialog, QPlainTextEdit, QSpinBox, QHBoxLayout, QVBoxLayout, QComboBox, \
    QCompleter, QLabel
from PyQt5.QtCore import Qt, QTimer
from . import CommitableComboBoxWithHistory, make_icon_button, get_monospace_font, show_error, FilterBar


logger = logging.getLogger(__name__)


def _list_message_data_type_names_with_dtid():
    # Custom data type mappings must be configured in the library
    message_types = []
    for (dtid, kind), dtype in uavcan.DATATYPES.items():
        if dtid is not None and kind == uavcan.dsdl.CompoundType.KIND_MESSAGE:
            message_types.append(str(dtype))
    return list(sorted(message_types))


class QuantityDisplay(QWidget):
    def __init__(self, parent, quantity_name, units_of_measurement):
        super(QuantityDisplay, self).__init__(parent)

        self._label = QLabel('?', self)

        layout = QHBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(QLabel(quantity_name, self))
        layout.addWidget(self._label)
        layout.addWidget(QLabel(units_of_measurement, self))
        layout.addStretch(1)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def set(self, value):
        self._label.setText(str(value))


class RateEstimator:
    def __init__(self, update_interval=0.5, averaging_period=4):
        self._update_interval = update_interval
        self._estimate_lifetime = update_interval * averaging_period
        self._averaging_period = averaging_period
        self._hist = []
        self._checkpoint_ts = 0
        self._events_since_checkpoint = 0
        self._estimate_expires_at = time.monotonic()

    def register_event(self, timestamp):
        self._events_since_checkpoint += 1

        dt = timestamp - self._checkpoint_ts
        if dt >= self._update_interval:
            # Resetting the stat if expired
            mono_ts = time.monotonic()
            expired = mono_ts > self._estimate_expires_at
            self._estimate_expires_at = mono_ts + self._estimate_lifetime
            if expired:
                self._hist = []
            elif len(self._hist) >= self._averaging_period:
                self._hist.pop()
            # Updating the history
            self._hist.insert(0, self._events_since_checkpoint / dt)
            self._checkpoint_ts = timestamp
            self._events_since_checkpoint = 0

    def get_rate_with_timestamp(self):
        if time.monotonic() <= self._estimate_expires_at:
            return (sum(self._hist) / len(self._hist)), self._checkpoint_ts


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

        self._num_rows_spinbox = QSpinBox(self)
        self._num_rows_spinbox.setToolTip('Number of rows to display; large number will impair performance')
        self._num_rows_spinbox.valueChanged.connect(
            lambda: self._log_viewer.setMaximumBlockCount(self._num_rows_spinbox.value()))
        self._num_rows_spinbox.setMinimum(1)
        self._num_rows_spinbox.setMaximum(1000000)
        self._num_rows_spinbox.setValue(100)

        self._num_errors = 0
        self._num_messages_total = 0
        self._num_messages_past_filter = 0

        self._msgs_per_sec_estimator = RateEstimator()

        self._num_messages_total_label = QuantityDisplay(self, 'Total', 'msgs')
        self._num_messages_past_filter_label = QuantityDisplay(self, 'Accepted', 'msgs')
        self._msgs_per_sec_label = QuantityDisplay(self, 'Accepting', 'msgs/sec')

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
        self._type_selector.setFocus(Qt.OtherFocusReason)

        self._active_filter = None
        self._filter_bar = FilterBar(self)
        self._filter_bar.on_filter = self._install_filter

        self._start_stop_button = make_icon_button('video-camera', 'Begin subscription', self, checkable=True,
                                                   on_clicked=self._toggle_start_stop)
        self._pause_button = make_icon_button('pause', 'Pause updates, non-displayed messages will be queued in memory',
                                              self, checkable=True)
        self._clear_button = make_icon_button('trash-o', 'Clear output', self, on_clicked=self._do_clear)

        layout = QVBoxLayout(self)

        controls_layout = QHBoxLayout(self)
        controls_layout.addWidget(self._start_stop_button)
        controls_layout.addWidget(self._pause_button)
        controls_layout.addWidget(self._clear_button)
        controls_layout.addWidget(self._filter_bar.add_filter_button)
        controls_layout.addWidget(self._type_selector, 1)
        controls_layout.addWidget(self._num_rows_spinbox)

        layout.addLayout(controls_layout)
        layout.addWidget(self._filter_bar)
        layout.addWidget(self._log_viewer, 1)

        stats_layout = QHBoxLayout(self)
        stats_layout.addWidget(self._num_messages_total_label)
        stats_layout.addWidget(self._num_messages_past_filter_label)
        stats_layout.addWidget(self._msgs_per_sec_label)
        layout.addLayout(stats_layout)

        self.setLayout(layout)

    def _install_filter(self, f):
        self._active_filter = f

    def _apply_filter(self, yaml_message):
        """This function will throw if the filter expression is malformed!"""
        if self._active_filter is None:
            return True
        return self._active_filter.match(yaml_message)

    def _on_message(self, e):
        # Global statistics
        self._num_messages_total += 1

        # Rendering and filtering
        try:
            text = uavcan.to_yaml(e)
            if not self._apply_filter(text):
                return
        except Exception as ex:
            self._num_errors += 1
            text = '!!! [%d] MESSAGE PROCESSING FAILED: %s' % (self._num_errors, ex)
        else:
            self._num_messages_past_filter += 1
            self._msgs_per_sec_estimator.register_event(e.transfer.ts_monotonic)

        # Sending the text for later rendering
        try:
            self._message_queue.put_nowait(text)
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
        self._num_messages_total_label.set(self._num_messages_total)
        self._num_messages_past_filter_label.set(self._num_messages_past_filter)

        estimated_rate = self._msgs_per_sec_estimator.get_rate_with_timestamp()
        self._msgs_per_sec_label.set('N/A' if estimated_rate is None else ('%.0f' % estimated_rate[0]))

        if self._pause_button.isChecked():
            return

        self._log_viewer.setUpdatesEnabled(False)
        while True:
            try:
                text = self._message_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self._log_viewer.appendPlainText(text + '\n')

        self._log_viewer.setUpdatesEnabled(True)

    def _do_clear(self):
        self._num_messages_total = 0
        self._num_messages_past_filter = 0
        self._do_redraw()
        self._log_viewer.clear()

    def closeEvent(self, qcloseevent):
        try:
            self._subscriber_handle.close()
        except Exception:
            pass
        super(SubscriberWindow, self).closeEvent(qcloseevent)

    @staticmethod
    def spawn(parent, node):
        SubscriberWindow(parent, node).show()
