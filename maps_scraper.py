
import re
import pandas as pd
from playwright.sync_api import sync_playwright

def extract_coordinates(url):
    """
    ALGORITHM: Extracts GPS coordinates from Google Maps URLs.
    It looks for the pattern !3d(LAT)!4d(LONG) which is standard in Google's data blobs.
    """
    if not url:
        return "N/A", "N/A"
        
    try:
        # Priority 1: Look for the precise data entity (!3d and !4d)
        # Example: ...!8m2!3d33.6424886!4d73.0722253...
        lat_match = re.search(r'!3d([-0-9.]+)', url)
        long_match = re.search(r'!4d([-0-9.]+)', url)
        
        if lat_match and long_match:
            return lat_match.group(1), long_match.group(1)
        
        # Priority 2: Look for @lat,long (Less precise, usually map center, but fallback)
        at_match = re.search(r'@([-0-9.]+),([-0-9.]+)', url)
        if at_match:
            return at_match.group(1), at_match.group(2)
            
        return "N/A", "N/A"
    except:
        return "N/A", "N/A"

def scrape_google_maps(search_query):
    with sync_playwright() as p:
        # 1. Launch Browser
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # 2. Navigate
        print(f"📍 Searching for: {search_query}")
        url = f"https://www.google.com/maps/search/{search_query}/"
        page.goto(url)

        # 3. Handle Consent
        try:
            page.locator("form[action*='consent'] button").first.click(timeout=3000)
        except:
            pass

        # 4. Wait for Feed
        print("🔍 Waiting for results panel...")
        try:
            page.wait_for_selector('div[role="feed"]', timeout=15000)
            feed_selector = 'div[role="feed"]'
        except:
            feed_selector = 'div[aria-label^="Results"]'
            page.wait_for_selector(feed_selector, timeout=10000)

        # 5. Scroll Loop (The "Infinite Scroll" Logic)
        print("🔄 Scrolling to load all restaurants...")
        last_height = page.evaluate('(sel) => document.querySelector(sel).scrollHeight', feed_selector)

        while True:
            page.evaluate('(sel) => document.querySelector(sel).scrollTo(0, document.querySelector(sel).scrollHeight)', feed_selector)
            page.wait_for_timeout(2000)
            new_height = page.evaluate('(sel) => document.querySelector(sel).scrollHeight', feed_selector)
            
            if new_height == last_height:
                page.wait_for_timeout(2000)
                new_height = page.evaluate('(sel) => document.querySelector(sel).scrollHeight', feed_selector)
                if new_height == last_height:
                    break
            last_height = new_height

        # 6. Extraction
        listings = page.locator('div[role="article"]').all()
        print(f"📊 Found {len(listings)} restaurants. Extracting Location Data...")

        results = []
        
        for card in listings:
            data = {}
            
            # --- Name ---
            try:
                if card.get_attribute('aria-label'):
                    data['Name'] = card.get_attribute('aria-label')
                else:
                    data['Name'] = card.locator('.fontHeadlineSmall').first.inner_text()
            except:
                data['Name'] = "Unknown"
            
            # --- Rating ---
            try:
                aria_string = card.locator('span[role="img"]').first.get_attribute('aria-label')
                if aria_string and "stars" in aria_string:
                    parts = aria_string.split(" ")
                    data['Rating'] = parts[0]
                    data['Reviews'] = parts[2] if len(parts) > 2 else "0"
                else:
                    data['Rating'] = "N/A"
                    data['Reviews'] = "0"
            except:
                data['Rating'] = "N/A"
                data['Reviews'] = "0"

            # --- Link & COORDINATES (The New Algo) ---
            try:
                link = card.locator('a').first.get_attribute('href')
                data['Link'] = link
                
                # Apply the Location Algo
                lat, long = extract_coordinates(link)
                data['Latitude'] = lat
                data['Longitude'] = long
            except:
                data['Link'] = ""
                data['Latitude'] = "N/A"
                data['Longitude'] = "N/A"

            # --- Address Text ---
            try:
                text_content = card.inner_text()
                lines = text_content.split('\n')
                clean_lines = [line for line in lines if line and line != data['Name'] and "Reviews" not in line]
                data['Address_Snippet'] = clean_lines[0] if clean_lines else "N/A"
            except:
                data['Address_Snippet'] = "N/A"

            if data['Name'] != "Unknown":
                results.append(data)

        # 7. Save to CSV
        if results:
            df = pd.DataFrame(results)
            # Reorder columns to put Location next to Address
            cols = ['Name', 'Rating', 'Reviews', 'Address_Snippet', 'Latitude', 'Longitude', 'Link']
            # Only select cols that actually exist in the dataframe
            actual_cols = [c for c in cols if c in df.columns]
            df = df[actual_cols]
            
            clean_query = search_query.replace('+', '_').replace('%20', '_')
            filename = f"{clean_query}_results_with_location.csv"
            df.to_csv(filename, index=False, encoding='utf-8-sig')
            print(f"💾 Success! Saved {len(results)} rows with Locations to {filename}")
        else:
            print("⚠️ No data found.")

        browser.close()

if __name__ == "__main__":
    scrape_google_maps("Restaurant+in+rawalpindi")