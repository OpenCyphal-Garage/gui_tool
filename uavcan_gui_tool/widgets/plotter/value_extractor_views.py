#
# Copyright (C) 2016  UAVCAN Development Team  <uavcan.org>
#
# This software is distributed under the terms of the MIT License.
#
# Author: Pavel Kirienko <pavel.kirienko@zubax.com>
#

import uavcan
from PyQt5.QtWidgets import QDialog, QLabel, QHBoxLayout, QGroupBox, QVBoxLayout, QLineEdit, QSpinBox, \
    QColorDialog, QComboBox, QCompleter, QCheckBox
from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtCore import Qt, QStringListModel
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


def _set_button_background(button, color):
    pal = button.palette()
    pal.setColor(QPalette.Button, QColor(color))
    button.setAutoFillBackground(True)
    button.setPalette(pal)
    button.update()


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
        _set_button_background(self._select_color_button, self._selected_color)

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
        dialog = QColorDialog()
        for idx, color in enumerate(DEFAULT_COLORS):
            dialog.setCustomColor(idx, color)

        self._selected_color = dialog.getColor(self._selected_color, self, 'Select line color')
        if self._selected_color.isValid():
            _set_button_background(self._select_color_button, self._selected_color)

    def _update_data_type_list(self):
        if self._show_all_types_button.isChecked():
            items = ActiveDataTypeDetector.get_names_of_all_message_types_with_data_type_id()
        else:
            items = list(sorted(self._active_data_types))
        self._type_selector.clear()
        self._type_selector.addItems(items)
