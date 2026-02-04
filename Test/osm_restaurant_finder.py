import requests
import json
import time

def find_restaurants_osm(city_name):
    """
    Finds restaurants in a specific city using OpenStreetMap's Nominatim API.
    No API Key required.
    """
    base_url = "https://nominatim.openstreetmap.org/search"
    
    # Search query
    query = f"restaurants in {city_name}"
    
    # --- FIX FOR 403 ERROR ---
    # Nominatim requires a valid User-Agent and often checks for a real email.
    # If you get a 403 error, you MUST change 'your_real_email@gmail.com' to your actual email.
    headers = {
        'User-Agent': 'RawalpindiFoodExplorer/1.0 (huziafa.malik45@gmail.com)', 
        'Referer': 'https://www.openstreetmap.org/'
    }
    
    params = {
        'q': query,
        'format': 'json',
        'addressdetails': 1,
        'limit': 20, # Number of results
        'featuretype': 'amenity' # Tries to focus on amenities
    }

    try:
        print(f"Searching for restaurants in {city_name} via OpenStreetMap...")
        response = requests.get(base_url, params=params, headers=headers)
        response.raise_for_status() # Check for errors
        
        results = response.json()
        
        if not results:
            print("No results found. Try a different city name.")
            return

        print(f"\n--- Found {len(results)} Locations ---")
        
        for idx, place in enumerate(results, 1):
            name = place.get('name', 'Unknown Name')
            # OSM addresses can be complex, usually 'display_name' has the full string
            address = place.get('display_name', 'No address available')
            lat = place.get('lat')
            lon = place.get('lon')
            
            # Only print if it actually has a name (sometimes OSM returns unnamed points)
            if name: 
                print(f"{idx}. {name}")
                print(f"   Address: {address}")
                print(f"   Coordinates: {lat}, {lon}")
                print("-" * 30)
                
            # Be nice to the free API server
            time.sleep(1) # Increased delay to be more polite to the API

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        if "403" in str(e):
             print("\n!!! 403 FORBIDDEN ERROR DETECTED !!!")
             print("OpenStreetMap blocked the request. Please open the script and change")
             print("'your_real_email@gmail.com' in the headers to your actual email address.")

if __name__ == "__main__":
    # You can change this to 'Lahore', 'Islamabad', 'Karachi', etc.
    city = "Rawalpindi"
    find_restaurants_osm(city)