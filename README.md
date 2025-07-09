# Record Pen

This repository provides two ways to record and replay stylus (pen) input on Windows.

- `record_pen.py` – the original Python implementation using ctypes.
- `RecordPen` – a C# WinForms application that offers the same recording and replay functionality.

Both approaches store the captured samples in `recording.json` and replay them preserving timing and pressure.

## Python approach

The Python script relies on Windows Raw Pointer APIs and requires:

- Windows 10 with the Windows 10 SDK installed
- Python 3.8+ with `comtypes` installed
- Administrator privileges for input injection

Install the dependency (the script can auto-install when run as administrator):

```bash
pip install comtypes
```

Run the GUI or record from the command line:

```bash
python record_pen.py --record   # capture strokes
python record_pen.py --replay   # replay them
```

Running without arguments launches a Tkinter window with **Record** and **Replay** buttons.

## C# WinForms approach

If the Python version does not work on your system, you can build the C# project instead. Install the .NET SDK 8.0 or newer, then run:

```bash
cd RecordPen
 dotnet build -c Release
```

This produces `RecordPen.exe` in `bin/Release/net8.0-windows`. Run it to get a window with **Record** and **Replay** buttons. The application listens for pen input when **Record** is pressed and writes the data to `recording.json`. Selecting **Replay** injects the stored strokes back.

Administrator rights are still required for replaying input.
