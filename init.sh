#!/bin/bash
# ============================================================
# 运维异常检测与自动化处理系统 - 快速启动脚本 (Linux/Mac)
# ============================================================

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "============================================================"
echo "   运维异常检测与自动化处理系统 - 初始化脚本"
echo "============================================================"
echo

# 1. 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "[1/5] 创建Python虚拟环境..."
    python3 -m venv .venv
fi

# 2. 激活虚拟环境
echo "[2/5] 激活虚拟环境..."
source .venv/bin/activate

# 3. 安装依赖
echo "[3/5] 安装项目依赖..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. 环境配置
if [ ! -f ".env" ]; then
    echo "[4/5] 创建环境配置文件..."
    cp .env.example .env
    echo "   - 请根据实际情况修改 .env 文件中的配置"
else
    echo "[4/5] 环境配置文件已存在，跳过..."
fi

# 5. 初始化数据
echo "[5/5] 初始化数据库表和示例数据..."
export PYTHONPATH="$PROJECT_DIR"
python3 scripts/init_data.py

echo
echo "============================================================"
echo "  初始化完成！"
echo "============================================================"
echo
echo "  启动服务:"
echo "    bash start_server.sh"
echo "    或执行: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo
echo "  访问地址:"
echo "    - API 文档: http://localhost:8000/docs"
echo "    - 健康检查: http://localhost:8000/health"
echo
echo "  默认账号:"
echo "    - 管理员: admin / Admin@123456"
echo "    - 运维:   operator1 / Oper@123"
echo
