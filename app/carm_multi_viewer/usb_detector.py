import win32gui
import win32api
import win32con
import threading
from PyQt5.QtCore import QObject, pyqtSignal

class USBDeviceListener(QObject):
    """Listens for hardware changes (USB arrival) using Windows Messages."""
    device_arrived = pyqtSignal(str) # Emits the drive letter of the arrived device

    def __init__(self):
        super().__init__()
        self._thread = threading.Thread(target=self._run_listener, daemon=True)
        self._thread.start()

    def _run_listener(self):
        # Create a hidden window to receive messages
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wnd_proc
        wc.lpszClassName = "USBDetectorWindow"
        
        hinst = win32api.GetModuleHandle(None)
        class_atom = win32gui.RegisterClass(wc)
        
        self.hwnd = win32gui.CreateWindow(
            class_atom,
            "USB Detector",
            0, 0, 0, 0, 0,
            0, 0, hinst, None
        )
        
        # Message loop
        win32gui.PumpMessages()

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == win32con.WM_DEVICECHANGE:
            # DBT_DEVICEARRIVAL = 0x8000
            if wparam == 0x8000:
                print("Hardware device arrival detected!")
                # For simplicity, we delay slightly and check for new drive letters
                # Real implementation would parse lparam to find the specific drive
                # But a simple scan of logical drives is robust.
                threading.Timer(2.0, self._scan_new_drives).start()
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _scan_new_drives(self):
        # Scan for removable drives
        import os
        import string
        from ctypes import windll

        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                drive = f"{letter}:\\"
                # Check if it's a removable drive or CDRom (often USBs)
                type = windll.kernel32.GetDriveTypeW(drive)
                if type in (2, 5): # DRIVE_REMOVABLE, DRIVE_CDROM
                    self.device_arrived.emit(drive)
            bitmask >>= 1
