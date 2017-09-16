from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QSpinBox, QSlider, QLabel, QMainWindow, \
    QWidget, QTabWidget, QGroupBox, QCheckBox, QApplication, QAction, QPushButton, QFileDialog,QComboBox, \
    QMenu,QActionGroup,QMessageBox
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QKeySequence, QColor
from logging import getLogger
from ..widgets import make_icon_button, get_icon, get_monospace_font
from .plotter import IPCChannel, MessageTransfer
from .plotter.analysis_plot_container import PlotContainerWidget
from .plotter.plot_areas import PLOT_AREAS
from .plotter.value_extractor import Extractor, Expression
from .plotter.value_extractor_custom import customExtractor
from .plotter.value_extractor_views import ExtractorWidget
from functools import partial
import uavcan
from multiprocessing import Process,Value,Array,Manager
import os
import sys
import time
import datetime
import csv
import serial
import serial.tools.list_ports
from threading import Thread
from queue import  Queue

PLOT_TYPES = ("Acc", "RPM", "Torque", "Thrust", "ESC Power", "Efficiency", "Current")
MESSAGE_TYPE = "uavcan.equipment.esc.Status"
MESSAGES = (
    "msg.error_count", "msg.voltage", "msg.current", "msg.temperature", "msg.rpm", "msg.power_rating_pct",
    "msg.esc_index")
MESSAGES = (
"sensors.acc", "msg.rpm", "sensors.torque", "sensors.thrust", "sensors.esc_power", "sensors.efficiency", "msg.current")
BOARDCAST_INTERVAL = 0.1
RPM_MAX = 3000
RPM_MIN = 0
__all__ = 'analysisManager'
logger = getLogger(__name__)
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

    def set_value(self, rpm):
        print("set value:{}", rpm)
        self._escSlider.setValue(rpm)


class RecordWidget(QWidget):
    def __init__(self, parent, automatic):
        super(RecordWidget, self).__init__(parent)
        self._sampleCount = 0
        self._savePath = "{}/analysisData/log-{}.csv".format(os.getcwd(),
                                                             datetime
                                                             .datetime
                                                             .now()
                                                             .strftime("%Y%m%d_%H%M%S"))
        self._automatic = automatic
        self._getEscInfoCallback = None
        self._getThrustCallback = None
        self._setPlotStyle=None
        self._timestamp = time.time()
        self._initUI()

    def _initUI(self):
        vbox = QVBoxLayout(self)
        self.setLayout(vbox)
        vbox.addWidget(QLabel("Record to CSV file:"))
        hboxBtnGroup = QHBoxLayout(self)

        if self._automatic == False:
            self._takeSampleBtn = QPushButton(get_icon("camera"), "&Take Sample")
            self._takeSampleBtn.clicked.connect(self._takeSample)
            hboxBtnGroup.addWidget(self._takeSampleBtn)
            hboxBtnGroup.addStretch(1)

        self._newLogBtn = QPushButton(get_icon("plus-circle"), "&New Log")
        self._newLogBtn.clicked.connect(self._getNewLogPath)
        hboxBtnGroup.addWidget(self._newLogBtn)
        hboxBtnGroup.addStretch(1)
        self._cleanLogBtn = QPushButton(get_icon("eraser"), "&Clean Log")
        self._cleanLogBtn.clicked.connect(self._cleanLog)
        hboxBtnGroup.addWidget(self._cleanLogBtn)
        vbox.addLayout(hboxBtnGroup)
        self._labelSampleCount = QLabel("{} samples saved in {}".format(self._sampleCount, self._savePath))
        self._labelSampleCount.setWordWrap(True)
        vbox.addWidget(self._labelSampleCount)
        vbox.addStretch(1)



    def _getNewLogPath(self):
        fileDialog = QFileDialog(self)
        fileName = fileDialog.getSaveFileName(self, "Create new Log CSV File", os.getcwd(), "CSV file (*.csv)")
        self._savePath = fileName[0]

    def _cleanLog(self):
        with open(self._savePath,'w') as f:
            f.truncate()
        self._refresh_sample_count(0)

    def _takeSample(self):
        with open(self._savePath, 'a+') as csvfile:
            def isEmpty(file):
                file.seek(0)
                first_char = file.read(1)
                if not first_char:
                    return True
                return False

            fieldKeys = ['Time (s)', 'ESC signal (µs)', 'AccX (g)', 'AccY (g)',
                         'AccZ (g)', 'Voltage (V)', 'Current (A)', 'Torque (N*m)',
                         'Thrust (kgf)', 'Motor Speed (rpm)', 'Electrical Power (W)',
                         'Mechanical Power (W)', 'Motor Efficiency (%)', 'Propeller Mech.Efficiency(kgf/W)',
                         'Overall Efficiency (kgf/W)']
            writer = csv.DictWriter(csvfile, fieldnames=fieldKeys)
            escInfo = self._getEscInfoCallback()
            thrust = self._getThrustCallback()
            if (isEmpty(csvfile)):
                writer.writeheader()
            writer.writerow({'Time (s)': time.time() - self._timestamp,
                             'ESC signal (µs)': '',
                             'AccX (g)': '',
                             'AccY (g)': '',
                             'AccZ (g)': '',
                             'Voltage (V)': escInfo.voltage,
                             'Current (A)': escInfo.current,
                             'Torque (N*m)': '',
                             'Thrust (kgf)': thrust,
                             'Motor Speed (rpm)': escInfo.rpm,
                             'Electrical Power (W)': escInfo.voltage * escInfo.current
                             })
            self._refresh_sample_count(self._sampleCount+1)

    def _refresh_sample_count(self,count):
        self._sampleCount=count
        self._labelSampleCount.setText("{} samples saved in {}".format(self._sampleCount, self._savePath))


class ManualControlPanel(QWidget):
    def __init__(self, parent):
        super(ManualControlPanel, self).__init__(parent)
        self._initUI()

    def _initUI(self):
        self._hbox = QHBoxLayout(self)
        self.setLayout(self._hbox)
        self._escSlider = EscSlider(self)
        self._hbox.addWidget(self._escSlider)
        self._hbox.addStretch()
        self._recordWidget = RecordWidget(self, automatic=False)
        self._hbox.addWidget(self._recordWidget)


class AutomaticControlPanel(QWidget):
    def __init__(self, parent, setValueCallback):
        super(AutomaticControlPanel, self).__init__(parent)
        self._setValue = setValueCallback
        self._initUI()

    def _initUI(self):
        vbox = QVBoxLayout(self)
        hbox = QHBoxLayout(self)
        self._recordWidget = RecordWidget(self, automatic=True)
        vbox.addWidget(self._recordWidget)
        hbox.addLayout(vbox)

        self.setLayout(hbox)

        self._spinbox_step = QSpinBox(self)
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

        self._btn_control = QPushButton()
        self._setCtrBtnType("start")
        vbox.addWidget(self._btn_control)

    def _startTest(self):

        self._step = self._spinbox_step.value()
        start = self._spinbox_start.value()
        end = self._spinbox_end.value()
        period = self._spinbox_period.value()
        self._startTime = time.time()
        self._endtime = self._startTime + (end - start) / self._step * period

        self._testTimer = QTimer(self)
        self._testTimer.start(period * 1e3)
        self._rpm = start
        self._setValue(start)
        self._testTimer.timeout.connect(self._addRpm)
        self._setCtrBtnType("stop")
        self._recordWidget._setPlotStyle(start=True)



    def _stopTest(self):
        self._testTimer.stop()
        self._setValue(0)
        self._setCtrBtnType("start")
        self._recordWidget._setPlotStyle(start=False)

    def _addRpm(self):
        if (time.time() > self._endtime):
            self._stopTest()
            return
        self._rpm += self._step
        self._setValue(self._rpm)

        #
        # Delay for 0.01 second ,to wait for the motor to react.
        #
        self.singleShotTimer = QTimer(self)
        self.singleShotTimer.setSingleShot(True)
        self.singleShotTimer.start(0.5 * 1e3)
        self.singleShotTimer.timeout.connect(lambda: self._recordWidget._takeSample())

    def _setCtrBtnType(self,btnType):
        self._btn_control.setIcon(get_icon("play" if btnType=="start" else "stop"))
        self._btn_control.setText("START" if btnType=="start" else "STOP")
        reconnect(self._btn_control.clicked,self._startTest if btnType=="start" else self._stopTest)




class PlotsWidget(QWidget):
    DEFAULT_INTERVAL = 0.001

    def __init__(self,parent,getTransferCallback):
        super(PlotsWidget, self).__init__(parent)
        self._get_transfer = getTransferCallback
        self._parent=parent

        self._active_data_types = set()
        self._base_time = time.monotonic()
        self._initUI()



    def _initUI(self):

        self._hbox = QHBoxLayout(self)
        self.setLayout(self._hbox)

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
            chkBox.stateChanged.connect(partial(self._addOrDelPlot, type, chkBox))
            hboxPlotTypesChks.addWidget(chkBox)
        #
        # Main plot
        #

        self._vboxPlots.addWidget(self._plotsGroup)
        self._do_add_integrated_plot()

        #
        # Thrust plot
        #
        self._vboxPlots.addWidget(self._plotsGroup)
        self._do_add_thrust_plot()


    def _do_add_integrated_plot(self):

        self._plc = PlotContainerWidget(self, PLOT_AREAS['Efficiency analysis plot'], self._active_data_types,"RPM")
        self._vboxPlots.addWidget(self._plc)

    def _do_add_thrust_plot(self):
        def remove():
            self._plot_containers.remove(self._plc)

        self._plc_thrust = PlotContainerWidget(self, PLOT_AREAS['Thrust plot'], self._active_data_types,"Thrust")
        self._plc_thrust.setHowToLabel("Go to [Config]-->[Thrust Serial Ports] to choose a thrust sensor.","warning")
        self._plc_thrust.on_close = remove

        color = QColor("green")
        expression = Expression("sensors.thrust")
        extractor = customExtractor("custom.data", expression, color)
        def done(extractor):
            self._plc_thrust._extractors.append(extractor)
            def remove():
                print("remove plot")
                self._plc._plot_area.remove_curves_provided_by_extractor(extractor)
                self._plc._extractors.remove(extractor)
        done(extractor)
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

        if self._parent._stop_action.isChecked():
            return

        if not self._parent._pause_action.isChecked():

            tr = self._get_transfer()
            # self._updateBusInfo(tr)
            tr.data_type_name=MESSAGE_TYPE
            tr.source_node_id=1
            self._active_data_types.add(MESSAGE_TYPE)
            try:
                timestamp=tr.transfer.ts_monotonic-self._base_time
                self._plc.setValue(tr.message.rpm)
                self._plc_thrust.process_thrust(timestamp=timestamp,
                                                    value=self._plc_thrust._value)
                self._plc.process_transfer(timestamp=timestamp,
                                               tr=tr)  # process_transfer(timestamp,tr)
            except Exception:
                logger.error('Plot container failed to process a transfer', exc_info=True)

        try:
            self._plc.update()
            self._plc_thrust.update()
        except Exception:
            logger.error('Plot container failed to update', exc_info=True)



    def _addOrDelPlot(self, plotType, chkBox):
        print("add plot:" + plotType)

        def done(extractor):
            self._plc._extractors.append(extractor)

            # widget = ExtractorWidget(self._plc, extractor)
            # self._plc._extractors_layout.addWidget(widget)

            def remove():
                print("remove plot")
                self._plc._plot_area.remove_curves_provided_by_extractor(extractor)
                self._plc._extractors.remove(extractor)
                # self._plc._extractors_layout.removeWidget(widget)
                chkBox.stateChanged.disconnect()
                chkBox.stateChanged.connect(partial(self._addOrDelPlot, plotType, chkBox))
            # widget._type = plotType
            # widget.on_remove = remove
            chkBox.stateChanged.disconnect()
            chkBox.stateChanged.connect(remove)

        e = MESSAGES[PLOT_TYPES.index(plotType)]
        if (e.startswith("msg.")):
            color = QColor("black")
            if (e == "msg.rpm"):
                color = QColor("red")
            expression = Expression(e)
            extractor = Extractor(MESSAGE_TYPE, expression, [], color)
            done(extractor)
        else:
            # todo Add Other Sensor type plot
            color=QColor("black")
            if(e == "sensors.thrust"):
                color=QColor("green")
            expression=Expression(e)
            extractor = customExtractor("custom.data",expression,color)
            done(extractor)

    def setPlotStyle(self,start):
        if not start:
            self._plc_thrust._plot_area.setBackgroundColor(QColor("gray"))
            self._plc._plot_area.setBackgroundColor(QColor("gray"))
        else:
            self._plc_thrust._plot_area.setBackgroundColor(QColor("white"))
            self._plc._plot_area.setBackgroundColor(QColor("white"))


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

        # self.getTransfer=get_transfer_callback
        self._node = node
        self._initUI()
        node.add_handler(uavcan.equipment.esc.Status, self._updateEscInfo)
        self._bcast_timer = QTimer(self)
        self._bcast_timer.start(self.DEFAULT_INTERVAL * 1e3)
        self._bcast_timer.timeout.connect(self._do_broadcast)

        # self._transfer_timer = QTimer(self)
        # self._transfer_timer.setSingleShot(False)
        # self._transfer_timer.start(self.DEFAULT_INTERVAL * 1e3)
        # self._transfer_timer.timeout.connect(self._update)
        self._thrust_timer = QTimer(self)
        self._thrust_timer.start(self.DEFAULT_INTERVAL * 1e3)
        self._thrust_timer.timeout.connect(self._updateThrust)
        self._thrust_port = None
        self._thrust_queue = None
        self._refreshSerialPortsList()

    def _initUI(self):

        #
        # init layout
        #

        self.setGeometry(560, 240, 1000, 500)
        # self.setFixedSize(500, 500
        self.setWindowTitle('Motor Analysis')
        self._mainWidget = QWidget(self)
        # init box layout
        mainHbox = QHBoxLayout(self._mainWidget)
        vboxLeft = QVBoxLayout(self._mainWidget)
        vboxRight = QVBoxLayout(self._mainWidget)
        mainHbox.addLayout(vboxLeft)
        mainHbox.addLayout(vboxRight)

        self._statusGroup = QGroupBox("Sensor Status")
        vboxStatus = QVBoxLayout(self._statusGroup)
        self._statusGroup.setLayout(vboxStatus)
        vboxLeft.addWidget(self._statusGroup)
        self._statusLabel = QLabel('Load info failed.')
        vboxStatus.addWidget(self._statusLabel)

        # fill right column

        self._controlTypeTabs = QTabWidget(self._mainWidget)
        self._manualControlPanel = ManualControlPanel(self._controlTypeTabs)
        self._manualControlPanel._recordWidget._getEscInfoCallback = self._getEscInfo
        self._manualControlPanel._recordWidget._getThrustCallback = self._getThrust

        self._automaticControlPanel = AutomaticControlPanel(self._controlTypeTabs,
                                                            self._manualControlPanel._escSlider.set_value)
        self._automaticControlPanel._recordWidget._getEscInfoCallback = self._getEscInfo
        self._automaticControlPanel._recordWidget._getThrustCallback = self._getThrust


        self._controlTypeTabs.addTab(self._manualControlPanel, "Manual Control")
        self._controlTypeTabs.addTab(self._automaticControlPanel, "Automatic Control")
        vboxRight.addWidget(self._controlTypeTabs)

        self._plotWidget = PlotsWidget(self, self._getTransfer)
        vboxRight.addWidget(self._plotWidget)
        self._automaticControlPanel._recordWidget._setPlotStyle = self._plotWidget.setPlotStyle
        self.setCentralWidget(self._mainWidget)

        #
        # Control menu
        #
        control_menu = self.menuBar().addMenu('Plot &control')

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
        self._reset_time_action.triggered.connect(self._plotWidget._do_reset)
        control_menu.addAction(self._reset_time_action)
        self.setWindowTitle("Motor Status Plots")

        #
        # Config Menu
        #
        config_menu = self.menuBar().addMenu('Con&fig')
        self._thrust_ports_menu = QMenu("Thrust Sensor Ports")
        self._thrust_port_lists = QActionGroup(self)
        config_menu.addMenu(self._thrust_ports_menu)



    def _on_stop_toggled(self, checked):
        self._pause_action.setChecked(False)
        self.statusBar().showMessage('Stopped' if checked else 'Un-stopped')

    def _on_pause_toggled(self, checked):
        self.statusBar().showMessage('Paused' if checked else 'Un-paused')


    def _do_broadcast(self):
        try:
            msg = uavcan.equipment.esc.RPMCommand()
            raw_value = self._manualControlPanel._escSlider.get_value()
            value = raw_value
            msg.rpm.append(int(value))
            self._node.broadcast(msg)
        except Exception as ex:
            logger.info("RPM Message publishing failed:" + str(ex))
            return

    def _updateEscInfo(self, tr):
        self._tr=tr
        self._plotWidget._update()
        self._statusLabel.setText('''
    Voltage   :{}
    Current   :{}
    Thrust    :{}
    Torque    :{}
    Weight    :{}
    MotorSpeed:{}
        '''.format(str(tr.message.voltage)[0:5],
                   str(tr.message.current)[0:5],
                   self._getThrust(),
                   "N/A",
                   "N/A",
                   tr.message.rpm))

    def _getThrust(self):
        return self._plotWidget._plc_thrust._value
    def _getEscInfo(self):
        return self._tr.message

    def _getTransfer(self):
        return self._tr

    def _refreshSerialPortsList(self):
        print("refresh serial ports list")
        ports = list(serial.tools.list_ports.comports())
        self._thrust_ports_menu.clear()
        if(len(ports)==0):
            action=QAction("No Serial Device Found.",self)
            self._thrust_ports_menu.addAction(action)
            return
        for p in ports:
            print("{}:{}".format(p[0],p[1]))
            action=QAction("{}:{}".format(p[0],p[1]),self)
            action.setCheckable(True)
            action.triggered.connect(partial(self._setThrustSerialPort,port=p[0]))
            self._thrust_port_lists.addAction(action)
            self._thrust_ports_menu.addAction(action)

    def _updateThrust(self):
        if (self._thrust_queue != None):
            try:
                thrust = self._thrust_queue.get_nowait()
            except Exception:
                return
            self._plotWidget._plc_thrust.setValue(thrust)

    def _setThrustSerialPort(self,port):
        print(port)
        self._thrust_port=port
        self._plotWidget._plc_thrust.setHowToLabel("Thrust data source successfully set to {}".format(port)
                                                   , "success")
        self._startThrustAcquireLoop()

    def _startThrustAcquireLoop(self):
        def handle_data(data,q):
            if(data!=b'' and data!=b'-' and data!=b'\n'):
                q.put(data.decode().rstrip())


        def read_from_port(ser,q):
            while ser.isOpen():
                msg = ser.read(ser.inWaiting())
                handle_data(msg,q)
                time.sleep(0.1)

        if(self._thrust_port!=None):
            print("set thrust port:{}".format(self._thrust_port))
            arduino = serial.Serial(self._thrust_port, 9600, timeout=5)
            self._thrust_queue=Queue()
            self._thrust_read_thread=Thread(target=read_from_port,args=(arduino,self._thrust_queue))
            self._thrust_read_thread.start()

        else:
            msgbox = QMessageBox(self)
            msgbox.setText("ERROR: Can not configure the thrust device automatically."
                           + "Please select it manually in <Thrust Sensor Ports> menu.")
            msgbox.exec()


class analysisManager:
    def __init__(self, parent, node):
        self._inferiors = []
        self._hook_handle = None
        self._parent = parent
        self._node = node
        self._analysisWindow=None

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
        if self._analysisWindow is None:
            self._analysisWindow = AnalysisMainWindow(parent=self._parent, node=self._node)

        self._analysisWindow.show()
        self._analysisWindow.raise_()
        self._analysisWindow.activateWindow()
        return self._analysisWindow

    def _spawnPlotsWindow(self):

        channel = IPCChannel()
        if self._hook_handle is None:
            self._hook_handle = self._node.add_transfer_hook(self._transfer_hook)
        proc = Process(target=_process_entry_point, name="AnalysisPlotsWindow", args=(channel,self._node))
        proc.daemon = True
        proc.start()
        self._inferiors.append((proc, channel))
        logger.info("Spawned new Analysis process %r", proc)


def _process_entry_point(channel,node):
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

    print(node)
    win = PlotsWindow(get_transfer)
    win.show()
    logger.info("Analysis process %r initialized successfully ,now starting the event loop", os.getpid())
    sys.exit(app.exec_())

def reconnect(signal,newhandler=None):
    try:
        signal.disconnect()
        signal.connect(newhandler)
    except TypeError:
        signal.connect(newhandler)
