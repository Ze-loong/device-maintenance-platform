"""unregistered_alert 表持久化：未注册产线/设备的告警落库。"""
from sqlalchemy.orm import Session

from app.models.unregistered_alert import UnregisteredAlert


class UnregisteredAlertRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, line_id_raw: str, device_id_raw: str, topic: str, reason: str, raw_payload: dict) -> UnregisteredAlert:
        alert = UnregisteredAlert(line_id_raw=line_id_raw, device_id_raw=device_id_raw, topic=topic, reason=reason, raw_payload=raw_payload)
        self.db.add(alert)
        self.db.flush()
        return alert
