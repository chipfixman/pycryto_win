"""
tickers
"""
import threading
from datetime import datetime, timezone
import wx
import wx.grid
from wx.lib.mixins.listctrl import ListCtrlAutoWidthMixin

from config import API_KEY, SECRET_KEY, PASSPHRASE, USE_DEMO
from okx_client import (
    get_instruments,
    get_tickers,
)
from okx_ws import OKXWebSocket


class TickersPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        self.grid = wx.grid.Grid(self)
        self.grid.CreateGrid(0, 7)
        self.grid.SetColLabelValue(0, "Pair")
        self.grid.SetColLabelValue(1, "Last")
        self.grid.SetColLabelValue(2, "Change %")
        self.grid.SetColLabelValue(3, "High 24h")
        self.grid.SetColLabelValue(4, "Low 24h")
        self.grid.SetColLabelValue(5, "Volume 24h")
        self.grid.SetColLabelValue(6, "Time")
        self.grid.EnableEditing(False)
        layout.Add(self.grid, 1, wx.EXPAND)
        self.SetSizer(layout)
        self._ticker_map = {}
        self._row_for_inst = {}

    def load(self):
        def work():
            try:
                data = get_tickers("SPOT")
                wx.CallAfter(self._set_tickers, data)
            except Exception as e:
                wx.CallAfter(self._show_error, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _set_tickers(self, data: list):
        usdt = [d for d in data if (d.get("instId") or "").endswith("-USDT")]
        self._ticker_map = {d["instId"]: d for d in usdt}
        self._sync_grid()

    def _sync_grid(self):
        rows = sorted(self._ticker_map.keys())
        n = self.grid.GetNumberRows()
        if n > 0:
            self.grid.DeleteRows(0, n)
        for i, inst_id in enumerate(rows[:200]):
            self.grid.AppendRows(1)
            self._update_row(i, inst_id, self._ticker_map[inst_id])
        self._row_for_inst = {inst_id: i for i, inst_id in enumerate(rows[:200])}

    def update_ticker(self, inst_id: str, data: dict):
        self._ticker_map[inst_id] = data
        if inst_id in self._row_for_inst:
            row = self._row_for_inst[inst_id]
            self._update_row(row, inst_id, data)
        else:
            self._sync_grid()

    def _update_row(self, row: int, inst_id: str, d: dict):
        last = d.get("last", "") or d.get("lastPx", "")
        open_px = d.get("open24h", "") or d.get("sodUtc0", "")
        self.grid.SetCellValue(row, 0, inst_id)
        self.grid.SetCellValue(row, 1, str(last))
        try:
            lf, of = float(last), float(open_px)
            ch = ((lf - of) / of * 100) if of else 0
            self.grid.SetCellValue(row, 2, f"{ch:.2f}%")
            self.grid.SetCellBackgroundColour(row, 2, wx.Colour(0, 200, 0) if ch >= 0 else wx.Colour(200, 0, 0))
        except (TypeError, ValueError):
            self.grid.SetCellValue(row, 2, "")
        self.grid.SetCellValue(row, 3, str(d.get("high24h", "") or d.get("highPx", "")))
        self.grid.SetCellValue(row, 4, str(d.get("low24h", "") or d.get("lowPx", "")))
        self.grid.SetCellValue(row, 5, str(d.get("vol24h", "") or d.get("volCcy24h", "")))
        self.grid.SetCellValue(row, 6, str(d.get("ts", ""))[:19] if d.get("ts") else "")

    def _show_error(self, msg: str):
        wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)