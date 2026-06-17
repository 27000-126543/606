#!/bin/bash
# ============================================================
# 运维异常检测与自动化处理系统 - 启动脚本 (Linux/Mac)
# ============================================================

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "============================================================"
echo "   运维异常检测与自动化处理系统 - 启动服务"
echo "============================================================"
echo

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

export PYTHONPATH="$PROJECT_DIR"
export APP_ENV=development
export APP_DEBUG=true

echo "[1/3] 检查数据库连接..."
python3 -c "
import asyncio
try:
    from app.database import async_session_maker
    from sqlalchemy import text
    async def check():
        async with async_session_maker() as db:
            result = await db.execute(text('SELECT 1'))
            print(f'   数据库连接: OK (test={result.scalar()})')
    asyncio.run(check())
except Exception as e:
    print(f'   数据库连接: 警告 - {e}')
    print('   请确保PostgreSQL已启动并正确配置.env文件')
" || echo

echo
echo "[2/3] 启动服务..."
echo
echo "  访问地址:"
echo "    - Swagger 文档: http://localhost:8000/docs"
echo "    - ReDoc 文档:   http://localhost:8000/redoc"
echo "    - 健康检查:     http://localhost:8000/health"
echo "    - 系统状态:     http://localhost:8000/api/v1/query/system/stats"
echo
echo "  停止服务请按: Ctrl+C"
echo
echo "============================================================"
echo

python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --log-level info
