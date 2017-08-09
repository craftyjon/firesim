import logging as log
import os.path

# This is a workaround for a Linux + NVIDIA + PyQt5 bug causing no graphics to be rendered
# because PyQt5 is linking to the wrong libGL.so / NVIDIA isn't overriding the MESA one.
# See: https://bugs.launchpad.net/ubuntu/+source/python-qt4/+bug/941826
from OpenGL import GL

from PyQt5.QtCore import pyqtProperty, pyqtSignal, pyqtSlot, QObject, QUrl, QTimer, QSize
from PyQt5.QtQml import qmlRegisterType, QQmlComponent
from PyQt5.QtQuick import QQuickView
from PyQt5.QtWidgets import QApplication

from ui.canvasview import CanvasView

from lib.config import Config
from models.scene import Scene
from controllers.netcontroller import NetController


class UIState(QObject):
    def __init__(self, parent=None):
        super(UIState, self).__init__(parent)
        self.parent = parent
        self._backdrop_enable = parent.scene.get("backdrop-enable", False)
        self._labels_visible = parent.scene.get("labels-visible", False)
        self._locked = parent.scene.get("locked", False)
        self._center_visible = parent.scene.get("center-visible", False)
        self._blur_enable = parent.scene.get("blur-enable", False)

    backdrop_enable_changed = pyqtSignal()
    labels_visible_changed = pyqtSignal()
    locked_changed = pyqtSignal()
    center_visible_changed = pyqtSignal()
    blur_enable_changed = pyqtSignal()

    @pyqtProperty(bool, notify=backdrop_enable_changed)
    def backdrop_enable(self):
        return self._backdrop_enable

    @backdrop_enable.setter
    def backdrop_enable(self, val):
        if self._backdrop_enable != val:
            self._backdrop_enable = val
            self.backdrop_enable_changed.emit()

    @pyqtProperty(bool, notify=labels_visible_changed)
    def labels_visible(self):
        return self._labels_visible

    @labels_visible.setter
    def labels_visible(self, val):
        if self._labels_visible != val:
            self._labels_visible = val
            self.labels_visible_changed.emit()

    @pyqtProperty(bool, notify=locked_changed)
    def locked(self):
        return self._locked

    @locked.setter
    def locked(self, val):
        if self._locked != val:
            self._locked = val
            self.locked_changed.emit()

    @pyqtProperty(bool, notify=center_visible_changed)
    def center_visible(self):
        return self._center_visible

    @center_visible.setter
    def center_visible(self, val):
        if self._center_visible != val:
            self._center_visible = val
            self.center_visible_changed.emit()

    @pyqtProperty(bool, notify=blur_enable_changed)
    def blur_enable(self):
        return self._blur_enable

    @blur_enable.setter
    def blur_enable(self, val):
        if self._blur_enable != val:
            self._blur_enable = val
            self.blur_enable_changed.emit()


class FireSimGUI(QObject):

    def __init__(self, args=None):
        QObject.__init__(self)

        self.app = QApplication(["FireSim"])
        self.args = args
        self.config = Config("data/config.json")

        if self.args.profile:
            try:
                import yappi
                yappi.start()
            except ImportError:
                log.error("Could not enable YaPPI profiling")

        self.selected_fixture = None
        self.is_blurred = False

        scene_file_path = (self.args.scene if self.args.scene is not None
                           else self.config.get("last-opened-scene"))

        self.scene = Scene(scene_file_path)

        qmlRegisterType(CanvasView, "FireSim", 1, 0, "Canvas")

        self.view = QQuickView()

        self.view.setTitle("FireSim - %s" % self.scene.name)
        self.view.setResizeMode(QQuickView.SizeRootObjectToView)

        self.view.closeEvent = self.on_close

        self.context = self.view.rootContext()
        self.context.setContextProperty('main', self)

        self.state = UIState(self)
        self.context.setContextProperty('App', self.state)

        self.view.setSource(QUrl('ui/qml/FireSimGUI.qml'))

        self.root = self.view.rootObject()
        self.canvas = self.root.findChild(CanvasView)
        self.canvas.gui = self
        self.canvas.model.scene = self.scene

        cw, ch = self.scene.extents
        self.canvas.setWidth(cw)
        self.canvas.setHeight(ch)

        #self.net_thread = QThread()
        #self.net_thread.start()
        self.netcontroller = NetController(self)
        #self.netcontroller.moveToThread(self.net_thread)
        #self.netcontroller.start.emit()

        self.redraw_timer = QTimer()
        self.redraw_timer.setInterval(33)
        self.redraw_timer.timeout.connect(self.canvas.update)
        self.redraw_timer.start()

        self.netcontroller.new_frame.connect(self.canvas.controller.on_new_frame)

        self.view.setMinimumSize(QSize(800, 600))
        self.view.resize(QSize(800, 600))
        self.view.widthChanged.connect(self.canvas.on_resize)
        self.view.heightChanged.connect(self.canvas.on_resize)

        self.view.show()
        #self.view.showFullScreen()
        #self.view.setGeometry(self.app.desktop().availableGeometry())

    @pyqtSlot()
    def quit(self):
        self.app.quit()

    def run(self):
        return self.app.exec_()

    def on_close(self, e):
        self.netcontroller.running = False
        #self.net_thread.quit()
        if self.args.profile:
            try:
                import yappi
                yappi.get_func_stats().print_all()
            except ImportError:
                pass

    @pyqtSlot()
    def on_network_event(self):
        self.canvas.update()

    @pyqtSlot()
    def on_btn_add_fixture(self):
        pass

    @pyqtSlot()
    def on_btn_save(self):
        self.scene.save()
