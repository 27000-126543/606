@echo off
chcp 65001 >nul
echo ============================================================
echo    运维异常检测与自动化处理系统 - 快速启动脚本 (Windows)
echo ============================================================
echo.

cd /d "%~dp0"

if not exist ".venv" (
    echo [1/5] 创建Python虚拟环境...
    python -m venv .venv || goto :error
)

echo [2/5] 激活虚拟环境...
call .venv\Scripts\activate.bat || goto :error

echo [3/5] 安装项目依赖...
pip install -r requirements.txt || goto :error

if not exist ".env" (
    echo [4/5] 创建环境配置文件...
    copy .env.example .env
    echo   - 请根据实际情况修改 .env 文件中的配置
)

echo [5/5] 初始化数据库表和示例数据...
set PYTHONPATH=%~dp0
python scripts\init_data.py || goto :error

echo.
echo ============================================================
echo   初始化完成！
echo ============================================================
echo.
echo   启动服务请运行:  start_server.bat
echo   或手动执行:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
echo.
echo   访问地址:
echo     - API 文档: http://localhost:8000/docs
echo     - 健康检查: http://localhost:8000/health
echo.
echo   默认账号:
echo     - 管理员: admin / Admin@123456
echo     - 运维:   operator1 / Oper@123
echo.
pause
exit /b 0

:error
echo.
echo ============================================================
echo   错误: 初始化过程中出现问题！
echo   请检查上面的错误信息并重试。
echo ============================================================
pause
exit /b 1
