@echo off
chcp 65001 >nul
echo ========================================
echo   台指期多時框看板 - 打包 EXE
echo ========================================
echo.

pip install -r requirements.txt
echo.

echo 正在打包...
pyinstaller --onefile --windowed ^
    --name "TW_Futures_Dashboard" ^
    --add-data "indicators.py;." ^
    --add-data "data_loader.py;." ^
    --add-data "gui.py;." ^
    --hidden-import=yfinance ^
    --hidden-import=pandas ^
    --hidden-import=numpy ^
    main.py

echo.
echo ========================================
if exist "dist\TW_Futures_Dashboard.exe" (
    echo   打包完成!
    echo   EXE 位置: dist\TW_Futures_Dashboard.exe
    echo.
    echo   使用方式:
    echo   將 EXE 複製到 CSV 資料檔所在的資料夾即可執行
) else (
    echo   打包失敗，請檢查錯誤訊息
)
echo ========================================
pause
