"""Record and replay pen input on Windows.

The script records WM_POINTER messages with pressure data using the Raw Pointer
API and replays them with the Win32 synthetic pointer device APIs. It only
depends on ``ctypes`` and ``comtypes``; the optional ``winrt`` package is not
required.
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import threading
import tkinter as tk
from ctypes import wintypes

# Windows type aliases for systems that lack these in ctypes.wintypes
UINT32 = getattr(wintypes, "UINT32", ctypes.c_uint32)
INT32 = getattr(wintypes, "INT32", ctypes.c_int32)


def is_admin() -> bool:
    """Return True if the script is running with administrator privileges."""
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """Relaunch the current script with elevated rights."""
    if os.name != "nt" or is_admin():
        return False
    params = " ".join(f'"{a}"' for a in sys.argv)
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    sys.exit(0)


def ensure_dependencies():
    """Install required Python packages if missing."""
    missing = []
    try:
        import comtypes  # noqa: F401
    except Exception:
        missing.append("comtypes")

    if missing and is_admin():
        subprocess.call([sys.executable, "-m", "pip", "install", *missing])

    # Reload comtypes if it was just installed
    global comtypes
    try:
        import comtypes as _comtypes
        comtypes = _comtypes
    except Exception:
        comtypes = None

try:
    import comtypes
except ImportError:
    comtypes = None

# The WinRT package `winrt` is not required. Set InputInjector to None to
# indicate that the optional dependency is unavailable.
try:
    from winrt.windows.ui.input.preview.injection import InputInjector  # type: ignore
except Exception:
    InputInjector = None

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Constants
WM_POINTERDOWN = 0x0246
WM_POINTERUPDATE = 0x0247
WM_POINTERUP = 0x0248

# Pointer device constants
PT_PEN = 0x00000003

# Feedback mode
POINTER_FEEDBACK_DEFAULT = 1

# Basic pointer flags
POINTER_FLAG_NONE = 0x00000000
POINTER_FLAG_INRANGE = 0x00000002
POINTER_FLAG_INCONTACT = 0x00000004
POINTER_FLAG_DOWN = 0x00010000
POINTER_FLAG_UPDATE = 0x00020000
POINTER_FLAG_UP = 0x00040000

# Structures from Win32 API
class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]

class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", wintypes.DWORD),
        ("pointerId", UINT32),
        ("frameId", UINT32),
        ("pointerFlags", wintypes.DWORD),
        ("sourceDevice", wintypes.HANDLE),
        ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", POINT),
        ("ptHimetricLocation", POINT),
        ("ptPixelLocationRaw", POINT),
        ("ptHimetricLocationRaw", POINT),
        ("dwTime", wintypes.DWORD),
        ("historyCount", UINT32),
        ("inputData", INT32),
        ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", wintypes.ULONGLONG),
        ("ButtonChangeType", wintypes.DWORD),
    ]

class POINTER_PEN_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("penFlags", wintypes.DWORD),
        ("penMask", wintypes.DWORD),
        ("pressure", UINT32),
        ("rotation", UINT32),
        ("tiltX", INT32),
        ("tiltY", INT32),
    ]


class _POINTER_TYPE_INFO_UNION(ctypes.Union):
    _fields_ = [
        ("penInfo", POINTER_PEN_INFO),
    ]


class POINTER_TYPE_INFO(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("DUMMYUNIONNAME", _POINTER_TYPE_INFO_UNION),
    ]

# Function prototypes
GetPointerFramePenInfoHistory = user32.GetPointerFramePenInfoHistory
GetPointerFramePenInfoHistory.restype = wintypes.BOOL
GetPointerFramePenInfoHistory.argtypes = [
    UINT32,
    ctypes.POINTER(UINT32),
    ctypes.POINTER(UINT32),
    ctypes.POINTER(POINTER_PEN_INFO),
]

InjectSyntheticPointerInput = user32.InjectSyntheticPointerInput
InjectSyntheticPointerInput.restype = wintypes.BOOL
InjectSyntheticPointerInput.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(POINTER_TYPE_INFO),
    UINT32,
]

# Additional Win32 APIs for injecting pointers without WinRT
CreateSyntheticPointerDevice = user32.CreateSyntheticPointerDevice
CreateSyntheticPointerDevice.restype = wintypes.HANDLE
CreateSyntheticPointerDevice.argtypes = [
    wintypes.DWORD,  # POINTER_INPUT_TYPE
    wintypes.ULONG,
    wintypes.DWORD,  # POINTER_FEEDBACK_MODE
]

DestroySyntheticPointerDevice = user32.DestroySyntheticPointerDevice
DestroySyntheticPointerDevice.restype = None
DestroySyntheticPointerDevice.argtypes = [wintypes.HANDLE]

# Message window setup
WNDPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

records = []

@WNDPROC
def wnd_proc(hwnd, msg, wparam, lparam):
    if msg in (WM_POINTERDOWN, WM_POINTERUPDATE, WM_POINTERUP):
        pointer_id = wparam & 0xFFFF
        count = UINT32()
        # Query how many coalesced samples are available
        GetPointerFramePenInfoHistory(pointer_id, None, ctypes.byref(count), None)
        arr_type = POINTER_PEN_INFO * count.value
        infos = arr_type()
        GetPointerFramePenInfoHistory(pointer_id, None, ctypes.byref(count), infos)
        evt_type = {
            WM_POINTERDOWN: "down",
            WM_POINTERUPDATE: "move",
            WM_POINTERUP: "up",
        }[msg]
        for info in infos:
            pt = info.pointerInfo.ptPixelLocation
            records.append(
                {
                    "type": evt_type,
                    "x": pt.x,
                    "y": pt.y,
                    "pressure": info.pressure,
                    "t": time.time(),
                }
            )
        if msg == WM_POINTERUP:
            with open("recording.json", "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2)
            print("Recording saved to recording.json")
            user32.PostQuitMessage(0)
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

WNDCLASS = ctypes.Structure
class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]

atom = None
hwnd = None


def create_message_window():
    global atom, hwnd
    class_name = "PenRecorderWindow"
    wc = WNDCLASS()
    wc.lpfnWndProc = wnd_proc
    wc.lpszClassName = class_name
    wc.hInstance = user32.GetModuleHandleW(None)
    atom = user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(
        0,
        atom,
        class_name,
        0,
        0,
        0,
        0,
        0,
        0x00000000 | 0x00000080,  # WS_OVERLAPPED, WS_EX_NOACTIVATE
        0,
        wc.hInstance,
        None,
    )


def message_loop():
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


def record():
    """Run the pointer message loop and save events to recording.json."""
    records.clear()
    create_message_window()
    message_loop()
    if hwnd:
        user32.DestroyWindow(hwnd)
    if atom:
        user32.UnregisterClassW(atom, user32.GetModuleHandleW(None))


def replay():
    """Replay events stored in recording.json using synthetic pointer APIs."""
    with open("recording.json", "r", encoding="utf-8") as f:
        events = json.load(f)

    device = CreateSyntheticPointerDevice(PT_PEN, 1, POINTER_FEEDBACK_DEFAULT)
    if not device:
        print("Failed to create synthetic pen device")
        return

    try:
        prev_t = None
        for ev in events:
            if prev_t is not None:
                time.sleep(max(ev["t"] - prev_t, 0))
            prev_t = ev["t"]

            pointer = POINTER_TYPE_INFO()
            pointer.type = PT_PEN
            pen = pointer.DUMMYUNIONNAME.penInfo
            pen.pointerInfo.pointerType = PT_PEN
            pen.pointerInfo.pointerId = 0
            if ev["type"] == "down":
                pen.pointerInfo.pointerFlags = (
                    POINTER_FLAG_DOWN | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
                )
            elif ev["type"] == "up":
                pen.pointerInfo.pointerFlags = POINTER_FLAG_UP
            else:
                pen.pointerInfo.pointerFlags = (
                    POINTER_FLAG_UPDATE | POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT
                )
            pen.pointerInfo.ptPixelLocation = POINT(int(ev["x"]), int(ev["y"]))
            pen.penFlags = 0
            pen.penMask = 1  # PEN_MASK_PRESSURE
            pen.pressure = int(ev["pressure"])

            InjectSyntheticPointerInput(device, ctypes.byref(pointer), 1)
    finally:
        DestroySyntheticPointerDevice(device)


def main():
    # Relaunch with admin rights if necessary
    relaunch_as_admin()

    ensure_dependencies()

    if comtypes:
        comtypes.CoInitialize()

    def run_gui():
        root = tk.Tk()
        root.title("Pen Recorder")
        status = tk.StringVar(value="Idle")

        def start_record():
            status.set("Recording...")
            threading.Thread(target=lambda: (record(), status.set("Idle")), daemon=True).start()

        def start_replay():
            status.set("Replaying...")
            threading.Thread(target=lambda: (replay(), status.set("Idle")), daemon=True).start()

        tk.Button(root, text="Record", command=start_record).pack(fill="x")
        tk.Button(root, text="Replay", command=start_replay).pack(fill="x")
        tk.Label(root, textvariable=status).pack(fill="x")
        root.mainloop()

    if "--record" in sys.argv:
        record()
    elif "--replay" in sys.argv:
        replay()
    else:
        run_gui()

    if comtypes:
        comtypes.CoUninitialize()


if __name__ == "__main__":
    main()
