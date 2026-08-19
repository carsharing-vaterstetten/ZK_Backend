import zipfile
from datetime import datetime, timezone
from io import BytesIO

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlmodel import select

from app.database import SessionDep
from app.models.device import DeviceDB
from app.models.firmware import FirmwareDB, FirmwarePublic
from app.models.firmware_update import FirmwareUpdateDB, FirmwareUpdatePublic

router = APIRouter(prefix="/firmware")


@router.get("/download")
async def download_fw(version: str, session: SessionDep):
    fw_db = session.exec(select(FirmwareDB).where(FirmwareDB.version == version)).first()

    if not fw_db:
        raise HTTPException(status_code=404, detail="Firmware not found")

    buffer = BytesIO()

    files = {
        "firmware.bin": fw_db.firmware,
        "partitions.bin": fw_db.partitions,
        "bootloader.bin": fw_db.bootloader,
    }

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            if data is not None:
                z.writestr(name, data)

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={fw_db.version}.zip"},
    )


@router.post("/upload-new", response_model=FirmwarePublic)
async def upload_new_firmware(
    version: str,
    session: SessionDep,
    bootloader: UploadFile = File(...),
    firmware: UploadFile = File(...),
    partitions: UploadFile = File(...),
    overwrite_existing: bool = False,
):
    existing = session.exec(
        select(FirmwareDB).where(FirmwareDB.version == version)
    ).first()

    if existing and not overwrite_existing:
        raise HTTPException(400, "Firmware already exists")

    bootloader_bytes = await bootloader.read()
    firmware_bytes = await firmware.read()
    partitions_bytes = await partitions.read()

    if not bootloader_bytes or not firmware_bytes or not partitions_bytes:
        raise HTTPException(400, "One or more files are empty")

    if existing:
        db_firmware = existing
        db_firmware.bootloader = bootloader_bytes
        db_firmware.firmware = firmware_bytes
        db_firmware.partitions = partitions_bytes
    else:
        db_firmware = FirmwareDB(
            version=version,
            bootloader=bootloader_bytes,
            firmware=firmware_bytes,
            partitions=partitions_bytes,
        )

    session.add(db_firmware)
    session.commit()
    session.refresh(db_firmware)

    return db_firmware


@router.post("/issue-new", response_model=FirmwareUpdatePublic)
async def issue_new_firmware_to_device(device_imei: str, firmware_version: str, session: SessionDep):
    # check device exists
    device = session.get(DeviceDB, device_imei)

    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_imei} not found")

    # check firmware exists
    firmware = session.get(FirmwareDB, firmware_version)
    if not firmware:
        raise HTTPException(status_code=404, detail=f"Firmware {firmware_version} not found")

    # check if hardware is compatible
    if not any(device.hw_revision_number == hw.revision_number for hw in firmware.compatible_hardware):
        raise HTTPException(status_code=422, detail='Firmware is not compatible with the device')

    # check for existing pending update
    existing_update = session.exec(
        select(FirmwareUpdateDB).where(FirmwareUpdateDB.target_device_imei == device_imei)
    ).first()

    if existing_update is not None:

        if existing_update.target_firmware_version == firmware.version:
            raise HTTPException(status_code=200,
                                detail="Update has already been issued at " + existing_update.update_issued_at.isoformat())

        # just override the existing record
        existing_update.target_firmware_version = firmware.version
        existing_update.update_issued_at = datetime.now(tz=timezone.utc)
        existing_update.update_last_downloaded = None
        fw_update = existing_update
    else:
        # create a new one if none exists
        fw_update = FirmwareUpdateDB(
            target_device_imei=device.imei,
            target_firmware_version=firmware.version
        )
        session.add(fw_update)

    session.commit()
    session.refresh(fw_update)

    return fw_update


@router.get("/all", response_model=list[FirmwarePublic])
async def get_all_available_firmwares(session: SessionDep):
    return session.exec(select(FirmwareDB)).all()
