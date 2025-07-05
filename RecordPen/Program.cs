using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows.Forms;
using Windows.UI.Input.Preview.Injection;

namespace RecordPen
{
    public partial class MainForm : Form
    {
        private const int WM_POINTERDOWN = 0x0246;
        private const int WM_POINTERUPDATE = 0x0247;
        private const int WM_POINTERUP = 0x0248;

        [StructLayout(LayoutKind.Sequential)]
        struct POINT { public int x; public int y; }

        [StructLayout(LayoutKind.Sequential)]
        struct POINTER_INFO
        {
            public uint pointerType;
            public uint pointerId;
            public uint frameId;
            public uint pointerFlags;
            public IntPtr sourceDevice;
            public IntPtr hwndTarget;
            public POINT ptPixelLocation;
            public POINT ptHimetricLocation;
            public POINT ptPixelLocationRaw;
            public POINT ptHimetricLocationRaw;
            public uint dwTime;
            public uint historyCount;
            public int inputData;
            public uint dwKeyStates;
            public ulong PerformanceCount;
            public uint ButtonChangeType;
        }

        [StructLayout(LayoutKind.Sequential)]
        struct POINTER_PEN_INFO
        {
            public POINTER_INFO pointerInfo;
            public uint penFlags;
            public uint penMask;
            public uint pressure;
            public uint rotation;
            public int tiltX;
            public int tiltY;
        }

        [DllImport("user32.dll")]
        static extern bool GetPointerFramePenInfoHistory(uint pointerId, IntPtr entriesCount, ref uint count, [Out] POINTER_PEN_INFO[] penInfo);

        private List<PenEvent> events = new();
        private bool recording = false;

        public MainForm()
        {
            Text = "Record Pen";
            Width = 200;
            Height = 120;

            var recordButton = new Button { Text = "Record", Dock = DockStyle.Top };
            var replayButton = new Button { Text = "Replay", Dock = DockStyle.Top };
            var statusLabel = new Label { Text = "Idle", Dock = DockStyle.Top };

            recordButton.Click += (s, e) =>
            {
                events.Clear();
                recording = true;
                statusLabel.Text = "Recording...";
            };

            replayButton.Click += async (s, e) =>
            {
                statusLabel.Text = "Replaying...";
                await System.Threading.Tasks.Task.Run(() => Replay());
                statusLabel.Text = "Idle";
            };

            Controls.Add(replayButton);
            Controls.Add(recordButton);
            Controls.Add(statusLabel);
        }

        protected override void WndProc(ref Message m)
        {
            base.WndProc(ref m);
            if (!recording) return;
            if (m.Msg == WM_POINTERDOWN || m.Msg == WM_POINTERUPDATE || m.Msg == WM_POINTERUP)
            {
                uint pointerId = (uint)m.WParam.ToInt32() & 0xFFFF;
                uint count = 0;
                GetPointerFramePenInfoHistory(pointerId, IntPtr.Zero, ref count, null);
                if (count > 0)
                {
                    var arr = new POINTER_PEN_INFO[count];
                    GetPointerFramePenInfoHistory(pointerId, IntPtr.Zero, ref count, arr);
                    string type = m.Msg switch
                    {
                        WM_POINTERDOWN => "down",
                        WM_POINTERUP => "up",
                        _ => "move"
                    };
                    foreach (var info in arr)
                    {
                        events.Add(new PenEvent
                        {
                            Type = type,
                            X = info.pointerInfo.ptPixelLocation.x,
                            Y = info.pointerInfo.ptPixelLocation.y,
                            Pressure = info.pressure,
                            Timestamp = Stopwatch.GetTimestamp() / (double)Stopwatch.Frequency
                        });
                    }
                    if (m.Msg == WM_POINTERUP)
                    {
                        File.WriteAllText("recording.json", JsonSerializer.Serialize(events, new JsonSerializerOptions { WriteIndented = true }));
                        recording = false;
                    }
                }
            }
        }

        private void Replay()
        {
            if (!File.Exists("recording.json")) return;
            var data = JsonSerializer.Deserialize<List<PenEvent>>(File.ReadAllText("recording.json"));
            if (data == null || data.Count == 0) return;

            var injector = InputInjector.TryCreate();
            var device = injector.InitializePenInjection();
            double prev = data[0].Timestamp;
            foreach (var ev in data)
            {
                System.Threading.Thread.Sleep(TimeSpan.FromSeconds(ev.Timestamp - prev));
                prev = ev.Timestamp;
                var info = new InjectedInputPenInfo
                {
                    PointerInfo = new InjectedInputPointerInfo
                    {
                        PointerOptions = ev.Type == "down" ? InjectedInputPointerOptions.InRange | InjectedInputPointerOptions.InContact | InjectedInputPointerOptions.Primary | InjectedInputPointerOptions.PenDown
                            : ev.Type == "up" ? InjectedInputPointerOptions.PointerUp
                            : InjectedInputPointerOptions.InRange | InjectedInputPointerOptions.InContact,
                        PixelLocation = new Windows.Foundation.Point(ev.X, ev.Y)
                    },
                    Pressure = (ushort)Math.Min(Math.Max(ev.Pressure, 0), 1024)
                };
                injector.InjectPenInput(new[] { info });
            }
        }
    }

    class PenEvent
    {
        public string Type { get; set; } = "";
        public int X { get; set; }
        public int Y { get; set; }
        public uint Pressure { get; set; }
        public double Timestamp { get; set; }
    }

    internal static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}
