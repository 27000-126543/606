from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from contextlib import asynccontextmanager
import asyncio
import time
import sys
import os
from typing import Dict, Any, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_available_modules: Dict[str, bool] = {}
_service_instances: Dict[str, Any] = {}


def _safe_import(module_path: str, instance_name: str = None):
    try:
        if instance_name:
            mod = __import__(module_path, fromlist=[instance_name])
            instance = getattr(mod, instance_name)
            _available_modules[module_path] = True
            _service_instances[instance_name] = instance
            return instance
        else:
            mod = __import__(module_path, fromlist=['*'])
            _available_modules[module_path] = True
            return mod
    except Exception as e:
        _available_modules[module_path] = False
        print(f"[WARN] Failed to import {module_path}: {type(e).__name__}: {e}")
        return None


try:
    from .config import settings
    _available_modules['config'] = True
except Exception as e:
    print(f"[WARN] Using default settings: {e}")
    _available_modules['config'] = False

    class MockSettings:
        APP_NAME = "运维异常检测与自动化处理系统"
        APP_ENV = "development"
        APP_DEBUG = True
        APP_HOST = "0.0.0.0"
        APP_PORT = 8000
        MAX_WORKERS = 1
    settings = MockSettings()

try:
    from .utils.logger import logger
    _available_modules['logger'] = True
except Exception as e:
    print(f"[WARN] Using basic logger: {e}")
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger("ops_monitor")
    _available_modules['logger'] = False

try:
    from .database import init_db, async_session_maker, get_db
    from sqlalchemy import text
    _available_modules['database'] = True
except Exception as e:
    logger.warning(f"Database module unavailable: {e}")
    _available_modules['database'] = False
    init_db = None
    async_session_maker = None
    get_db = None
    text = None

_safe_import('app.services.task_scheduler', 'task_scheduler')
_safe_import('app.services.log_collector', 'log_collector')
_safe_import('app.services.anomaly_detector', 'baseline_detector')
_safe_import('app.services.ticket_service', 'ticket_service')
_safe_import('app.services.report_service', 'report_service')
_safe_import('app.services.root_cause_analyzer', 'root_cause_analyzer')
_safe_import('app.services.playbook_executor', 'playbook_executor')
_safe_import('app.services.case_matcher', 'case_matcher')
_safe_import('app.services.audit_service', 'audit_service')
_safe_import('app.services.query_service', 'query_service')


def get_service(name: str):
    svc = _service_instances.get(name)
    if svc is None:
        raise RuntimeError(
            f"服务 {name} 不可用，请检查依赖是否安装。"
            f"可用服务: {[k for k, v in _available_modules.items() if v]}"
        )
    return svc


def check_database():
    if not _available_modules.get('database') or async_session_maker is None:
        raise RuntimeError("数据库服务不可用，请检查PostgreSQL连接和SQLAlchemy依赖")


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_start = time.time()
    logger.info("=" * 60)
    logger.info(f"Starting {settings.APP_NAME}")
    logger.info(f"Environment: {settings.APP_ENV} | Debug: {settings.APP_DEBUG}")
    logger.info("=" * 60)

    available = [k for k, v in _available_modules.items() if v]
    unavailable = [k for k, v in _available_modules.items() if not v]
    logger.info(f"Available modules: {available}")
    if unavailable:
        logger.warning(f"Unavailable modules (features disabled): {unavailable}")

    db_ok = False
    if _available_modules.get('database') and init_db and async_session_maker:
        try:
            logger.info("Initializing database...")
            await init_db()
            logger.info("Database tables initialized")

            async with async_session_maker() as db:
                result = await db.execute(text("SELECT 1"))
                db_ok = result.scalar() == 1
                logger.info(f"Database connection test: {'OK' if db_ok else 'FAILED'}")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            logger.warning("Continuing without database - some features will be disabled")
    else:
        logger.warning("Database module not available - DB features disabled")

    bg_tasks = []
    if _service_instances.get('task_scheduler'):
        try:
            logger.info("Starting task scheduler...")
            bg_tasks.append(asyncio.create_task(_service_instances['task_scheduler'].start()))
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")

    if _service_instances.get('log_collector'):
        try:
            logger.info("Starting log collector...")
            bg_tasks.append(asyncio.create_task(_service_instances['log_collector'].start()))
        except Exception as e:
            logger.error(f"Failed to start log collector: {e}")

    if _service_instances.get('baseline_detector'):
        try:
            logger.info("Starting anomaly detector...")
            bg_tasks.append(asyncio.create_task(_service_instances['baseline_detector'].start()))
        except Exception as e:
            logger.error(f"Failed to start anomaly detector: {e}")

    startup_duration = (time.time() - startup_start) * 1000
    logger.info(f"Application startup completed in {startup_duration:.1f}ms")
    logger.info(f"API server listening on http://{settings.APP_HOST}:{settings.APP_PORT}")
    logger.info(f"Docs: http://{settings.APP_HOST}:{settings.APP_PORT}/docs")
    logger.info(f"Health: http://{settings.APP_HOST}:{settings.APP_PORT}/health")

    app.state.db_ok = db_ok
    app.state.available_modules = available
    app.state.unavailable_modules = unavailable

    yield

    logger.info("=" * 60)
    logger.info("Shutting down application...")

    for name in ['task_scheduler', 'log_collector']:
        svc = _service_instances.get(name)
        if svc and hasattr(svc, 'stop'):
            try:
                await svc.stop()
                logger.info(f"{name} stopped")
            except Exception as e:
                logger.error(f"Error stopping {name}: {e}")

    svc = _service_instances.get('baseline_detector')
    if svc and hasattr(svc, 'stop'):
        try:
            svc.stop()
            logger.info("baseline_detector stopped")
        except Exception as e:
            logger.error(f"Error stopping baseline_detector: {e}")

    for task in bg_tasks:
        if not task.done():
            task.cancel()

    logger.info("Application shutdown complete")
    logger.info("=" * 60)


app = FastAPI(
    title=settings.APP_NAME,
    description="运维异常检测与自动化处理系统 - 基于动态基线算法的高并发日志实时分析平台",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=86400,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
    except RuntimeError as e:
        logger.warning(f"Service unavailable for {request.method} {request.url.path}: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "code": 503,
                "message": "服务暂不可用",
                "detail": str(e),
                "available_services": [k for k, v in _available_modules.items() if v],
            },
        )
    except Exception as e:
        logger.error(f"Unhandled exception for {request.method} {request.url.path}: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "服务器内部错误",
                "detail": str(e) if settings.APP_DEBUG else None,
            },
        )

    process_time = (time.time() - start_time) * 1000

    if request.url.path not in ["/health", "/docs", "/openapi.json", "/redoc", "/"]:
        client_ip = request.client.host if request.client else "unknown"
        log_level = logger.warning if process_time > 1000 else logger.info
        log_level(
            f"{client_ip} | {request.method} {request.url.path} | "
            f"Status: {response.status_code} | Time: {process_time:.1f}ms"
        )

    response.headers["X-Process-Time"] = f"{process_time:.1f}"
    response.headers["X-Server"] = "ops-monitor"
    response.headers["X-Modules-Available"] = ",".join([k for k, v in _available_modules.items() if v])
    return response


api_prefix = "/api/v1"

try:
    from .api.v1.auth_routes import router as auth_router
    app.include_router(auth_router, prefix=api_prefix, tags=["认证授权"])
    logger.info("Auth router registered")
except Exception as e:
    logger.warning(f"Auth router not available: {e}")

try:
    from .api.v1.anomaly_routes import router as anomaly_router
    app.include_router(anomaly_router, prefix=api_prefix + "/anomalies", tags=["异常管理"])
    logger.info("Anomaly router registered")
except Exception as e:
    logger.warning(f"Anomaly router not available: {e}")

try:
    from .api.v1.ticket_routes import router as ticket_router
    app.include_router(ticket_router, prefix=api_prefix, tags=["工单与预案"])
    logger.info("Ticket router registered")
except Exception as e:
    logger.warning(f"Ticket router not available: {e}")

try:
    from .api.v1.query_routes import router as query_router
    app.include_router(query_router, prefix=api_prefix + "/query", tags=["报表、日志与查询"])
    logger.info("Query router registered")
except Exception as e:
    logger.warning(f"Query router not available: {e}")


@app.get("/", tags=["基础"])
async def root():
    return {
        "name": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": f"http://{settings.APP_HOST}:{settings.APP_PORT}/docs",
        "api_base": api_prefix,
        "available_services": [k for k, v in _available_modules.items() if v],
        "disabled_services": [k for k, v in _available_modules.items() if not v],
    }


@app.get("/health", tags=["基础"])
async def health_check(response: Response):
    response.headers["Cache-Control"] = "no-cache"
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": "healthy",
            "timestamp": time.time(),
            "database": "ok" if getattr(app.state, 'db_ok', False) else "unavailable",
            "available_modules": getattr(app.state, 'available_modules', []),
        }
    }


@app.get("/ready", tags=["基础"])
async def readiness_check():
    db_ok = False
    if _available_modules.get('database') and async_session_maker and text:
        try:
            async with async_session_maker() as db:
                result = await db.execute(text("SELECT 1"))
                db_ok = result.scalar() == 1
        except Exception:
            db_ok = False

    return {
        "status": "ready" if db_ok else "not_ready",
        "database": "ok" if db_ok else "error",
        "timestamp": time.time(),
    }


@app.get("/api/status", tags=["基础"])
async def api_status():
    return {
        "code": 200,
        "message": "success",
        "data": {
            "available_modules": {k: v for k, v in _available_modules.items()},
            "services": list(_service_instances.keys()),
            "database_available": _available_modules.get('database', False),
        }
    }


@app.exception_handler(422)
async def validation_exception_handler(request, exc):
    errors = []
    if hasattr(exc, "errors"):
        for err in exc.errors():
            field = ".".join(str(loc) for loc in err.get("loc", []))
            errors.append(f"{field}: {err.get('msg', '')}")
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "请求参数验证失败",
            "errors": errors,
        },
    )


@app.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={"code": 404, "message": "资源不存在"},
    )


@app.exception_handler(403)
async def forbidden_handler(request, exc):
    return JSONResponse(
        status_code=403,
        content={"code": 403, "message": getattr(exc, 'detail', '权限不足')},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        workers=1,
        reload=settings.APP_DEBUG,
        log_level="info",
        access_log=False,
    )
