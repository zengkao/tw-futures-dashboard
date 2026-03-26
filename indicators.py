"""
台指期多時框看板 - 技術指標計算模組

指標列表:
  1. 本根 - K棒方向 (Close vs Open)
  2. KD  - 隨機指標 (台灣標準 9,3,3)
  3. MA  - 移動平均線 (20期)
  4. VWAP - 成交量加權平均價 (滾動20期)
  5. MC  - MACD (12,26,9)
  6. SAR - 拋物線SAR (0.02, 0.2)
  7. ST  - SuperTrend (ATR10, 乘數3)
"""

import numpy as np
import pandas as pd


def bar_direction(df: pd.DataFrame) -> int:
    """本根方向"""
    if len(df) == 0:
        return 0
    last = df.iloc[-1]
    if last['Close'] > last['Open']:
        return 1
    elif last['Close'] < last['Open']:
        return -1
    return 0


def stochastic_kd(df: pd.DataFrame, period=9) -> int:
    """KD指標 (台灣標準: RSV→K=2/3*K_prev+1/3*RSV, D=2/3*D_prev+1/3*K)"""
    if len(df) < period:
        return 0
    lowest = df['Low'].rolling(period, min_periods=1).min()
    highest = df['High'].rolling(period, min_periods=1).max()
    denom = highest - lowest
    denom = denom.replace(0, np.nan)
    rsv = ((df['Close'] - lowest) / denom * 100).fillna(50)
    # ewm(alpha=1/3) ≡ K = 1/3*RSV + 2/3*K_prev
    k = rsv.ewm(alpha=1.0 / 3, adjust=False).mean()
    d = k.ewm(alpha=1.0 / 3, adjust=False).mean()
    if k.iloc[-1] > d.iloc[-1]:
        return 1
    elif k.iloc[-1] < d.iloc[-1]:
        return -1
    return 0


def moving_average(df: pd.DataFrame, period=20) -> int:
    """移動平均線"""
    if len(df) < period:
        period = max(1, len(df))
    ma = df['Close'].rolling(period, min_periods=1).mean()
    if df['Close'].iloc[-1] > ma.iloc[-1]:
        return 1
    elif df['Close'].iloc[-1] < ma.iloc[-1]:
        return -1
    return 0


def calc_vwap(df: pd.DataFrame, period=20) -> int:
    """滾動VWAP"""
    if len(df) == 0:
        return 0
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vol_sum = df['Volume'].rolling(period, min_periods=1).sum()
    vp_sum = (tp * df['Volume']).rolling(period, min_periods=1).sum()
    vol_sum = vol_sum.replace(0, np.nan)
    vwap_val = vp_sum / vol_sum
    last_close = df['Close'].iloc[-1]
    last_vwap = vwap_val.iloc[-1]
    if pd.isna(last_vwap):
        return 0
    if last_close > last_vwap:
        return 1
    elif last_close < last_vwap:
        return -1
    return 0


def calc_macd(df: pd.DataFrame, fast=12, slow=26, signal_period=9) -> int:
    """MACD"""
    if len(df) < slow:
        return 0
    close = df['Close']
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    if macd_line.iloc[-1] > signal_line.iloc[-1]:
        return 1
    elif macd_line.iloc[-1] < signal_line.iloc[-1]:
        return -1
    return 0


def parabolic_sar(df: pd.DataFrame, af_start=0.02, af_step=0.02, af_max=0.2) -> int:
    """拋物線SAR"""
    if len(df) < 5:
        return 0
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    close = df['Close'].values.astype(float)
    n = len(df)

    sar = np.zeros(n)
    is_uptrend = close[1] > close[0]
    af = af_start

    if is_uptrend:
        sar[0] = low[0]
        ep = high[0]
    else:
        sar[0] = high[0]
        ep = low[0]

    for i in range(1, n):
        prev_sar = sar[i - 1]
        sar[i] = prev_sar + af * (ep - prev_sar)

        if is_uptrend:
            sar[i] = min(sar[i], low[i - 1])
            if i >= 2:
                sar[i] = min(sar[i], low[i - 2])
            if low[i] < sar[i]:
                is_uptrend = False
                sar[i] = ep
                ep = low[i]
                af = af_start
            else:
                if high[i] > ep:
                    ep = high[i]
                    af = min(af + af_step, af_max)
        else:
            sar[i] = max(sar[i], high[i - 1])
            if i >= 2:
                sar[i] = max(sar[i], high[i - 2])
            if high[i] > sar[i]:
                is_uptrend = True
                sar[i] = ep
                ep = high[i]
                af = af_start
            else:
                if low[i] < ep:
                    ep = low[i]
                    af = min(af + af_step, af_max)

    if close[-1] > sar[-1]:
        return 1
    elif close[-1] < sar[-1]:
        return -1
    return 0


def supertrend(df: pd.DataFrame, period=10, multiplier=3.0) -> int:
    """SuperTrend"""
    if len(df) < period + 1:
        return 0
    high = df['High'].values.astype(float)
    low = df['Low'].values.astype(float)
    close = df['Close'].values.astype(float)
    n = len(df)

    # True Range & ATR
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))
    atr = np.zeros(n)
    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    # 前 period-1 用簡單平均填充
    for i in range(period - 1):
        atr[i] = np.mean(tr[: i + 1])

    hl2 = (high + low) / 2.0
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    upper_band = np.copy(upper_basic)
    lower_band = np.copy(lower_basic)
    direction = np.ones(n)  # 1=多, -1=空

    for i in range(1, n):
        # Final upper band
        if upper_basic[i] < upper_band[i - 1] or close[i - 1] > upper_band[i - 1]:
            upper_band[i] = upper_basic[i]
        else:
            upper_band[i] = upper_band[i - 1]
        # Final lower band
        if lower_basic[i] > lower_band[i - 1] or close[i - 1] < lower_band[i - 1]:
            lower_band[i] = lower_basic[i]
        else:
            lower_band[i] = lower_band[i - 1]
        # Direction
        if direction[i - 1] == 1:
            if close[i] < lower_band[i]:
                direction[i] = -1
            else:
                direction[i] = 1
        else:
            if close[i] > upper_band[i]:
                direction[i] = 1
            else:
                direction[i] = -1

    return int(direction[-1])


def calculate_all_signals(df: pd.DataFrame) -> dict:
    """計算所有指標的最新信號 (1=多, -1=空, 0=中性)"""
    # 只取最後500根做計算 (加速且足夠精確)
    calc_df = df.tail(500).copy()
    return {
        '本根': bar_direction(calc_df),
        'KD': stochastic_kd(calc_df),
        'MA': moving_average(calc_df),
        'VWAP': calc_vwap(calc_df),
        'MC': calc_macd(calc_df),
        'SAR': parabolic_sar(calc_df),
        'ST': supertrend(calc_df),
    }
