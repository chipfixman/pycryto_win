"""
OKX Crypto Desktop App - wxPython 4.
Markets, tickers, candles (REST + WebSocket), spot trading (REST + WebSocket).
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
    place_order,
    cancel_order,
    get_orders,
    get_balance,
)
from okx_ws import OKXWebSocket
from candles_chart import CandlesChartPanel
from tickers_sidebar import TickersPanel
from markets_sidebar import MarketsPanel



class TradingPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(wx.StaticText(self, label="Spot order (REST)"), 0, wx.ALL, 2)
        fgs = wx.FlexGridSizer(5, 2, 4, 4)
        fgs.Add(wx.StaticText(self, label="Pair:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.inst_id = wx.TextCtrl(self, value="BTC-USDT", size=(120, -1))
        fgs.Add(self.inst_id, 0)
        fgs.Add(wx.StaticText(self, label="Side:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.side = wx.Choice(self, choices=["buy", "sell"])
        self.side.SetSelection(0)
        fgs.Add(self.side, 0)
        fgs.Add(wx.StaticText(self, label="Type:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.ord_type = wx.Choice(self, choices=["limit", "market"])
        self.ord_type.SetSelection(0)
        fgs.Add(self.ord_type, 0)
        fgs.Add(wx.StaticText(self, label="Price:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.px = wx.TextCtrl(self, value="", size=(100, -1))
        fgs.Add(self.px, 0)
        fgs.Add(wx.StaticText(self, label="Size:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.sz = wx.TextCtrl(self, value="0.001", size=(100, -1))
        fgs.Add(self.sz, 0)
        layout.Add(fgs, 0, wx.ALL, 4)
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.place_btn = wx.Button(self, label="Place order")
        self.cancel_btn = wx.Button(self, label="Cancel selected")
        btn_row.Add(self.place_btn, 0, wx.RIGHT, 4)
        btn_row.Add(self.cancel_btn, 0)
        layout.Add(btn_row, 0, wx.ALL, 4)
        layout.Add(wx.StaticText(self, label="Open orders:"), 0, wx.ALL, 2)
        self.orders_list = wx.ListCtrl(self, style=wx.LC_REPORT)
        self.orders_list.AppendColumn("Order ID", width=100)
        self.orders_list.AppendColumn("Pair", width=90)
        self.orders_list.AppendColumn("Side", width=50)
        self.orders_list.AppendColumn("Price", width=80)
        self.orders_list.AppendColumn("Size", width=80)
        self.orders_list.AppendColumn("State", width=60)
        layout.Add(self.orders_list, 1, wx.EXPAND)
        self.SetSizer(layout)
        self.place_btn.Bind(wx.EVT_BUTTON, self._on_place)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        self.orders_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_order_sel)
        self._selected_ord_id = None
        self._selected_inst_id = None

    def set_inst_id(self, inst_id: str):
        self.inst_id.SetValue(inst_id or "BTC-USDT")

    def _on_place(self, evt):
        if not API_KEY or not SECRET_KEY or not PASSPHRASE:
            wx.MessageBox("Set OKX_API_KEY, OKX_SECRET_KEY, OKX_PASSPHRASE to trade.", "Config", wx.OK)
            return
        inst_id = self.inst_id.GetValue().strip()
        side = ["buy", "sell"][self.side.GetSelection()]
        ord_type = ["limit", "market"][self.ord_type.GetSelection()]
        sz = self.sz.GetValue().strip()
        px = self.px.GetValue().strip() if ord_type == "limit" else None
        if not inst_id or not sz:
            wx.MessageBox("Pair and size required.", "Error", wx.OK | wx.ICON_ERROR)
            return
        if ord_type == "limit" and (not px or float(px) <= 0):
            wx.MessageBox("Price required for limit order.", "Error", wx.OK | wx.ICON_ERROR)
            return

        def work():
            try:
                out = place_order(inst_id, side, ord_type, sz, px=px)
                msg = out.get("msg", "")
                s_code = out.get("data", [{}])[0].get("sCode", "") if out.get("data") else ""
                code = out.get("code", "")
                if code == "0" or s_code == "0":
                    wx.CallAfter(wx.MessageBox, "Order placed.", "OK", wx.OK)
                    wx.CallAfter(self._refresh_orders)
                else:
                    wx.CallAfter(wx.MessageBox, msg or str(out), "Error", wx.OK | wx.ICON_ERROR)
            except Exception as e:
                wx.CallAfter(wx.MessageBox, str(e), "Error", wx.OK | wx.ICON_ERROR)

        threading.Thread(target=work, daemon=True).start()

    def _on_cancel(self, evt):
        if not self._selected_ord_id or not self._selected_inst_id:
            wx.MessageBox("Select an order first.", "Error", wx.OK)
            return
        if not API_KEY or not SECRET_KEY or not PASSPHRASE:
            wx.MessageBox("Set API credentials to cancel.", "Config", wx.OK)
            return
        ord_id = self._selected_ord_id
        inst_id = self._selected_inst_id

        def work():
            try:
                out = cancel_order(inst_id, ord_id)
                if out.get("code") == "0":
                    wx.CallAfter(wx.MessageBox, "Order cancelled.", "OK", wx.OK)
                    wx.CallAfter(self._refresh_orders)
                else:
                    wx.CallAfter(wx.MessageBox, out.get("msg", "Cancel failed"), "Error", wx.OK | wx.ICON_ERROR)
            except Exception as e:
                wx.CallAfter(wx.MessageBox, str(e), "Error", wx.OK | wx.ICON_ERROR)

        threading.Thread(target=work, daemon=True).start()

    def _on_order_sel(self, evt):
        idx = evt.GetIndex()
        self._selected_ord_id = self.orders_list.GetItemText(idx, 0)
        self._selected_inst_id = self.orders_list.GetItemText(idx, 1)

    def _refresh_orders(self):
        if not API_KEY or not SECRET_KEY or not PASSPHRASE:
            return

        def work():
            try:
                data = get_orders("SPOT")
                wx.CallAfter(self._set_orders, data)
            except Exception as e:
                wx.CallAfter(wx.MessageBox, str(e), "Error", wx.OK | wx.ICON_ERROR)

        threading.Thread(target=work, daemon=True).start()

    def _set_orders(self, data: list):
        self.orders_list.DeleteAllItems()
        for d in data:
            self.orders_list.Append((
                d.get("ordId", ""),
                d.get("instId", ""),
                d.get("side", ""),
                d.get("px", ""),
                d.get("sz", ""),
                d.get("state", ""),
            ))

    def update_order_ws(self, data: dict):
        wx.CallAfter(self._refresh_orders)

