from datetime import datetime

from sqlmodel import SQLModel, Field, Relationship

from app.models import VehicleDB


class VehicleLocation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    timestamp: datetime
    vehicle_name: str
    latitude: float
    longitude: float

    vehicle_id: int | None = Field(foreign_key="vehicledb.id")
    vehicle: VehicleDB = Relationship(back_populates="locations")
