"""
台指期多時框看板 - GUI模組
"""

import tkinter as tk
from tkinter import messagebox
import threading
from datetime import datetime

from data_loader import load_all_timeframes, get_latest_price
from indicators import calculate_all_signals

# === 色彩定義 ===
COLOR_BG = '#161a2e'
COLOR_HEADER_BG = '#2a2f4f'
COLOR_CELL_NEUTRAL = '#22263e'
COLOR_BULL = '#1a6b35'       # 多 - 深綠
COLOR_BEAR = '#9b1b1b'       # 空 - 深紅
COLOR_BULL_TEXT = '#4cff88'
COLOR_BEAR_TEXT = '#ff5555'
COLOR_TEXT = '#e0e0e0'
COLOR_DIM = '#666680'
COLOR_SUMMARY_NEUTRAL_BG = '#2a3050'

TIMEFRAMES = ['5', '10', '30', '60', '日', '週', '月']
INDICATOR_KEYS = ['本根', 'KD', 'MA', 'VWAP', 'MC', 'SAR', 'ST']
HEADERS = ['時框'] + INDICATOR_KEYS + ['分數', '總結']


class DashboardApp(tk.Tk):
    def __init__(self, data_dir: str):
        super().__init__()
        self.data_dir = data_dir
        self.title("台指期多時框看板")
        self.configure(bg=COLOR_BG)
        self.resizable(False, False)

        self.auto_refresh = True
        self.refresh_interval = 300_000  # 5分鐘 (ms)
        self._refresh_job = None
        self._loading = False

        self.cells = {}
        self._create_widgets()
        self._center_window()
        self.refresh_data()

    def _center_window(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        # === 標題區 ===
        title_frame = tk.Frame(self, bg=COLOR_BG)
        title_frame.pack(fill='x', padx=20, pady=(15, 0))

        tk.Label(
            title_frame, text="台指期 多時框看板",
            font=("Microsoft JhengHei", 22, "bold"),
            fg="#ffffff", bg=COLOR_BG
        ).pack()

        # === 報價區 ===
        price_frame = tk.Frame(self, bg=COLOR_BG)
        price_frame.pack(fill='x', padx=20, pady=(8, 0))

        self.price_label = tk.Label(
            price_frame, text="載入中...",
            font=("Consolas", 18, "bold"),
            fg=COLOR_BULL_TEXT, bg=COLOR_BG
        )
        self.price_label.pack()

        self.change_label = tk.Label(
            price_frame, text="",
            font=("Consolas", 12),
            fg=COLOR_DIM, bg=COLOR_BG
        )
        self.change_label.pack()

        # === 更新時間 ===
        self.time_label = tk.Label(
            self, text="",
            font=("Microsoft JhengHei", 9),
            fg=COLOR_DIM, bg=COLOR_BG
        )
        self.time_label.pack(pady=(4, 8))

        # === 看板表格 ===
        grid_frame = tk.Frame(self, bg=COLOR_BG)
        grid_frame.pack(padx=20, pady=5)

        col_widths = [5, 4, 4, 4, 5, 4, 4, 4, 4, 5]

        # 表頭
        for j, header in enumerate(HEADERS):
            lbl = tk.Label(
                grid_frame, text=header,
                font=("Microsoft JhengHei", 11, "bold"),
                fg="#ffffff", bg=COLOR_HEADER_BG,
                width=col_widths[j], height=2,
                relief="flat", borderwidth=0,
                padx=4
            )
            lbl.grid(row=0, column=j, sticky="nsew", padx=1, pady=1)

        # 資料行
        for i, tf in enumerate(TIMEFRAMES):
            for j in range(len(HEADERS)):
                if j == 0:
                    text = tf
                    bg = COLOR_HEADER_BG
                    fg = "#ffffff"
                    font = ("Microsoft JhengHei", 12, "bold")
                else:
                    text = "–"
                    bg = COLOR_CELL_NEUTRAL
                    fg = COLOR_DIM
                    font = ("Microsoft JhengHei", 12)

                lbl = tk.Label(
                    grid_frame, text=text,
                    font=font, fg=fg, bg=bg,
                    width=col_widths[j], height=2,
                    relief="flat", borderwidth=0,
                    padx=4
                )
                lbl.grid(row=i + 1, column=j, sticky="nsew", padx=1, pady=1)
                self.cells[(i, j)] = lbl

        # === 底部控制列 ===
        bottom_frame = tk.Frame(self, bg=COLOR_BG)
        bottom_frame.pack(fill='x', padx=20, pady=(12, 15))

        self.refresh_btn = tk.Button(
            bottom_frame, text="⟳ 更新資料",
            command=self.refresh_data,
            font=("Microsoft JhengHei", 10),
            bg=COLOR_HEADER_BG, fg="#ffffff",
            activebackground='#3a3f6f', activeforeground='#ffffff',
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.refresh_btn.pack(side='left', padx=(0, 10))

        self.auto_btn = tk.Button(
            bottom_frame, text="自動更新: ON",
            command=self._toggle_auto_refresh,
            font=("Microsoft JhengHei", 10),
            bg=COLOR_HEADER_BG, fg=COLOR_BULL_TEXT,
            activebackground='#3a3f6f', activeforeground=COLOR_BULL_TEXT,
            relief="flat", padx=12, pady=4, cursor="hand2"
        )
        self.auto_btn.pack(side='left', padx=(0, 10))

        self.mode_label = tk.Label(
            bottom_frame, text="模式: 非重繪",
            font=("Microsoft JhengHei", 9),
            fg=COLOR_DIM, bg=COLOR_BG
        )
        self.mode_label.pack(side='left', padx=(0, 10))

        self.source_label = tk.Label(
            bottom_frame, text="資料源: –",
            font=("Microsoft JhengHei", 9),
            fg=COLOR_DIM, bg=COLOR_BG
        )
        self.source_label.pack(side='right')

    def refresh_data(self):
        """更新資料並重新計算指標"""
        if self._loading:
            return
        self._loading = True
        self.refresh_btn.config(state='disabled', text="更新中...")

        def do_refresh():
            try:
                tf_data = load_all_timeframes(self.data_dir, use_online=True)
                data_source = tf_data.pop('_source', 'CSV')

                results = {}
                for tf_name in TIMEFRAMES:
                    if tf_name in tf_data and len(tf_data[tf_name]) > 0:
                        signals = calculate_all_signals(tf_data[tf_name])
                        results[tf_name] = signals

                price_info = get_latest_price(tf_data)
                self.after(0, lambda: self._update_display(
                    results, price_info, data_source
                ))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda m=err_msg: self._show_error(m))
            finally:
                self.after(0, self._refresh_done)

        thread = threading.Thread(target=do_refresh, daemon=True)
        thread.start()

    def _refresh_done(self):
        self._loading = False
        self.refresh_btn.config(state='normal', text="⟳ 更新資料")
        self._schedule_next_refresh()

    def _schedule_next_refresh(self):
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None
        if self.auto_refresh:
            self._refresh_job = self.after(
                self.refresh_interval, self.refresh_data
            )

    def _toggle_auto_refresh(self):
        self.auto_refresh = not self.auto_refresh
        if self.auto_refresh:
            self.auto_btn.config(text="自動更新: ON", fg=COLOR_BULL_TEXT)
            self._schedule_next_refresh()
        else:
            self.auto_btn.config(text="自動更新: OFF", fg=COLOR_BEAR_TEXT)
            if self._refresh_job:
                self.after_cancel(self._refresh_job)
                self._refresh_job = None

    def _update_display(self, results: dict, price_info: dict | None,
                        data_source: str):
        """更新看板顯示"""
        # 報價
        if price_info:
            price = price_info['price']
            change = price_info['change']
            change_pct = price_info['change_pct']
            vol = price_info['volume']

            self.price_label.config(text=f"{price:,.0f}")

            if change >= 0:
                arrow = "▲"
                color = COLOR_BULL_TEXT
            else:
                arrow = "▼"
                color = COLOR_BEAR_TEXT

            self.change_label.config(
                text=f"{arrow} {change:+.0f} ({change_pct:+.2f}%)  Vol: {vol:,.0f}",
                fg=color
            )
            self.price_label.config(fg=color)

        # 更新時間
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.time_label.config(text=f"更新時間: {now}")

        # 資料源
        self.source_label.config(text=f"資料源: {data_source}")

        # 更新表格
        for i, tf in enumerate(TIMEFRAMES):
            if tf not in results:
                continue
            signals = results[tf]

            for j_idx, key in enumerate(INDICATOR_KEYS):
                col = j_idx + 1
                signal = signals.get(key, 0)

                if key == '本根':
                    if signal == 1:
                        text, bg, fg = '▲', COLOR_BULL, COLOR_BULL_TEXT
                    elif signal == -1:
                        text, bg, fg = '▼', COLOR_BEAR, COLOR_BEAR_TEXT
                    else:
                        text, bg, fg = '·', COLOR_CELL_NEUTRAL, COLOR_DIM
                else:
                    if signal == 1:
                        text, bg, fg = '多', COLOR_BULL, '#ffffff'
                    elif signal == -1:
                        text, bg, fg = '空', COLOR_BEAR, '#ffffff'
                    else:
                        text, bg, fg = '–', COLOR_CELL_NEUTRAL, COLOR_DIM

                self.cells[(i, col)].config(text=text, bg=bg, fg=fg)

            # 分數 (6指標合計，不含本根)
            score = sum(signals.get(k, 0) for k in INDICATOR_KEYS[1:])
            score_col = len(INDICATOR_KEYS) + 1

            if score > 0:
                s_bg, s_fg = COLOR_BULL, COLOR_BULL_TEXT
            elif score < 0:
                s_bg, s_fg = COLOR_BEAR, COLOR_BEAR_TEXT
            else:
                s_bg, s_fg = COLOR_CELL_NEUTRAL, COLOR_DIM

            self.cells[(i, score_col)].config(
                text=str(score), bg=s_bg, fg=s_fg
            )

            # 總結
            summary_col = score_col + 1
            if score > 0:
                s_text = '偏多'
                s_bg, s_fg = COLOR_BULL, COLOR_BULL_TEXT
            elif score < 0:
                s_text = '偏空'
                s_bg, s_fg = COLOR_BEAR, COLOR_BEAR_TEXT
            else:
                s_text = '中性'
                s_bg, s_fg = COLOR_SUMMARY_NEUTRAL_BG, '#ffffff'

            self.cells[(i, summary_col)].config(
                text=s_text, bg=s_bg, fg=s_fg
            )

    def _show_error(self, msg: str):
        self.time_label.config(text=f"錯誤: {msg}", fg=COLOR_BEAR_TEXT)
