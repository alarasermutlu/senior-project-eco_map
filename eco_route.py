import osmnx as ox
import networkx as nx
import requests
import time
import matplotlib.pyplot as plt  # Added for plotting
import argparse
import aiohttp
import asyncio
import logging

# --- CONFIGURATION ---
PLACE = "Istanbul, Turkey"  # The area to download the map from
NETWORK_TYPE = "drive"      # Type of network: 'drive' for car routes
VEHICLE = {
    "base_l_per_km": 0.07,      # Base fuel consumption in liters per km
    "uphill_factor": 10,        # Fuel increase per 1% uphill slope
    "downhill_factor": -5       # Fuel decrease per 1% downhill slope
}

# --- ELEVATION FETCHING (BATCH) ---
async def get_elevations_batch(coords):
    """
    Fetches elevation data for a batch of coordinates using the Open Elevation API.
    coords: list of (lat, lon) tuples
    returns: list of elevations (meters above sea level)
    """
    url = "https://api.open-elevation.com/api/v1/lookup"  # API endpoint
    # Prepare the locations in the format required by the API
    locations = [{"latitude": lat, "longitude": lon} for lat, lon in coords]
    try:
        # Open an asynchronous HTTP session
        async with aiohttp.ClientSession() as session:
            # Send a POST request with the locations as JSON
            async with session.post(url, json={"locations": locations}) as r:
                # Check if the request was successful
                if r.status == 200:
                    # Parse the JSON response
                    data = await r.json()
                    # Extract the elevation for each location
                    return [res['elevation'] for res in data['results']]
    except Exception as e:
        # Log any errors that occur during the request
        logging.error("Elevation API error:", e)
    # If there was an error, return a list of zeros (fallback)
    return [0] * len(coords)

# --- MAIN LOGIC ---
def main(start_lat, start_lon, end_lat, end_lon):
    logging.info("Downloading map...")
    # Download the street network graph for the area around the start point
    G = ox.graph_from_point((start_lat, start_lon), dist=5000, network_type=NETWORK_TYPE)
    logging.info("Map downloaded.")

    # Add elevation to nodes (batch)
    logging.info("Fetching elevations in batches...")
    node_list = list(G.nodes(data=True))  # List of (node_id, node_data) tuples
    coords = [(data['y'], data['x']) for node, data in node_list]  # Extract (lat, lon) for each node
    batch_size = 100  # Number of coordinates per API request
    elevations = []   # List to store all elevations
    for i in range(0, len(coords), batch_size):
        batch = coords[i:i+batch_size]  # Get the next batch
        # Fetch elevations for the batch (async call)
        elevations.extend(asyncio.run(get_elevations_batch(batch)))
        time.sleep(1)  # Be gentle to the API (avoid rate limits)

    # Assign the fetched elevations back to the graph nodes
    for idx, (node, data) in enumerate(node_list):
        G.nodes[node]['elevation'] = elevations[idx]

    # Add slope to edges
    logging.info("Calculating slopes...")
    for u, v, k, data in G.edges(keys=True, data=True):
        elev_u = G.nodes[u]['elevation']  # Elevation at start node
        elev_v = G.nodes[v]['elevation']  # Elevation at end node
        dist = data['length']             # Length of the edge in meters
        if dist > 0:
            # Slope = (elevation change) / (distance)
            data['slope'] = (elev_v - elev_u) / dist
        else:
            data['slope'] = 0  # Avoid division by zero

    # Find the nearest graph nodes to the start and end coordinates
    orig_node = ox.nearest_nodes(G, start_lon, start_lat)
    dest_node = ox.nearest_nodes(G, end_lon, end_lat)

    # Custom fuel cost function for eco-routing
    def fuel_cost(u, v, data):
        slope = data.get('slope', 0)      # Slope of the edge
        length = data.get('length', 1)    # Length of the edge
        base = VEHICLE['base_l_per_km']   # Base fuel consumption
        # Adjust fuel consumption based on slope
        if slope > 0:
            cons = base * (1 + slope * VEHICLE['uphill_factor'])
        else:
            cons = base * (1 + slope * VEHICLE['downhill_factor'])
        # Return estimated fuel used for this edge (liters)
        return cons * (length / 1000)

    logging.info("Calculating eco-friendly route...")
    # Find the shortest path by distance
    shortest_route = nx.shortest_path(G, orig_node, dest_node, weight='length')

    # Find the most fuel-efficient path using the custom cost function
    eco_route = nx.shortest_path(G, orig_node, dest_node, weight=fuel_cost)

    # Output the 3D route (lat, lon, elevation) for the eco route
    route_coords = [
        (G.nodes[n]['y'], G.nodes[n]['x'], G.nodes[n]['elevation']) for n in eco_route
    ]
    logging.info("3D Route coordinates:")
    for pt in route_coords:
        logging.info(pt)

    # Plot both routes on the map
    fig, ax = ox.plot_graph_route(
        G, 
        shortest_route, 
        route_color='b', 
        route_linewidth=2, 
        node_size=0, 
        bgcolor='w', 
        show=False, 
        close=False
    )
    # Overlay the eco route in red
    ox.plot_graph_route(
        G, 
        eco_route, 
        route_color='r', 
        route_linewidth=3, 
        node_size=0, 
        ax=ax, 
        show=False, 
        close=False
    )
    # Save the plot to a file
    fig.savefig("eco_vs_shortest_route.png", dpi=150)
    logging.info("Both routes plotted and saved as eco_vs_shortest_route.png")

    # Optionally: Save the eco route to a CSV file for frontend visualization
    try:
        with open("route3d.csv", "w") as f:
            f.write("lat,lon,elevation\n")
            for pt in route_coords:
                f.write(f"{pt[0]},{pt[1]},{pt[2]}\n")
        logging.info("Route saved to route3d.csv")
    except Exception as e:
        logging.error("Error saving route to file:", e)

if __name__ == "__main__":
    # Parse command-line arguments for start and end coordinates
    parser = argparse.ArgumentParser(description="Calculate eco-friendly route")
    parser.add_argument("--start-lat", type=float, required=True, help="Start latitude")
    parser.add_argument("--start-lon", type=float, required=True, help="Start longitude")
    parser.add_argument("--end-lat", type=float, required=True, help="End latitude")
    parser.add_argument("--end-lon", type=float, required=True, help="End longitude")
    args = parser.parse_args()
    # Run the main function with the provided coordinates
    main(args.start_lat, args.start_lon, args.end_lat, args.end_lon)