@echo off
chcp 65001 >nul
echo ================================================
echo   全球期貨 多時框技術分析看板 - 打包 EXE
echo   12 商品 x 7 時框 x 7 指標
echo ================================================
echo.

pip install -r requirements.txt
echo.

echo 正在打包 ...
pyinstaller --onefile ^
    --name "Global_Dashboard" ^
    --icon=NONE ^
    --add-data "global_dashboard.html;." ^
    --add-data "indicators.py;." ^
    --add-data "data_loader.py;." ^
    --hidden-import=yfinance ^
    --hidden-import=pandas ^
    --hidden-import=numpy ^
    --hidden-import=appdirs ^
    --hidden-import=six ^
    --hidden-import=html5lib ^
    --hidden-import=lxml ^
    --hidden-import=requests ^
    --hidden-import=urllib3 ^
    --hidden-import=certifi ^
    --hidden-import=charset_normalizer ^
    --hidden-import=frozendict ^
    --hidden-import=peewee ^
    --hidden-import=platformdirs ^
    --collect-all yfinance ^
    global_dashboard.py

echo.
echo ================================================
if exist "dist\Global_Dashboard.exe" (
    echo   打包完成!
    echo   EXE: dist\Global_Dashboard.exe
    echo.
    echo   使用: 直接執行 EXE，自動開啟瀏覽器
    echo   注意: 首次啟動需 20-40 秒計算指標
) else (
    echo   打包失敗，請檢查錯誤訊息
)
echo ================================================
pause
