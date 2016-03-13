#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from PyQt5.QtWidgets import QDialog, QWidget, QLabel, QHBoxLayout, QGroupBox, QVBoxLayout, QLineEdit, QSpinBox, \
    QColorDialog, QComboBox, QCompleter, QCheckBox, QApplication
from PyQt5.QtGui import QColor, QPalette, QFontMetrics
from PyQt5.QtCore import Qt, QStringListModel, QTimer
from .. import make_icon_button, get_monospace_font, CommitableComboBoxWithHistory, show_error
from active_data_type_detector import ActiveDataTypeDetector
from .value_extractor import EXPRESSION_VARIABLE_FOR_MESSAGE, EXPRESSION_VARIABLE_FOR_SRC_NODE_ID, Expression, \
    Extractor


DEFAULT_COLORS = [
    Qt.red, Qt.green, Qt.blue,                        # RGB - http://ux.stackexchange.com/questions/79561
    Qt.yellow, Qt.cyan, Qt.magenta,                   # Close to RGB
]


def _make_expression_completer(owner, data_type):
    model = QStringListModel()
    comp = QCompleter(owner)
    comp.setCaseSensitivity(Qt.CaseSensitive)

    if isinstance(data_type, str):
        data_type = uavcan.TYPENAMES[data_type]

    # TODO: implement proper completion, requires Python lexer
    # TODO: IPython/Jupyter solves the same task splendidly, might make sense to take a closer look at their code
    def make_suggestions(t):
        """Builds a flat list of fields in a given data type"""
        if t.category == t.CATEGORY_COMPOUND:
            out = []
            for a in t.fields + t.constants:
                if (a.type.category != a.type.CATEGORY_COMPOUND) and \
                   (a.type.category != a.type.CATEGORY_VOID) and \
                   (a.type.category != a.type.CATEGORY_ARRAY or
                            a.type.value_type.category == a.type.value_type.CATEGORY_PRIMITIVE):
                    out.append(a.name)
                out += [(a.name + x) for x in make_suggestions(a.type)]
            return [('.' + x) for x in out]
        elif t.category == t.CATEGORY_ARRAY:
            base = '[0]'
            if t.value_type.category == t.CATEGORY_COMPOUND:
                return [(base + x) for x in make_suggestions(t.value_type)]
            else:
                return [base]
        return []

    suggestions = [(EXPRESSION_VARIABLE_FOR_MESSAGE + x) for x in make_suggestions(data_type)]

    model.setStringList(suggestions)
    comp.setModel(model)
    return comp


def _set_color(widget, role, color):
    pal = widget.palette()
    pal.setColor(role, QColor(color))
    widget.setAutoFillBackground(True)
    widget.setPalette(pal)
    widget.update()


def _show_color_dialog(current_color, parent):
    dialog = QColorDialog()
    for idx, color in enumerate(DEFAULT_COLORS):
        dialog.setCustomColor(idx, color)

    current_color = dialog.getColor(current_color, parent, 'Select line color')
    if current_color.isValid():
        return current_color


class DefaultColorRotator:
    def __init__(self):
        self._index = 0

    def get(self):
        return QColor(DEFAULT_COLORS[self._index])

    def rotate(self):
        self._index += 1
        if self._index >= len(DEFAULT_COLORS):
            self._index = 0


class NewValueExtractorWindow(QDialog):
    default_color_rotator = DefaultColorRotator()

    def __init__(self, parent, active_data_types):
        super(NewValueExtractorWindow, self).__init__(parent)
        self.setWindowTitle('New Plot')
        self.setModal(True)

        self._active_data_types = active_data_types
        self.on_done = print

        # Message type selection box
        self._type_selector = CommitableComboBoxWithHistory(self)
        self._type_selector.setToolTip('Name of the message type to plot')
        self._type_selector.setInsertPolicy(QComboBox.NoInsert)
        type_completer = QCompleter(self._type_selector)
        type_completer.setCaseSensitivity(Qt.CaseSensitive)
        type_completer.setModel(self._type_selector.model())
        self._type_selector.setCompleter(type_completer)
        self._type_selector.setFont(get_monospace_font())
        self._type_selector.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self._type_selector.setFocus(Qt.OtherFocusReason)
        self._type_selector.currentTextChanged.connect(self._on_type_changed)

        self._show_all_types_button = make_icon_button('puzzle-piece',
                                                       'Show all known message types, not only those that are '
                                                       'currently being exchanged over the bus',
                                                       self, checkable=True, on_clicked=self._update_data_type_list)

        # Existence is torment.
        self._extraction_expression_box = QLineEdit(self)
        self._extraction_expression_box.setFont(get_monospace_font())
        self._extraction_expression_box.setToolTip('Example: msg.cmd[0] / 16384')

        # Node ID filter
        self._node_id_filter_checkbox = QCheckBox('Accept messages only from specific node', self)
        self._node_id_filter_checkbox.stateChanged.connect(
            lambda: self._node_id_filter_spinbox.setEnabled(self._node_id_filter_checkbox.isChecked()))

        self._node_id_filter_spinbox = QSpinBox(self)
        self._node_id_filter_spinbox.setMinimum(1)
        self._node_id_filter_spinbox.setMaximum(127)
        self._node_id_filter_spinbox.setValue(1)
        self._node_id_filter_spinbox.setEnabled(False)

        # Expression filter
        self._filter_expression_box = QLineEdit(self)
        self._filter_expression_box.setFont(get_monospace_font())
        self._filter_expression_box.setToolTip('Example: msg.esc_index == 3')

        # Visualization options
        self._selected_color = self.default_color_rotator.get()
        self._select_color_button = make_icon_button('paint-brush', 'Select line color', self,
                                                     on_clicked=self._select_color)
        self._select_color_button.setFlat(True)
        _set_color(self._select_color_button, QPalette.Button, self._selected_color)

        # Buttons
        self._ok_button = make_icon_button('check', 'Create new extractor with these settings', self,
                                           text='OK', on_clicked=self._on_ok)

        # Layout
        layout = QVBoxLayout(self)

        msg_type_box = QGroupBox('Message type', self)
        msg_type_box_layout = QHBoxLayout(self)
        msg_type_box_layout.addWidget(self._show_all_types_button)
        msg_type_box_layout.addWidget(self._type_selector, 1)
        msg_type_box.setLayout(msg_type_box_layout)
        layout.addWidget(msg_type_box)

        expr_box = QGroupBox('Expression to plot', self)
        expr_box_layout = QVBoxLayout(self)
        expr_box_layout.addWidget(QLabel('Message is stored in the variable "msg"', self))
        expr_box_layout.addWidget(self._extraction_expression_box)
        expr_box.setLayout(expr_box_layout)
        layout.addWidget(expr_box)

        nid_filter_box = QGroupBox('Node ID filter', self)
        nid_filter_box_layout = QHBoxLayout(self)
        nid_filter_box_layout.addWidget(self._node_id_filter_checkbox)
        nid_filter_box_layout.addWidget(self._node_id_filter_spinbox, 1)
        nid_filter_box.setLayout(nid_filter_box_layout)
        layout.addWidget(nid_filter_box)

        field_filter_box = QGroupBox('Field filter', self)
        field_filter_box_layout = QVBoxLayout(self)
        field_filter_box_layout.addWidget(QLabel('Message is stored in the variable "msg"', self))
        field_filter_box_layout.addWidget(self._filter_expression_box)
        field_filter_box.setLayout(field_filter_box_layout)
        layout.addWidget(field_filter_box)

        vis_box = QGroupBox('Visualization', self)
        vis_box_layout = QHBoxLayout(self)
        vis_box_layout.addWidget(QLabel('Plot line color', self))
        vis_box_layout.addWidget(self._select_color_button)
        vis_box.setLayout(vis_box_layout)
        layout.addWidget(vis_box)

        layout.addWidget(self._ok_button)

        self.setLayout(layout)
        self.setFixedHeight(layout.sizeHint().height())

        # Initialization
        self._update_data_type_list()
        self._on_type_changed()

    def _on_ok(self):
        # Data type name
        data_type_name = self._type_selector.currentText()
        try:
            data_type = uavcan.TYPENAMES[self._type_selector.currentText()]
            if data_type.kind != data_type.KIND_MESSAGE:
                show_error('Invalid configuration', 'Selected data type is not a message type', data_type_name, self)
                return
        except KeyError:
            show_error('Invalid configuration', 'Selected data type does not exist', data_type_name, self)
            return

        # Extraction expression
        try:
            extraction_expression = Expression(self._extraction_expression_box.text())
        except Exception as ex:
            show_error('Invalid configuration', 'Extraction expression is invalid', ex, self)
            return

        # Filter expressions
        filter_expressions = []
        if self._node_id_filter_checkbox.isChecked():
            node_id = self._node_id_filter_spinbox.value()
            filter_expressions.append(
                Expression('%s == %d' % (EXPRESSION_VARIABLE_FOR_SRC_NODE_ID, node_id)))

        if self._filter_expression_box.text().strip():
            try:
                fe = Expression(self._filter_expression_box.text())
            except Exception as ex:
                show_error('Invalid configuration', 'Filter expression is invalid', ex, self)
                return
            filter_expressions.append(fe)

        # Visualization
        color = self._selected_color

        # Finally!
        extractor = Extractor(data_type_name, extraction_expression, filter_expressions, color)
        self.on_done(extractor)

        # Suicide
        self.setParent(None)
        self.deleteLater()
        self.close()

    def _on_type_changed(self):
        try:
            data_type = uavcan.TYPENAMES[self._type_selector.currentText()]
            if data_type.kind != data_type.KIND_MESSAGE:
                return
        except KeyError:
            return

        if len(data_type.fields):
            self._extraction_expression_box.setText(
                '%s.%s' % (EXPRESSION_VARIABLE_FOR_MESSAGE, data_type.fields[0].name))
        else:
            self._extraction_expression_box.clear()

        self._extraction_expression_box.setCompleter(
            _make_expression_completer(self._extraction_expression_box, data_type))

        self._filter_expression_box.clear()
        self._filter_expression_box.setCompleter(
            _make_expression_completer(self._filter_expression_box, data_type))

    def _select_color(self):
        col = _show_color_dialog(self._selected_color, self)
        if col:
            self._selected_color = col
            _set_color(self._select_color_button, QPalette.Button, self._selected_color)

    def _update_data_type_list(self):
        if self._show_all_types_button.isChecked():
            items = ActiveDataTypeDetector.get_names_of_all_message_types_with_data_type_id()
        else:
            items = list(sorted(self._active_data_types))
        self._type_selector.clear()
        self._type_selector.addItems(items)


class ExtractorWidget(QWidget):
    def __init__(self, parent, model):
        super(ExtractorWidget, self).__init__(parent)

        self.on_remove = lambda: None

        self._model = model

        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(False)
        self._update_timer.timeout.connect(self._update)
        self._update_timer.start(200)

        self._delete_button = make_icon_button('trash-o', 'Remove this extractor', self, on_clicked=self._do_remove)

        self._color_button = make_icon_button('paint-brush', 'Change plot color', self, on_clicked=self._change_color)
        self._color_button.setFlat(True)
        _set_color(self._color_button, QPalette.Button, model.color)

        self._extraction_expression_box = QLineEdit(self)
        self._extraction_expression_box.setToolTip('Extraction expression')
        self._extraction_expression_box.setFont(get_monospace_font())
        self._extraction_expression_box.setText(model.extraction_expression.source)
        self._extraction_expression_box.textChanged.connect(self._on_extraction_expression_changed)
        self._extraction_expression_box.setCompleter(
            _make_expression_completer(self._extraction_expression_box, model.data_type_name))

        self._error_label = make_icon_button('warning', 'Extraction error count; click to reset', self,
                                             on_clicked=self._reset_errors)
        self._reset_errors()

        def box(text, tool_tip):
            w = QLineEdit(self)
            w.setReadOnly(True)
            w.setFont(get_monospace_font())
            w.setText(str(text))
            w.setToolTip(tool_tip)
            fm = QFontMetrics(w.font())
            magic_number = 10
            text_size = fm.size(0, w.text())
            w.setMinimumWidth(text_size.width() + magic_number)
            return w

        layout = QHBoxLayout(self)
        layout.addWidget(self._delete_button)
        layout.addWidget(self._color_button)
        layout.addWidget(box(model.data_type_name, 'Message type name'))
        layout.addWidget(box(' AND '.join([x.source for x in model.filter_expressions]), 'Filter expressions'))
        layout.addWidget(self._extraction_expression_box, 1)
        layout.addWidget(self._error_label)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def _on_extraction_expression_changed(self):
        text = self._extraction_expression_box.text()
        try:
            expr = Expression(text)
            self._extraction_expression_box.setPalette(QApplication.palette())
        except Exception:
            _set_color(self._extraction_expression_box, QPalette.Base, Qt.red)
            return

        self._model.extraction_expression = expr

    def _change_color(self):
        col = _show_color_dialog(self._model.color, self)
        if col:
            self._model.color = col
            _set_color(self._color_button, QPalette.Button, self._model.color)

    def _update(self):
        self._error_label.setText(str(self._model.error_count))

    def _reset_errors(self):
        self._model.reset_error_count()
        self._update()

    def _do_remove(self):
        self.on_remove()
        self._update_timer.stop()
        self.setParent(None)
        self.close()
        self.deleteLater()
