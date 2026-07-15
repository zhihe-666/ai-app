@echo off
REM AI 中控台 — 一键启动脚本 (Windows)
REM 前置：Windows + Python 3.10+ + Node 18+ + npm

setlocal enabledelayedexpansion

chcp 65001 >nul

echo === AI 中控台 启动脚本 ===

cd /d "%~dp0"

REM ---- 1. 环境检查 ----
echo [1/6] 检查环境...

where python >nul 2>nul
if errorlevel 1 (
    echo 错误: 未找到 python，请安装 Python 3.10+ ^(https://python.org^)
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo 错误: 未找到 node，请安装 Node 18+ ^(https://nodejs.org^)
    pause
    exit /b 1
)

python --version
node -v

REM ---- 2. 后端 venv + 依赖 ----
echo [2/6] 准备后端环境...
cd backend

if not exist "venv" (
    echo   创建虚拟环境...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo   安装后端依赖（首次较慢）...
pip install --upgrade pip -q
pip install -r requirements.txt -q 2>nul || pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple -q

cd ..

REM ---- 3. 前端依赖 + build ----
echo [3/6] 准备前端环境...
cd frontend

if not exist "node_modules" (
    echo   安装前端依赖（首次较慢）...
    npm install --silent 2>nul || npm install --registry=https://registry.npmmirror.com
)

if not exist "dist" (
    echo   构建前端...
    npm run build
)

cd ..

REM ---- 4. 飞书 lark-cli ----
echo [4/6] 检查飞书配置...

set LARK_CONFIG_DIR=%USERPROFILE%\.dewuclaw\lark-cli-config

if exist "lark-config" (
    if not exist "%LARK_CONFIG_DIR%" (
        echo   复制飞书配置到 %LARK_CONFIG_DIR% ...
        mkdir "%USERPROFILE%\.dewuclaw" 2>nul
        xcopy /E /I /Y "lark-config" "%LARK_CONFIG_DIR%" >nul
    )
)

where lark-cli >nul 2>nul
if errorlevel 1 (
    echo   安装 lark-cli ...
    npm install -g lark-cli 2>nul
)

REM ---- 5. 默认配置 ----
echo [5/6] 加载默认配置...
if exist "backend\.env" (
    echo   使用 backend\.env 默认配置
    for /f "usebackq tokens=1,* delims==" %%a in ("backend\.env") do (
        set "%%a=%%b"
    )
) else (
    echo   未找到 backend\.env，请在前端配置 LLM/Git Token
)

REM ---- 6. 启动后端 ----
echo [6/6] 启动后端...
cd backend
call venv\Scripts\activate.bat

echo === 启动完成 ===
echo   访问地址: http://localhost:5000
echo   停止服务: Ctrl+C
echo.

python run.py

pause
