@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Heytea Painter
cd /d "%~dp0"

echo ====================================
echo Heytea Painter 启动脚本
echo ====================================
echo.

if not exist "env\" (
    echo [ERROR] env 文件夹不存在！
    echo 请先运行 setup_env.bat 创建环境
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0env\Scripts\python.exe" (
    echo [ERROR] Python 未找到！
    echo 环境可能损坏，请重新运行 setup_portable.bat
    echo.
    pause
    exit /b 1
)

echo [1/3] 检查 Python 环境...
"%~dp0env\Scripts\python.exe" --version
if errorlevel 1 (
    echo [ERROR] Python 执行失败！
    pause
    exit /b 1
)
echo.

echo [2/3] 检查模型文件 (models\netG.pth)...
if not exist "%~dp0models\netG.pth" (
    echo.
    echo [ERROR] 关键模型文件 'models\netG.pth' 未找到！
    echo.
    echo 此文件是程序运行所必需的。
    echo 请从项目主页或 Readme 中找到下载链接，
    echo 下载 netG.pth 文件并将其放置在 'models' 文件夹中。
    echo.
    pause
    exit /b 1
)
echo 模型文件检查通过。
echo.

echo [3/3] 启动 Heytea Painter...
echo 提示: 绘画时请查看本窗口的输出信息
echo.

"%~dp0env\Scripts\python.exe" heytea_modern.py

if errorlevel 1 (
    echo.
    echo [ERROR] 程序异常退出！错误代码: %errorlevel%
    echo.
    pause
)

exit
