@echo off
REM 设置 GitHub Trending Push 每两天执行一次的 Windows 计划任务

set SCRIPT_DIR=%~dp0
set PYTHON=python
set TASK_NAME=GitHubTrendingPush

REM 查找 python 路径
for /f "tokens=*" %%i in ('where python') do set PYTHON=%%i
if "%PYTHON%"=="" (
    echo 未找到 Python，请先安装 Python 并添加到 PATH
    exit /b 1
)

echo Python 路径: %PYTHON%
echo 脚本路径: %SCRIPT_DIR%trending_push.py

REM 删除旧任务（如果存在）
schtasks /delete /tn "%TASK_NAME%" /f 2>nul

REM 创建计划任务：每两天执行一次，从今天开始
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON%\" \"%SCRIPT_DIR%trending_push.py\"" ^
    /sc DAILY ^
    /mo 2 ^
    /st 09:00 ^
    /ru "%USERNAME%" ^
    /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo  计划任务已创建成功！
    echo  任务名称: %TASK_NAME%
    echo  执行频率: 每2天，上午9点
    echo  如要修改频率，运行: taskschd.msc
    echo ============================================
) else (
    echo 创建计划任务失败，请以管理员身份运行此脚本
)
pause
