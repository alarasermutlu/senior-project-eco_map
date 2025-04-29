import osmnx as ox
import networkx as nx
import requests
import time
import matplotlib.pyplot as plt  # Added for plotting

# --- CONFIGURATION ---c:\Users\alara\Desktop\eco_route.py
PLACE = "Istanbul, Turkey"
NETWORK_TYPE = "drive"
VEHICLE = {
    "base_l_per_km": 0.07,      # liters per km
    "uphill_factor": 10,        # increase per 1% slope
    "downhill_factor": -5       # decrease per 1% slope
}

# --- ELEVATION FETCHING (BATCH) ---
def get_elevations_batch(coords):
    """
    coords: list of (lat, lon)
    returns: list of elevations
    """
    url = "https://api.open-elevation.com/api/v1/lookup"
    locations = [{"latitude": lat, "longitude": lon} for lat, lon in coords]
    try:
        r = requests.post(url, json={"locations": locations})
        if r.status_code == 200:
            return [res['elevation'] for res in r.json()['results']]
    except Exception as e:
        print("Elevation API error:", e)
    return [0] * len(coords)

# --- MAIN LOGIC ---
def main(start_lat, start_lon, end_lat, end_lon):
    print("Downloading map...")
    G = ox.graph_from_point((start_lat, start_lon), dist=5000, network_type=NETWORK_TYPE)
    print("Map downloaded.")

    # Add elevation to nodes (batch)
    print("Fetching elevations in batches...")
    node_list = list(G.nodes(data=True))
    coords = [(data['y'], data['x']) for node, data in node_list]
    batch_size = 100
    elevations = []
    for i in range(0, len(coords), batch_size):
        batch = coords[i:i+batch_size]
        elevations.extend(get_elevations_batch(batch))
        time.sleep(1)  # Be gentle to the API

    for idx, (node, data) in enumerate(node_list):
        G.nodes[node]['elevation'] = elevations[idx]

    # Add slope to edges
    print("Calculating slopes...")
    for u, v, k, data in G.edges(keys=True, data=True):
        elev_u = G.nodes[u]['elevation']
        elev_v = G.nodes[v]['elevation']
        dist = data['length']
        if dist > 0:
            data['slope'] = (elev_v - elev_u) / dist
        else:
            data['slope'] = 0

    # Find nearest nodes to start/end
    orig_node = ox.nearest_nodes(G, start_lon, start_lat)
    dest_node = ox.nearest_nodes(G, end_lon, end_lat)

    # Custom fuel cost function
    def fuel_cost(u, v, data):
        slope = data.get('slope', 0)
        length = data.get('length', 1)
        base = VEHICLE['base_l_per_km']
        if slope > 0:
            cons = base * (1 + slope * VEHICLE['uphill_factor'])
        else:
            cons = base * (1 + slope * VEHICLE['downhill_factor'])
        return cons * (length / 1000)

    print("Calculating eco-friendly route...")
    # Shortest path (by distance)
    shortest_route = nx.shortest_path(G, orig_node, dest_node, weight='length')

    # Fuel-efficient path (by custom fuel cost)
    eco_route = nx.shortest_path(G, orig_node, dest_node, weight=fuel_cost)

    # Output 3D route (lat, lon, elevation)
    route_coords = [
        (G.nodes[n]['y'], G.nodes[n]['x'], G.nodes[n]['elevation']) for n in eco_route
    ]
    print("3D Route coordinates:")
    for pt in route_coords:
        print(pt)

    # Plot both routes
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
    fig.savefig("eco_vs_shortest_route.png", dpi=150)
    print("Both routes plotted and saved as eco_vs_shortest_route.png")

    # Optionally: Save to file for frontend visualization
    with open("route3d.csv", "w") as f:
        f.write("lat,lon,elevation\n")
        for pt in route_coords:
            f.write(f"{pt[0]},{pt[1]},{pt[2]}\n")
    print("Route saved to route3d.csv")

if __name__ == "__main__":
    # Example: Taksim Square to Sultanahmet, Istanbul
    start_lat, start_lon = 41.0369, 28.9850
    end_lat, end_lon = 41.0086, 28.9802
    main(start_lat, start_lon, end_lat, end_lon)