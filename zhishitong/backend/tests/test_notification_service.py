import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, NotificationType, User
from services.notification_service import create_notification, get_user_notifications


class NotificationServiceTest(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine)

    def test_filters_types_before_paginating(self):
        db = self.Session()
        try:
            user = User(username="student", hashed_password="x")
            db.add(user)
            db.commit()
            db.refresh(user)

            for i in range(3):
                create_notification(db, user.id, NotificationType.system_announcement, f"系统{i}", "系统消息")
            for i in range(3):
                create_notification(db, user.id, NotificationType.approval_submitted, f"待处理{i}", "待处理消息")

            result = get_user_notifications(
                db,
                user.id,
                page=1,
                page_size=2,
                types=[NotificationType.approval_submitted.value],
            )

            self.assertEqual(result["total"], 3)
            self.assertEqual(len(result["items"]), 2)
            self.assertTrue(all(n.type == NotificationType.approval_submitted for n in result["items"]))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
