from datetime import datetime
from enum import Enum

from sqlmodel import SQLModel, Field, Relationship

from app.models.dataclasses.log import ParsedLogEntry
from app.models.device import DeviceDB

class LoggingLevel(str, Enum):
    debug = "DEBUG"
    info = "INFO"
    warning = "WARNING"
    error = "ERROR"
    critical = "CRITICAL"


class _LogEntryBase(SQLModel):
    timestamp: datetime
    original_timestamp: datetime | None = None
    level: LoggingLevel
    task: str | None = None
    message: str
    imei: str
    timestamp_is_valid: bool # in case the Modem failed to sync time with network
    upload_timestamp: datetime

    def __str__(self):
        return f"[{self.timestamp.isoformat()}][{self.level.value}]{f'[{self.task}]' if self.task is not None else ''} {self.message}"


class LogEntryDB(_LogEntryBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    imei: str = Field(foreign_key="devicedb.imei")
    device: DeviceDB | None = Relationship(back_populates="logs")

    @staticmethod
    def from_dataclass(dc: ParsedLogEntry, imei: str, upload_time: datetime):
        return LogEntryDB(**dc.__dict__, imei=imei,upload_timestamp=upload_time, timestamp_is_valid=2025 <= dc.timestamp.year and dc.timestamp < upload_time)


def char_to_logging_level(char: str) -> LoggingLevel:
    match char:
        case "D":
            return LoggingLevel.debug
        case "I":
            return LoggingLevel.info
        case "W":
            return LoggingLevel.warning
        case "E":
            return LoggingLevel.error
        case "C":
            return LoggingLevel.critical

    raise ValueError()
