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
    get_candles,
    place_order,
    cancel_order,
    get_orders,
    get_balance,
)
from okx_ws import OKXWebSocket
from candles_chart import CandlesChartPanel


# Custom events for thread-safe UI updates
EVT_WS_TICKER = wx.NewEventType()
EVT_WS_CANDLE = wx.NewEventType()
EVT_WS_ORDER = wx.NewEventType()
EVT_WS_ERROR = wx.NewEventType()
EVT_WS_TICKER_BINDER = wx.PyEventBinder(EVT_WS_TICKER, 1)
EVT_WS_CANDLE_BINDER = wx.PyEventBinder(EVT_WS_CANDLE, 1)
EVT_WS_ORDER_BINDER = wx.PyEventBinder(EVT_WS_ORDER, 1)
EVT_WS_ERROR_BINDER = wx.PyEventBinder(EVT_WS_ERROR, 1)


class WsTickerEvent(wx.PyEvent):
    def __init__(self, inst_id: str, data: dict):
        super().__init__(eventType=EVT_WS_TICKER)
        self.inst_id = inst_id
        self.data = data


class WsCandleEvent(wx.PyEvent):
    def __init__(self, inst_id: str, data: list):
        super().__init__(eventType=EVT_WS_CANDLE)
        self.inst_id = inst_id
        self.data = data


class WsOrderEvent(wx.PyEvent):
    def __init__(self, data: dict):
        super().__init__(eventType=EVT_WS_ORDER)
        self.data = data


class WsErrorEvent(wx.PyEvent):
    def __init__(self, msg: str):
        super().__init__(eventType=EVT_WS_ERROR)
        self.msg = msg


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
        self.list.AppendColumn("Base", width=50)
        self.list.AppendColumn("Quote", width=50)
        layout.Add(self.list, 1, wx.EXPAND)
        self.SetSizer(layout)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_sel)
        self.search.Bind(wx.EVT_TEXT, self._on_filter)
        self._instruments = []
        self._filtered = []

    def load(self):
        def work():
            try:
                data = get_instruments("SPOT")
                wx.CallAfter(self._set_instruments, data)
            except Exception as e:
                wx.CallAfter(self._show_error, str(e))

        threading.Thread(target=work, daemon=True).start()

    def _set_instruments(self, data: list):
        self._instruments = [d for d in data if d.get("state") == "live" and d.get("quoteCcy") == "USDT"]
        self._filtered = self._instruments.copy()
        self._refresh_list()

    def _refresh_list(self):
        self.list.DeleteAllItems()
        for d in self._filtered[:500]:
            self.list.Append((d.get("instId", ""), d.get("baseCcy", ""), d.get("quoteCcy", "")))

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


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="OKX Crypto Desktop", size=(1200, 750))
        self._ws_public: OKXWebSocket | None = None
        self._ws_private: OKXWebSocket | None = None
        self._current_inst_id = "BTC-USDT"
        
        # Menu bar
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_EXIT, "E&xit")
        menubar.Append(file_menu, "&File")
        self.SetMenuBar(menubar)
        self.Bind(wx.EVT_MENU, self.OnExit, id=wx.ID_EXIT)
        self._build_ui()
        self._connect_events()
        self.Centre()
        # Load data
        self.markets_panel.load()
        self.tickers_panel.load()
        self.candles_panel.set_pair(self._current_inst_id)
        self.trading_panel._refresh_orders()
        self._start_ws()

    def _build_ui(self):
        panel = wx.Panel(self)
        main = wx.BoxSizer(wx.HORIZONTAL)
        # Left: markets
        left = wx.BoxSizer(wx.VERTICAL)
        left.Add(wx.StaticText(panel, label="Markets (SPOT USDT)"), 0, wx.ALL, 4)
        self.markets_panel = MarketsPanel(panel, on_select=self._on_market_select)
        self.markets_panel.SetMinSize((220, 200))
        left.Add(self.markets_panel, 1, wx.EXPAND)
        main.Add(left, 0, wx.EXPAND)
        main.Add(wx.StaticLine(panel, style=wx.LI_VERTICAL), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        # Center: tickers + candles
        center = wx.BoxSizer(wx.VERTICAL)
        center.Add(wx.StaticText(panel, label="Tickers (live)"), 0, wx.ALL, 2)
        self.tickers_panel = TickersPanel(panel)
        center.Add(self.tickers_panel, 1, wx.EXPAND)
        center.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)
        center.Add(wx.StaticText(panel, label="Candles"), 0, wx.ALL, 2)



        self.candles_chart_panel = CandlesChartPanel(panel)
        center.Add(self.candles_chart_panel, 1, wx.EXPAND)       
        self.candles_panel = CandlesPanel(panel, on_candles_set=lambda data: self.candles_chart_panel.set_data(data or []))
        center.Add(self.candles_panel, 1, wx.EXPAND)
        main.Add(center, 1, wx.EXPAND)
        main.Add(wx.StaticLine(panel, style=wx.LI_VERTICAL), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        # Right: trading
        right = wx.BoxSizer(wx.VERTICAL)
        self.trading_panel = TradingPanel(panel)
        self.trading_panel.SetMinSize((280, 200))
        right.Add(self.trading_panel, 1, wx.EXPAND)
        main.Add(right, 0, wx.EXPAND)
        panel.SetSizer(main)
        self.status = self.CreateStatusBar()
        self.status.SetStatusText("OKX Spot — REST + WebSocket" + (" (Demo)" if USE_DEMO else ""))

    def _connect_events(self):
        self.Bind(EVT_WS_TICKER_BINDER, self._on_ws_ticker)
        self.Bind(EVT_WS_CANDLE_BINDER, self._on_ws_candle)
        self.Bind(EVT_WS_ORDER_BINDER, self._on_ws_order)
        self.Bind(EVT_WS_ERROR_BINDER, self._on_ws_error)

    def _on_market_select(self, inst_id: str):
        self._current_inst_id = inst_id
        self.candles_panel.set_pair(inst_id)
        self.trading_panel.set_inst_id(inst_id)
        if self._ws_public:
            self._ws_public.subscribe_ticker(inst_id)
            bar = CandlesPanel.BAR_OPTIONS[self.candles_panel.bar_choice.GetSelection()]
            self._ws_public.subscribe_candle(inst_id, bar)
        self.status.SetStatusText(f"Selected {inst_id}")

    def _start_ws(self):
        def on_ticker(msg):
            arg = msg.get("arg", {})
            inst_id = arg.get("instId", "")
            data = msg.get("data")
            if isinstance(data, list) and data:
                data = data[0]
            if inst_id and data:
                evt = WsTickerEvent(inst_id, data if isinstance(data, dict) else {})
                wx.PostEvent(self, evt)

        def on_candle(msg):
            arg = msg.get("arg", {})
            inst_id = arg.get("instId", "")
            data = msg.get("data")
            if isinstance(data, list) and data:
                data = data[0]  # single candle array [ts, o, h, l, c, vol, ...]
            if inst_id and data:
                evt = WsCandleEvent(inst_id, data if isinstance(data, list) else [])
                wx.PostEvent(self, evt)

        def on_error(err):
            wx.PostEvent(self, WsErrorEvent(str(err)))

        self._ws_public = OKXWebSocket(private=False, on_message=lambda m: self._dispatch_ws(m, on_ticker, on_candle), on_error=on_error)
        self._ws_public.start()
        self._ws_public.subscribe_ticker("BTC-USDT")
        self._ws_public.subscribe_candle("BTC-USDT", "1m")
        if API_KEY and SECRET_KEY and PASSPHRASE:
            def on_order(msg):
                wx.PostEvent(self, WsOrderEvent(msg.get("data", {})))

            self._ws_private = OKXWebSocket(private=True, on_message=on_order, on_error=on_error)
            self._ws_private.start()
            self._ws_private.subscribe_orders("SPOT")

    def _dispatch_ws(self, msg, on_ticker, on_candle):
        arg = msg.get("arg", {})
        ch = arg.get("channel", "")
        if ch == "tickers":
            on_ticker(msg)
        elif ch and ch.startswith("candle"):
            on_candle(msg)

    def _on_ws_ticker(self, evt: WsTickerEvent):
        self.tickers_panel.update_ticker(evt.inst_id, evt.data)

    def _on_ws_candle(self, evt: WsCandleEvent):
        self.candles_panel.append_candle(evt.inst_id, evt.data)

    def _on_ws_order(self, evt: WsOrderEvent):
        self.trading_panel.update_order_ws(evt.data)

    def _on_ws_error(self, evt: WsErrorEvent):
        self.status.SetStatusText(f"WS error: {evt.msg}")
        wx.MessageBox(evt.msg, "WebSocket Error", wx.OK | wx.ICON_WARNING)

    def OnExit(self, evt):
        if self._ws_public:
            self._ws_public.stop()
        if self._ws_private:
            self._ws_private.stop()
        self.Destroy()


def main():
    app = wx.App()
    f = MainFrame()
    f.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
