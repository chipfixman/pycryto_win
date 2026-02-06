

"""
markets
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

class AutoWidthListCtrl(wx.ListCtrl, ListCtrlAutoWidthMixin):
    def __init__(self, parent, *args, **kwargs):
        wx.ListCtrl.__init__(self, parent, *args, **kwargs)
        ListCtrlAutoWidthMixin.__init__(self)


class MarketsPanel(wx.Panel):
    def __init__(self, parent, on_select: callable):
        super().__init__(parent)
        self.on_select = on_select
        layout = wx.BoxSizer(wx.VERTICAL)
        self.search = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.search.SetDescriptiveText("Filter pair...")
        layout.Add(self.search, 0, wx.EXPAND | wx.ALL, 2)
        self.list = AutoWidthListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.list.AppendColumn("Pair", width=120)
        self.list.AppendColumn("Price", width=50)
        self.list.AppendColumn("Change", width=50)
        layout.Add(self.list, 1, wx.EXPAND)
        self.SetSizer(layout)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_sel)
        self.search.Bind(wx.EVT_TEXT, self._on_filter)
        self._instruments = []
        self._filtered = []

    def load(self):
        def work():
            try:
                # data = get_instruments("SPOT")
                data = data = get_tickers("SPOT")
                wx.CallAfter(self._set_instruments, data)
            except Exception as e:
                wx.CallAfter(self._show_error, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _set_instruments(self, data: list):
        # self._instruments = [d for d in data if d.get("state") == "live" and d.get("quoteCcy") == "USDT"]
        # self._filtered = self._instruments.copy()
        self._tickers = [d for d in data if (d.get("instId") or "").endswith("-USDT")]
        self._filtered = self._tickers.copy()
        self._refresh_list()

    def _refresh_list(self):
        self.list.DeleteAllItems()
        for d in self._filtered: #[:150]:
            last = last = d.get("last", "") or d.get("lastPx", "")
            open_px = d.get("open24h", "") or d.get("sodUtc0", "")
            try:
                lf, of = float(last), float(open_px)
                ch = ((lf - of) / of * 100) if of else 0
                self.list.Append((d.get("instId", ""), last, ch))
            except (TypeError, ValueError):
                # self.grid.SetCellValue(row, 2, "")
                self.list.Append((d.get("instId", ""), last, ""))

            

    def _on_filter(self, evt):
        q = self.search.GetValue().strip().upper()
        if not q:
            self._filtered = self._instruments.copy()
        else:
            self._filtered = [d for d in self._instruments if q in (d.get("instId") or "").upper()]
        self._refresh_list()

    def _on_sel(self, evt):
        idx = evt.GetIndex()
        if 0 <= idx < len(self._filtered):
            inst_id = self._filtered[idx].get("instId", "")
            if inst_id and self.on_select:
                self.on_select(inst_id)

    def _show_error(self, msg: str):
        wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR)


