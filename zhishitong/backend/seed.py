"""种子数据 — 管理员 & 两所学校演示用户"""
import os
from database import SessionLocal, engine
from models import Base, User, TierEnum, ResourceRoom, ResourceVehicle
from auth import hash_password

Base.metadata.create_all(bind=engine)

# ===== 学校定义 =====
SCHOOLS = {
    "山东科技大学": {"tier": TierEnum.pro, "prefix": "sdu"},          # Pro 版
    "山东科技大学（济南校区）": {"tier": TierEnum.free, "prefix": "sdujn"},  # Free 版
}


def seed():
    db = SessionLocal()
    try:
        # 清理与旧演示用户关联的审批记录
        old_usernames = ["demo_free", "demo_pro", "demo_enterprise",
                         "school_admin", "dept_cs", "dept_finance", "finance_admin"]
        old_users = db.query(User).filter(User.username.in_(old_usernames)).all()
        old_user_ids = [u.id for u in old_users]
        if old_user_ids:
            # 清理关联的审批记录和配额流水
            from models import ApprovalRecord, QuotaLog, AdminAuditLog, SystemLog
            db.query(QuotaLog).filter(QuotaLog.user_id.in_(old_user_ids)).delete(synchronize_session=False)
            db.query(ApprovalRecord).filter(ApprovalRecord.user_id.in_(old_user_ids)).delete(synchronize_session=False)
            # 删除旧用户
            for u in old_users:
                db.delete(u)
            db.flush()

        # ---- 超级管理员（唯一，不属于任何学校） ----
        # 生产部署前请务必通过 ADMIN_INIT_PASSWORD 环境变量覆盖初始密码
        _admin_pwd = os.getenv("ADMIN_INIT_PASSWORD", "admin123")
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(
                username="admin", hashed_password=hash_password(_admin_pwd),
                tier=TierEnum.pro_plus, llm_ocr_quota=99999, is_admin=True,
                real_name="系统管理员", gender="男",
                phone="13800138000", email="admin@example.edu.cn",
                department="信息中心", school="",
            ))

        # ---- 每个学校一套完整角色，全员使用学校的统一层级 ----
        for school_name, school_info in SCHOOLS.items():
            prefix = school_info["prefix"]
            school_tier = school_info["tier"]
            # 学校层级决定所有用户的配额
            ocr_quota = 30 if school_tier == TierEnum.pro else 0

            # 2 名学生（所有学生使用学校层级）
            student_data = [
                ("student_a", "123456", "张明", "男", "13912345678",
                 "2024001", "计算机科学与技术", "计科2401班", 2024, "李芳"),
                ("student_b", "123456", "王丽", "女", "13987654321",
                 "2023012", "软件工程", "软工2302班", 2023, "王强"),
            ]
            for sd in student_data:
                uname = f"{prefix}_{sd[0]}"
                if not db.query(User).filter(User.username == uname).first():
                    db.add(User(
                        username=uname, hashed_password=hash_password(sd[1]),
                        tier=school_tier, llm_ocr_quota=ocr_quota,
                        real_name=sd[2], gender=sd[3], phone=sd[4],
                        student_id=sd[5], major=sd[6], class_name=sd[7],
                        enrollment_year=sd[8], advisor=sd[9],
                        department="计算机学院", school=school_name,
                    ))

            # 学校管理员
            uname = f"{prefix}_school_admin"
            if not db.query(User).filter(User.username == uname).first():
                db.add(User(
                    username=uname, hashed_password=hash_password("admin123"),
                    tier=school_tier, llm_ocr_quota=ocr_quota,
                    is_school_admin=True,
                    real_name=f"赵校长({school_name})", gender="女",
                    employee_id=f"T2010001_{prefix}", title="教授",
                    department="学校办公室", school=school_name,
                ))

            # 部门管理员（计算机学院）
            uname = f"{prefix}_dept_cs"
            if not db.query(User).filter(User.username == uname).first():
                db.add(User(
                    username=uname, hashed_password=hash_password("123456"),
                    tier=school_tier, llm_ocr_quota=ocr_quota,
                    is_dept_admin=True,
                    real_name=f"刘主任({school_name})", gender="男",
                    employee_id=f"T2015012_{prefix}", title="副教授",
                    department="计算机学院", school=school_name,
                ))

            # 部门管理员（财务处）
            uname = f"{prefix}_dept_fin"
            if not db.query(User).filter(User.username == uname).first():
                db.add(User(
                    username=uname, hashed_password=hash_password("123456"),
                    tier=school_tier, llm_ocr_quota=ocr_quota,
                    is_dept_admin=True,
                    real_name=f"孙会计({school_name})", gender="女",
                    employee_id=f"T2018020_{prefix}", title="会计师",
                    department="财务处", school=school_name,
                ))

            # 财务管理员
            uname = f"{prefix}_finance_admin"
            if not db.query(User).filter(User.username == uname).first():
                db.add(User(
                    username=uname, hashed_password=hash_password("admin123"),
                    tier=school_tier, llm_ocr_quota=ocr_quota,
                    is_finance_admin=True,
                    real_name=f"周处长({school_name})", gender="男",
                    employee_id=f"T2013005_{prefix}", title="高级会计师",
                    department="财务处", school=school_name,
                ))

        db.commit()

        # ── 初始化智能预审规则 ──
        from services.rule_engine import get_default_rules
        from models import RuleConfig
        admin_user = db.query(User).filter(User.username == "admin").first()
        if admin_user:
            for rule_data in get_default_rules():
                existing = db.query(RuleConfig).filter(
                    RuleConfig.rule_key == rule_data["rule_key"]
                ).first()
                if not existing:
                    db.add(RuleConfig(
                        rule_key=rule_data["rule_key"],
                        rule_name=rule_data["rule_name"],
                        document_type=rule_data.get("document_type"),
                        rule_type=rule_data["rule_type"],
                        field_key=rule_data.get("field_key"),
                        operator=rule_data.get("operator"),
                        threshold_value=rule_data.get("threshold_value"),
                        error_message=rule_data["error_message"],
                        severity=rule_data.get("severity", "error"),
                        priority=rule_data.get("priority", 0),
                        created_by=admin_user.id,
                    ))

        # ── 初始化示例公告 ──
        from models import Announcement
        if db.query(Announcement).count() == 0 and admin_user:
            sample_announcements = [
                {
                    "title": "📢 智审通系统正式上线",
                    "content": "智审通高校行政审批自动化平台已正式上线运行。\n\n系统支持以下功能：\n1. 智能 OCR 识别 + 自动填表\n2. 多阶段审批流程（部门 → 财务 → 学校）\n3. AI 辅助决策建议\n4. 会议室与车辆预约\n\n如有疑问请联系信息中心。",
                    "category": "announcement",
                    "is_pinned": True,
                },
                {
                    "title": "📜 报销审批制度（暂行）",
                    "content": "一、报销范围\n1. 办公用品采购\n2. 差旅交通费\n3. 实验耗材费\n4. 图书资料费\n\n二、审批标准\n- 单次报销 ≤ 5000 元：部门审批\n- 5000 元 < 单次报销 ≤ 20000 元：部门 + 财务审批\n- 单次报销 > 20000 元：部门 + 财务 + 学校审批\n\n三、发票要求\n- 必须为增值税发票\n- 发票抬头为学校全称\n- 发票号码不得重复使用",
                    "category": "policy",
                    "document_type": "reimbursement",
                },
                {
                    "title": "📖 请假申请操作指南",
                    "content": "1. 进入「智能审批」页面，上传请假条照片或 PDF\n2. 系统自动 OCR 识别并填写表单\n3. 检查自动填充的信息，手动修改错误项\n4. 确认无误后提交审批\n5. 在「历史记录」中跟踪审批进度\n\n温馨提示：\n- 事假需提前 24 小时申请\n- 病假需附医院诊断证明\n- 请假 3 天以上需辅导员和学院双重审批",
                    "category": "guide",
                    "document_type": "leave",
                },
            ]
            for a_data in sample_announcements:
                db.add(Announcement(
                    title=a_data["title"],
                    content=a_data["content"],
                    category=a_data["category"],
                    document_type=a_data.get("document_type"),
                    is_pinned=a_data.get("is_pinned", False),
                    author_id=admin_user.id,
                ))

        # ── 初始化可预约资源 ──
        if db.query(ResourceRoom).count() == 0:
            sample_rooms = [
                {"name": "行政楼 301 会议室", "location": "行政楼三层", "capacity": 18, "equipment": "投影仪、白板、视频会议"},
                {"name": "图书馆一楼研讨室", "location": "图书馆一层东侧", "capacity": 10, "equipment": "电子屏、白板"},
                {"name": "信息中心培训室", "location": "信息中心二层", "capacity": 32, "equipment": "投影仪、讲台、无线麦克风"},
            ]
            for room_data in sample_rooms:
                db.add(ResourceRoom(**room_data))

        if db.query(ResourceVehicle).count() == 0:
            sample_vehicles = [
                {"plate_number": "鲁B·K2025", "model": "别克 GL8", "seats": 7, "driver": "王师傅"},
                {"plate_number": "鲁B·S0701", "model": "大众帕萨特", "seats": 5, "driver": "李师傅"},
            ]
            for vehicle_data in sample_vehicles:
                db.add(ResourceVehicle(**vehicle_data))

        db.commit()
        print("✅ 种子数据就绪")
        print(f"\n\033[93m[安全提醒] 以下为开发环境演示账号，密码为弱口令，生产环境请务必修改！\033[0m")
        print(f"   系统管理员:")
        print(f"     admin / {_admin_pwd}")
        for school_name, school_info in SCHOOLS.items():
            pfx = school_info["prefix"]
            tier_name = "Pro" if school_info["tier"] == TierEnum.pro else "Free"
            print(f"   {school_name} ({tier_name}):")
            for role in ["student_a", "student_b", "school_admin",
                         "dept_cs", "dept_fin", "finance_admin"]:
                pw = "admin123" if "admin" in role else "123456"
                print(f"     {pfx}_{role} / {pw}")
        print()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
