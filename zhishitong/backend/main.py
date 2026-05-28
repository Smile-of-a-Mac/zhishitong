"""智审通 FastAPI 主入口"""
import logging, time
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from database import engine
from models import Base

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="智审通 API", version="0.3.0", docs_url="/api/docs")

from config import ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 请求日志中间件 ----
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000)
    # 只记录 API 请求，跳过静态文件
    if request.url.path.startswith("/api/"):
        from services.logging_service import LogCategory, log as syslog
        status = response.status_code
        level = "error" if status >= 500 else ("warning" if status >= 400 else "info")
        syslog(
            LogCategory.SYSTEM,
            level,
            f"{request.method} {request.url.path} → {status}",
            duration_ms=duration_ms,
            method=request.method,
            path=request.url.path,
            status=status,
        )
    return response


# ---- 路由 ----
from routers.auth_router import router as auth_router
from routers.ocr_router import router as ocr_router
from routers.approval_router import router as approval_router
from routers.admin_router import router as admin_router
from routers.monitor_router import router as monitor_router

from routers.dept_router import router as dept_router
from routers.finance_router import router as finance_router
from routers.school_router import router as school_router
from routers.notification_router import router as notification_router
from routers.dashboard_router import router as dashboard_router
from routers.resource_router import router as resource_router
from routers.announcement_router import router as announcement_router
from routers.rag_router import router as rag_router

app.include_router(auth_router)
app.include_router(ocr_router)
app.include_router(approval_router)
app.include_router(admin_router)
app.include_router(monitor_router)
app.include_router(dept_router)
app.include_router(finance_router)
app.include_router(school_router)
app.include_router(notification_router)
app.include_router(dashboard_router)
app.include_router(resource_router)
app.include_router(announcement_router)
app.include_router(rag_router)
logger.info("路由已挂载: auth, ocr, approvals, admin, monitor, dept, finance, school, notifications, dashboard, resources, announcements, ai")

# ---- 模板接口 ----
@app.get("/api/templates")
def list_templates():
    from services.template_service import _load
    data = _load()
    return [
        {"key": k, "label": v["label"], "icon": v.get("icon", ""), "fields": v.get("fields", [])}
        for k, v in data.get("templates", {}).items()
    ]

# ---- 文件服务 ----
from fastapi.responses import FileResponse
from config import UPLOAD_DIR
from models import ApprovalRecord, User
from database import SessionLocal
from auth import get_current_user

@app.get("/api/files/{record_id}")
def serve_file(record_id: int, user: User = Depends(get_current_user)):
    """根据 record_id 返回对应的上传文件（仅允许文件所有者或管理员访问）"""
    db = SessionLocal()
    try:
        record = db.query(ApprovalRecord).filter(ApprovalRecord.id == record_id).first()
        if not record or not record.storage_path:
            raise HTTPException(404, "文件不存在")
        # 权限检查：仅文件所有者或管理员可访问
        if record.user_id != user.id and not (user.is_admin or user.is_school_admin or user.is_dept_admin or user.is_finance_admin):
            raise HTTPException(403, "无权访问该文件")
        # 学校隔离：非超级管理员仅能查看本校文件
        if not user.is_admin:
            record_owner = db.query(User).filter(User.id == record.user_id).first()
            if record_owner and record_owner.school != user.school:
                raise HTTPException(403, "无权访问其他学校的文件")
        full_path = UPLOAD_DIR.parent / record.storage_path
        if not full_path.exists():
            raise HTTPException(404, "文件已物理删除")
        mime = record.mime_type or "image/jpeg"
        return FileResponse(str(full_path), media_type=mime)
    finally:
        db.close()


# ---- 健康检查 ----
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.3.0"}

# ---- 前端 SPA 路由 ----
import os
from starlette.staticfiles import StaticFiles as StarletteSF
from fastapi.responses import FileResponse

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    from starlette.exceptions import HTTPException as StarletteHTTPException

    class _SPA(StarletteSF):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                # 仅在 404（路径不存在）时回退到 SPA index，其他错误继续上抛
                if exc.status_code == 404:
                    index = os.path.join(self.directory, "index.html")
                    if os.path.exists(index):
                        return FileResponse(index)
                raise

    app.mount("/", _SPA(directory=frontend_dist, html=True, check_dir=False), name="frontend")
    logger.info("前端 SPA 静态文件已挂载")
