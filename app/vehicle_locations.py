from datetime import datetime

from pykml import parser
from urllib.request import urlopen
from app.database import engine
from sqlmodel import Session, select
from app.models import VehicleDB, VehicleLocation

KML_URL = "https://www.google.com/maps/d/kml?forcekml=1&mid=1k1WUVpi6m-_RwS6K9mcTyYQ1pMTqYg0"


def fetch_latest_kml():
    tree = parser.parse(urlopen(KML_URL))
    return tree.getroot()


def extract_placemarks(root) -> list[dict]:
    """Yield (name, lon, lat) for every Placemark in the KML."""
    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    placemarks = []
    for placemark in root.findall(".//kml:Placemark", namespaces=ns):
        name_el = placemark.find("kml:name", namespaces=ns)
        coords_el = placemark.find(".//kml:coordinates", namespaces=ns)

        if name_el is None or coords_el is None:
            continue

        name = name_el.text.strip()
        lon_str, lat_str, *_ = coords_el.text.strip().split(",")
        placemarks.append({
            "name": name,
            "lon": float(lon_str),
            "lat": float(lat_str),
        })

    return placemarks


def match_vehicle_names_to_ids(vehicle_names: list[str]) -> dict[str, int]:
    res = {}

    with Session(engine) as session:
        db_vehicles: list[VehicleDB] = session.exec(select(VehicleDB)).all()

    for vehicle_name in vehicle_names:

        translated_vehicle_name = vehicle_name.translate(str.maketrans("", "", " -.,")).lower()

        for db_vehicle in db_vehicles:
            translated_db_vehicle_name = f"{db_vehicle.designation} {db_vehicle.location}"
            translated_db_vehicle_name = translated_db_vehicle_name.translate(str.maketrans("", "", " -.,")).lower()

            if len(translated_vehicle_name) < 3 or len(translated_db_vehicle_name) < 3:
                # avoid empty strings / small strings
                continue

            if translated_vehicle_name == translated_db_vehicle_name:
                res[vehicle_name] = db_vehicle.id

    return res



def fetch_locations_and_place_in_db(dry_run: bool = False):

    ts = datetime.now()

    root = fetch_latest_kml()
    data = extract_placemarks(root)

    vehicle_names_and_ids = match_vehicle_names_to_ids([d["name"] for d in data])

    with Session(engine) as session:

        for entry in data:
            vehicle_location = VehicleLocation(
                timestamp = ts,
                vehicle_name = entry["name"],
                latitude = entry["lat"],
                longitude = entry["lon"],
                vehicle_id = vehicle_names_and_ids.get(entry["name"]),
            )
            session.add(vehicle_location)

        if dry_run:
            session.rollback()
        else:
            session.commit()
