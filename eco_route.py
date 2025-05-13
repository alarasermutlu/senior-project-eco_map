import osmnx as ox
import time
import asyncio
import aiohttp
import logging
import os
import matplotlib.pyplot as plt

from routing import (
    generate_graph,
    calculate_slope,
    find_shortest_and_eco_route,
    get_vehicle_params
)

logging.basicConfig(level=logging.INFO)

PLACE = "Istanbul, Turkey"
NETWORK_TYPE = "drive"

# --- ELEVATION FETCHING (BATCH) ---
async def get_elevations_batch(coords):
    """
    Fetches elevation data for a batch of coordinates using the Open Elevation API.
    coords: list of (lat, lon) tuples
    returns: list of elevations (meters above sea level)
    """
    url = "https://api.open-elevation.com/api/v1/lookup"
    locations = [{"latitude": lat, "longitude": lon} for lat, lon in coords]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"locations": locations}) as r:
                if r.status == 200:
                    data = await r.json()
                    return [res['elevation'] for res in data['results']]
    except Exception as e:
        logging.error("Elevation API error:", e)
    return [0] * len(coords)

# --- MAIN LOGIC ---
def main(start_lat, start_lon, end_lat, end_lon, vehicle_params):
    logging.info("Downloading map...")
    G = generate_graph(start_lat, start_lon, NETWORK_TYPE)
    logging.info("Map downloaded.")

    # Fetch elevations
    logging.info("Fetching elevations in batches...")
    node_list = list(G.nodes(data=True))
    coords = [(data['y'], data['x']) for node, data in node_list]
    batch_size = 100
    elevations = []
    for i in range(0, len(coords), batch_size):
        batch = coords[i:i + batch_size]
        elevations.extend(asyncio.run(get_elevations_batch(batch)))
        time.sleep(1)

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

    # Create 3D route output
    route_coords = [
        (G.nodes[n]['y'], G.nodes[n]['x'], G.nodes[n]['elevation']) for n in eco_route
    ]
    logging.info("3D Route coordinates:")
    for pt in route_coords:
        logging.info(pt)

    # Plot both routes
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
    fig.savefig("eco_vs_shortest_route.png", dpi=150)
    logging.info("Routes plotted and saved as eco_vs_shortest_route.png")

    # Save to CSV
    try:
        with open("route3d.csv", "w") as f:
            f.write("lat,lon,elevation\n")
            for pt in route_coords:
                f.write(f"{pt[0]},{pt[1]},{pt[2]}\n")
        logging.info("Route saved to route3d.csv")
    except Exception as e:
        logging.error("Error saving route to file:", e)

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

    # Example coordinates in Istanbul
    start_lat = 41.0369
    start_lon = 28.9850
    end_lat = 41.0086
    end_lon = 28.9802
    main(start_lat, start_lon, end_lat, end_lon, vehicle_params)
