import pandas as pd
import time
import random
import requests
import os

# You need to install these libraries:
# pip install ddgs pandas requests

try:
    from ddgs import DDGS
except ImportError:
    print("Error: The 'ddgs' library is missing.")
    print("Please run: pip install ddgs pandas requests")
    exit()

def fetch_restaurants_from_osm(city_name):
    """
    Fetches a list of restaurants for a given city using OpenStreetMap (Overpass API).
    """
    print(f"\nSearching OpenStreetMap for restaurants in '{city_name}'...")
    print("This may take a few seconds depending on the city size...")

    # Overpass QL query to find nodes/ways tagged as 'restaurant' in the search area
    overpass_url = "http://overpass-api.de/api/interpreter"
    overpass_query = f"""
    [out:json][timeout:60];
    area["name"="{city_name}"]->.searchArea;
    (
      node["amenity"="restaurant"](area.searchArea);
      way["amenity"="restaurant"](area.searchArea);
    );
    out center;
    """
    
    try:
        response = requests.get(overpass_url, params={'data': overpass_query})
        response.raise_for_status() # Check for HTTP errors
        data = response.json()
        
        restaurants = []
        for element in data.get('elements', []):
            # Try to get the name tag
            name = element.get('tags', {}).get('name')
            if name:
                restaurants.append(name)
        
        # Remove duplicates
        restaurants = list(set(restaurants))
        print(f"  Found {len(restaurants)} restaurants in {city_name}!")
        return restaurants

    except Exception as e:
        print(f"Error fetching data from OpenStreetMap: {e}")
        return []

def check_for_mobile_app(restaurant_name):
    """
    Searches DuckDuckGo for the restaurant name + 'mobile app'.
    Returns True if an App Store or Play Store link is found in the top results.
    """
    query = f"{restaurant_name} mobile app android ios"
    print(f"Checking: {restaurant_name}...")
    
    found_app = False
    
    try:
        # Use DuckDuckGo Search (DDGS)
        # 'max_results' limits the number of links we fetch
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=5)
            
            # DuckDuckGo returns a list of dictionaries: [{'href': 'url', 'title': '...'}, ...]
            if results:
                for r in results:
                    url = r.get('href', '')
                    
                    # Check for key domains indicating an app exists
                    if "play.google.com" in url or "apps.apple.com" in url:
                        found_app = True
                        break
                
    except Exception as e:
        print(f"  Error searching for {restaurant_name}: {e}")
        return None # Return None to indicate an error occurred

    return found_app

def main():
    input_file = 'restaurant.csv'
    output_file = 'restaurants_audit_results.csv'
    df = None

    # --- Step 1: Get Data (CSV or Auto-Generate) ---
    if os.path.exists(input_file):
        print(f"Found {input_file}. Loading data...")
        df = pd.read_csv(input_file)
        
        # Detect name column
        name_col = None
        possible_names = ['Name', 'Restaurant', 'Restaurant Name', 'Business Name']
        for col in df.columns:
            if col in possible_names:
                name_col = col
                break
        if not name_col:
            name_col = df.columns[0]
            print(f"Warning: Using first column '{name_col}' as Name.")
            
    else:
        print(f"'{input_file}' not found.")
        city = input("Enter a city name to find restaurants automatically (e.g., London, New York): ").strip()
        
        if not city:
            print("No city entered. Exiting.")
            return

        restaurant_list = fetch_restaurants_from_osm(city)
        
        if not restaurant_list:
            print("No restaurants found. Try a different city name (check spelling).")
            return
            
        # Create DataFrame from list
        df = pd.DataFrame(restaurant_list, columns=['Restaurant Name'])
        name_col = 'Restaurant Name'
        
        # Save this generated list so the user has it
        df.to_csv('generated_restaurants.csv', index=False)
        print("Saved generated list to 'generated_restaurants.csv'.")

    # --- Step 2: Iterate and Check ---
    # Limit for safety if the list is huge
    if len(df) > 50:
        print(f"\nNote: The list has {len(df)} restaurants.")
        confirm = input("Scanning all of them might take a while. Continue? (y/n): ")
        if confirm.lower() != 'y':
            return

    df['Has_App'] = "Unknown"
    
    print("-" * 40)
    print("Starting App Scan... (Press Ctrl+C to stop early)")
    print("-" * 40)

    try:
        for index, row in df.iterrows():
            name = row[name_col]
            has_app = check_for_mobile_app(name)
            
            if has_app:
                print(f"  [YES] App found for {name}")
                df.at[index, 'Has_App'] = "Yes"
            else:
                print(f"  [NO] No app found for {name}")
                df.at[index, 'Has_App'] = "No"
            
            # Sleep to be polite to the search engine
            time.sleep(random.uniform(2, 4))
            
    except KeyboardInterrupt:
        print("\nStopping scan early... Saving progress.")

    # --- Step 3: Save Results ---
    # Filter for restaurants WITHOUT apps
    no_app_df = df[df['Has_App'] == "No"]
    
    df.to_csv(output_file, index=False)
    no_app_df.to_csv("restaurants_without_apps.csv", index=False)
    
    print("-" * 40)
    print("Done!")
    print(f"Full report saved to: {output_file}")
    print(f"List of restaurants MISSING apps saved to: restaurants_without_apps.csv")
    print(f"Found {len(no_app_df)} restaurants without apps.")

if __name__ == "__main__":
    main()