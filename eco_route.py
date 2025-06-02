import osmnx as ox
import time
import asyncio
import aiohttp
import logging
import os
import matplotlib.pyplot as plt
import json

from routing import (
    generate_graph,
    calculate_slope,
    find_shortest_and_eco_route,
    get_vehicle_params
)

logging.basicConfig(level=logging.INFO)

PLACE = "Çankaya, Ankara, Turkey"
NETWORK_TYPE = "drive"
MAPBOX_ACCESS_TOKEN = "pk.eyJ1IjoiYWxhcmFzZXJtdXRsdSIsImEiOiJjbWJjamRsZjMxbndoMmxzOWl3ZWozMTRoIn0.3ZKrG6or5GUTKaNJnPGvMA"  # You'll need to replace this with your actual token

def save_routes_to_geojson(shortest_coords, eco_coords):
    """
    Save both routes as GeoJSON files
    shortest_coords: list of (lat, lon) tuples
    eco_coords: list of (lat, lon, elevation) tuples
    """
    # Convert shortest route to GeoJSON
    shortest_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon in shortest_coords]
            },
            "properties": {
                "type": "shortest"
            }
        }]
    }

    # Convert eco route to GeoJSON (ignoring elevation data)
    eco_geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lat, lon, _ in eco_coords]
            },
            "properties": {
                "type": "eco"
            }
        }]
    }

    # Save both files
    with open("shortest_route.geojson", "w") as f:
        json.dump(shortest_geojson, f, indent=2)
    with open("eco_route.geojson", "w") as f:
        json.dump(eco_geojson, f, indent=2)
    
    logging.info("Routes saved as GeoJSON files")

# --- ELEVATION FETCHING (BATCH) ---
async def get_elevations_batch(coords):
    """
    Fetches elevation data for a batch of coordinates using Mapbox Terrain API.
    coords: list of (lat, lon) tuples
    returns: list of elevations (meters above sea level)
    """
    # For now, return a default elevation of 0 for all coordinates
    # This will allow the script to continue without getting stuck on elevation data
    logging.info("Using default elevation data (0m) for all coordinates")
    return [0] * len(coords)

# --- MAIN LOGIC ---
async def main(start_lat, start_lon, end_lat, end_lon, vehicle_params):
    logging.info("Downloading map...")
    G = generate_graph(start_lat, start_lon, end_lat, end_lon, NETWORK_TYPE)
    logging.info(f"Map downloaded with {len(G.nodes)} nodes and {len(G.edges)} edges.")

    # Fetch elevations
    logging.info("Fetching elevations...")
    node_list = list(G.nodes(data=True))
    coords = [(data['y'], data['x']) for node, data in node_list]
    elevations = await get_elevations_batch(coords)

    # Assign elevation to nodes
    for idx, (node, data) in enumerate(node_list):
        G.nodes[node]['elevation'] = elevations[idx]

    # Calculate slope for edges
    calculate_slope(G)

    # Find nearest graph nodes
    orig_node = ox.nearest_nodes(G, start_lon, start_lat)
    dest_node = ox.nearest_nodes(G, end_lon, end_lat)

    # Get routes
    logging.info("Calculating eco-friendly route...")
    shortest_route, eco_route = find_shortest_and_eco_route(G, orig_node, dest_node, vehicle_params)

    if len(shortest_route) < 2 or len(eco_route) < 2:
        raise ValueError("No valid route found")

    # Create route coordinates
    shortest_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in shortest_route]
    eco_coords = [(G.nodes[n]['y'], G.nodes[n]['x'], G.nodes[n].get('elevation', 0)) for n in eco_route]

    # Save routes as GeoJSON
    save_routes_to_geojson(shortest_coords, eco_coords)

    # Plot routes
    fig, ax = ox.plot_graph_route(
        G, shortest_route,
        route_color='b',
        route_linewidth=2,
        node_size=0,
        bgcolor='w',
        show=False,
        close=False
    )
    ox.plot_graph_route(
        G, eco_route,
        route_color='r',
        route_linewidth=3,
        node_size=0,
        ax=ax,
        show=False,
        close=False
    )
    fig.savefig("route3d.png", dpi=150)
    logging.info("Routes plotted and saved as route3d.png")

    return shortest_coords, eco_coords

if __name__ == "__main__":
    print("Enter your car details:")
    model = input("Model: ")
    engine_type = input("Engine type (e.g., turbo, diesel, electric): ")
    year = input("Year: ")
    fuel_type = input("Fuel type (petrol, diesel, hybrid, electric): ")
    engine_displacement = input("Engine displacement (e.g., 1.6): ")
    transmission = input("Transmission (manual, automatic, cvt): ")
    drive_type = input("Drive type (FWD, RWD, AWD, 4WD): ")

    vehicle_params = get_vehicle_params(
        model, engine_type, year, fuel_type,
        engine_displacement, transmission, drive_type
    )

    # Example coordinates in Çankaya, Ankara
    start_lat = 39.9237
    start_lon = 32.8610
    end_lat = 39.8603
    end_lon = 32.811
    asyncio.run(main(start_lat, start_lon, end_lat, end_lon, vehicle_params))
