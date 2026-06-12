@echo off
chcp 65001 >nul
echo ========================================
echo   B站 BAS 弹幕工具 - 依赖安装
echo ========================================
echo.
echo 正在安装 opencv-python 和 numpy ...
echo.
pip install opencv-python>=4.5.0 numpy>=1.20.0
echo.
if %errorlevel% equ 0 (
    echo ========================================
    echo   ✅ 安装完成！可以运行 video_to_bas.py
    echo ========================================
) else (
    echo ========================================
    echo   ❌ 安装失败，请检查网络或 pip 配置
    echo ========================================
)
echo.
pause
