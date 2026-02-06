
"""
CandlesTblPanel: draw OHLCV candlestick chart with volume.
Data format: list of [ts, open, high, low, close, vol, ...] (OKX style).
"""
import wx
import threading
from datetime import datetime, timezone

from okx_client import (
    get_candles,
)

class CandlesPanel(wx.Panel):
    BAR_OPTIONS = ["1m", "3m", "5m", "15m", "30m", "1H", "2H", "4H", "1D"]

    def __init__(self, parent, on_candles_set=None):
        super().__init__(parent)
        self._on_candles_set = on_candles_set
        layout = wx.BoxSizer(wx.VERTICAL)
        bar_row = wx.BoxSizer(wx.HORIZONTAL)
        bar_row.Add(wx.StaticText(self, label="Pair:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.pair_label = wx.StaticText(self, label="—")
        bar_row.Add(self.pair_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        bar_row.Add(wx.StaticText(self, label="Bar:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.bar_choice = wx.Choice(self, choices=self.BAR_OPTIONS)
        self.bar_choice.SetSelection(0)
        bar_row.Add(self.bar_choice, 0, wx.RIGHT, 8)
        self.refresh_btn = wx.Button(self, label="Refresh")
        bar_row.Add(self.refresh_btn, 0)
        layout.Add(bar_row, 0, wx.ALL, 4)
        self.grid = wx.grid.Grid(self)
        self.grid.CreateGrid(0, 6)
        self.grid.SetColLabelValue(0, "Time")
        self.grid.SetColLabelValue(1, "Open")
        self.grid.SetColLabelValue(2, "High")
        self.grid.SetColLabelValue(3, "Low")
        self.grid.SetColLabelValue(4, "Close")
        self.grid.SetColLabelValue(5, "Volume")
        self.grid.EnableEditing(False)
        layout.Add(self.grid, 1, wx.EXPAND)
        self.SetSizer(layout)
        self._inst_id = None
        self._candles = []
        self.bar_choice.Bind(wx.EVT_CHOICE, lambda e: self._load())
        self.refresh_btn.Bind(wx.EVT_BUTTON, lambda e: self._load())

    def set_pair(self, inst_id: str):
        self._inst_id = inst_id
        self.pair_label.SetLabel(inst_id or "—")
        self._load()

    def _load(self):
        if not self._inst_id:
            return
        bar = self.BAR_OPTIONS[self.bar_choice.GetSelection()]
        inst_id = self._inst_id

        def work():
            try:
                data = get_candles(inst_id, bar=bar, limit="100")
                wx.CallAfter(self._set_candles, data)
            except Exception as e:
                wx.CallAfter(self._show_error, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _set_candles(self, data: list):
        # OKX returns [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        self._candles = data
        if self._on_candles_set:
            self._on_candles_set(data)
        n = self.grid.GetNumberRows()
        if n > 0:
            self.grid.DeleteRows(0, n)
        for row, c in enumerate(reversed(data)):
            self.grid.AppendRows(1)
            ts = c[0] if isinstance(c[0], str) else str(c[0])
            try:
                dt = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            except Exception:
                dt = ts
            self.grid.SetCellValue(row, 0, dt)
            self.grid.SetCellValue(row, 1, str(c[1]))
            self.grid.SetCellValue(row, 2, str(c[2]))
            self.grid.SetCellValue(row, 3, str(c[3]))
            self.grid.SetCellValue(row, 4, str(c[4]))
            self.grid.SetCellValue(row, 5, str(c[5]) if len(c) > 5 else "")




    def append_candle(self, inst_id: str, arr: list):
        if inst_id != self._inst_id or not arr:
            return
        # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        self._candles.append(arr)
        self.grid.AppendRows(1)
        row = self.grid.GetNumberRows() - 1
        ts = arr[0] if isinstance(arr[0], str) else str(arr[0])
        try:
            dt = datetime.fromtimestamp(int(ts) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
        except Exception:
            dt = ts
        self.grid.SetCellValue(row, 0, dt)
        self.grid.SetCellValue(row, 1, str(arr[1]))
        self.grid.SetCellValue(row, 2, str(arr[2]))
        self.grid.SetCellValue(row, 3, str(arr[3]))
        self.grid.SetCellValue(row, 4, str(arr[4]))
        self.grid.SetCellValue(row, 5, str(arr[5]) if len(arr) > 5 else "")
        if self._on_candles_set:
            self._on_candles_set(self._candles)

    def _show_error(self, msg: str):
        wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)            