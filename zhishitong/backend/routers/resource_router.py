"""资源管理 API — 会议室·车辆·预约"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime
from database import SessionLocal
from auth import get_current_user
from models import (
    User, ResourceRoom, ResourceVehicle, ResourceBooking,
    ResourceType, BookingStatus,
)
from schemas import (
    ResourceRoomCreate, ResourceRoomOut,
    ResourceVehicleCreate, ResourceVehicleOut,
    ResourceBookingCreate, ResourceBookingOut,
    BookingApproveRequest,
)

router = APIRouter(prefix="/api/resources", tags=["resources"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def can_manage_resources(user: User) -> bool:
    return bool(user.is_admin or user.is_school_admin)


def get_resource_name(db: Session, resource_type: ResourceType, resource_id: int) -> str:
    if resource_type == ResourceType.meeting_room:
        room = db.query(ResourceRoom).filter(ResourceRoom.id == resource_id).first()
        return room.name if room else ""
    vehicle = db.query(ResourceVehicle).filter(ResourceVehicle.id == resource_id).first()
    return vehicle.plate_number if vehicle else ""


# ── 会议室 ──

@router.get("/rooms", response_model=list[ResourceRoomOut])
def list_rooms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(ResourceRoom).filter(ResourceRoom.is_active == True).all()


@router.post("/rooms", response_model=ResourceRoomOut)
def create_room(
    data: ResourceRoomCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage_resources(current_user):
        raise HTTPException(403, "仅管理员可管理资源")
    room = ResourceRoom(**data.model_dump())
    db.add(room)
    db.commit()
    db.refresh(room)
    return room


@router.delete("/rooms/{room_id}")
def delete_room(
    room_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage_resources(current_user):
        raise HTTPException(403)
    room = db.query(ResourceRoom).filter(ResourceRoom.id == room_id).first()
    if not room:
        raise HTTPException(404)
    room.is_active = False
    db.commit()
    return {"ok": True}


# ── 车辆 ──

@router.get("/vehicles", response_model=list[ResourceVehicleOut])
def list_vehicles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(ResourceVehicle).filter(ResourceVehicle.is_active == True).all()


@router.post("/vehicles", response_model=ResourceVehicleOut)
def create_vehicle(
    data: ResourceVehicleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage_resources(current_user):
        raise HTTPException(403)
    vehicle = ResourceVehicle(**data.model_dump())
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not can_manage_resources(current_user):
        raise HTTPException(403)
    v = db.query(ResourceVehicle).filter(ResourceVehicle.id == vehicle_id).first()
    if not v:
        raise HTTPException(404)
    v.is_active = False
    db.commit()
    return {"ok": True}


# ── 预约 ──

@router.get("/bookings", response_model=list[ResourceBookingOut])
def list_bookings(
    resource_type: str = Query(None, pattern=r"^(meeting_room|vehicle)$"),
    status: str = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """预约列表：普通用户看自己的，管理员看全部"""
    q = db.query(ResourceBooking)
    if not (current_user.is_admin or current_user.is_school_admin):
        q = q.filter(ResourceBooking.user_id == current_user.id)
    if resource_type:
        q = q.filter(ResourceBooking.resource_type == resource_type)
    if status:
        q = q.filter(ResourceBooking.status == status)

    bookings = q.order_by(ResourceBooking.start_time.desc()).limit(100).all()
    result = []
    for b in bookings:
        resource_name = get_resource_name(db, b.resource_type, b.resource_id)

        username = ""
        u = db.query(User).filter(User.id == b.user_id).first()
        if u:
            username = u.real_name or u.username

        result.append(ResourceBookingOut(
            id=b.id,
            resource_type=b.resource_type.value,
            resource_id=b.resource_id,
            resource_name=resource_name,
            user_id=b.user_id,
            username=username,
            title=b.title,
            start_time=b.start_time,
            end_time=b.end_time,
            status=b.status.value,
            participants=b.participants,
            reject_reason=b.reject_reason,
            created_at=b.created_at,
        ))
    return result


@router.post("/bookings", response_model=ResourceBookingOut)
def create_booking(
    data: ResourceBookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建预约（用户均可）"""
    try:
        start_time = datetime.fromisoformat(data.start_time)
        end_time = datetime.fromisoformat(data.end_time)
    except ValueError:
        raise HTTPException(422, "时间格式不正确")

    if end_time <= start_time:
        raise HTTPException(422, "结束时间必须晚于开始时间")

    resource_type = ResourceType(data.resource_type)

    if resource_type == ResourceType.meeting_room:
        resource_exists = db.query(ResourceRoom).filter(
            ResourceRoom.id == data.resource_id,
            ResourceRoom.is_active == True,
        ).first()
    else:
        resource_exists = db.query(ResourceVehicle).filter(
            ResourceVehicle.id == data.resource_id,
            ResourceVehicle.is_active == True,
        ).first()
    if not resource_exists:
        raise HTTPException(404, "预约资源不存在或已停用")

    # 检查时间冲突
    conflict = (
        db.query(ResourceBooking)
        .filter(
            ResourceBooking.resource_type == resource_type,
            ResourceBooking.resource_id == data.resource_id,
            ResourceBooking.status.in_([BookingStatus.pending, BookingStatus.approved]),
            ResourceBooking.start_time < end_time,
            ResourceBooking.end_time > start_time,
        )
        .first()
    )
    if conflict:
        raise HTTPException(409, "该时段已被预约，请选择其他时间")

    booking = ResourceBooking(
        resource_type=resource_type,
        resource_id=data.resource_id,
        user_id=current_user.id,
        title=data.title,
        start_time=start_time,
        end_time=end_time,
        participants=data.participants,
        status=BookingStatus.pending,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    return ResourceBookingOut(
        id=booking.id,
        resource_type=booking.resource_type.value,
        resource_id=booking.resource_id,
        resource_name=get_resource_name(db, booking.resource_type, booking.resource_id),
        user_id=booking.user_id,
        username=current_user.real_name or current_user.username,
        title=booking.title,
        start_time=booking.start_time,
        end_time=booking.end_time,
        status=booking.status.value,
        participants=booking.participants,
        reject_reason="",
        created_at=booking.created_at,
    )


@router.post("/bookings/{booking_id}/approve")
def approve_booking(
    booking_id: int,
    data: BookingApproveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """审批预约（学校管理员）"""
    if not (current_user.is_admin or current_user.is_school_admin):
        raise HTTPException(403, "仅管理员可审批预约")

    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(404)

    booking.status = data.status
    booking.approver_id = current_user.id
    if data.status == "rejected":
        booking.reject_reason = data.reject_reason

    db.commit()

    # 通知预约人审批结果
    try:
        from services.notification_service import create_notification
        from models import NotificationType
        if data.status == "approved":
            create_notification(db, booking.user_id, NotificationType.approval_approved,
                "✅ 预约已通过", f"你的资源预约「{booking.title}」已通过审批", record_id=None)
        else:
            create_notification(db, booking.user_id, NotificationType.approval_rejected,
                "❌ 预约被驳回", f"你的资源预约「{booking.title}」已被驳回。原因：{booking.reject_reason or '无'}", record_id=None)
    except Exception:
        pass  # 通知失败不影响主流程

    return {"ok": True}


@router.delete("/bookings/{booking_id}")
def cancel_booking(
    booking_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """取消预约（本人或管理员）"""
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == booking_id).first()
    if not booking:
        raise HTTPException(404)
    if booking.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(403)
    booking.status = BookingStatus.cancelled
    db.commit()
    return {"ok": True}
