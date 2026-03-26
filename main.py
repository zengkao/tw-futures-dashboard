"""
台指期多時框看板 - 主程式

多時間框架技術指標看板:
  時框: 5分/10分/30分/60分/日/週/月
  指標: 本根/KD/MA/VWAP/MACD/SAR/SuperTrend
  資料: CSV + Yahoo Finance + TAIFEX API
"""

import sys
import os

# 判斷執行環境
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 確保模組路徑
sys.path.insert(0, BASE_DIR)

from gui import DashboardApp


def main():
    app = DashboardApp(data_dir=BASE_DIR)
    app.mainloop()


if __name__ == '__main__':
    main()
