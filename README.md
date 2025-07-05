# Record Pen

This repository provides a Python script `record_pen.py` for recording and replaying stylus (pen) input on Windows.

The script relies on Windows Raw Pointer APIs to capture coalesced pen samples along with pressure values and stores them in `recording.json`. It can also replay the captured strokes using the Input Injection API via WinRT.

## Requirements

- Windows 10 with the Windows 10 SDK installed
 - Python 3.8+ with `comtypes` and `winrt` packages installed
- Administrator privileges are required for input injection

Install dependencies:

```bash
pip install comtypes winrt
```

## Usage

You can either run the script with command-line flags or use the built-in GUI.

### Command line

Record pen input:

```bash
python record_pen.py --record
```

Replay the recorded input:

```bash
python record_pen.py --replay
```

### GUI

Running the script without any arguments launches a simple window with
**Record** and **Replay** buttons. Press **Record** to capture a stroke and
save it to `recording.json`, or **Replay** to inject the saved events back.
