from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response, HTTPException

from app import database
from app.auth import auth_device
from app.helpers.log_parser import parse_log
from app.models.badlog import BadLogDB
from app.models.device import DeviceDB
from app.models.log import LogEntryDB

router = APIRouter(prefix="/log", tags=["Logs"])


@router.post("/upload")
async def upload_log(session: database.SessionDep, request: Request, device: DeviceDB = Depends(auth_device)):
    upload_time = datetime.now(timezone.utc)
    file = await request.body()  # read raw bytes from body
    raw_log = file.decode()
    try:
        parsed_entries = parse_log(raw_log)
    except Exception as ve:
        session.add(BadLogDB(text=raw_log, upload_timestamp=upload_time, imei=device.imei))
        session.commit()
        print(f"Failed to parse log: {ve}. Saved to db")
        # Return success because we saved the log and the device can delete its log
        raise HTTPException(200, "Malformed log")

    log_db: list[LogEntryDB] = [LogEntryDB.from_dataclass(pe, device.imei, upload_time) for pe in parsed_entries]

    session.add_all(log_db)
    session.commit()
    print("Added", len(log_db), "log entries")
    return Response(status_code=200)
