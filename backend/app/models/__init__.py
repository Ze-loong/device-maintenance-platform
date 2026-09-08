"""集中导入全部表模型，确保 Base.metadata 在 create_all 时能拿到全部表定义。
scripts/init_db.py 只需要 `from app.models import Base` 就能建出全部 9 张表，
不用逐个模块 import（Python 只有真正 import 过的模块才会把表注册进 metadata）。
"""
from app.models.admin_user import AdminUser
from app.models.base import Base
from app.models.device import Device
from app.models.event import Event
from app.models.line import Line
from app.models.prediction import Prediction
from app.models.prediction_profile_segment import PredictionProfileSegment
from app.models.profile import Profile
from app.models.profile_segment import ProfileSegment
from app.models.unregistered_alert import UnregisteredAlert

__all__ = ["Base", "AdminUser", "Device", "Event", "Line", "Prediction", "PredictionProfileSegment", "Profile", "ProfileSegment", "UnregisteredAlert"]
