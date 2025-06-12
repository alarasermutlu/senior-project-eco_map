import logging
from eco_route import download_city_map, get_elevations, cache_manager

# Enable debug logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def download_ankara_data():
    logging.info("Starting Ankara data download...")
    
    # Download and cache the map
    G = download_city_map("Ankara")
    if G is None:
        logging.error("Failed to download Ankara map")
        return
    
    # Get all node coordinates
    node_list = list(G.nodes(data=True))
    coords = [(data['y'], data['x']) for node, data in node_list]
    
    # Download and cache elevations
    logging.info(f"Downloading elevations for {len(coords)} locations in Ankara...")
    elevations = get_elevations(coords)
    
    # Assign elevations to nodes
    for idx, (node, data) in enumerate(node_list):
        G.nodes[node]['elevation'] = elevations[idx]
    
    # Save the graph with elevations to cache
    cache_manager.save_to_cache('city_map', {'city': 'Ankara', 'country': 'Turkey'}, G)
    
    logging.info("Ankara data download complete!")
    logging.info(f"Map contains {len(G.nodes)} nodes and {len(G.edges)} edges")
    logging.info(f"Elevations downloaded for {len(elevations)} locations")

if __name__ == '__main__':
    download_ankara_data() 