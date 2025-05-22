# routing.py

import osmnx as ox
import networkx as nx

def generate_graph(start_lat, start_lon, network_type="drive"):
    """
    Downloads a street network graph based on the starting latitude and longitude.
    """
    return ox.graph_from_point((start_lat, start_lon), dist=10000, network_type=network_type)

def calculate_slope(G):
    """
    Adds slope data to the graph based on elevation differences between nodes.
    """
    for u, v, k, data in G.edges(keys=True, data=True):
        elev_u = G.nodes[u].get('elevation', 0)
        elev_v = G.nodes[v].get('elevation', 0)
        dist = data.get('length', 1)
        data['slope'] = (elev_v - elev_u) / dist if dist > 0 else 0

def fuel_cost(u, v, data, vehicle_params):
    """
    Custom fuel cost function considering slopes and vehicle parameters.
    """
    slope = data.get('slope', 0)
    length = data.get('length', 1)
    base = vehicle_params['base_l_per_km']
    if slope > 0:
        cons = base * (1 + slope * vehicle_params['uphill_factor'])
    else:
        cons = base * (1 + slope * vehicle_params['downhill_factor'])
    return cons * (length / 1000)

def find_shortest_and_eco_route(G, orig_node, dest_node, vehicle_params):
    """
    Finds both the shortest path and the eco-friendly path (using fuel_cost).
    """
    shortest_route = nx.shortest_path(G, orig_node, dest_node, weight='length')
    eco_route = nx.shortest_path(
        G, 
        orig_node, 
        dest_node, 
        weight=lambda u, v, data: fuel_cost(u, v, data, vehicle_params)
    )
    return shortest_route, eco_route

def get_vehicle_params(model, engine_type, year, fuel_type, engine_displacement, transmission, drive_type):
    """
    Returns a dict of vehicle parameters used in eco route calculation.
    You can improve this by adding real data or a lookup table.
    """
    # Basic default values — customize as needed
    base_l_per_km = 0.07  # baseline consumption
    uphill_factor = 5     # consumption increases uphill
    downhill_factor = 2   # recovery or engine braking downhill

    # You could improve this function to match actual cars
    return {
        "model": model,
        "engine_type": engine_type,
        "year": year,
        "fuel_type": fuel_type,
        "engine_displacement": engine_displacement,
        "transmission": transmission,
        "drive_type": drive_type,
        "base_l_per_km": base_l_per_km,
        "uphill_factor": uphill_factor,
        "downhill_factor": downhill_factor
    } 