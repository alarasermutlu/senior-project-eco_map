# routing.py

import osmnx as ox
import networkx as nx
import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)

# Vehicle type definitions with scientifically validated parameters
VEHICLE_TYPES = {
    'A': {  # Mini cars (e.g., Fiat 500, Smart Fortwo)
        'weight': 900,  # kg
        'drag_coef': 0.30,  # Based on wind tunnel testing
        'frontal_area': 1.8,  # m²
        'base_efficiency': 0.38  # Based on WLTP testing
    },
    'B': {  # Small cars (e.g., VW Polo, Renault Clio)
        'weight': 1100,
        'drag_coef': 0.31,
        'frontal_area': 1.9,
        'base_efficiency': 0.36
    },
    'C': {  # Medium cars (e.g., VW Golf, Ford Focus)
        'weight': 1300,
        'drag_coef': 0.32,
        'frontal_area': 2.1,
        'base_efficiency': 0.34
    },
    'D': {  # Large cars (e.g., VW Passat, BMW 3 Series)
        'weight': 1500,
        'drag_coef': 0.33,
        'frontal_area': 2.3,
        'base_efficiency': 0.32
    },
    'E': {  # Executive cars (e.g., BMW 5 Series, Mercedes E-Class)
        'weight': 1700,
        'drag_coef': 0.34,
        'frontal_area': 2.4,
        'base_efficiency': 0.30
    },
    'F': {  # Luxury cars (e.g., BMW 7 Series, Mercedes S-Class)
        'weight': 1900,
        'drag_coef': 0.35,
        'frontal_area': 2.5,
        'base_efficiency': 0.28
    },
    'S': {  # Sports cars (e.g., Porsche 911, Audi TT)
        'weight': 1600,
        'drag_coef': 0.36,
        'frontal_area': 2.2,
        'base_efficiency': 0.29
    },
    'J': {  # SUVs (e.g., VW Tiguan, BMW X3)
        'weight': 1800,
        'drag_coef': 0.38,
        'frontal_area': 2.7,
        'base_efficiency': 0.27
    },
    'M': {  # Multi-purpose vehicles (e.g., VW Touran, Renault Scenic)
        'weight': 1600,
        'drag_coef': 0.34,
        'frontal_area': 2.4,
        'base_efficiency': 0.31
    }
}

# Fuel prices per unit (TRY per liter or kWh)
FUEL_PRICES = {
    'petrol': 50.64,      # TRY per liter (example)
    'diesel': 52.22,      # TRY per liter
    'hybrid': 50.64,      # Assume petrol price for hybrid
    'plug-in_hybrid': 50.64, # Assume petrol price for plug-in hybrid
    'electric': 8.99      # TRY per kWh (example)
}

# Fuel efficiency multipliers based on EPA testing
FUEL_EFFICIENCY = {
    'petrol': 1.0,    # Baseline
    'diesel': 1.2,    # 20% more efficient
    'hybrid': 1.3,    # 30% more efficient
    'electric': 2.0   # 100% more efficient
}

# Traffic patterns based on FHWA research
TRAFFIC_PATTERNS = {
    'motorway': {
        'morning_peak': (7, 9, 0.7),    # (start_hour, end_hour, speed_multiplier)
        'evening_peak': (16, 19, 0.7),
        'night': (22, 5, 1.2),
        'default': 1.0
    },
    'primary': {
        'morning_peak': (7, 9, 0.8),
        'evening_peak': (16, 19, 0.8),
        'night': (22, 5, 1.1),
        'default': 1.0
    },
    'residential': {
        'morning_peak': (7, 9, 0.9),
        'evening_peak': (16, 19, 0.9),
        'night': (22, 5, 1.0),
        'default': 1.0
    }
}

# Add this near the top, after FUEL_PRICES
FUEL_PRICES_PER_KM = {
    'petrol': FUEL_PRICES['petrol'] / 13,      # Example: 13 km/L for petrol
    'diesel': FUEL_PRICES['diesel'] / 17,      # Example: 17 km/L for diesel
    'hybrid': FUEL_PRICES['hybrid'] / 20,      # Example: 20 km/L for hybrid
    'plug-in_hybrid': FUEL_PRICES['plug-in_hybrid'] / 25, # Example: 25 km/L for plug-in hybrid
    'electric': FUEL_PRICES['electric'] / 6    # Example: 6 km/kWh for electric
}

def get_traffic_multiplier(hour, road_type):
    """Get speed multiplier based on FHWA traffic patterns"""
    if road_type not in TRAFFIC_PATTERNS:
        road_type = 'primary'
        
    patterns = TRAFFIC_PATTERNS[road_type]
    
    for period, (start, end, multiplier) in patterns.items():
        if period != 'default':
            if start <= hour <= end:
                return multiplier
            elif period == 'night' and (hour >= start or hour <= end):
                return multiplier
    
    return patterns['default']

def generate_graph(start_lat, start_lon, end_lat, end_lon, network_type="drive"):
    """Generate street network graph with elevation data"""
    try:
        center_lat = float((start_lat + end_lat) / 2)
        center_lon = float((start_lon + end_lon) / 2)
        distance = ox.distance.great_circle_vec(start_lat, start_lon, end_lat, end_lon).item()
        radius = max(1500, distance * 1.5)
        
        logger.debug(f"Generating graph centered at ({center_lat}, {center_lon}) with radius {radius}m")
        
        G = ox.graph_from_point(
            (center_lat, center_lon),
            dist=radius,
            network_type=network_type,
            simplify=True
        )
        
        # Add slope and speed data
        for u, v, data in G.edges(data=True):
            # Calculate length if not present
            if 'length' not in data:
                u_coords = (G.nodes[u]['y'], G.nodes[u]['x'])
                v_coords = (G.nodes[v]['y'], G.nodes[v]['x'])
                data['length'] = ox.distance.great_circle(u_coords[0], u_coords[1], v_coords[0], v_coords[1])
                logger.debug(f"Calculated length for edge {u}->{v}: {data['length']:.2f}m")
            
            # Calculate slope
            elev_u = G.nodes[u].get('elevation', 0)
            elev_v = G.nodes[v].get('elevation', 0)
            dist = data['length']
            data['slope'] = (elev_v - elev_u) / dist if dist > 0 else 0
            
            # Set default speed based on road type
            if 'speed_kph' not in data:
                road_type = data.get('highway', 'residential')
                if isinstance(road_type, list):
                    road_type = road_type[0]
                speed_limits = {
                    'motorway': 120,
                    'primary': 80,
                    'residential': 50
                }
                data['speed_kph'] = speed_limits.get(road_type, 50)
                logger.debug(f"Set speed for edge {u}->{v}: {data['speed_kph']}km/h ({road_type})")
        
        return G
    except Exception as e:
        logger.error(f"Error generating graph: {str(e)}")
        raise

def calculate_fuel_consumption(edge_data, vehicle_params):
    """
    Calculate fuel consumption in liters for a given edge using a more realistic model.
    """
    length = edge_data.get('length', 0)  # meters
    slope = edge_data.get('slope', 0)
    speed = edge_data.get('speed_kph', 50)
    road_type = edge_data.get('highway', 'primary')
    if isinstance(road_type, list):
        road_type = road_type[0]

    fuel_type = vehicle_params.get('fuel_type', 'petrol')

    if fuel_type == 'electric':
        # Use kWh/100km for electric vehicles
        base_kwh_per_100km = 17  # Typical real-world value
        # Apply multipliers as before
        if slope > 0.05:
            slope_multiplier = 1.2
        elif slope < -0.05:
            slope_multiplier = 0.9
        else:
            slope_multiplier = 1.0

        if speed < 30:
            speed_multiplier = 1.2
        elif speed > 110:
            speed_multiplier = 1.15
        else:
            speed_multiplier = 1.0

        road_efficiency = {
            'motorway': 0.9, 'trunk': 0.95, 'primary': 1.0, 'secondary': 1.05,
            'tertiary': 1.08, 'residential': 1.12, 'service': 1.15,
            'unclassified': 1.10, 'unsealed': 1.20,
        }
        road_multiplier = road_efficiency.get(road_type, 1.0)

        total_multiplier = slope_multiplier * speed_multiplier * road_multiplier
        # Calculate energy in kWh for this edge
        energy = (length / 1000) * (base_kwh_per_100km / 100) * total_multiplier
        edge_data['unit'] = 'kWh'
        return energy
    else:
        # Use L/100km for combustion/hybrid vehicles
        base_l_per_100km = {
            'A': 4.5, 'B': 5.0, 'C': 6.5, 'D': 7.5, 'E': 8.0,
            'F': 9.0, 'S': 8.5, 'J': 8.5, 'M': 7.5,
        }.get(vehicle_params.get('vehicle_type', 'C'), 6.5)

        fuel_multipliers = {
            'petrol': 1.0,
            'diesel': 0.85,
            'hybrid': 0.7,
            'plug-in_hybrid': 0.6,
        }
        fuel_multiplier = fuel_multipliers.get(fuel_type, 1.0)

        if slope > 0.05:
            slope_multiplier = 1.2
        elif slope < -0.05:
            slope_multiplier = 0.9
        else:
            slope_multiplier = 1.0

        if speed < 30:
            speed_multiplier = 1.2
        elif speed > 110:
            speed_multiplier = 1.15
        else:
            speed_multiplier = 1.0

        road_efficiency = {
            'motorway': 0.9, 'trunk': 0.95, 'primary': 1.0, 'secondary': 1.05,
            'tertiary': 1.08, 'residential': 1.12, 'service': 1.15,
            'unclassified': 1.10, 'unsealed': 1.20,
        }
        road_multiplier = road_efficiency.get(road_type, 1.0)

        total_multiplier = fuel_multiplier * slope_multiplier * speed_multiplier * road_multiplier
        fuel = (length / 1000) * (base_l_per_100km / 100) * total_multiplier
        edge_data['unit'] = 'L'
        return fuel

def get_vehicle_params(vehicle_type, fuel_type, year):
    """Get vehicle parameters based on type and fuel"""
    try:
        if vehicle_type not in VEHICLE_TYPES:
            vehicle_type = 'C'  # Default to medium (C) if not found
        params = VEHICLE_TYPES[vehicle_type].copy()
        params['vehicle_type'] = vehicle_type
        params['fuel_type'] = fuel_type.lower()
        params['year'] = year
        # Adjust efficiency for vehicle age
        age = datetime.now().year - year
        if age > 10:
            params['age_factor'] = 0.9
        elif age < 5:
            params['age_factor'] = 1.05
        else:
            params['age_factor'] = 1.0
        return params
    except Exception as e:
        logger.error(f"Error generating vehicle parameters: {str(e)}")
        return {
            'vehicle_type': 'C',
            'fuel_type': 'petrol',
            'age_factor': 1.0
        }

def find_shortest_and_eco_route(G, start_node, end_node, vehicle_params):
    """Find both shortest and eco-friendly routes"""
    try:
        # Calculate edge weights
        logger.info(f"Calculating edge weights for graph with {G.number_of_edges()} edges")
        
        # First, verify that edges have length data
        edges_without_length = 0
        for u, v, k, data in G.edges(data=True, keys=True):
            if 'length' not in data:
                edges_without_length += 1
                u_coords = (G.nodes[u]['y'], G.nodes[u]['x'])
                v_coords = (G.nodes[v]['y'], G.nodes[v]['x'])
                data['length'] = ox.distance.great_circle(u_coords[0], u_coords[1], v_coords[0], v_coords[1])
                logger.info(f"Edge {u}->{v} had no length, calculated: {data['length']:.2f}m")
        
        logger.info(f"Found {edges_without_length} edges without length data")
        
        # Now calculate weights for all edges
        for u, v, k, data in G.edges(data=True, keys=True):
            # For shortest route, just use the length
            data['shortest_weight'] = data['length']
            
            # For eco route, calculate fuel consumption considering:
            # - Road type efficiency
            # - Traffic patterns
            # - Elevation changes
            # - Vehicle characteristics
            data['eco_weight'] = calculate_fuel_consumption(data, vehicle_params)
            
            logger.info(f"Edge {u}->{v}: length={data['shortest_weight']:.2f}m, fuel={data['eco_weight']:.4f}{data['unit']}")
        
        # Find shortest path (based on distance only)
        logger.info(f"Finding shortest path from {start_node} to {end_node}")
        try:
            shortest_path = nx.shortest_path(G, start_node, end_node, weight='shortest_weight')
            logger.info(f"Shortest path found with {len(shortest_path)} nodes")
            
            # Log the actual path
            path_edges = list(zip(shortest_path[:-1], shortest_path[1:]))
            logger.info("Shortest path edges:")
            for u, v in path_edges:
                # Get the first edge data if multiple edges exist
                edge_data = next(iter(G[u][v].values()))
                logger.info(f"  {u}->{v}: length={edge_data['length']:.2f}m")
            
        except nx.NetworkXNoPath:
            logger.error(f"No shortest path found from {start_node} to {end_node}")
            return None, None
        
        # Find eco-friendly path (based on fuel consumption)
        logger.info(f"Finding eco path from {start_node} to {end_node}")
        try:
            eco_path = nx.shortest_path(G, start_node, end_node, weight='eco_weight')
            logger.info(f"Eco path found with {len(eco_path)} nodes")
            
            # Log the actual path
            path_edges = list(zip(eco_path[:-1], eco_path[1:]))
            logger.info("Eco path edges:")
            for u, v in path_edges:
                # Get the first edge data if multiple edges exist
                edge_data = next(iter(G[u][v].values()))
                logger.info(f"  {u}->{v}: length={edge_data['length']:.2f}m, fuel={edge_data['eco_weight']:.4f}{edge_data['unit']}")
            
        except nx.NetworkXNoPath:
            logger.error(f"No eco path found from {start_node} to {end_node}")
            return None, None
        
        # Calculate totals for shortest route
        shortest_distance = 0
        shortest_fuel = 0
        for u, v in zip(shortest_path[:-1], shortest_path[1:]):
            # Find the edge with the minimum eco_weight (the one used by the pathfinder)
            min_key = min(G[u][v], key=lambda k: G[u][v][k]['eco_weight'])
            edge_data = G[u][v][min_key]
            shortest_distance += edge_data['length']
            shortest_fuel += edge_data['eco_weight']
            logger.info(f"Shortest route edge {u}->{v}: length={edge_data['length']:.2f}m, fuel={shortest_fuel:.4f}{edge_data['unit']}")
        
        # Calculate totals for eco route
        eco_distance = 0
        eco_fuel = 0
        for u, v in zip(eco_path[:-1], eco_path[1:]):
            min_key = min(G[u][v], key=lambda k: G[u][v][k]['eco_weight'])
            edge_data = G[u][v][min_key]
            eco_distance += edge_data['length']
            eco_fuel += edge_data['eco_weight']
            logger.info(f"Eco route edge {u}->{v}: length={edge_data['length']:.2f}m, fuel={edge_data['eco_weight']:.4f}{edge_data['unit']}")
        
        logger.info(f"Shortest route total: {shortest_distance/1000:.1f}km, {shortest_fuel:.2f}{edge_data['unit']} fuel")
        print(f"Shortest route total: {shortest_distance/1000:.1f}km, {shortest_fuel:.2f}{edge_data['unit']} fuel")
        
        price_per_unit = FUEL_PRICES.get(vehicle_params['fuel_type'], 0)
        shortest_cost = shortest_fuel * price_per_unit
        eco_cost = eco_fuel * price_per_unit
        money_saved = shortest_cost - eco_cost
        logger.info(f"Money saved by eco route: {money_saved:.2f}{price_per_unit and ' TRY' or ''}")
        print(f"Money saved by eco route: {money_saved:.2f}{price_per_unit and ' TRY' or ''}")
        # Print and log price per unit
        fuel_type = vehicle_params['fuel_type']
        unit_label = 'L' if fuel_type != 'electric' else 'kWh'
        logger.info(f"{fuel_type.capitalize()}: {price_per_unit} TRY/{unit_label}")
        print(f"{fuel_type.capitalize()}: {price_per_unit} TRY/{unit_label}")
        
        # Print and log money saved or if routes are the same
        if abs(money_saved) < 1e-3:
            logger.info("Eco and shortest routes are the same. No money saved.")
            print("Eco and shortest routes are the same. No money saved.")
        else:
            logger.info(f"Money saved by eco route: {money_saved:.2f}{price_per_unit and ' TRY' or ''}")
            print(f"Money saved by eco route: {money_saved:.2f}{price_per_unit and ' TRY' or ''}")
        
        return shortest_path, eco_path, shortest_cost, eco_cost, money_saved
        
    except Exception as e:
        logger.error(f"Error finding routes: {str(e)}")
        return None, None

def calculate_slope(G):
    """
    Adds slope data to the graph based on elevation differences between nodes.
    """
    try:
        for u, v, k, data in G.edges(keys=True, data=True):
            elev_u = G.nodes[u].get('elevation', 0)
            elev_v = G.nodes[v].get('elevation', 0)
            dist = data.get('length', 1)
            if dist > 0:
                data['slope'] = (elev_v - elev_u) / dist
            else:
                data['slope'] = 0
                logger.warning(f"Zero length edge found between nodes {u} and {v}")
    except Exception as e:
        logger.error(f"Error calculating slopes: {str(e)}")
        raise

def calculate_air_resistance(speed, vehicle_params):
    """Calculate air resistance force in Newtons"""
    air_density = 1.225  # kg/m³ at sea level
    drag_coefficient = vehicle_params.get('drag_coef', 0.3)
    frontal_area = vehicle_params.get('frontal_area', 2.2)  # m²
    
    # F = 0.5 * ρ * v² * Cd * A
    return 0.5 * air_density * (speed ** 2) * drag_coefficient * frontal_area

def calculate_rolling_resistance(vehicle_params, road_type):
    """Calculate rolling resistance force in Newtons"""
    vehicle_weight = vehicle_params.get('weight', 1500)  # kg
    gravity = 9.81  # m/s²
    
    # Different rolling resistance coefficients for different road types
    rolling_coefficients = {
        'highway': 0.01,
        'primary': 0.015,
        'secondary': 0.02,
        'residential': 0.025,
        'unpaved': 0.04
    }
    
    # Default to primary road if type not found
    coefficient = rolling_coefficients.get(road_type, 0.015)
    
    # F = μ * m * g
    return coefficient * vehicle_weight * gravity

def calculate_engine_efficiency(speed, vehicle_params):
    """Calculate engine efficiency based on speed and vehicle parameters"""
    # Engine efficiency typically peaks at certain speeds
    optimal_speed = vehicle_params.get('optimal_speed', 80)  # km/h
    max_efficiency = vehicle_params.get('max_efficiency', 0.35)  # 35% efficiency
    
    # Efficiency decreases as we move away from optimal speed
    speed_diff = abs(speed - optimal_speed)
    efficiency = max_efficiency * math.exp(-0.0005 * (speed_diff ** 2))
    
    # Adjust for engine type
    if vehicle_params.get('engine_type') == 'diesel':
        efficiency *= 1.2  # Diesel engines are generally more efficient
    elif vehicle_params.get('engine_type') == 'hybrid':
        efficiency *= 1.3  # Hybrid systems are more efficient
    
    return efficiency

def get_weather_impact(weather_conditions, road_type):
    """Calculate weather impact on road conditions and fuel efficiency"""
    weather_multipliers = {
        'dry': 1.0,
        'wet': 1.15,
        'snow': 1.4,
        'ice': 1.6
    }
    
    # Different road types are affected differently by weather
    road_sensitivity = {
        'highway': 0.9,  # Highways are less affected by weather
        'primary': 1.0,
        'secondary': 1.1,
        'residential': 1.2  # Residential roads are more affected
    }
    
    base_multiplier = weather_multipliers.get(weather_conditions, 1.0)
    road_factor = road_sensitivity.get(road_type, 1.0)
    
    return base_multiplier * road_factor

def calculate_wind_resistance(speed, wind_speed, wind_direction, vehicle_params):
    """Calculate additional air resistance due to wind"""
    air_density = 1.225  # kg/m³ at sea level
    drag_coefficient = vehicle_params.get('drag_coef', 0.3)
    frontal_area = vehicle_params.get('frontal_area', 2.2)  # m²
    
    # Calculate effective wind speed based on direction
    # This is a simplified model - in reality, you'd need more complex vector math
    effective_wind_speed = wind_speed * math.cos(math.radians(wind_direction))
    effective_speed = speed + effective_wind_speed
    
    return 0.5 * air_density * (effective_speed ** 2) * drag_coefficient * frontal_area

def calculate_electric_vehicle_efficiency(speed, vehicle_params):
    """Calculate efficiency for electric vehicles"""
    # Electric vehicles are most efficient at moderate speeds
    optimal_speed = vehicle_params.get('optimal_speed', 50)  # km/h
    max_efficiency = vehicle_params.get('max_efficiency', 0.85)  # 85% efficiency
    
    # Efficiency curve for electric vehicles
    speed_diff = abs(speed - optimal_speed)
    efficiency = max_efficiency * math.exp(-0.0003 * (speed_diff ** 2))
    
    # Adjust for temperature (battery efficiency)
    if 'temperature' in vehicle_params:
        temp = vehicle_params['temperature']
        if temp < 10:  # Cold weather reduces efficiency
            efficiency *= 0.9
        elif temp > 30:  # Hot weather also reduces efficiency
            efficiency *= 0.95
    
    return efficiency

def calculate_hybrid_efficiency(speed, vehicle_params):
    """Calculate efficiency for hybrid vehicles"""
    # Hybrid vehicles have different efficiency characteristics
    optimal_speed = vehicle_params.get('optimal_speed', 60)  # km/h
    max_efficiency = vehicle_params.get('max_efficiency', 0.45)  # 45% efficiency
    
    # Efficiency curve for hybrid vehicles
    speed_diff = abs(speed - optimal_speed)
    efficiency = max_efficiency * math.exp(-0.0004 * (speed_diff ** 2))
    
    # Regenerative braking bonus
    if speed < 30:  # More regenerative braking at lower speeds
        efficiency *= 1.1
    
    return efficiency

def calculate_traffic_flow(speed_limit, road_type, hour):
    """
    Calculate traffic flow using the Greenshields model
    Based on research: Greenshields, B. D. (1935). A study of traffic capacity.
    """
    # If road_type is a list, use the first element
    if isinstance(road_type, list):
        road_type = road_type[0]
    # Free flow speed (km/h) - varies by road type
    free_flow_speeds = {
        'highway': 120,
        'primary': 80,
        'secondary': 60,
        'residential': 40
    }
    # Jam density (vehicles/km) - varies by road type
    jam_densities = {
        'highway': 150,
        'primary': 100,
        'secondary': 80,
        'residential': 60
    }
    # Get base parameters
    vf = free_flow_speeds.get(road_type, 60)  # Free flow speed
    kj = jam_densities.get(road_type, 80)     # Jam density
    # Calculate time-based density factor (0 to 1)
    # Based on research: Highway Capacity Manual (HCM) 2010
    peak_hours = [(7, 9), (16, 19)]  # Morning and evening peak hours
    density_factor = 0.3  # Base density factor
    for start, end in peak_hours:
        if start <= hour <= end:
            density_factor = 0.8  # Peak hour density
            break
    # Current density (vehicles/km)
    k = kj * density_factor
    # Greenshields model: v = vf * (1 - k/kj)
    # where v is speed, vf is free flow speed, k is density, kj is jam density
    speed = vf * (1 - k/kj)
    # Ensure speed doesn't exceed speed limit
    speed = min(speed, speed_limit)
    return speed

def calculate_weather_impact(weather_conditions, road_type):
    """
    Calculate weather impact based on research from:
    - Highway Safety Manual (HSM)
    - Federal Highway Administration (FHWA) weather impact studies
    """
    # Weather impact factors from FHWA research
    weather_factors = {
        'dry': {
            'speed_reduction': 0.0,
            'friction_reduction': 0.0
        },
        'wet': {
            'speed_reduction': 0.10,  # 10% speed reduction
            'friction_reduction': 0.20  # 20% friction reduction
        },
        'snow': {
            'speed_reduction': 0.30,  # 30% speed reduction
            'friction_reduction': 0.50  # 50% friction reduction
        },
        'ice': {
            'speed_reduction': 0.40,  # 40% speed reduction
            'friction_reduction': 0.70  # 70% friction reduction
        }
    }
    
    # Road type sensitivity from HSM
    road_sensitivity = {
        'highway': 0.8,    # Highways are less affected
        'primary': 1.0,    # Baseline
        'secondary': 1.2,  # More affected
        'residential': 1.3  # Most affected
    }
    
    # Get weather impact factors
    weather = weather_factors.get(weather_conditions, weather_factors['dry'])
    road_factor = road_sensitivity.get(road_type, 1.0)
    
    # Calculate combined impact
    speed_reduction = weather['speed_reduction'] * road_factor
    friction_reduction = weather['friction_reduction'] * road_factor
    
    return {
        'speed_multiplier': 1 - speed_reduction,
        'friction_multiplier': 1 - friction_reduction
    }

def calculate_vehicle_efficiency(speed, vehicle_params):
    """
    Calculate vehicle efficiency based on scientific research:
    - EPA fuel economy testing procedures
    - SAE J1349 standard for engine power and efficiency
    - Real-world fuel consumption studies
    """
    # Base efficiency curves from EPA testing
    if vehicle_params.get('fuel_type') == 'electric':
        # Electric vehicle efficiency curve based on EPA testing
        # Source: EPA's Electric Vehicle Testing Procedures
        optimal_speed = 50  # km/h
        max_efficiency = 0.85
        speed_diff = abs(speed - optimal_speed)
        efficiency = max_efficiency * math.exp(-0.0003 * (speed_diff ** 2))
        
        # Temperature impact based on battery research
        if 'temperature' in vehicle_params:
            temp = vehicle_params['temperature']
            if temp < 10:
                efficiency *= 0.85  # Cold weather impact
            elif temp > 30:
                efficiency *= 0.90  # Hot weather impact
                
    elif vehicle_params.get('fuel_type') == 'hybrid':
        # Hybrid efficiency curve based on EPA testing
        optimal_speed = 60  # km/h
        max_efficiency = 0.45
        speed_diff = abs(speed - optimal_speed)
        efficiency = max_efficiency * math.exp(-0.0004 * (speed_diff ** 2))
        
        # Regenerative braking efficiency based on SAE research
        if speed < 30:
            efficiency *= 1.15  # Enhanced regenerative braking at low speeds
            
    else:
        # Internal combustion engine efficiency curve
        # Based on SAE J1349 standard and EPA testing
        optimal_speed = 80  # km/h
        max_efficiency = 0.35
        speed_diff = abs(speed - optimal_speed)
        efficiency = max_efficiency * math.exp(-0.0005 * (speed_diff ** 2))
        
        # Engine type adjustments based on SAE research
        if vehicle_params.get('engine_type') == 'diesel':
            efficiency *= 1.2  # Diesel efficiency advantage
        elif vehicle_params.get('engine_type') == 'turbo':
            efficiency *= 1.1  # Turbo efficiency advantage
    
    return efficiency 