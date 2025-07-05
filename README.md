# Record Pen

This repository provides a Python script `record_pen.py` for recording and replaying stylus (pen) input on Windows.

The script relies on Windows Raw Pointer APIs to capture coalesced pen samples along with pressure values and stores them in `recording.json`. It can also replay the captured strokes using the Input Injection API via WinRT.

## Requirements

- Windows 10 with the Windows 10 SDK installed
- Python 3.8+ with `comtypes` and `pywinrt` packages installed
- Administrator privileges are required for input injection

Install dependencies:

```bash
pip install comtypes pywinrt
```

## Usage

To record pen input:

```bash
python record_pen.py --record
```

Press the pen on the screen to draw. The samples will be saved to `recording.json` when the pen is lifted.

To replay the recorded input:

```bash
python record_pen.py --replay
```

The replay uses the timestamps stored in the JSON file to reproduce the drawing speed.
