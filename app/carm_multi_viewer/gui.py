import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QPushButton, QFileDialog,
                             QSlider, QFrame, QScrollArea, QStatusBar,
                             QSplitter, QComboBox, QGroupBox, QLineEdit, QMessageBox)
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor
from PyQt5.QtCore import Qt, QSize, pyqtSlot, QThread, pyqtSignal
import serial
import serial.tools.list_ports
import time
import datetime

from carm_multi_viewer.models import ImageFrame
from carm_multi_viewer.detector import get_reader
from carm_multi_viewer.processors import to_display_8bit, apply_filter, FILTER_NAMES
from carm_multi_viewer.usb_detector import USBDeviceListener


# ── Worker Threads ────────────────────────────────────────────────────────────

class LiveCaptureThread(QThread):
    frame_ready = pyqtSignal(np.ndarray)
    error_occurred = pyqtSignal(str)

    def __init__(self, camera_index=0):
        super().__init__()
        self.camera_index = camera_index
        self.running = True

    def run(self):
        cap = cv2.VideoCapture(self.camera_index)
        if not cap.isOpened():
            self.error_occurred.emit(f"Could not open camera {self.camera_index}")
            return
        while self.running:
            ret, frame = cap.read()
            if ret:
                self.frame_ready.emit(frame)
            else:
                break
            self.msleep(30)
        cap.release()

    def stop(self):
        self.running = False
        self.wait()


class SerialReaderThread(QThread):
    data_received = pyqtSignal(bytes)
    status_changed = pyqtSignal(str)

    def __init__(self, port, baud):
        super().__init__()
        self.port = port
        self.baud = baud
        self.running = True
        self.ser = None

    def run(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            self.status_changed.emit(f"Connected to {self.port} at {self.baud}")
            while self.running:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(self.ser.in_waiting)
                    self.data_received.emit(data)
                self.msleep(10)
        except Exception as e:
            self.status_changed.emit(f"Serial Error: {str(e)}")
        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()


class AutoBaudScanner(QThread):
    baud_detected = pyqtSignal(int)
    scan_status = pyqtSignal(str)

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.bauds = [9600, 19200, 38400, 57600, 115200]

    def run(self):
        for baud in self.bauds:
            self.scan_status.emit(f"Scanning at {baud}...")
            try:
                ser = serial.Serial(self.port, baud, timeout=1)
                start_time = time.time()
                while time.time() - start_time < 1.5:
                    if ser.in_waiting > 0:
                        ser.close()
                        self.baud_detected.emit(baud)
                        return
                ser.close()
            except:
                continue
        self.scan_status.emit("Auto-Baud failed (no data detected)")


# ── Image Viewer Widget ───────────────────────────────────────────────────────

class ImageViewer(QLabel):
    """Custom Label for displaying images with Zoom capability. Supports grayscale and color."""
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #000000;")
        self.setMinimumSize(300, 300)
        self.pixmap_data = None
        self.zoom_factor = 1.0

    def set_image(self, img: np.ndarray):
        """Accepts either (H,W) grayscale or (H,W,3) RGB uint8 array."""
        if img.ndim == 2:
            # Grayscale
            h, w = img.shape
            q_img = QImage(img.data, w, h, w, QImage.Format_Grayscale8)
        else:
            # Color (H, W, 3) RGB
            h, w, ch = img.shape
            q_img = QImage(img.data, w, h, ch * w, QImage.Format_RGB888)
        self.pixmap_data = QPixmap.fromImage(q_img.copy())
        self.update_display()

    def update_display(self):
        if self.pixmap_data:
            w = int(self.pixmap_data.width() * self.zoom_factor)
            h = int(self.pixmap_data.height() * self.zoom_factor)
            self.setPixmap(self.pixmap_data.scaled(w, h, Qt.KeepAspectRatio, Qt.FastTransformation))

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom_factor = min(self.zoom_factor * 1.1, 8.0)
        else:
            self.zoom_factor = max(self.zoom_factor / 1.1, 0.1)
        self.update_display()


# ── Single View Panel (viewer + per-panel filter controls) ────────────────────

class ViewPanel(QWidget):
    """One side of the dual-view. Contains an ImageViewer and its own filter controls."""
    params_changed = pyqtSignal()

    def __init__(self, title="View A"):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Panel header
        header = QLabel(title)
        header.setAlignment(Qt.AlignCenter)
        header.setStyleSheet("""
            font-size: 13px; font-weight: bold; color: #0078D4;
            background: #1A1A2E; padding: 6px; border-radius: 4px;
        """)
        layout.addWidget(header)

        # Image viewer in scroll area
        self.viewer = ImageViewer()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.viewer)
        scroll.setStyleSheet("border: none; background-color: #000;")
        layout.addWidget(scroll, stretch=1)

        # ── Filter Controls ──
        ctrl_box = QGroupBox("Filter Controls")
        ctrl_box.setStyleSheet("""
            QGroupBox { color: #AAA; border: 1px solid #333; border-radius: 4px;
                        margin-top: 8px; padding-top: 8px; font-size: 11px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; }
        """)
        ctrl_layout = QVBoxLayout(ctrl_box)
        ctrl_layout.setSpacing(4)

        # Filter dropdown
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(FILTER_NAMES)
        self.filter_combo.currentIndexChanged.connect(self.params_changed)
        filter_row.addWidget(self.filter_combo)
        ctrl_layout.addLayout(filter_row)

        # Window Level
        wl_row = QHBoxLayout()
        wl_row.addWidget(QLabel("W.Level:"))
        self.slider_level = QSlider(Qt.Horizontal)
        self.slider_level.setRange(0, 255)
        self.slider_level.setValue(127)
        self.slider_level.valueChanged.connect(self.params_changed)
        wl_row.addWidget(self.slider_level)
        self.lbl_level = QLabel("127")
        self.lbl_level.setFixedWidth(30)
        self.slider_level.valueChanged.connect(lambda v: self.lbl_level.setText(str(v)))
        wl_row.addWidget(self.lbl_level)
        ctrl_layout.addLayout(wl_row)

        # Window Width
        ww_row = QHBoxLayout()
        ww_row.addWidget(QLabel("W.Width:"))
        self.slider_width = QSlider(Qt.Horizontal)
        self.slider_width.setRange(1, 1024)
        self.slider_width.setValue(255)
        self.slider_width.valueChanged.connect(self.params_changed)
        ww_row.addWidget(self.slider_width)
        self.lbl_width = QLabel("255")
        self.lbl_width.setFixedWidth(35)
        self.slider_width.valueChanged.connect(lambda v: self.lbl_width.setText(str(v)))
        ww_row.addWidget(self.lbl_width)
        ctrl_layout.addLayout(ww_row)

        layout.addWidget(ctrl_box)

    def get_filter_name(self):
        return self.filter_combo.currentText()

    def get_window_level(self):
        return self.slider_level.value()

    def get_window_width(self):
        return self.slider_width.value()

    def render_frame(self, source_pixels: np.ndarray, bit_depth: int):
        """Apply windowing + selected filter and display."""
        wc = self.get_window_level()
        ww = self.get_window_width()

        if bit_depth > 8:
            wc *= 256
            ww *= 256

        img_8bit = to_display_8bit(source_pixels, wc, ww)
        img_final = apply_filter(img_8bit, self.get_filter_name())
        self.viewer.set_image(img_final)


# ── Main Window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Antigravity C-arm Multi Viewer — Dual View")
        self.resize(1400, 900)

        self.current_frame: ImageFrame = None
        self.serial_thread = None
        self.baud_scanner = None
        self.live_thread = None
        self.last_live_frame = None

        self.init_ui()
        self.init_usb_listener()
        self.refresh_com_ports()

    def init_ui(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #0D0D0D; }
            QWidget { background-color: #0D0D0D; color: #E0E0E0; font-family: 'Segoe UI', sans-serif; font-size: 12px; }
            QFrame#Sidebar { background-color: #1A1A1A; border-right: 1px solid #2A2A2A; }
            QPushButton {
                background-color: #252525; border: 1px solid #353535;
                padding: 8px 12px; border-radius: 5px; color: #DDD;
            }
            QPushButton:hover { background-color: #353535; border-color: #0078D4; }
            QPushButton#Primary { background-color: #0078D4; border: none; font-weight: bold; }
            QPushButton#Primary:hover { background-color: #0090FF; }
            QPushButton#Danger { background-color: #C62828; border: none; font-weight: bold; }
            QPushButton#Danger:hover { background-color: #E53935; }
            QLabel#SideTitle { font-size: 16px; font-weight: bold; color: #0078D4; }
            QSlider::groove:horizontal { height: 4px; background: #333; border-radius: 2px; }
            QSlider::handle:horizontal { background: #0078D4; border-radius: 5px; width: 12px; height: 12px; margin: -4px 0; }
            QComboBox { background: #252525; border: 1px solid #353535; padding: 4px; border-radius: 4px; }
            QComboBox::drop-down { border: none; }
            QLineEdit { background: #252525; border: 1px solid #353535; padding: 5px; border-radius: 4px; color: #FFF; }
            QGroupBox { color: #888; border: 1px solid #2A2A2A; border-radius: 5px; margin-top: 8px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(260)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(12, 16, 12, 16)
        sb.setSpacing(8)

        title = QLabel("C-ARM VIEWER")
        title.setObjectName("SideTitle")
        title.setAlignment(Qt.AlignCenter)
        sb.addWidget(title)

        sub = QLabel("Dual View Comparison Mode")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("color: #666; font-size: 10px;")
        sb.addWidget(sub)

        sb.addSpacing(8)

        btn_open = QPushButton("📁  Open File")
        btn_open.clicked.connect(self.on_open_file)
        sb.addWidget(btn_open)

        btn_usb = QPushButton("🔌  Scan USB Devices")
        btn_usb.clicked.connect(self.on_scan_usb)
        sb.addWidget(btn_usb)

        sb.addSpacing(6)

        self.btn_live = QPushButton("🔴  START LIVE FEED")
        self.btn_live.setObjectName("Primary")
        self.btn_live.clicked.connect(self.toggle_live_feed)
        sb.addWidget(self.btn_live)

        self.btn_capture = QPushButton("📸  CAPTURE FRAME")
        self.btn_capture.setObjectName("Danger")
        self.btn_capture.setEnabled(False)
        self.btn_capture.clicked.connect(self.on_capture_frame)
        sb.addWidget(self.btn_capture)

        sb.addSpacing(10)

        # Patient Info
        pi_box = QGroupBox("Patient Information")
        pi = QVBoxLayout(pi_box)
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("Patient Name")
        pi.addWidget(self.input_name)
        self.input_id = QLineEdit()
        self.input_id.setPlaceholderText("Patient ID")
        pi.addWidget(self.input_id)
        sb.addWidget(pi_box)

        sb.addSpacing(8)

        # Metadata
        meta_box = QGroupBox("Image Metadata")
        meta_layout = QVBoxLayout(meta_box)
        self.metadata_label = QLabel("—")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setStyleSheet("color: #999; font-size: 10px;")
        meta_layout.addWidget(self.metadata_label)
        sb.addWidget(meta_box)

        sb.addSpacing(8)

        # Serial
        ser_box = QGroupBox("Serial Connectivity")
        ser_l = QVBoxLayout(ser_box)
        com_row = QHBoxLayout()
        self.com_combo = QComboBox()
        com_row.addWidget(self.com_combo)
        btn_ref = QPushButton("🔄")
        btn_ref.setFixedWidth(36)
        btn_ref.clicked.connect(self.refresh_com_ports)
        com_row.addWidget(btn_ref)
        ser_l.addLayout(com_row)

        baud_row = QHBoxLayout()
        baud_row.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["AUTO", "9600", "115200", "38400", "57600"])
        baud_row.addWidget(self.baud_combo)
        ser_l.addLayout(baud_row)

        self.btn_serial = QPushButton("🔗  Connect Serial")
        self.btn_serial.clicked.connect(self.toggle_serial)
        ser_l.addWidget(self.btn_serial)
        sb.addWidget(ser_box)

        sb.addStretch()

        btn_chart = QPushButton("📖  Exposure Chart")
        btn_chart.clicked.connect(self.show_reference)
        sb.addWidget(btn_chart)

        btn_kiosk = QPushButton("📺  Fullscreen")
        btn_kiosk.setCheckable(True)
        btn_kiosk.clicked.connect(self.toggle_kiosk)
        sb.addWidget(btn_kiosk)

        btn_shutdown = QPushButton("🛑  System Shutdown")
        btn_shutdown.setStyleSheet("color: #FF5252;")
        btn_shutdown.clicked.connect(self.system_shutdown)
        sb.addWidget(btn_shutdown)

        root_layout.addWidget(sidebar)

        # ── Dual View Area ────────────────────────────────────────────────────
        self.panel_a = ViewPanel("◀  VIEW A")
        self.panel_b = ViewPanel("VIEW B  ▶")

        # Connect filter changes to re-render
        self.panel_a.params_changed.connect(self.refresh_display)
        self.panel_b.params_changed.connect(self.refresh_display)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.panel_a)
        splitter.addWidget(self.panel_b)
        splitter.setSizes([600, 600])
        splitter.setHandleWidth(6)
        splitter.setStyleSheet("QSplitter::handle { background: #2A2A2A; }")

        root_layout.addWidget(splitter, stretch=1)

        # Status bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready — Open a file or start live feed")

    def init_usb_listener(self):
        self.usb_listener = USBDeviceListener()
        self.usb_listener.device_arrived.connect(self.on_usb_arrived)

    @pyqtSlot(str)
    def on_usb_arrived(self, drive_path):
        self.statusBar.showMessage(f"USB Detected: {drive_path}. Scanning...", 5000)
        for root, dirs, files in os.walk(drive_path):
            for file in files:
                full_path = os.path.join(root, file)
                reader = get_reader(full_path)
                if reader:
                    self.load_image(full_path)
                    return

    def refresh_display(self):
        """Re-render both panels with current frame and their individual filters."""
        if self.current_frame is None:
            return
        self.panel_a.render_frame(self.current_frame.pixels, self.current_frame.bit_depth)
        self.panel_b.render_frame(self.current_frame.pixels, self.current_frame.bit_depth)

    def toggle_live_feed(self):
        if self.live_thread and self.live_thread.isRunning():
            self.live_thread.stop()
            self.live_thread = None
            self.btn_live.setText("🔴  START LIVE FEED")
            self.btn_capture.setEnabled(False)
            self.statusBar.showMessage("Live feed stopped")
        else:
            self.live_thread = LiveCaptureThread(0)
            self.live_thread.frame_ready.connect(self.on_live_frame)
            self.live_thread.error_occurred.connect(lambda msg: self.statusBar.showMessage(msg))
            self.live_thread.start()
            self.btn_live.setText("⏹  STOP LIVE FEED")
            self.btn_capture.setEnabled(True)
            self.statusBar.showMessage("Live feed active — dual view rendering")

    def on_live_frame(self, frame):
        self.last_live_frame = frame
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Create a temp ImageFrame from the live grayscale frame
        temp = ImageFrame(
            pixels=gray, width=gray.shape[1], height=gray.shape[0],
            bit_depth=8, source_format="LIVE", metadata={}
        )
        self.current_frame = temp
        self.refresh_display()

    def on_capture_frame(self):
        if self.last_live_frame is not None:
            gray = cv2.cvtColor(self.last_live_frame, cv2.COLOR_BGR2GRAY)
            self.current_frame = ImageFrame(
                pixels=gray, width=gray.shape[1], height=gray.shape[0],
                bit_depth=8, source_format="LIVE_CAPTURE",
                metadata={
                    "PatientName": self.input_name.text(),
                    "PatientID": self.input_id.text(),
                    "CaptureTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            )
            self.statusBar.showMessage("Frame Captured")
            self.refresh_display()
            self.update_metadata()

    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Medical Image", "",
            "All Supported (*.dcm *.bmp *.jpg *.png *.raw *.bin *.avi *.mp4);;DICOM (*.dcm)"
        )
        if path:
            self.load_image(path)

    def load_image(self, path):
        try:
            reader = get_reader(path)
            if not reader:
                if path.lower().endswith((".raw", ".bin")):
                    from .readers.raw_reader import RawReader
                    reader = RawReader()
                else:
                    self.statusBar.showMessage("Unsupported format")
                    return
            self.current_frame = reader.read(path)
            self.statusBar.showMessage(
                f"Loaded: {os.path.basename(path)} — {self.current_frame.width}x{self.current_frame.height} "
                f"({self.current_frame.source_format})"
            )
            self.refresh_display()
            self.update_metadata()
        except Exception as e:
            self.statusBar.showMessage(f"Error: {str(e)}")

    def update_metadata(self):
        info = []
        if self.current_frame:
            info.append(f"Format: {self.current_frame.source_format}")
            info.append(f"Size: {self.current_frame.width} × {self.current_frame.height}")
            info.append(f"Bit Depth: {self.current_frame.bit_depth}")
            for k, v in self.current_frame.metadata.items():
                if v and not isinstance(v, (np.ndarray, list, dict)):
                    info.append(f"{k}: {v}")
        self.metadata_label.setText("\n".join(info))

    def on_scan_usb(self):
        self.statusBar.showMessage("Scanning USB drives...")
        self.usb_listener._scan_new_drives()

    def show_reference(self):
        chart = """EXPOSURE CHART (400 SPEED)
─────────────────────────────
Hand (AP/Lat): 45–50 kVp | 2–3 mAs
Wrist: 50–55 kVp | 3–4 mAs
Forearm: 55–60 kVp | 4–6 mAs
Elbow: 60–65 kVp | 5–8 mAs
Humerus: 65–70 kVp | 10–15 mAs
Shoulder: 70–75 kVp | 15–25 mAs"""
        QMessageBox.information(self, "Exposure Chart", chart)

    def system_shutdown(self):
        reply = QMessageBox.question(
            self, 'Confirm Shutdown', "Shut down the system?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            os.system("shutdown /s /t 5")
            QApplication.quit()

    def toggle_kiosk(self):
        sender = self.sender()
        if sender.isChecked():
            self.showFullScreen()
            self.statusBar.hide()
        else:
            self.showNormal()
            self.statusBar.show()

    def refresh_com_ports(self):
        self.com_combo.clear()
        ports = serial.tools.list_ports.comports()
        for p in ports:
            self.com_combo.addItem(p.device)
        if not ports:
            self.com_combo.addItem("No COM found")

    def toggle_serial(self):
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.running = False
            self.serial_thread.wait()
            self.serial_thread = None
            self.btn_serial.setText("🔗  Connect Serial")
            self.statusBar.showMessage("Serial Disconnected")
            return
        port = self.com_combo.currentText()
        if port == "No COM found":
            return
        baud_text = self.baud_combo.currentText()
        if baud_text == "AUTO":
            self.baud_scanner = AutoBaudScanner(port)
            self.baud_scanner.baud_detected.connect(lambda b: self._start_serial(port, b))
            self.baud_scanner.scan_status.connect(lambda s: self.statusBar.showMessage(s))
            self.baud_scanner.start()
        else:
            self._start_serial(port, int(baud_text))

    def _start_serial(self, port, baud):
        self.serial_thread = SerialReaderThread(port, baud)
        self.serial_thread.status_changed.connect(lambda s: self.statusBar.showMessage(s))
        self.serial_thread.data_received.connect(self.on_serial_data)
        self.serial_thread.start()
        self.btn_serial.setText("🚫  Disconnect Serial")

    def on_serial_data(self, data):
        pass  # Placeholder for C-arm packet parsing


def run():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = app.palette()
    palette.setColor(palette.Window, QColor(13, 13, 13))
    palette.setColor(palette.WindowText, QColor(224, 224, 224))
    palette.setColor(palette.Base, QColor(25, 25, 25))
    palette.setColor(palette.AlternateBase, QColor(37, 37, 37))
    palette.setColor(palette.Text, QColor(224, 224, 224))
    palette.setColor(palette.Button, QColor(37, 37, 37))
    palette.setColor(palette.ButtonText, QColor(224, 224, 224))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
