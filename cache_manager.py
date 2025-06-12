import os
import json
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class CacheManager:
    def __init__(self, cache_dir="cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
    def _get_cache_key(self, data):
        """Generate a unique cache key for the given data."""
        # Convert data to a string representation and hash it
        data_str = json.dumps(data, sort_keys=True)
        return hashlib.sha1(data_str.encode()).hexdigest()
    
    def get_cached_data(self, data_type, data):
        """Try to get data from cache."""
        cache_key = self._get_cache_key(data)
        cache_file = self.cache_dir / f"{data_type}_{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                logger.info(f"Retrieved {data_type} data from cache")
                return cached_data
            except Exception as e:
                logger.warning(f"Error reading cache file: {str(e)}")
        return None
    
    def save_to_cache(self, data_type, data, result):
        """Save data to cache."""
        cache_key = self._get_cache_key(data)
        cache_file = self.cache_dir / f"{data_type}_{cache_key}.json"
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(result, f)
            logger.info(f"Saved {data_type} data to cache")
        except Exception as e:
            logger.warning(f"Error saving to cache: {str(e)}") 