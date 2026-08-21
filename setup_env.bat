@echo off
setlocal enabledelayedexpansion

title Heytea Painter - Portable Setup
cd /d "%~dp0"

echo ========================================
echo Heytea Painter - 便携式环境安装
echo ========================================
echo.

REM Check if env exists
if exist "env\" (
    echo [INFO] 虚拟环境已存在: env/
    echo [INFO] 跳过安装...
    goto :complete
)

echo [步骤 1/3] 检查 Python 安装...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] 未找到 Python！
    echo.
    echo 请先安装 Python 3.10 或更高版本
    echo 下载地址: https://www.python.org/downloads/
    echo.
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo [INFO] 找到 Python %PYTHON_VERSION%
echo.

echo [步骤 2/3] 创建虚拟环境...
python -m venv env

if errorlevel 1 (
    echo [ERROR] 创建虚拟环境失败！
    pause
    exit /b 1
)

echo [INFO] 虚拟环境创建成功
echo.

echo [步骤 3/3] 安装依赖包...
echo 这可能需要 5-10 分钟，请耐心等待...
echo.

call env\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install packages
pip install customtkinter==5.2.2
pip install opencv-python==4.8.1.78
pip install pillow==10.1.0
pip install numpy==1.26.2
pip install scipy==1.11.4
pip install torch==2.2.0 torchvision==0.17.0 --index-url https://download.pytorch.org/whl/cpu
pip install pydirectinput==1.0.4
pip install keyboard==0.13.5
pip install pynput==1.7.6
pip install pyautogui==0.9.54
pip install screeninfo==0.8.1

if errorlevel 1 (
    echo.
    echo [ERROR] 安装依赖包失败！
    pause
    exit /b 1
)

deactivate

:complete
echo.
echo ========================================
echo 安装完成！
echo ========================================
echo.
echo 虚拟环境位置: %~dp0env
echo.
echo.
pause
