"""Record and replay pen input on Windows using Raw Pointer and Input Injection APIs."""

import ctypes
import json
import sys
import time
import threading
import tkinter as tk
from ctypes import wintypes

try:
    import comtypes
except ImportError:
    comtypes = None

try:
    from winrt.windows.ui.input.preview.injection import (
        InputInjector,
        InjectedInputPenInfo,
        InjectedInputPointerInfo,
        InjectedInputPointerOptions,
        InjectedInputPenButtons,
    )
except ImportError:
    InputInjector = None

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Constants
WM_POINTERDOWN = 0x0246
WM_POINTERUPDATE = 0x0247
WM_POINTERUP = 0x0248

# Structures from Win32 API
class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]

class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", wintypes.DWORD),
        ("pointerId", wintypes.UINT32),
        ("frameId", wintypes.UINT32),
        ("pointerFlags", wintypes.DWORD),
        ("sourceDevice", wintypes.HANDLE),
        ("hwndTarget", wintypes.HWND),
        ("ptPixelLocation", POINT),
        ("ptHimetricLocation", POINT),
        ("ptPixelLocationRaw", POINT),
        ("ptHimetricLocationRaw", POINT),
        ("dwTime", wintypes.DWORD),
        ("historyCount", wintypes.UINT32),
        ("inputData", wintypes.INT32),
        ("dwKeyStates", wintypes.DWORD),
        ("PerformanceCount", wintypes.ULONGLONG),
        ("ButtonChangeType", wintypes.DWORD),
    ]

class POINTER_PEN_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("penFlags", wintypes.DWORD),
        ("penMask", wintypes.DWORD),
        ("pressure", wintypes.UINT32),
        ("rotation", wintypes.UINT32),
        ("tiltX", wintypes.INT32),
        ("tiltY", wintypes.INT32),
    ]

# Function prototypes
GetPointerFramePenInfoHistory = user32.GetPointerFramePenInfoHistory
GetPointerFramePenInfoHistory.restype = wintypes.BOOL
GetPointerFramePenInfoHistory.argtypes = [
    wintypes.UINT32,
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.POINTER(ctypes.c_uint32),
    ctypes.POINTER(POINTER_PEN_INFO),
]

InjectSyntheticPointerInput = user32.InjectSyntheticPointerInput
InjectSyntheticPointerInput.restype = wintypes.BOOL
InjectSyntheticPointerInput.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(POINTER_PEN_INFO),
    wintypes.UINT32,
]

# Message window setup
WNDPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

records = []

@WNDPROC
def wnd_proc(hwnd, msg, wparam, lparam):
    if msg == WM_POINTERUPDATE:
        pointer_id = wparam & 0xFFFF
        count = ctypes.c_uint32()
        GetPointerFramePenInfoHistory(pointer_id, None, ctypes.byref(count), None)
        arr_type = POINTER_PEN_INFO * count.value
        infos = arr_type()
        GetPointerFramePenInfoHistory(pointer_id, None, ctypes.byref(count), infos)
        for info in infos:
            pt = info.pointerInfo.ptPixelLocation
            records.append({
                "x": pt.x,
                "y": pt.y,
                "pressure": info.pressure,
                "t": time.time(),
            })
    elif msg == WM_POINTERUP:
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
    if InputInjector is None:
        print("WinRT input injection APIs not available")
        return
    with open("recording.json", "r", encoding="utf-8") as f:
        events = json.load(f)
    injector = InputInjector.try_create()
    if injector is None:
        print("Failed to create InputInjector")
        return
    prev_t = None
    for ev in events:
        if prev_t is not None:
            time.sleep(max(ev["t"] - prev_t, 0))
        prev_t = ev["t"]
        pen = InjectedInputPenInfo()
        info = InjectedInputPointerInfo()
        info.pointer_options = InjectedInputPointerOptions.IN_CONTACT | InjectedInputPointerOptions.PEN
        info.pixel_location = POINT(ev["x"], ev["y"])
        pen.pointer_info = info
        pen.pressure = int(ev["pressure"])
        injector.inject_pen_input([pen])


def main():
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
