import re
from enum import Enum

from pydantic import field_validator
from sqlmodel import SQLModel, Field, Relationship

license_plate_re = re.compile(r"^[A-ZÄÖÜ]{1,3}-[A-Z]{1,2}\d{1,4}$")  # For germany


class VehicleType(str, Enum):
    Car = "Car"


class _VehicleBase(SQLModel):
    type: VehicleType
    license_plate: str | None = None
    designation: str | None = None
    location: str | None = None
    notes: str | None = None

    @field_validator("license_plate")
    def check_license_place(cls, v):

        if v is None:
            return v

        v = v.replace(" ", "").upper()

        if not license_plate_re.match(v):
            raise ValueError(f"Invalid license plate: {v}")

        return v


class VehicleDB(_VehicleBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    locations: list["VehicleLocation"] | None = Relationship(back_populates="vehicle")
