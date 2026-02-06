"""
CandlesChartPanel: draw OHLCV candlestick chart with volume.
Data format: list of [ts, open, high, low, close, vol, ...] (OKX style).
"""
import wx
from datetime import datetime, timezone


def _f(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


class CandlesChartPanel(wx.Panel):
    """Draw candlesticks (OHLC) and volume bars. Call set_data() with list of [ts, o, h, l, c, vol, ...]."""

    MARGIN_LEFT = 52
    MARGIN_RIGHT = 12
    MARGIN_TOP = 24
    MARGIN_BOTTOM = 48
    VOL_HEIGHT_RATIO = 0.22  # volume area height ratio of chart

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._candles = []  # list of [ts, o, h, l, c, vol, ...]
        self.SetBackgroundColour(wx.Colour(28, 30, 34))
        self.SetMinSize((300, 180))
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_data(self, data: list):
        """Set OHLCV data. Each row: [ts, open, high, low, close, vol, ...] (OKX order)."""
        if not data:
            self._candles = []
        else:
            self._candles = list(data)
        self.Refresh()

    def append_candle(self, row: list):
        """Append one candle and refresh."""
        self._candles.append(row)
        self.Refresh()

    def _on_size(self, evt):
        self.Refresh()
        evt.Skip()

    def _on_paint(self, evt):
        dc = wx.PaintDC(self)
        w, h = self.GetClientSize()
        if w <= 0 or h <= 0:
            return
        self._draw(dc, w, h)

    def _draw(self, dc: wx.DC, w: int, h: int):
        candles = self._candles
        if not candles:
            dc.SetTextForeground(wx.Colour(120, 120, 120))
            dc.DrawText("No candle data", self.MARGIN_LEFT, self.MARGIN_TOP + 20)
            return

        # Parse to floats; OKX order is [ts, o, h, l, c, vol, ...]
        rows = []
        for c in candles:
            ts = c[0]
            o, hi, lo, cl = _f(c[1]), _f(c[2]), _f(c[3]), _f(c[4])
            vol = _f(c[5]) if len(c) > 5 else 0.0
            rows.append((ts, o, hi, lo, cl, vol))

        n = len(rows)
        price_min = min(r[3] for r in rows)
        price_max = max(r[2] for r in rows)
        if price_max <= price_min:
            price_max = price_min + 1.0
        vol_max = max(r[5] for r in rows) or 1.0

        # Chart area
        chart_left = self.MARGIN_LEFT
        chart_right = w - self.MARGIN_RIGHT
        chart_top = self.MARGIN_TOP
        chart_bottom = h - self.MARGIN_BOTTOM
        chart_w = chart_right - chart_left
        chart_h = chart_bottom - chart_top

        vol_area_h = int(chart_h * self.VOL_HEIGHT_RATIO)
        candle_area_h = chart_h - vol_area_h
        vol_top = chart_top + candle_area_h

        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(wx.Colour(60, 62, 68), 1))

        # Price scale labels (left)
        for i in range(5):
            y = chart_top + (candle_area_h * i) // 4
            p = price_max - (price_max - price_min) * i / 4
            dc.SetTextForeground(wx.Colour(140, 142, 148))
            dc.DrawText(f"{p:.4g}", chart_left - 48, y - 6)
        dc.DrawLine(chart_left, chart_top, chart_left, chart_top + candle_area_h)
        dc.DrawLine(chart_left, vol_top, chart_left, chart_bottom)

        # Candles
        bar_w = max(2, (chart_w - 2) // n - 2)
        gap = 1
        x0 = chart_left + 2

        for i, (ts, o, hi, lo, cl, vol) in enumerate(rows):
            x = x0 + i * (bar_w + gap)
            xc = x + bar_w // 2

            # Y scale: top = price_max, bottom = price_min
            def py(price):
                t = (price - price_min) / (price_max - price_min)
                return chart_top + int((1.0 - t) * candle_area_h)

            y_hi = py(hi)
            y_lo = py(lo)
            y_o = py(o)
            y_c = py(cl)

            is_up = cl >= o
            colour = wx.Colour(34, 180, 114) if is_up else wx.Colour(230, 72, 82)
            dc.SetPen(wx.Pen(colour, 1))
            dc.SetBrush(wx.Brush(colour))

            # Wick
            dc.DrawLine(xc, y_hi, xc, y_lo)
            # Body
            body_top = min(y_o, y_c)
            body_h = max(1, abs(y_c - y_o))
            dc.DrawRectangle(x, body_top, bar_w, body_h)

        # Volume bars
        for i, (ts, o, hi, lo, cl, vol) in enumerate(rows):
            x = x0 + i * (bar_w + gap)
            is_up = cl >= o
            colour = wx.Colour(34, 180, 114, 180) if is_up else wx.Colour(230, 72, 82, 180)
            dc.SetPen(wx.Pen(colour, 1))
            dc.SetBrush(wx.Brush(colour))
            vh = int((vol / vol_max) * (vol_area_h - 4)) if vol_max else 0
            vy = vol_top + (vol_area_h - 4) - vh
            dc.DrawRectangle(x, vy, bar_w, max(1, vh))

        # Time labels (bottom, sample)
        dc.SetTextForeground(wx.Colour(140, 142, 148))
        step = max(1, n // 6)
        for i in range(0, n, step):
            if i >= n:
                break
            ts = rows[i][0]
            try:
                t = int(ts) / 1000
                dt = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%m-%d %H:%M")
            except Exception:
                dt = str(ts)
            x = x0 + i * (bar_w + gap)
            dc.DrawText(dt, x - 20, chart_bottom - 16)
