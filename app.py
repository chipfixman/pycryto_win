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
    # get_instruments,
    get_tickers,
    place_order,
    cancel_order,
    get_orders,
    get_balance,
)
from okx_ws import OKXWebSocket
from candles_chart import CandlesChartPanel
# from tickers_sidebar import TickersPanel
from markets_sidebar import MarketsPanel
from trading_panel import TradingPanel

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
        
        # build UI
        self._build_ui()
        
        self._connect_events()
        self.Centre()
        # Load data
        self.markets_panel.load()
        # self.tickers_panel.load()
        #self.candles_panel.set_pair(self._current_inst_id)
        self.candles_chart_panel.set_pair(self._current_inst_id)
        
        self.trading_panel._refresh_orders()
        self._start_ws()

    def _build_ui(self):
        panel = wx.Panel(self)
        main = wx.BoxSizer(wx.HORIZONTAL)
        # Left: markets
        left = wx.BoxSizer(wx.VERTICAL)
        left.Add(wx.StaticText(panel, label="Markets (SPOT USDT)"), 0, wx.ALL, 4)
        self.markets_panel = MarketsPanel(panel, on_select=self._on_market_select)
        self.markets_panel.SetMinSize((370, 200))
        left.Add(self.markets_panel, 1, wx.EXPAND)
        main.Add(left, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        main.Add(wx.StaticLine(panel, style=wx.LI_VERTICAL), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        # Center: tickers + candles
        # center = wx.BoxSizer(wx.VERTICAL)
        # center.Add(wx.StaticText(panel, label="Tickers (live)"), 0, wx.ALL, 2)
        # self.tickers_panel = TickersPanel(panel)
        # center.Add(self.tickers_panel, 1, wx.EXPAND)
        # center.Add(wx.StaticLine(panel), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)
        # center.Add(wx.StaticText(panel, label="Candles"), 0, wx.ALL, 2)
        # main.Add(center, 1, wx.EXPAND)
        # main.Add(center, proportion=0, flag=wx.EXPAND | wx.ALL, border=5)
        # main.Add(wx.StaticLine(panel, style=wx.LI_VERTICAL), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        

        # Right: candle and trading
        right = wx.BoxSizer(wx.VERTICAL)
        # candles
        self.candles_chart_panel = CandlesChartPanel(panel)
        # center.Add(self.candles_chart_panel, 1, wx.EXPAND)       
        # self.candles_panel = CandlesPanel(panel, on_candles_set=lambda data: self.candles_chart_panel.set_data(data or []))
        # center.Add(self.candles_panel, 1, wx.EXPAND)
        right.Add(self.candles_chart_panel, 1, wx.EXPAND)

        self.trading_panel = TradingPanel(panel)
        self.trading_panel.SetMinSize((580, 200))
        right.Add(self.trading_panel, 1, wx.EXPAND)
        # main.Add(right, 0, wx.EXPAND)
        main.Add(right, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)

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
        self.candles_chart_panel.set_pair(inst_id)
        self.trading_panel.set_inst_id(inst_id)
        if self._ws_public:
            self._ws_public.subscribe_ticker(inst_id)
            # bar = CandlesPanel.BAR_OPTIONS[self.candles_panel.bar_choice.GetSelection()]
            bar = "1m"
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
