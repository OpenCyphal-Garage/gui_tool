import logging
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QLabel
from PyQt5.QtCore import Qt
from .. import make_icon_button
from .value_extractor_views import NewValueExtractorWindow, ExtractorWidget


logger = logging.getLogger(__name__)
COLOR_WARNING="red"
COLOR_INFO="blue"
COLOR_SUCCESS="green"

class PlotContainerWidget(QWidget):
    def __init__(self, parent, plot_area_class, active_data_types ,valueName):
        super(PlotContainerWidget, self).__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)              # This is required to stop background timers!
        self._valueName=valueName
        self._value="N/A"
        self._plot_area = plot_area_class(self, display_measurements=self.setWindowTitle)

        self.update = self._plot_area.update
        self.reset = self._plot_area.reset

        self._active_data_types = active_data_types
        self._extractors = []

        # self._new_extractor_button = make_icon_button('plus', 'Add new value extractor', self,
        #                                               on_clicked=self._do_new_extractor)

        self._how_to_label = QLabel('', self)

        hLayoutMain=QHBoxLayout(self)
        self._valueLabel = QLabel("{}:{}".format(self._valueName, self._value))
        hLayoutMain.addWidget(self._valueLabel)
        layout = QVBoxLayout(self)

        layout.addWidget(self._plot_area, 1)

        footer_layout = QHBoxLayout(self)

        # controls_layout = QVBoxLayout(self)
        # # controls_layout.addWidget(self._new_extractor_button)
        # controls_layout.addStretch(1)
        # controls_layout.setContentsMargins(0, 0, 0, 0)
        # footer_layout.addLayout(controls_layout)
        footer_layout.addWidget(self._how_to_label)
        self._extractors_layout = QVBoxLayout(self)
        self._extractors_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addLayout(self._extractors_layout, 1)

        footer_layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(footer_layout)

        hLayoutMain.addLayout(layout)

        self.setLayout(hLayoutMain)
        self.setMinimumWidth(300)
        self.setMinimumHeight(150)

    def _do_new_extractor(self):
        if self._how_to_label is not None:
            self._how_to_label.hide()
            self._how_to_label.setParent(None)
            self._how_to_label.deleteLater()
            self._how_to_label = None

        def done(extractor):
            self._extractors.append(extractor)
            widget = ExtractorWidget(self, extractor)
            self._extractors_layout.addWidget(widget)

            def remove():
                self._plot_area.remove_curves_provided_by_extractor(extractor)
                self._extractors.remove(extractor)
                self._extractors_layout.removeWidget(widget)

            widget.on_remove = remove

        win = NewValueExtractorWindow(self, self._active_data_types)
        win.on_done = done
        win.show()

    def process_transfer(self, timestamp, tr):
        for extractor in self._extractors:
            if(extractor.extraction_expression.source=="sensors.thrust"):
                print("thrust continue")
                continue
            try:
                value = extractor.try_extract(tr)
                if value is None:
                    continue
                self._plot_area.add_value(extractor, timestamp, value)
            except Exception as ex:
                print(ex)
                extractor.register_error()

    def process_thrust(self,timestamp,value):
        for extractor in self._extractors:
            if(extractor.extraction_expression.source=="sensors.thrust"):
                if(value =="N/A"):
                    return
                self._plot_area.add_value(extractor,timestamp,float(value))
                break

    def setValue(self,value):
        if(value!=""):
            # print("set {} Value: {}".format(self._valueName,value))
            self._value=value
            self._valueLabel.setText("{}:{}".format(self._valueName,self._value))

    #
    # style="warning" | "success" | "info"
    #

    def setHowToLabel(self,text,style):
        self._how_to_label.setText(text)
        if(style=="warning"):
            self._how_to_label.setStyleSheet("QLabel {color: %s}"%(COLOR_WARNING))
        elif (style=="success"):
            self._how_to_label.setStyleSheet("QLabel {color: %s}" % (COLOR_SUCCESS))
        elif (style=="info"):
            self._how_to_label.setStyleSheet("QLabel {color: %s}" % (COLOR_INFO))
        else:
            logger.info("Failed to set howToLabel color: Unknown label type.")

    def setStatus(self):
        self._plot_area
