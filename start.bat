@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Heytea Painter
cd /d "%~dp0"

echo ====================================
echo Heytea Painter 启动脚本
echo ====================================
echo.

set "ENV_NAME=heytea-painter"
set "PYTHON_EXE="

REM Prefer CONDA_ROOT, then common Miniconda / Anaconda locations
if not defined CONDA_ROOT (
    if exist "C:\Users\a1234\Projects\miniconda3\Scripts\conda.exe" set "CONDA_ROOT=C:\Users\a1234\Projects\miniconda3"
    if exist "%USERPROFILE%\miniconda3\Scripts\conda.exe" set "CONDA_ROOT=%USERPROFILE%\miniconda3"
    if exist "%USERPROFILE%\Miniconda3\Scripts\conda.exe" set "CONDA_ROOT=%USERPROFILE%\Miniconda3"
    if exist "%USERPROFILE%\anaconda3\Scripts\conda.exe" set "CONDA_ROOT=%USERPROFILE%\anaconda3"
    if exist "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe" set "CONDA_ROOT=%LOCALAPPDATA%\miniconda3"
)

if defined CONDA_ROOT (
    if exist "%CONDA_ROOT%\envs\%ENV_NAME%\python.exe" (
        set "PYTHON_EXE=%CONDA_ROOT%\envs\%ENV_NAME%\python.exe"
        echo [INFO] 使用 conda 环境: %ENV_NAME%
        echo        %PYTHON_EXE%
    )
)

REM Fallback: portable local env\
if not defined PYTHON_EXE (
    if exist "%~dp0env\python.exe" (
        set "PYTHON_EXE=%~dp0env\python.exe"
        echo [INFO] 使用本地便携环境: env\
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] 未找到可用的 Python 环境。
    echo.
    echo 未检测到 conda 环境 "%ENV_NAME%"，本地 env\ 也不存在。
    echo.
    echo 请先任选其一:
    echo   1. 安装 Miniconda，创建环境 heytea-painter，或设置 CONDA_ROOT
    echo   2. 运行 setup_env.bat 创建便携 env\
    echo.
    pause
    exit /b 1
)
echo.

echo [1/3] 检查 Python 环境...
"%PYTHON_EXE%" --version
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

"%PYTHON_EXE%" heytea_modern.py

if errorlevel 1 (
    echo.
    echo [ERROR] 程序异常退出！错误代码: %errorlevel%
    echo.
    pause
)

exit
