# main.py
import tracemalloc
tracemalloc.start()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from osmnx.geocoder import geocode
from routing import get_vehicle_params
from eco_route import main as find_routes


app = FastAPI()

# Request Models
class Vehicle(BaseModel):
    model: str
    engine_type: str
    year: int
    fuel_type: str
    engine_displacement: float
    transmission: str
    drive_type: str

class RouteRequest(BaseModel):
    start: str
    end: str
    vehicle: Vehicle

# Route Endpoint
@app.post("/route")
async def route_handler(req: RouteRequest):
    try:
        # 1. Geocode the start and end locations
        start_lat, start_lon = geocode(req.start)
        end_lat, end_lon = geocode(req.end)

        # 2. Generate vehicle parameters
        vehicle_params = get_vehicle_params(**req.vehicle.dict())

        # 3. Compute routes
        shortest_route, eco_route = await find_routes(
            start_lat, start_lon, end_lat, end_lon, vehicle_params
        )

        # 4. Return the route results
        return {
            "shortest_route": shortest_route,
            "eco_route": eco_route
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
