import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFileDialog, 
                             QSlider, QFrame, QScrollArea, QStatusBar, QSplitter, QComboBox)
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor
from PyQt5.QtCore import Qt, QSize, pyqtSlot, QThread, pyqtSignal
import serial
import serial.tools.list_ports
import time
import datetime

from carm_multi_viewer.models import ImageFrame
from carm_multi_viewer.detector import get_reader
from carm_multi_viewer.processors import to_display_8bit, apply_lut
from carm_multi_viewer.usb_detector import USBDeviceListener

class LiveCaptureThread(QThread):
    """Thread to handle live video stream from a capture card."""
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
            self.msleep(30) # ~30 FPS
        
        cap.release()

    def stop(self):
        self.running = False
        self.wait()

class SerialReaderThread(QThread):
    """Thread to handle incoming Serial data without freezing the UI."""
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
    """Probes different baud rates to find valid data."""
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
                # Wait for any data arrival within 1.5 seconds
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

class ImageViewer(QLabel):
    """Custom Label for displaying images with Zoom and Pan capability."""
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #000000;")
        self.setMinimumSize(400, 400)
        self.pixmap_data = None
        self.zoom_factor = 1.0

    def set_image(self, img_8bit: np.ndarray):
        height, width = img_8bit.shape
        bytes_per_line = width
        q_img = QImage(img_8bit.data, width, height, bytes_per_line, QImage.Format_Grayscale8)
        self.pixmap_data = QPixmap.fromImage(q_img)
        self.update_display()

    def update_display(self):
        if self.pixmap_data:
            w = int(self.pixmap_data.width() * self.zoom_factor)
            h = int(self.pixmap_data.height() * self.zoom_factor)
            self.setPixmap(self.pixmap_data.scaled(w, h, Qt.KeepAspectRatio, Qt.FastTransformation))

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            self.zoom_factor *= 1.1
        else:
            self.zoom_factor /= 1.1
        self.update_display()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Antigravity C-arm Multi Viewer")
        self.resize(1200, 800)
        self.current_frame: ImageFrame = None
        self.window_center = 127
        self.window_width = 255
        self.serial_thread = None
        self.baud_scanner = None
        
        self.init_ui()
        self.init_usb_listener()
        self.refresh_com_ports()
        
        self.live_thread = None
        self.last_live_frame = None

    def init_ui(self):
        # Premium Dark Theme
        self.setStyleSheet("""
            QMainWindow { background-color: #121212; }
            QWidget { background-color: #121212; color: #E0E0E0; font-family: 'Segoe UI', sans-serif; }
            QFrame#ControlPanel { background-color: #1E1E1E; border-right: 1px solid #333; }
            QPushButton { 
                background-color: #2D2D2D; border: 1px solid #3D3D3D; padding: 8px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #3D3D3D; }
            QPushButton#PrimaryAction { background-color: #0078D4; border: none; }
            QPushButton#CaptureAction { background-color: #D32F2F; border: none; font-weight: bold; }
            QLabel#Title { font-size: 18px; font-weight: bold; color: #0078D4; margin-bottom: 15px; }
            QSlider::handle:horizontal { background: #0078D4; border-radius: 5px; width: 10px; }
            QLineEdit { background-color: #2D2D2D; border: 1px solid #3D3D3D; padding: 5px; color: #FFF; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar / Control Panel ---
        sidebar = QFrame()
        sidebar.setObjectName("ControlPanel")
        sidebar.setFixedWidth(300)
        sidebar_layout = QVBoxLayout(sidebar)
        
        title_label = QLabel("C-ARM VIEWER")
        title_label.setObjectName("Title")
        sidebar_layout.addWidget(title_label)

        btn_open = QPushButton("📁 Open File")
        btn_open.clicked.connect(self.on_open_file)
        sidebar_layout.addWidget(btn_open)

        btn_usb = QPushButton("🔌 Scan USB Devices")
        btn_usb.clicked.connect(self.on_scan_usb)
        sidebar_layout.addWidget(btn_usb)

        sidebar_layout.addSpacing(10)
        self.btn_live = QPushButton("🔴 START LIVE FEED")
        self.btn_live.setObjectName("PrimaryAction")
        self.btn_live.clicked.connect(self.toggle_live_feed)
        sidebar_layout.addWidget(self.btn_live)

        self.btn_capture = QPushButton("📸 CAPTURE FRAME")
        self.btn_capture.setObjectName("CaptureAction")
        self.btn_capture.setEnabled(False)
        self.btn_capture.clicked.connect(self.on_capture_frame)
        sidebar_layout.addWidget(self.btn_capture)

        # --- Patient Info Section ---
        sidebar_layout.addSpacing(20)
        sidebar_layout.addWidget(QLabel("PATIENT INFORMATION"))
        from PyQt5.QtWidgets import QLineEdit
        self.input_patient_name = QLineEdit()
        self.input_patient_name.setPlaceholderText("Name")
        sidebar_layout.addWidget(self.input_patient_name)
        
        self.input_patient_id = QLineEdit()
        self.input_patient_id.setPlaceholderText("Patient ID")
        sidebar_layout.addWidget(self.input_patient_id)

        sidebar_layout.addSpacing(20)
        sidebar_layout.addWidget(QLabel("WINDOW LEVEL"))
        self.slider_level = QSlider(Qt.Horizontal)
        self.slider_level.setRange(0, 255)
        self.slider_level.setValue(127)
        self.slider_level.valueChanged.connect(self.on_params_changed)
        sidebar_layout.addWidget(self.slider_level)

        sidebar_layout.addWidget(QLabel("WINDOW WIDTH"))
        self.slider_width = QSlider(Qt.Horizontal)
        self.slider_width.setRange(1, 1024)
        self.slider_width.setValue(255)
        self.slider_width.valueChanged.connect(self.on_params_changed)
        sidebar_layout.addWidget(self.slider_width)

        self.btn_invert = QPushButton("🌓 Invert Grayscale")
        self.btn_invert.setCheckable(True)
        self.btn_invert.clicked.connect(self.on_params_changed)
        sidebar_layout.addWidget(self.btn_invert)

        # --- Serial Connectivity Section ---
        sidebar_layout.addSpacing(20)
        sidebar_layout.addWidget(QLabel("SERIAL CONNECTIVITY"))
        
        com_layout = QHBoxLayout()
        self.com_combo = QComboBox()
        com_layout.addWidget(self.com_combo)
        
        btn_refresh_com = QPushButton("🔄")
        btn_refresh_com.setFixedWidth(40)
        btn_refresh_com.clicked.connect(self.refresh_com_ports)
        com_layout.addWidget(btn_refresh_com)
        sidebar_layout.addLayout(com_layout)

        baud_layout = QHBoxLayout()
        baud_layout.addWidget(QLabel("Baud:"))
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["AUTO", "9600", "115200", "38400", "57600"])
        baud_layout.addWidget(self.baud_combo)
        sidebar_layout.addLayout(baud_layout)

        self.btn_connect_serial = QPushButton("🔗 Connect Serial")
        self.btn_connect_serial.clicked.connect(self.toggle_serial)
        sidebar_layout.addWidget(self.btn_connect_serial)

        # --- Metadata Display Section ---
        sidebar_layout.addSpacing(20)
        sidebar_layout.addWidget(QLabel("METADATA"))
        self.metadata_label = QLabel("")
        self.metadata_label.setWordWrap(True)
        self.metadata_label.setStyleSheet("color: #AAAAAA; font-size: 11px;")
        sidebar_layout.addWidget(self.metadata_label)

        sidebar_layout.addSpacing(20)
        btn_reference = QPushButton("📖 Exposure Chart")
        btn_reference.clicked.connect(self.show_reference)
        sidebar_layout.addWidget(btn_reference)

        btn_shutdown = QPushButton("🛑 System Shutdown")
        btn_shutdown.setStyleSheet("color: #FF5252;")
        btn_shutdown.clicked.connect(self.system_shutdown)
        sidebar_layout.addWidget(btn_shutdown)

        self.btn_kiosk = QPushButton("📺 Fullscreen Kiosk")
        self.btn_kiosk.setCheckable(True)
        self.btn_kiosk.clicked.connect(self.toggle_kiosk)
        sidebar_layout.addWidget(self.btn_kiosk)

        sidebar_layout.addStretch()

        main_layout.addWidget(sidebar)

        # --- Image Display Area ---
        display_layout = QVBoxLayout()
        self.viewer = ImageViewer()
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(self.viewer)
        scroll_area.setStyleSheet("border: none; background-color: #000;")
        
        display_layout.addWidget(scroll_area)
        main_layout.addLayout(display_layout)

        # Status Bar
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Ready")

    def init_usb_listener(self):
        self.usb_listener = USBDeviceListener()
        self.usb_listener.device_arrived.connect(self.on_usb_arrived)

    @pyqtSlot(str)
    def on_usb_arrived(self, drive_path):
        self.statusBar.showMessage(f"USB Device Detected: {drive_path}. Scanning...", 5000)
        # Automatically scan for DICOM or RAW in the root
        for root, dirs, files in os.walk(drive_path):
            for file in files:
                full_path = os.path.join(root, file)
                reader = get_reader(full_path)
                if reader:
                    self.load_image(full_path)
                    return # Load the first valid file found

    def toggle_live_feed(self):
        if self.live_thread and self.live_thread.isRunning():
            self.live_thread.stop()
            self.live_thread = None
            self.btn_live.setText("🔴 START LIVE FEED")
            self.btn_capture.setEnabled(False)
            self.statusBar.showMessage("Live feed stopped")
        else:
            self.live_thread = LiveCaptureThread(0) # Default cam
            self.live_thread.frame_ready.connect(self.on_live_frame)
            self.live_thread.error_occurred.connect(lambda msg: self.statusBar.showMessage(msg))
            self.live_thread.start()
            self.btn_live.setText("⏹ STOP LIVE FEED")
            self.btn_capture.setEnabled(True)
            self.statusBar.showMessage("Live feed active")

    def on_live_frame(self, frame):
        self.last_live_frame = frame
        # Convert BGR to Grayscale for display if needed, or keep color
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.viewer.set_image(gray)

    def on_capture_frame(self):
        if self.last_live_frame is not None:
            gray = cv2.cvtColor(self.last_live_frame, cv2.COLOR_BGR2GRAY)
            # Create an ImageFrame
            frame_obj = ImageFrame(
                pixels=gray,
                width=gray.shape[1],
                height=gray.shape[0],
                bit_depth=8,
                source_format="LIVE_CAPTURE",
                metadata={
                    "PatientName": self.input_patient_name.text(),
                    "PatientID": self.input_patient_id.text(),
                    "CaptureTime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            )
            self.current_frame = frame_obj
            self.statusBar.showMessage("Frame Captured Successfully")
            self.update_image_display()
            self.update_metadata()

    def show_reference(self):
        from PyQt5.QtWidgets import QMessageBox
        chart_text = """
        EXPOSURE CHART (400 SPEED)
        --------------------------
        Hand (AP/Lat): 45-50 kVp | 2-3 mAs
        Wrist: 50-55 kVp | 3-4 mAs
        Forearm: 55-60 kVp | 4-6 mAs
        Elbow: 60-65 kVp | 5-8 mAs
        Humerus: 65-70 kVp | 10-15 mAs
        Shoulder: 70-75 kVp | 15-25 mAs
        """
        QMessageBox.information(self, "Exposure Chart", chart_text)

    def system_shutdown(self):
        from PyQt5.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, 'Confirm Shutdown', 
                                   "Are you sure you want to shut down the system?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.statusBar.showMessage("Shutting down system...")
            os.system("shutdown /s /t 5") # Windows shutdown command
            QApplication.quit()

    def toggle_kiosk(self):
        if self.btn_kiosk.isChecked():
            self.showFullScreen()
            self.statusBar.hide()
        else:
            self.showNormal()
            self.statusBar.show()

    def on_open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Medical Image", "", 
                                              "All Supported (*.dcm *.bmp *.jpg *.png *.raw *.bin *.avi *.mp4);;DICOM (*.dcm)")
        if path:
            self.load_image(path)

    def load_image(self, path):
        try:
            reader = get_reader(path)
            if not reader:
                # Try RAW fallback if it failed but we might want it
                if path.lower().endswith((".raw", ".bin")):
                    from .readers.raw_reader import RawReader
                    reader = RawReader() # Default 1024x1024 16bit
                else:
                    self.statusBar.showMessage("Unsupported format")
                    return

            self.current_frame = reader.read(path)
            self.statusBar.showMessage(f"Loaded: {os.path.basename(path)} ({self.current_frame.source_format})")
            
            # Update Windowing based on metadata if available
            wc = self.current_frame.metadata.get("WindowCenter")
            ww = self.current_frame.metadata.get("WindowWidth")
            
            if wc is not None and ww is not None:
                # Rescale sliders to match bit depth? 
                # For now, keep it simple 8-bit controls or adapt
                pass

            self.update_image_display()
            self.update_metadata()
        except Exception as e:
            self.statusBar.showMessage(f"Error: {str(e)}")

    def update_image_display(self):
        if self.current_frame is not None:
            # Get windowing from sliders
            wc = self.slider_level.value()
            ww = self.slider_width.value()
            
            # If it's a 16-bit image, sliders need to be scaled
            if self.current_frame.bit_depth > 8:
                # Scale 0-255 to 0-65535 (loose heuristic)
                wc = wc * 256
                ww = ww * 256

            img_8bit = to_display_8bit(self.current_frame.pixels, wc, ww)
            img_final = apply_lut(img_8bit, self.btn_invert.isChecked())
            self.viewer.set_image(img_final)

    def update_metadata(self):
        info = []
        if self.current_frame:
            info.append(f"Format: {self.current_frame.source_format.upper()}")
            info.append(f"Resolution: {self.current_frame.width} x {self.current_frame.height}")
            info.append(f"Bit Depth: {self.current_frame.bit_depth}")
            for k, v in self.current_frame.metadata.items():
                if v and not isinstance(v, (np.ndarray, list, dict)):
                    info.append(f"{k}: {v}")
        self.metadata_label.setText("\n".join(info))

    def on_params_changed(self):
        self.update_image_display()

    def on_scan_usb(self):
        # Manual trigger
        self.statusBar.showMessage("Scanning logical drives...")
        self.usb_listener._scan_new_drives()

    def on_export(self):
        if self.current_frame is not None:
            path, _ = QFileDialog.getSaveFileName(self, "Export Image", "export.png", "PNG Image (*.png)")
            if path:
                # Get current display image (processed)
                wc = self.slider_level.value()
                ww = self.slider_width.value()
                if self.current_frame.bit_depth > 8:
                    wc *= 256
                    ww *= 256
                img_8bit = to_display_8bit(self.current_frame.pixels, wc, ww)
                img_final = apply_lut(img_8bit, self.btn_invert.isChecked())
                cv2.imwrite(path, img_final)
                self.statusBar.showMessage(f"Exported to {path}")

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
            self.btn_connect_serial.setText("🔗 Connect Serial")
            self.statusBar.showMessage("Serial Disconnected")
            return

        port = self.com_combo.currentText()
        if port == "No COM found":
            return

        baud_text = self.baud_combo.currentText()
        if baud_text == "AUTO":
            self.start_baud_scan(port)
        else:
            self.start_serial(port, int(baud_text))

    def start_baud_scan(self, port):
        self.statusBar.showMessage(f"Auto-scanning Baud for {port}...")
        self.baud_scanner = AutoBaudScanner(port)
        self.baud_scanner.baud_detected.connect(lambda b: self.on_baud_detected(port, b))
        self.baud_scanner.scan_status.connect(lambda s: self.statusBar.showMessage(s))
        self.baud_scanner.start()

    def on_baud_detected(self, port, baud):
        self.statusBar.showMessage(f"Baud {baud} detected! Connecting...", 3000)
        index = self.baud_combo.findText(str(baud))
        if index >= 0:
            self.baud_combo.setCurrentIndex(index)
        self.start_serial(port, baud)

    def start_serial(self, port, baud):
        self.serial_thread = SerialReaderThread(port, baud)
        self.serial_thread.status_changed.connect(lambda s: self.statusBar.showMessage(s))
        self.serial_thread.data_received.connect(self.on_serial_data)
        self.serial_thread.start()
        self.btn_connect_serial.setText("🚫 Disconnect Serial")

    def on_serial_data(self, data):
        # Placeholder for C-arm packet parsing
        # print(f"Serial Input: {data.hex()}")
        pass

def run():
    from PyQt5.QtWidgets import QComboBox # Ensure QComboBox is accessible in scope
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    # Global palette for true dark mode
    palette = app.palette()
    palette.setColor(app.palette().Window, QColor(18, 18, 18))
    # ... more palette config if needed
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
