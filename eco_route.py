import osmnx as ox
import logging
import os
import matplotlib.pyplot as plt
import json
import requests
import time
from urllib.parse import urlencode
from cache_manager import CacheManager

from routing import (
    generate_graph,
    calculate_slope,
    find_shortest_and_eco_route,
    get_vehicle_params
)

# Enable debug logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

NETWORK_TYPE = "drive"
MAPBOX_ACCESS_TOKEN = "pk.eyJ1IjoiYWxhcmFzZXJtdXRsdSIsImEiOiJjbWJjamRsZjMxbndoMmxzOWl3ZWozMTRoIn0.3ZKrG6or5GUTKaNJnPGvMA"

# Initialize cache manager
cache_manager = CacheManager()

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

def get_elevations(coords, batch_size=100):
    """
    Get elevation data for coordinates using Google Elevation API.
    coords: list of (lat, lon) tuples
    returns: list of elevations (meters above sea level)
    """
    # Try to get from cache first
    cache_data = {
        'coords': coords,
        'batch_size': batch_size
    }
    cached_elevations = cache_manager.get_cached_data('elevations', cache_data)
    if cached_elevations is not None:
        return cached_elevations

    elevations = []
    total_coords = len(coords)
    
    # Process coordinates in batches to avoid API limits
    for i in range(0, total_coords, batch_size):
        batch = coords[i:i + batch_size]
        
        # Format coordinates for API
        locations = []
        for lat, lon in batch:
            locations.append(f"{lat},{lon}")
        locations_str = "|".join(locations)
        
        # Google Elevation API endpoint
        url = "https://maps.googleapis.com/maps/api/elevation/json"
        params = {
            "locations": locations_str,
            "key": "AIzaSyA4WJZcT2uWL9kVuTscKp-zRpJfJKMA48w"  
        }
        
        try:
            logging.info(f"Fetching elevations for batch {i//batch_size + 1}/{(total_coords + batch_size - 1)//batch_size}")
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            # Parse elevation data from response
            data = response.json()
            if data.get('status') == 'OK' and 'results' in data:
                batch_elevations = [result['elevation'] for result in data['results']]
                elevations.extend(batch_elevations)
            else:
                logging.warning(f"No elevation data in response for batch {i//batch_size + 1}")
                elevations.extend([0] * len(batch))
            
            # Respect API rate limits
            time.sleep(0.5)  # Google API has higher rate limits
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Network error fetching elevations: {str(e)}")
            elevations.extend([0] * len(batch))
        except Exception as e:
            logging.error(f"Unexpected error fetching elevations: {str(e)}")
            elevations.extend([0] * len(batch))
    
    if len(elevations) != total_coords:
        logging.warning(f"Got {len(elevations)} elevations for {total_coords} coordinates")
        # Pad with zeros if we got fewer elevations than coordinates
        elevations.extend([0] * (total_coords - len(elevations)))
    
    # Save to cache
    cache_manager.save_to_cache('elevations', cache_data, elevations)
    
    logging.info(f"Retrieved elevations for {len(elevations)} coordinates")
    return elevations

def download_city_map(city_name, country="Turkey"):
    """
    Download and cache the entire map for a city.
    Returns the graph object.
    """
    cache_key = f"city_{city_name}_{country}"
    cached_graph = cache_manager.get_cached_data('city_map', {'city': city_name, 'country': country})
    
    if cached_graph is not None:
        logging.info(f"Retrieved {city_name} map from cache")
        return ox.graph_from_gdfs(
            ox.graph_to_gdfs(ox.graph_from_json(cached_graph))
        )
    
    logging.info(f"Downloading map for {city_name}, {country}...")
    try:
        # Download the city's street network
        G = ox.graph_from_place(f"{city_name}, {country}", network_type=NETWORK_TYPE)
        
        # Save to cache
        cache_manager.save_to_cache('city_map', {'city': city_name, 'country': country}, ox.graph_to_json(G))
        logging.info(f"Map downloaded and cached for {city_name} with {len(G.nodes)} nodes and {len(G.edges)} edges")
        return G
    except Exception as e:
        logging.error(f"Error downloading city map: {str(e)}")
        return None

def main(start_lat, start_lon, end_lat, end_lon, vehicle_params, city_name=None):
    logging.info("Starting route calculation...")
    
    if city_name:
        # Use the city-wide map
        G = download_city_map(city_name)
        if G is None:
            logging.error(f"Failed to get map for {city_name}")
            return None, None
    else:
        # Use the original method for specific routes
        map_cache_data = {
            'start_lat': start_lat,
            'start_lon': start_lon,
            'end_lat': end_lat,
            'end_lon': end_lon,
            'network_type': NETWORK_TYPE
        }
        
        cached_graph = cache_manager.get_cached_data('map', map_cache_data)
        if cached_graph is not None:
            logging.info("Retrieved map data from cache")
            G = ox.graph_from_gdfs(
                ox.graph_to_gdfs(ox.graph_from_json(cached_graph))
            )
        else:
            logging.info("Downloading map...")
            G = generate_graph(start_lat, start_lon, end_lat, end_lon, NETWORK_TYPE)
            cache_manager.save_to_cache('map', map_cache_data, ox.graph_to_json(G))
            logging.info(f"Map downloaded with {len(G.nodes)} nodes and {len(G.edges)} edges.")

    # Find nearest graph nodes
    logging.info("Finding nearest nodes to start and end points...")
    orig_node = ox.nearest_nodes(G, start_lon, start_lat)
    dest_node = ox.nearest_nodes(G, end_lon, end_lat)
    
    logging.info(f"Start coordinates: ({start_lat}, {start_lon})")
    logging.info(f"End coordinates: ({end_lat}, {end_lon})")
    logging.info(f"Found start node: {orig_node}")
    logging.info(f"Found end node: {dest_node}")
    
    if orig_node == dest_node:
        logging.error("Start and end nodes are the same!")
        return None, None

    # Fetch elevations
    logging.info("Fetching elevations...")
    node_list = list(G.nodes(data=True))
    coords = [(data['y'], data['x']) for node, data in node_list]
    elevations = get_elevations(coords)
    logging.info(f"Got elevations for {len(elevations)} nodes")

    # Assign elevation to nodes
    logging.info("Assigning elevations to nodes...")
    for idx, (node, data) in enumerate(node_list):
        G.nodes[node]['elevation'] = elevations[idx]

    # Calculate slope for edges
    logging.info("Calculating slopes...")
    calculate_slope(G)

    # Get routes
    logging.info("Calculating eco-friendly route...")
    shortest_route, eco_route = find_shortest_and_eco_route(G, orig_node, dest_node, vehicle_params)

    if shortest_route is None or eco_route is None:
        logging.error("No valid route found")
        return None, None

    # Create route coordinates
    logging.info("Creating route coordinates...")
    shortest_coords = [(G.nodes[n]['y'], G.nodes[n]['x']) for n in shortest_route]
    eco_coords = [(G.nodes[n]['y'], G.nodes[n]['x'], G.nodes[n].get('elevation', 0)) for n in eco_route]

    # Save routes as GeoJSON
    logging.info("Saving routes as GeoJSON...")
    save_routes_to_geojson(shortest_coords, eco_coords)

    # Plot routes
    logging.info("Plotting routes...")
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
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Çankaya, Ankara coordinates
    start_lat = 39.8897
    start_lon = 32.7960
    end_lat = 39.9161
    end_lon = 32.8266
    
    # Set up vehicle parameters with simplified options
    vehicle_params = get_vehicle_params(
        vehicle_type='medium',  # Options: 'small', 'medium', 'large', 'suv'
        fuel_type='petrol',     # Options: 'petrol', 'diesel', 'hybrid', 'electric'
        year=2020
    )
    
    # Run the main function
    main(start_lat, start_lon, end_lat, end_lon, vehicle_params)
