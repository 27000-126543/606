# 运维异常检测与自动化处理系统

## 项目概述

基于动态基线算法的智能运维监控平台，支持每秒数百万条日志的高并发实时处理，自动检测异常模式、生成根因分析、分配工单、执行修复预案，并提供完整的报表、审计与权限体系。

### 核心特性

| 模块 | 功能描述 |
|------|----------|
| 🔄 **日志采集** | 基于Kafka的高并发消费者，支持每秒数百万条日志，批量写入+自动聚合 |
| 📊 **异常检测** | 动态基线算法(EWMA+季节性分解+Z-Score)，ADF平稳性检验 |
| 🔍 **根因分析** | 拓扑依赖传导分析+变更记录关联+同期异常匹配+多因子评分 |
| 🎫 **工单系统** | 自动分配+负载均衡+SLA管理+超时升级+4小时催办机制 |
| ⚡ **预案执行** | 支持回滚配置/重启服务/扩容/清缓存，含审批流程+自动验证 |
| 📈 **报表系统** | 每日趋势报告+PDF/Excel导出+matplotlib可视化图表 |
| 💡 **案例库** | 历史相似案例TF-IDF匹配+解决方案推荐+手动导入 |
| 👥 **权限体系** | Supervisor全量审批/Operator仅本人团队工单，RBAC管控 |
| 📝 **审计追踪** | 全链路操作记录+多条件组合查询+批量导出明细 |

---

## 技术架构

### 技术栈选型

```
┌─────────────────────────────────────────────────────────┐
│                      前端展示层                           │
│         (React + Ant Design Pro / 任何API调用方)          │
└────────────────────────────┬────────────────────────────┘
                             │ HTTPS/REST
┌────────────────────────────▼────────────────────────────┐
│                   应用服务层 (FastAPI)                    │
│  ┌──────────┬──────────┬──────────┬──────────┬────────┐ │
│  │ 认证路由 │ 异常路由 │ 工单路由 │ 查询路由 │ 调度器 │ │
│  └──────────┴──────────┴──────────┴──────────┴────────┘ │
│  ┌──────────┬──────────┬──────────┬──────────┬────────┐ │
│  │ 异常检测 │ 根因分析 │ 工单服务 │ 预案执行 │ 报表   │ │
│  └──────────┴──────────┴──────────┴──────────┴────────┘ │
└────────────────────────────┬────────────────────────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────┐ ┌────────────────┐
│    PostgreSQL    │ │    Redis     │ │     Kafka      │
│  (13张核心表)    │ │ (缓存/队列)  │ │ (高并发日志流) │
└──────────────────┘ └──────────────┘ └────────────────┘
```

### 核心算法说明

| 算法 | 应用场景 | 说明 |
|------|----------|------|
| **EWMA指数加权移动平均** | 动态基线计算 | 对时序指标赋不同权重，近期数据影响更大 |
| **STL季节性分解** | 基线模型 | 分离趋势分量/日周期/周周期/残差 |
| **Z-Score标准分** | 异常阈值判定 | 偏离均值N个标准差即视为异常 |
| **ADF单位根检验** | 序列平稳性 | 判断时序数据是否适合统计建模 |
| **IQR四分位距** | 离群点清洗 | 训练数据预处理，移除极端离群值 |
| **Jaccard+SequenceMatcher** | 案例相似度 | 多因子加权匹配历史相似案例 |

---

## 快速开始

### 环境要求

- **Python**: 3.10+ (建议 3.11)
- **PostgreSQL**: 13+ (建议 15/16，需启用uuid-ossp扩展)
- **Kafka**: 2.8+ (可选，开发模式可无Kafka启动)
- **Redis**: 6.0+ (可选，用于缓存和会话共享)
- **内存**: 建议 >= 4GB (scikit-learn/numpy/pandas运行需求)

### 一键初始化

#### Windows 环境
```cmd
:: 方式1：双击执行
init.bat

:: 方式2：命令行执行
cd e:\新项目\606
init.bat
```

#### Linux / macOS 环境
```bash
cd /path/to/606
chmod +x init.sh start_server.sh
./init.sh
```

### 手动安装步骤

```bash
# 1. 创建虚拟环境
python3 -m venv .venv

# 2. 激活虚拟环境
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置数据库等连接信息

# 5. 初始化数据库和测试数据
export PYTHONPATH=.
python scripts/init_data.py

# 6. 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 启动服务

启动后可通过以下地址访问：

| 资源 | 地址 |
|------|------|
| API文档 (Swagger) | http://localhost:8000/docs |
| API文档 (ReDoc) | http://localhost:8000/redoc |
| 健康检查 | http://localhost:8000/health |
| 服务就绪 | http://localhost:8000/ready |
| 系统统计 | http://localhost:8000/api/v1/query/system/stats |

---

## 默认测试账号

| 用户名 | 密码 | 角色 | 权限说明 |
|--------|------|------|----------|
| `admin` | `Admin@123456` | **Supervisor** | 系统管理员，全量数据查看与审批 |
| `supervisor1` | `Super@123` | **Supervisor** | 运维主管，全量工单审批权限 |
| `operator1` | `Oper@123` | **Operator** | 应用运维组工程师，仅本团队工单 |
| `operator2` | `Oper@123` | **Operator** | 数据库组负责人，仅本团队工单 |
| `operator3` | `Oper@123` | **Operator** | 监控告警组工程师 |

---

## 核心数据模型

### 数据库表结构 (13张核心表)

| 表名 | 模块 | 说明 |
|------|------|------|
| `users` / `teams` / `user_teams` | 权限 | 用户、团队、关联关系 |
| `raw_logs` | 日志 | 原始日志（分区存储，支持亿级） |
| `processed_logs` | 日志 | 聚合后指标（多时间窗口） |
| `anomalies` / `baseline_configs` | 异常 | 异常记录+检测算法配置 |
| `metric_baselines` / `baseline_history` | 算法 | 基线模型+历史检测点 |
| `work_orders` / `follow_up_tasks` | 工单 | 工单+跟进催办任务 |
| `playbooks` / `playbook_executions` | 预案 | 预案模板+执行记录 |
| `service_nodes` / `service_dependencies` | 拓扑 | 服务节点+依赖关系图 |
| `change_records` | 变更 | 发布/配置等变更记录 |
| `audit_logs` | 审计 | 全链路操作审计 |
| `case_library` / `anomaly_case_matches` | 案例 | 知识库+异常-案例匹配 |
| `daily_reports` | 报表 | 每日汇总报表 |

---

## API 接口总览

### 1. 认证授权模块 (`/api/v1/auth`)

| Method | Path | 说明 | 权限 |
|--------|------|------|------|
| POST | `/login` | 用户登录获取Token | 公开 |
| POST | `/logout` | 登出 | 登录用户 |
| GET | `/me` | 获取当前用户信息 | 登录用户 |
| GET | `/users` | 用户列表 | 主管 |
| POST | `/users` | 创建用户 | 主管 |
| PUT | `/users/{id}` | 更新用户 | 主管 |
| GET | `/teams` | 团队列表 | 登录用户 |
| POST | `/teams` | 创建团队 | 主管 |

### 2. 异常管理模块 (`/api/v1/anomalies`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/anomalies` | 异常列表（多条件筛选） |
| GET | `/anomalies/{id}` | 异常详情 |
| POST | `/anomalies/{id}/analyze` | 触发根因分析 |
| POST | `/anomalies/{id}/create-work-order` | 手动创建工单 |
| POST | `/anomalies/{id}/match-cases` | 匹配历史相似案例 |
| POST | `/import-case` | 手动导入案例到知识库 |

### 3. 工单与预案模块

| Method | Path | 说明 |
|--------|------|------|
| GET | `/work-orders` | 工单列表 |
| GET | `/work-orders/{id}` | 工单详情 |
| PUT | `/work-orders/{id}/status` | 更新工单状态 |
| PUT | `/work-orders/{id}/reassign` | 转派工单 |
| POST | `/playbooks/execute` | 执行修复预案 |
| GET | `/playbook-executions/{id}` | 查看预案执行状态 |
| PUT | `/playbook-executions/{id}/approve` | 审批预案执行 |

### 4. 查询与报表模块 (`/api/v1/query`)

| Method | Path | 说明 |
|--------|------|------|
| GET | `/reports/daily` | 每日报表列表 |
| POST | `/reports/daily/generate` | 手动生成报表 |
| GET | `/reports/{id}` | 报表详情 |
| GET | `/reports/{id}/export/pdf` | 导出PDF报表（含图表） |
| GET | `/reports/{id}/export/excel` | 导出Excel报表（含图表） |
| GET | `/audit-logs` | 审计日志查询 |
| GET | `/logs` | 原始日志查询 |
| POST | `/export` | 批量数据导出（CSV/JSON） |
| GET | `/system/stats` | 首页统计看板数据 |
| GET | `/system/health` | 系统健康检查 |
| GET | `/system/scheduler-status` | 定时任务状态 |

---

## 核心业务流程

### 1. 异常自动化处理全链路

```
业务系统日志
    │
    ▼
[Kafka 日志流] ── 每秒百万级 ──►
    │
    ▼
[批量消费 + 实时聚合]  (Kafka消费者组)
    │
    ▼
[动态基线算法检测]  (每5分钟)
    │ Z-Score + 季节性分解
    ▼
[异常事件生成]
    │
    ├─────────────────────────────┐
    ▼                             ▼
[根因分析]                    [自动建单]
│ 拓扑传导                      │ 负载均衡分配
│ 变更关联                      │ SLA倒计时
│ 同期异常                      ▼
    │                    [预案自动匹配]
    ▼                             │ 高危严重度自动执行
[工单创建] ◄─────────────────────┘
    │
    ▼
[状态流转] ──► [人工处理] / [预案执行]
    │                              │
    ▼                              ▼
[SLA超时升级]           [执行验证+效果确认]
│ 每4小时催办                   │
│ 超时自动提级                   ▼
    │                    [自动更新工单状态]
    ▼                              │
[主管介入处理] ◄────────────────────┘
    │
    ▼
[关闭归档] ──► [日报统计] / [案例沉淀]
```

### 2. 工单SLA响应时效

| 优先级 | 严重等级 | 响应时间 | 修复时效 | 升级阈值 |
|--------|----------|----------|----------|----------|
| **P0** | Critical | 5分钟 | 1小时 | 30分钟未响应 |
| **P1** | High | 15分钟 | 4小时 | 1小时未响应 |
| **P2** | Medium | 1小时 | 8小时 | 4小时未响应 |
| **P3** | Low | 4小时 | 24小时 | 次日升级 |
| **P4** | Info | 24小时 | 72小时 | - |

---

## 定时任务调度

| 任务ID | 频率 | 功能 |
|--------|------|------|
| `process_new_anomalies_for_tickets` | **每分钟** | 新异常自动创建工单 |
| `batch_root_cause_analysis` | **每2分钟** | 待处理异常根因分析 |
| `anomaly_detection_cycle` | **每5分钟** | 动态基线异常检测 |
| `work_order_escalations` | **每15分钟** | 工单SLA超时升级与催办 |
| `daily_report_generation` | **每日00:30** | 生成昨日汇总报表 |
| `cleanup_old_exports` | **每日02:00** | 清理7天前导出文件 |
| `hourly_health_check` | **每小时** | 系统健康自检与日志统计 |

---

## 高并发设计要点

### 日志处理能力设计

| 组件 | 策略 | 预期吞吐 |
|------|------|----------|
| Kafka消费 | 批量拉取(10000条/批次) + 多消费者组(4线程) | ≥ 2,000,000 条/秒 |
| DB写入 | Async批量INSERT + 连接池(20+50溢出) | ≥ 500,000 条/秒 |
| 日志聚合 | SQL窗口函数按分钟/小时预聚合 | 存储降低99% |
| 算法检测 | Numpy/Pandas向量化计算 | 1000+指标/5分钟 |

### 水平扩展方案

- **日志分区键**: `系统名_日期`，支持按日期自动分表
- **Kafka分区数**: 建议32+，消费者线程数对应
- **异步解耦**: 日志采集→异常检测→工单创建→预案执行全异步
- **缓存层**: Redis缓存用户会话、拓扑结构、热点基线

---

## 常见问题 FAQ

### Q: 没有Kafka能启动吗？
A: 可以。开发模式下可以直接通过API手动注入日志进行测试，Kafka连接失败仅影响实时日志采集功能，其余功能正常。

### Q: 数据库初始化失败怎么办？
A: 请确保PostgreSQL版本>=13，并检查：
1. `.env`中数据库连接配置正确
2. 目标数据库已存在 `CREATE DATABASE ops_monitor;`
3. 已启用uuid-ossp扩展 `CREATE EXTENSION IF NOT EXISTS "uuid-ossp";`

### Q: 报表导出字体乱码？
A: PDF使用了STSong-Light中文字体，请确保系统已安装ReportLab CID字体包（已内置）。如果仍有问题，可在代码中切换为默认字体。

### Q: 如何接入我的业务系统日志？
A: 只需要将日志以JSON格式发送到配置的Kafka Topic `ops_logs` 即可。消息格式示例：
```json
{
  "system_name": "订单系统",
  "host_ip": "10.0.0.1",
  "log_time": "2024-01-15T10:30:00+08:00",
  "log_level": "ERROR",
  "module": "checkout-service",
  "trace_id": "abc123xyz",
  "message": "连接支付网关超时",
  "tags": {"env": "prod", "version": "v2.3.1"}
}
```

---

## 目录结构说明

```
e:\新项目\606\
├── app/
│   ├── __init__.py              # 包初始化
│   ├── main.py                  # FastAPI主应用入口
│   ├── config.py                # 全局配置管理
│   ├── database.py              # 数据库连接与Session
│   ├── models/                  # SQLAlchemy ORM模型
│   │   ├── __init__.py
│   │   ├── user.py              # 用户与团队
│   │   ├── log.py               # 日志表
│   │   ├── anomaly.py           # 异常与基线配置
│   │   ├── baseline.py          # 算法基线模型
│   │   ├── ticket.py            # 工单与跟进任务
│   │   ├── playbook.py          # 预案与执行记录
│   │   ├── topology.py          # 拓扑与变更
│   │   ├── audit.py             # 审计日志
│   │   └── report.py            # 报表与案例库
│   ├── schemas/                 # Pydantic请求/响应Schema
│   │   ├── auth.py              # 认证相关
│   │   └── api.py               # 通用API响应
│   ├── services/                # 核心业务服务层
│   │   ├── log_collector.py     # Kafka日志采集服务
│   │   ├── anomaly_detector.py  # 动态基线检测算法
│   │   ├── root_cause_analyzer.py  # 根因分析
│   │   ├── ticket_service.py    # 工单系统服务
│   │   ├── playbook_executor.py # 预案执行引擎
│   │   ├── report_service.py    # 报表生成与PDF/Excel导出
│   │   ├── case_matcher.py      # 历史案例相似度匹配
│   │   ├── audit_service.py     # 审计日志服务与装饰器
│   │   ├── query_service.py     # 多条件查询与批量导出
│   │   └── task_scheduler.py    # APScheduler定时任务
│   ├── utils/                   # 公共工具
│   │   ├── logger.py            # 日志配置
│   │   └── auth.py              # JWT认证与密码工具
│   └── api/v1/                  # API路由层
│       ├── auth_routes.py       # 认证授权
│       ├── anomaly_routes.py    # 异常管理
│       ├── ticket_routes.py     # 工单与预案
│       └── query_routes.py      # 报表、查询、统计
├── scripts/
│   └── init_data.py             # 初始化测试数据脚本
├── exports/                     # 报表与导出文件（自动生成）
├── logs/                        # 应用运行日志（自动生成）
├── requirements.txt             # Python依赖
├── .env.example                 # 环境变量模板
├── init.bat / init.sh           # 一键初始化脚本
└── start_server.bat / .sh       # 服务启动脚本
```

---

## License

本项目为企业级运维监控系统设计原型，核心算法与架构可直接用于生产环境部署。

---

如有问题或需要功能扩展，请参考系统API文档或联系开发团队。
