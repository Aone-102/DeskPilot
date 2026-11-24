"""
screen_viewer.py
DeskPilot v2 - Remote PC Screen Capture & Active Windows Monitor
Provides real-time desktop screen capture and active window enumeration for mobile companion.
"""
import ctypes
from ctypes import wintypes
import io
import time
from datetime import datetime


def _attach_desktop():
    """Ensure current thread is attached to the interactive desktop (winsta0\\default)"""
    try:
        user32 = ctypes.windll.user32
        hwinsta = user32.OpenWindowStationW("winsta0", False, 0x037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def capture_screen_jpeg(quality=70, max_width=1080):
    """
    Captures the primary monitor screen and returns JPEG bytes and metadata.
    Resizes proportionally if max_width is provided to optimize mobile/remote transmission.
    Default max_width 1080, quality 70 for super-fast live transmission over external networks.
    """
    _attach_desktop()
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        orig_w, orig_h = img.size

        if max_width and orig_w > max_width:
            ratio = max_width / float(orig_w)
            new_h = int(float(orig_h) * ratio)
            img = img.resize((max_width, new_h))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        jpeg_bytes = buf.getvalue()

        return {
            "success": True,
            "bytes": jpeg_bytes,
            "width": orig_w,
            "height": orig_h,
            "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "size_kb": round(len(jpeg_bytes) / 1024, 1)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "bytes": b"",
            "width": 0,
            "height": 0,
            "captured_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


def get_active_windows():
    """
    Enumerates visible top-level application windows on the Windows desktop.
    """
    _attach_desktop()
    user32 = ctypes.windll.user32
    windows = []

    # System and background windows to ignore
    ignore_titles = {
        "Program Manager", "Default IME", "MSCTFIME UI", "Settings",
        "Windows Input Experience", "Search", "", "Desktop Window Manager"
    }

    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                if title and title not in ignore_titles:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    # Exclude invisible or 0x0 offscreen tooltips
                    if w > 40 and h > 40:
                        windows.append({
                            "title": title,
                            "width": w,
                            "height": h
                        })
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

    screen_w = user32.GetSystemMetrics(0)
    screen_h = user32.GetSystemMetrics(1)

    return {
        "success": True,
        "screen_resolution": f"{screen_w}x{screen_h}",
        "count": len(windows),
        "windows": windows,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
