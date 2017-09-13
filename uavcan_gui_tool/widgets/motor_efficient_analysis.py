from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QSpinBox, QSlider, QLabel, QMainWindow, \
    QWidget, QTabWidget, QGroupBox, QCheckBox, QApplication,QAction,QPushButton,QFileDialog
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QKeySequence,QColor
from logging import getLogger
from ..widgets import make_icon_button, get_icon, get_monospace_font
from .plotter import IPCChannel, MessageTransfer
from .plotter.plot_container import PlotContainerWidget
from .plotter.plot_areas import PLOT_AREAS
from .plotter.value_extractor import Extractor,Expression
from .plotter.value_extractor_views import ExtractorWidget
from functools import partial
import uavcan
import multiprocessing
import os
import sys
import time
import datetime
import csv
import copy

PLOT_TYPES = ("Acc", "RPM", "Torque", "Thrust", "ESC Power", "Efficiency","Current")
MESSAGE_TYPE = "uavcan.equipment.esc.Status"
MESSAGES = (
    "msg.error_count", "msg.voltage", "msg.current", "msg.temperature", "msg.rpm", "msg.power_rating_pct",
    "msg.esc_index")
MESSAGES = ("sensors.acc","msg.rpm","sensors.torque","sensors.thrust","sensors.esc_power","sensors.efficiency","msg.current")
BOARDCAST_INTERVAL = 0.1
RPM_MAX = 3000
RPM_MIN = 0
__all__ = 'analysisManager'
logger = getLogger(__name__)
_singleton = None
node = None

try:
    # noinspection PyUnresolvedReferences
    sys.getwindowsversion()
    RUNNING_ON_WINDOWS = True
except AttributeError:
    RUNNING_ON_WINDOWS = False
    PARENT_PID = os.getppid()


class EscSlider(QWidget):
    def __init__(self, parent):
        super(EscSlider, self).__init__(parent)
        vbox = QVBoxLayout(self)
        self._escSpinbox = QSpinBox(self)
        self._escSpinbox.setMinimum(RPM_MIN)
        self._escSpinbox.setMaximum(RPM_MAX)
        self._escSpinbox.setValue(RPM_MIN)
        self._escSlider = QSlider(Qt.Vertical, self)
        self._escSlider.setMinimum(RPM_MIN)
        self._escSlider.setMaximum(RPM_MAX)
        self._escSlider.setValue(RPM_MIN)
        self._escSlider.setTickInterval(100)
        self._escSlider.valueChanged.connect(lambda: self._escSpinbox.setValue(self._escSlider.value()))
        self._escSpinbox.valueChanged.connect(lambda: self._escSlider.setValue(self._escSpinbox.value()))
        self._zeroButton = make_icon_button('hand-stop-o', 'Zero setpoint', self, on_clicked=self.zero)
        vbox.addWidget(QLabel("ESC"))
        vbox.addWidget(self._escSlider)
        vbox.addWidget(self._escSpinbox)
        vbox.addWidget(self._zeroButton)
        vbox.setAlignment(Qt.AlignCenter)

    def zero(self):
        self._escSlider.setValue(0)

    def get_value(self):
        return self._escSlider.value()

    def set_value(self,rpm):
        print("set value:{}",rpm)
        self._escSlider.setValue(rpm)

class RecordWidget(QWidget):
    def __init__(self,parent,automatic):
        super(RecordWidget, self).__init__(parent)
        self._sampleCount=0
        self._savePath="{}/analysisData/log-{}.csv".format(os.getcwd(),
                                                            datetime
                                                            .datetime
                                                            .now()
                                                            .strftime("%Y%m%d_%H%M%S"))
        self._automatic=automatic
        self._getEscInfoCallback=None
        self._timestamp=time.time()
        self.initUI()

    def initUI(self):
        vbox=QVBoxLayout(self)
        self.setLayout(vbox)

        vbox.addWidget(QLabel("Record to CSV file:"))
        hboxBtnGroup=QHBoxLayout(self)

        if self._automatic==False :

            self._takeSampleBtn = QPushButton(get_icon("camera"), "&Take Sample")
            self._takeSampleBtn.clicked.connect(self._takeSample)
            hboxBtnGroup.addWidget(self._takeSampleBtn)
            hboxBtnGroup.addStretch(1)

        self._newLogBtn=QPushButton(get_icon("plus-circle"),"&New Log")
        self._newLogBtn.clicked.connect(self._getNewLogPath)
        hboxBtnGroup.addWidget(self._newLogBtn)
        hboxBtnGroup.addStretch(1)
        vbox.addLayout(hboxBtnGroup)
        self._labelSampleCount = QLabel("{} samples saved in {}".format(self._sampleCount, self._savePath))
        self._labelSampleCount.setWordWrap(True)
        vbox.addWidget(self._labelSampleCount)
        vbox.addStretch(1)

    def _getNewLogPath(self):
        fileDialog=QFileDialog(self)
        fileName=fileDialog.getSaveFileName(self,"Create new Log CSV File",os.getcwd(),"CSV file (*.csv)")
        self._savePath=fileName[0]

    def _takeSample(self):
        # In
        # rotational
        # mechanical
        # systems
        # power is expressed
        # by
        # torque(T)( if expressed in Pound - Foot) and the
        # angular
        # velocity(V)( if expressed in RPS) as below:
        # P = T * V
        # Foot - Pound / sec……………….Eqn
        # .5
        with open(self._savePath,'a+') as csvfile:
            def isEmpty(file):
                file.seek(0)
                first_char=file.read(1)
                if not first_char:
                    return True
                return False
            fieldKeys=['Time (s)','ESC signal (µs)','AccX (g)','AccY (g)',
                       'AccZ (g)','Voltage (V)','Current (A)','Torgue (N*m)',
                       'Thrust (kgf)','Motor Speed (rpm)','Electrical Power (W)',
                       'Mechanical Power (W)','Motor Efficiency (%)','Propeller Mech.Efficiency(kgf/W)',
                       'Overall Efficiency (kgf/W)']
            writer=csv.DictWriter(csvfile,fieldnames=fieldKeys)
            escInfo=self._getEscInfoCallback()
            if(isEmpty(csvfile)):
                writer.writeheader()
            writer.writerow({'Time (s)':time.time()-self._timestamp,
                             'ESC signal (µs)':'',
                             'AccX (g)':'',
                             'AccY (g)':'',
                             'AccZ (g)':'',
                             'Voltage (V)':escInfo.voltage,
                             'Current (A)':escInfo.current,
                             'Torgue (N*m)':'',
                             'Thrust (kgf)':'',
                             'Motor Speed (rpm)':escInfo.rpm,
                             'Electrical Power (W)':escInfo.voltage*escInfo.current
                             })
            self._sampleCount+=1
            self._labelSampleCount.setText("{} samples saved in {}".format(self._sampleCount, self._savePath))

class ManualControlPanel(QWidget):
    def __init__(self, parent):
        super(ManualControlPanel, self).__init__(parent)
        self.initUI()

    def initUI(self):
        self._hbox = QHBoxLayout(self)
        self.setLayout(self._hbox)
        self._escSlider = EscSlider(self)
        self._hbox.addWidget(self._escSlider)
        self._hbox.addStretch()
        self._recordWidget = RecordWidget(self,automatic=False)
        self._hbox.addWidget(self._recordWidget)


class AutomaticContrlPanel(QWidget):
    def __init__(self,parent,setValueCallback):
        super(AutomaticContrlPanel, self).__init__(parent)
        self._setValue=setValueCallback
        self.initUI()

    def initUI(self):
        vbox=QVBoxLayout(self)
        hbox=QHBoxLayout(self)
        self._recordWidget=RecordWidget(self,automatic=True)
        hbox.addWidget(self._recordWidget)
        hbox.addLayout(vbox)
        self.setLayout(hbox)

        self._spinbox_step=QSpinBox(self)
        self._spinbox_step.setMinimum(10)
        self._spinbox_step.setMaximum(500)
        self._spinbox_step.setValue(100)
        vbox.addWidget(QLabel("Choose RPM increase step:"))
        vbox.addWidget(self._spinbox_step)

        self._spinbox_start = QSpinBox(self)
        self._spinbox_start.setMinimum(10)
        self._spinbox_start.setMaximum(2500)
        self._spinbox_start.setValue(500)
        vbox.addWidget(QLabel("Choose initial starting RPM:"))
        vbox.addWidget(self._spinbox_start)

        self._spinbox_end = QSpinBox(self)
        self._spinbox_end.setMinimum(10)
        self._spinbox_end.setMaximum(5000)
        self._spinbox_end.setValue(2500)
        vbox.addWidget(QLabel("Choose ending RPM:"))
        vbox.addWidget(self._spinbox_end)

        self._spinbox_period = QSpinBox(self)
        self._spinbox_period.setMinimum(0.8)
        self._spinbox_period.setMaximum(100)
        self._spinbox_period.setValue(1)
        vbox.addWidget(QLabel("Choose period:"))
        vbox.addWidget(self._spinbox_period)

        self._btn_control=QPushButton(get_icon("play"),"START")
        self._btn_control.clicked.connect(lambda :self._startTest())
        vbox.addWidget(self._btn_control)

    def _startTest(self):
        self._step = self._spinbox_step.value()
        start = self._spinbox_start.value()
        end = self._spinbox_end.value()
        period = self._spinbox_period.value()
        self._startTime = time.time()
        self._endtime=self._startTime+(end-start)/self._step*period

        self._testTimer = QTimer(self)
        self._testTimer.start(period*1e3)
        self._rpm = start
        self._setValue(start)
        self._testTimer.timeout.connect(self._addRpm)


    def _addRpm(self):
        if(time.time()>self._endtime):
            self._testTimer.stop()
        self._rpm+=self._step
        self._setValue(self._rpm)

        #
        # Delay for 0.01 second waiting for the motor to react.
        #
        self.singleShotTimer=QTimer(self)
        self.singleShotTimer.setSingleShot(True)
        self.singleShotTimer.start(0.5*1e3)
        self.singleShotTimer.timeout.connect(lambda: self._recordWidget._takeSample())




class PlotsWindow(QMainWindow):
    DEFAULT_INTERVAL = 0.1

    def __init__(self, get_transfer_callback):
        super(PlotsWindow, self).__init__()
        self._get_transfer = get_transfer_callback
        self._transfer_timer = QTimer(self)
        self._transfer_timer.setSingleShot(False)
        self._transfer_timer.start(self.DEFAULT_INTERVAL * 1e3)
        self._transfer_timer.timeout.connect(self._update)
        self._active_data_types = set()
        self._base_time = time.monotonic()
        self.initUI()


    def initUI(self):
        self._mainWidget=QWidget()
        self.setCentralWidget(self._mainWidget)
        self._hbox=QHBoxLayout(self)
        self._mainWidget.setLayout(self._hbox)

        #
        # Display data type checkboxs group
        #
        self._plotsGroup = QGroupBox("Real-time plots")
        self._vboxPlots = QVBoxLayout(self)
        self._hbox.addWidget(self._plotsGroup)
        self._plotsGroup.setLayout(self._vboxPlots)
        hboxPlotTypesChks = QHBoxLayout()
        self._vboxPlots.addLayout(hboxPlotTypesChks)
        for type in PLOT_TYPES:
            chkBox = QCheckBox(type)
            chkBox.stateChanged.connect(partial(self._addOrDelPlot,type,chkBox))
            hboxPlotTypesChks.addWidget(chkBox)
        #
        # Main plot
        #

        self._vboxPlots.addWidget(self._plotsGroup)
        self._do_add_integrated_plot('Efficiency analysis plot')

        #
        # Thrust plot
        #
        self._vboxPlots.addWidget(self._plotsGroup)
        self._do_add_thrust_plot('Efficiency analysis plot')

        #
        # Control menu
        #
        control_menu = self.menuBar().addMenu('&Control')

        self._stop_action = QAction(get_icon('stop'), '&Stop Updates', self)
        self._stop_action.setStatusTip('While stopped, all new data will be discarded')
        self._stop_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self._stop_action.setCheckable(True)
        self._stop_action.toggled.connect(self._on_stop_toggled)
        control_menu.addAction(self._stop_action)

        self._pause_action = QAction(get_icon('pause'), '&Pause Updates', self)
        self._pause_action.setStatusTip('While paused, new data will be accumulated in memory '
                                        'to be processed once un-paused')
        self._pause_action.setShortcut(QKeySequence('Ctrl+Shift+P'))
        self._pause_action.setCheckable(True)
        self._pause_action.toggled.connect(self._on_pause_toggled)
        control_menu.addAction(self._pause_action)

        control_menu.addSeparator()

        self._reset_time_action = QAction(get_icon('history'), '&Reset', self)
        self._reset_time_action.setStatusTip('Base time will be reset; all plots will be reset')
        self._reset_time_action.setShortcut(QKeySequence('Ctrl+Shift+R'))
        self._reset_time_action.triggered.connect(self._do_reset)
        control_menu.addAction(self._reset_time_action)
        self.setWindowTitle("Motor Status Plots")





    def _on_stop_toggled(self, checked):
        self._pause_action.setChecked(False)
        self.statusBar().showMessage('Stopped' if checked else 'Un-stopped')

    def _on_pause_toggled(self, checked):
        self.statusBar().showMessage('Paused' if checked else 'Un-paused')

    def _do_add_integrated_plot(self, plot_area_name):
        def remove():
            self._plot_containers.remove(self._plc)

        self._plc = PlotContainerWidget(self, PLOT_AREAS[plot_area_name], self._active_data_types)
        self._plc.on_close = remove
        self._vboxPlots.addWidget(self._plc)

    def _do_add_thrust_plot(self,plot_area_name):
        def remove():
            self._plot_containers.remove(self._plc)

        self._plc_thrust = PlotContainerWidget(self, PLOT_AREAS[plot_area_name], self._active_data_types)
        self._plc_thrust.on_close = remove
        self._vboxPlots.addWidget(self._plc_thrust)

    def _do_reset(self):
        self._base_time = time.monotonic()

        for plc in self._plot_containers:
            try:
                plc.reset()
            except Exception:
                logger.error('Failed to reset plot container', exc_info=True)

        logger.info('Reset done, new time base %r', self._base_time)

    def _update(self):

        if self._stop_action.isChecked():
            while self._get_transfer() is not None:  # Discarding everything
                pass
            return

        if not self._pause_action.isChecked():
            while True:
                tr = self._get_transfer()
                if not tr:
                    break
                # self._updateBusInfo(tr)
                self._active_data_types.add(tr.data_type_name)
                try:
                    self._plc.process_transfer(timestamp=tr.ts_mono - self._base_time,
                                             tr=tr)  # process_transfer(timestamp,tr)
                except Exception:
                    logger.error('Plot container failed to process a transfer', exc_info=True)
        try:
            self._plc.update()
        except Exception:
            logger.error('Plot container failed to update', exc_info=True)

    def _addOrDelPlot(self,plotType,chkBox,state):
        print("add plot:"+plotType)
        expressions=MESSAGES[PLOT_TYPES.index(plotType)]
        if(expressions.startswith("msg.")):
            color=QColor("black")
            if (expressions == "msg.rpm"):
                color=QColor("red")
            expressions=Expression(expressions)
            extractor=Extractor(MESSAGE_TYPE,expressions,[],color)
        else:
            # todo Add Other Sensor type plot
            return
        def done(extractor):
            self._plc._extractors.append(extractor)
            widget = ExtractorWidget(self._plc,extractor)
            self._plc._extractors_layout.addWidget(widget)

            def remove():
                print("remove plot")
                self._plc._plot_area.remove_curves_provided_by_extractor(extractor)
                self._plc._extractors.remove(extractor)
                self._plc._extractors_layout.removeWidget(widget)
                chkBox.stateChanged.disconnect()
                chkBox.stateChanged.connect(partial(self._addOrDelPlot,plotType,chkBox))
            widget._type=plotType
            widget.on_remove=remove
            chkBox.stateChanged.disconnect()
            chkBox.stateChanged.connect(widget._do_remove)

        done(extractor)







class AnalysisWidget(QWidget):
    def __init__(self, parent):
        super(AnalysisWidget, self).__init__(parent)
        self._parent=parent
        self.initUI()

    def initUI(self):
        # init box layout
        mainHbox = QHBoxLayout(self)
        vboxLeft = QVBoxLayout(self)
        vboxRight = QVBoxLayout(self)
        mainHbox.addLayout(vboxLeft)
        mainHbox.addLayout(vboxRight)

        self._statusGroup = QGroupBox("Sensor Status")
        vboxStatus = QVBoxLayout(self)
        self._statusGroup.setLayout(vboxStatus)
        vboxLeft.addWidget(self._statusGroup)
        self._statusLabel = QLabel('Load info failed.')
        vboxStatus.addWidget(self._statusLabel)

        # fill right column
        self._controlTypeTabs = QTabWidget(self)
        self._manualControlPanel = ManualControlPanel(self)
        self._manualControlPanel._recordWidget._getEscInfoCallback=self._parent._getEscInfo
        self._automaticControlPanel = AutomaticContrlPanel(self,self._manualControlPanel._escSlider.set_value)
        self._automaticControlPanel._recordWidget._getEscInfoCallback=self._parent._getEscInfo


        self._controlTypeTabs.addTab(self._manualControlPanel, "Manual Control")
        self._controlTypeTabs.addTab(self._automaticControlPanel, "Automatic Control")
        vboxRight.addWidget(self._controlTypeTabs)



        # fill left column


class AnalysisMainWindow(QMainWindow):
    DEFAULT_INTERVAL = 0.1
    CMD_BIT_LENGTH = uavcan.get_uavcan_data_type(uavcan.equipment.esc.RawCommand().cmd).value_type.bitlen
    CMD_MAX = 2 ** (CMD_BIT_LENGTH - 1) - 1
    CMD_MIN = -(2 ** (CMD_BIT_LENGTH - 1))

    def __init__(self, parent, node):
        super(AnalysisMainWindow, self).__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)  # This is required to stop background timers
        self._inferiors = None
        self._hook_handle = None
        self._bcast_timer = QTimer(self)
        self._bcast_timer.start(self.DEFAULT_INTERVAL * 1e3)
        self._bcast_timer.timeout.connect(self._do_broadcast)
        # self.getTransfer=get_transfer_callback
        self._node = node
        self.setGeometry(560, 240, 600, 500)
        self.setFixedSize(500,500)
        self.setWindowTitle('Motor Analysis')
        self._mainWidget = AnalysisWidget(self)
        self.setCentralWidget(self._mainWidget)
        node.add_handler(uavcan.equipment.esc.Status,self._updateEscInfo)

    def _do_broadcast(self):
        try:
            msg = uavcan.equipment.esc.RPMCommand()
            raw_value = self._mainWidget._manualControlPanel._escSlider.get_value()
            value = raw_value
            msg.rpm.append(int(value))
            self._node.broadcast(msg)
        except Exception as ex:
            # print("RPM Message publishing failed:" + str(ex))
            return

    def _updateEscInfo(self, tr):
        self._escInfo=tr.message
        self._mainWidget._statusLabel.setText('''
    Voltage   :{}
    Current   :{}
    Thrust    :{}
    Torque    :{}
    Weight    :{}
    MotorSpeed:{}
        '''.format(str(tr.message.voltage)[0:5],
                    str(tr.message.current)[0:5],
                    "---",
                    "---",
                    "---",
                    tr.message.rpm))

    def _getEscInfo(self):
        return self._escInfo



class analysisManager:
    def __init__(self, parent, node):
        self._inferiors = []
        self._hook_handle = None
        self._parent = parent
        self._node = node

    def _transfer_hook(self, tr):
        if tr.direction == 'rx' and not tr.service_not_message and len(self._inferiors):
            msg = MessageTransfer(tr)
            for proc, channel in self._inferiors[:]:
                if proc.is_alive():
                    try:
                        channel.send_nonblocking(msg)
                    except Exception:
                        logger.error('Failed to send data to process %r', proc, exc_info=True)
                else:
                    logger.info('Plotter process %r appears to be dead, removing', proc)
                    self._inferiors.remove((proc, channel))


    def _spawnAnalysisWindow(self):
        global _singleton
        logger.info(_singleton)
        if _singleton is None:
            _singleton = AnalysisMainWindow(parent=self._parent, node=self._node)
        _singleton.show()
        _singleton.raise_()
        _singleton.activateWindow()
        return _singleton

    def _spawnPlotsWindow(self):

        channel = IPCChannel()
        if self._hook_handle is None:
            self._hook_handle = self._node.add_transfer_hook(self._transfer_hook)

        proc = multiprocessing.Process(target=_process_entry_point, name="AnalysisPlotsWindow", args=(channel,))
        proc.daemon = True
        proc.start()
        self._inferiors.append((proc, channel))
        logger.info("Spawned new Analysis process %r", proc)


def _process_entry_point(channel):
    IPC_COMMAND_STOP = 'stop'
    logger.info("analysis process started with PID %r", os.getpid())
    app = QApplication(sys.argv)

    def exit_if_should():
        if RUNNING_ON_WINDOWS:
            return False
        else:
            return os.getpid() != PARENT_PID

    exit_check_timer = QTimer()
    exit_check_timer.setSingleShot(False)
    exit_check_timer.timeout.connect(exit_if_should)
    exit_check_timer.start(2000)

    def get_transfer():
        received, obj = channel.receive_nonblocking()
        if received:
            if obj == IPC_COMMAND_STOP:
                logger.info('Plotter process has received a stop request, goodbye')
                app.exit(0)
            else:
                return obj


    # global _singleton
    # if _singleton is None:
    #     _singleton = AnalysisMainWindow(get_transfer)
    # _singleton.show()
    # _singleton.raise_()
    # _singleton.activateWindow()
    win = PlotsWindow(get_transfer)
    win.show()
    logger.info("Analysis process %r initialized successfully ,now starting the event loop", os.getpid())
    sys.exit(app.exec_())

