import string

from pathlib import Path
from typing import Optional

from PyQt5 import QtWidgets
from PyQt5.QtCore import QSize, Qt, QTimer, QRect
from PyQt5.QtGui import QPen, QColor
from PyQt5.Qt import QPainter, QWidget, pyqtSlot, QEvent

from config import Config, ConfigVal

from const import WINDOW_SIZE_X, WINDOW_SIZE_Y
from main import QRSVGLWidget
from state_manager import *

_g_scaling_factor = 1
def update_scaling_factor(app: QtWidgets.QApplication):
    global _g_scaling_factor

    # Make a test label
    alphabet = string.ascii_lowercase[:14]
    test_label = QtWidgets.QLabel(alphabet)
    test_label.setStyleSheet(app.styleSheet())
    test_label.ensurePolished()

    font_height = test_label.fontMetrics().height()

    _g_scaling_factor = font_height / 13

    print("Scaling factor updated to", _g_scaling_factor)

def get_scaling_factor():
    return _g_scaling_factor

def set_target_size(widget: QtWidgets.QWidget):
    base_size = QSize(*widget.SIZE)
    base_size.setWidth(round(base_size.width() * get_scaling_factor()))
    base_size.setHeight(round(base_size.height() * get_scaling_factor()))
    min_size = widget.sizeHint()

    #if widget.layout() is not None:
    #    min_size = widget.layout().sizeHint()
    #    min_size += QSize(widget.layout().spacing(), widget.layout().spacing()) * 2

    size = QSize(max(base_size.width(), min_size.width()), max(base_size.height(), min_size.height()))
    widget.setFixedSize(size)
    widget.resize(size)

class QConfigVal(QWidget):
    FLOAT_SLIDER_PREC = 100

    def __init__(self, name: str, config_val: ConfigVal):
        QWidget.__init__(self)

        self.name = name
        self.config_val = config_val

        self.setAttribute(Qt.WA_StyledBackground)
        self.setAutoFillBackground(True)

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignTop)

        self.label = QtWidgets.QLabel("...")

        self.slider = QtWidgets.QSlider(Qt.Horizontal, self)
        self.slider.setFixedHeight(round(10 * get_scaling_factor()))

        self.float_mode = (config_val.max - config_val.min) < 10

        if self.float_mode:
            self.slider.setRange(0, self.FLOAT_SLIDER_PREC)
            val_frac = (config_val.val - config_val.min) / (config_val.max - config_val.min)
            self.slider.setValue(round(val_frac * self.FLOAT_SLIDER_PREC))
        else:
            self.slider.setRange(round(config_val.min), round(config_val.max))
            self.slider.setValue(round(config_val.val))

        self.slider.valueChanged.connect(self.on_val_changed)

        self.on_val_changed()

        self.layout.addWidget(self.label)
        self.layout.addWidget(self.slider)

    def get_beautified_name(self):
        bname = self.name.replace('_''', ' ').capitalize()
        return bname

    @pyqtSlot()
    def on_val_changed(self):
        if self.float_mode:
            slider_frac = self.slider.value() / self.FLOAT_SLIDER_PREC
            self.config_val.val = self.config_val.min + (self.config_val.max - self.config_val.min) * slider_frac
        else:
            self.config_val.val = self.slider.value()
        self.label.setText(self.get_beautified_name() + ": " + str(self.config_val.val))

class QEditConfigWidget(QWidget):
    SIZE = (300, 500)

    def __init__(self, config: Config):
        QWidget.__init__(self)

        self.setAttribute(Qt.WA_StyledBackground)
        self.setAutoFillBackground(True)

        self.setLayout(QtWidgets.QVBoxLayout(self))

        self.text_label = QtWidgets.QLabel("Settings:\n")
        self.layout().addWidget(self.text_label)

        self.config = config

        self.camera_group = QtWidgets.QGroupBox("Camera")
        self.camera_group_layout = QtWidgets.QVBoxLayout(self)
        self.camera_group.setLayout(self.camera_group_layout)
        self.layout().addWidget(self.camera_group)

        for name, obj in self.config.__dict__.items():
            if isinstance(obj, ConfigVal):
                config_val = obj # type: ConfigVal

                widget = QConfigVal(name, config_val)

                if name.startswith("camera_"):
                    self.camera_group_layout.addWidget(widget)

        self.footer_label = QtWidgets.QLabel("\n(Click outside this area to close settings)")
        # TODO: Kinda hacky, ideally use setDisabled(True) and add disabled color to stylesheet?
        self.footer_label.setStyleSheet("color: gray")
        self.layout().addWidget(self.footer_label)

        set_target_size(self)

    def update(self):
        super().update()

class QUIBarWidget(QWidget):
    SIZE = (150, 100)

    def __init__(self, parent_window):
        QWidget.__init__(self)

        self.config_edit_popup = None

        self.parent_window = parent_window

        self.setAttribute(Qt.WA_StyledBackground)
        self.setAutoFillBackground(True)

        vbox = QtWidgets.QFormLayout()

        self.text_label = QtWidgets.QLabel("...")
        vbox.addWidget(self.text_label)

        self.edit_config_button = QtWidgets.QPushButton("Edit Settings")
        self.edit_config_button.clicked.connect(self.on_edit_config)
        vbox.addWidget(self.edit_config_button)

        self.setLayout(vbox)

        set_target_size(self)

    def update(self):
        super().update()

    @pyqtSlot()
    def on_edit_config(self):
        self.parent_window.toggle_edit_config()

    def set_text(self, text: str):
        self.text_label.setText(text)

class QUIBoostWidget(QWidget):
    FRAME_RATE = 60
    ACTUAL_FRAME_RATE = 1000 / round(1000 / FRAME_RATE)
    BOOST_USAGE_PER_FRAME = (100 / 3) / ACTUAL_FRAME_RATE

    ORANGE_COLOR = QColor(255, 0, 0)
    BLUE_COLOR = QColor(0, 0, 255)

    def __init__(self):
        QWidget.__init__(self)

        self.boost_amount = 0
        self.display_boost = 0    

        vbox = QtWidgets.QFormLayout()
        self.text_label = QtWidgets.QLabel("...")
        self.text_label.setStyleSheet("background: transparent; color: black;")
        vbox.addWidget(self.text_label)
        self.setLayout(vbox)

        self.repaint_timer = QTimer()
        self.repaint_timer.timeout.connect(self.update)
        self.repaint_timer.start(round(1000 / QUIBoostWidget.FRAME_RATE))
    
    def update_boost(self, boost: Optional[int]):
        if boost == self.boost_amount:
            return
        self.text_label.setText(str(boost))
        self.boost_amount = boost
    
    def force_update_boost(self, boost: int):
        self.text_label.setText(str(boost))
        self.display_boost = boost
        self.boost_amount = boost
    
    def do_resize(self, screen_width: int, screen_height: int):
        WIDTH_RATIO = .25
        MAX_WIDTH = 500
        HEIGHT = 40
        PADDING = 70

        sizing = round(min(screen_width * WIDTH_RATIO, MAX_WIDTH)) + PADDING
        self.resize(sizing, HEIGHT + PADDING)
    
    def update_display_boost(self):
        if self.boost_amount is None:
            return

        spectating_car_index = QRSVWindow.get_instance().gl_widget.spectate_idx
        if spectating_car_index == -1:
            return


        if self.boost_amount != math.ceil(self.display_boost):
            is_boosting = global_state_manager.state.car_states[spectating_car_index].is_boosting
            diff = self.boost_amount - self.display_boost

            # Assume car is boosting, display removing at a constant rate
            if is_boosting:
                self.display_boost -= QUIBoostWidget.BOOST_USAGE_PER_FRAME

            if diff > 0 or not is_boosting:
                diff = diff / 5
                self.display_boost += diff
        
        self.display_boost = min(max(self.display_boost, 0), 100)


    def paintEvent(self, event):
        painter = QPainter(self)
        painter.eraseRect(self.rect())
        painter.setRenderHint(QPainter.Antialiasing)

        if self.boost_amount is None:
            return
        self.update_display_boost()

        spectating_car_index = QRSVWindow.get_instance().gl_widget.spectate_idx
        team = global_state_manager.state.car_states[spectating_car_index].team_num
        color = QUIBoostWidget.BLUE_COLOR if team == 0 else QUIBoostWidget.ORANGE_COLOR

        pen = QPen(QColor(255, 255, 255))
        pen.setWidth(4)
        painter.setPen(pen)
        painter.setBrush(QColor(255, 255, 255))

        rect = QRect(10, 10, self.width() - 20, 20)
        painter.drawRoundedRect(rect, 5, 5, mode=Qt.AbsoluteSize)

        painter.setBrush(color)
        rect.setWidth(round(rect.width() * self.display_boost / 100))
        painter.drawRoundedRect(rect, 5, 5, mode=Qt.AbsoluteSize)

        # 1/16th of a degree
        # start_angle = 0
        # span_angle = int((self.boost_amount / 100) * 180 * 16)  # Half circle = 180 degrees

        # painter.drawArc(rect, start_angle, span_angle)

class QRSVWindow(QtWidgets.QMainWindow):
    _instance: "QRSVWindow" = None

    @staticmethod
    def get_instance() -> "QRSVWindow":
        return QRSVWindow._instance

    def __init__(self, gl_widget: "QRSVGLWidget"):
        super().__init__()

        self.setWindowTitle("RocketSimVis")

        path = Path(__file__).parent.resolve() / "qt_style_sheet.css"
        self.setStyleSheet(path.read_text())

        # Set the central widget of the Window.
        self.gl_widget = gl_widget
        self.setCentralWidget(self.gl_widget)

        self.base_layout = QtWidgets.QVBoxLayout(self)

        self.bar_widget = QUIBarWidget(self)
        self.layout().addWidget(self.bar_widget)

        self.edit_config_widget = QEditConfigWidget(self.gl_widget.config)
        self.layout().addWidget(self.edit_config_widget)
        self.edit_config_widget.hide()

        self.boost_widget = QUIBoostWidget()
        self.layout().addWidget(self.boost_widget)

        self.resize(WINDOW_SIZE_X, WINDOW_SIZE_Y)

        self.installEventFilter(self)
        self.centralWidget().installEventFilter(self)

        QRSVWindow._instance = self

    def position_bottom_right(self, widget):
        screen = self.geometry()

        x = screen.width() - widget.width()
        y = screen.height() - widget.height()

        widget.move(x, y)
    
    def resizeEvent(self, event):
        screen = self.geometry()
        self.boost_widget.do_resize(screen.width(), screen.height())
        self.position_bottom_right(self.boost_widget)
        super().resizeEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                press_pos = event.pos()

                # Close config window if we click outside of it
                if self.edit_config_widget.isVisible():
                    if not (press_pos in self.edit_config_widget.geometry()):
                        self.toggle_edit_config()
        elif event.type() == QEvent.KeyPress:
            self.gl_widget.keyPressEvent(event)

        return super().eventFilter(obj, event)

    def toggle_edit_config(self):
        if not self.edit_config_widget.isVisible():
            self.edit_config_widget.show()

            size = self.edit_config_widget.size()

            # Don't exceed our window size
            size.setWidth(min(size.width(), self.width()))
            size.setHeight(min(size.height(), self.height()))

            self.edit_config_widget.setFixedSize(size)

            self.edit_config_widget.setGeometry(
                0, self.bar_widget.height() + 20,
                size.width(), size.width()
            )
        else:
            self.edit_config_widget.hide()
