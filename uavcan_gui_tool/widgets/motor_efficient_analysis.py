

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from logging import getLogger

PLOT_TYPES = ("Acc", "RPM", "Torque", "Thrust", "ESC Power", "Efficiency")

class AnalysisWidget(QWidget):
    def __init__(self,parent):
        super().__init__(parent)
        self.initUI()
    def initUI(self):
        # init box layout
        mainHbox = QHBoxLayout(self)
        vboxLeft = QVBoxLayout(self)
        vboxRight = QVBoxLayout(self)
        mainHbox.addLayout(vboxLeft)
        mainHbox.addLayout(vboxRight)

        # fill right column
        controlTypeTabs = QTabWidget(self)
        controlTypeTabs.addTab(QLabel("tab1"), "Manual Control")
        controlTypeTabs.addTab(QLabel("tab2"), "Automatic Control")
        vboxRight.addWidget(controlTypeTabs)

        plotsGroup = QGroupBox("Real-time plots")
        hboxPlotTypes = QHBoxLayout()
        plotTypeChks = [QCheckBox(type) for type in PLOT_TYPES]
        for chkbox in plotTypeChks:
            print(chkbox)
            hboxPlotTypes.addWidget(chkbox)
        plotsGroup.setLayout(hboxPlotTypes)
        vboxRight.addWidget(plotsGroup)
        # fill left column


class AnalysisMainWindow(QMainWindow):
    def __init__(self,parent):
        super(AnalysisMainWindow,self).__init__(parent)
        self.setGeometry(560, 240, 800, 600)
        self.setMinimumWidth(500)
        self.setMinimumHeight(500)
        self.setWindowTitle('Motor Analysis')
        mainWidget=AnalysisWidget(self)
        self.setCentralWidget(mainWidget)




