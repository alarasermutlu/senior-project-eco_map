# main.py
import tracemalloc
tracemalloc.start()

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator
from osmnx.geocoder import geocode
from routing import get_vehicle_params
from eco_route import main as find_routes
from typing import List, Tuple, Optional
import logging
import traceback

# Configure logging with more detail
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Eco Route API",
    description="API for finding eco-friendly routes between locations",
    version="1.0.0"
)

# Request Models
class Vehicle(BaseModel):
    model: str = Field(..., description="Car model name")
    engine_type: str = Field(..., description="Engine type (e.g., turbo, diesel, electric)")
    year: int = Field(..., ge=1900, le=2024, description="Vehicle year")
    fuel_type: str = Field(..., description="Fuel type (petrol, diesel, hybrid, electric)")
    engine_displacement: float = Field(..., gt=0, description="Engine displacement in liters")
    transmission: str = Field(..., description="Transmission type (manual, automatic, cvt)")
    drive_type: str = Field(..., description="Drive type (FWD, RWD, AWD, 4WD)")

    @validator('fuel_type')
    def validate_fuel_type(cls, v):
        valid_types = ['petrol', 'diesel', 'hybrid', 'electric']
        if v.lower() not in valid_types:
            raise ValueError(f'fuel_type must be one of {valid_types}')
        return v.lower()

    @validator('drive_type')
    def validate_drive_type(cls, v):
        valid_types = ['FWD', 'RWD', 'AWD', '4WD']
        if v.upper() not in valid_types:
            raise ValueError(f'drive_type must be one of {valid_types}')
        return v.upper()

class RouteRequest(BaseModel):
    start: str = Field(..., description="Starting location (address or place name)")
    end: str = Field(..., description="Ending location (address or place name)")
    vehicle: Vehicle

class RouteResponse(BaseModel):
    shortest_route: List[Tuple[float, float]]
    eco_route: List[Tuple[float, float, float]]
    message: Optional[str] = None

# Route Endpoint
@app.post("/route", response_model=RouteResponse)
async def route_handler(req: RouteRequest):
    try:
        logger.info(f"Processing route request from {req.start} to {req.end}")
        
        # 1. Geocode the start and end locations
        try:
            logger.debug(f"Attempting to geocode start location: {req.start}")
            start_lat, start_lon = geocode(req.start)
            logger.debug(f"Start coordinates: {start_lat}, {start_lon}")
            
            logger.debug(f"Attempting to geocode end location: {req.end}")
            end_lat, end_lon = geocode(req.end)
            logger.debug(f"End coordinates: {end_lat}, {end_lon}")
        except Exception as e:
            logger.error(f"Geocoding error: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=400,
                detail=f"Could not find coordinates for locations: {str(e)}"
            )

        # 2. Generate vehicle parameters
        try:
            logger.debug("Generating vehicle parameters")
            vehicle_params = get_vehicle_params(**req.vehicle.dict())
            logger.debug(f"Vehicle parameters: {vehicle_params}")
        except Exception as e:
            logger.error(f"Vehicle parameter error: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=400,
                detail=f"Invalid vehicle parameters: {str(e)}"
            )

        # 3. Compute routes
        try:
            logger.debug("Starting route computation")
            shortest_route, eco_route = await find_routes(
                start_lat, start_lon, end_lat, end_lon, vehicle_params
            )
            logger.debug(f"Routes computed successfully. Shortest route length: {len(shortest_route)}, Eco route length: {len(eco_route)}")
        except ValueError as e:
            logger.error(f"Route computation error (ValueError): {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=404,
                detail=f"No valid route found: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Route computation error: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"Error computing routes: {str(e)}"
            )

        # 4. Return the route results
        return RouteResponse(
            shortest_route=shortest_route,
            eco_route=eco_route,
            message="Routes computed successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )
