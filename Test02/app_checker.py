import pandas as pd
import time
import random
from playwright.sync_api import sync_playwright
from thefuzz import fuzz # pip install thefuzz

# ================= CONFIGURATION =================
# We use the file we just created in the previous step (with locations)
INPUT_FILE = "Restaurant_in_rawalpindi_results_with_location.csv" 
OUTPUT_FILE = "Final_App_Analysis.csv"
MATCH_THRESHOLD = 80 
# =================================================

def check_apps_clean_output():
    # 1. Load Data
    try:w
        df = pd.read_csv(INPUT_FILE)
        print(f"📂 Loaded {len(df)} restaurants from {INPUT_FILE}")
    except FileNotFoundError:
        print(f"❌ Error: Could not find {INPUT_FILE}. Make sure you ran the Maps Scraper first.")
        return

    # Initialize new columns
    df['Has_App'] = False
    df['App_Name_Found'] = "N/A"
    df['Potential_Match_Score'] = 0
    # Note: 'Link' (Location Link) is already in the dataframe from the input file

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        print("🚀 Starting Play Store Analysis...")

        for index, row in df.iterrows():
            restaurant_name = str(row['Name'])
            if restaurant_name == "Unknown": continue

            print(f"[{index+1}/{len(df)}] Checking: {restaurant_name}...")

            encoded_name = restaurant_name.replace(" ", "%20")
            search_url = f"https://play.google.com/store/search?q={encoded_name}&c=apps"
            
            try:
                page.goto(search_url, timeout=10000)
                
                # Check top 3 results
                app_links = page.locator('a[href^="/store/apps/details"]').all()
                
                best_score = 0
                best_app_name = "N/A"

                for link in app_links[:3]: 
                    try:
                        app_title = link.inner_text().split('\n')[0]
                        if not app_title.strip(): continue

                        score = fuzz.partial_ratio(restaurant_name.lower(), app_title.lower())

                        if score > best_score:
                            best_score = score
                            best_app_name = app_title
                    except:
                        continue
                
                # Store Data
                if best_score >= MATCH_THRESHOLD:
                    df.at[index, 'Has_App'] = True
                    df.at[index, 'App_Name_Found'] = best_app_name
                    df.at[index, 'Potential_Match_Score'] = best_score
                    print(f"   ✅ MATCH! '{best_app_name}' ({best_score}%)")
                else:
                    df.at[index, 'Potential_Match_Score'] = best_score
                    print(f"   ❌ No App. Best partial: '{best_app_name}' ({best_score}%)")

            except Exception as e:
                print(f"   ⚠️ Error: {e}")

            time.sleep(random.uniform(0.5, 1.5))

        browser.close()

    # 2. SORTING (Highest Match First)
    print("\n🔄 Sorting data...")
    df.sort_values(by='Potential_Match_Score', ascending=False, inplace=True)

    # 3. CLEANING COLUMNS (Strictly what you asked for)
    # We select ONLY the requested columns.
    # 'Name' is included so you know which restaurant the row refers to.
    final_columns = ['Name', 'Potential_Match_Score', 'Has_App', 'App_Name_Found', 'Link']
    
    # Ensure 'Link' exists (it comes from the input csv)
    if 'Link' not in df.columns:
        print("⚠️ Warning: 'Link' column missing from input. Output may lack location links.")
        # Create empty link column if missing to prevent crash
        df['Link'] = "N/A"

    final_df = df[final_columns]
    
    # Rename columns for professional look
    final_df.columns = ['Restaurant Name', 'Match Score', 'Has App?', 'App Name Found', 'Location Link']

    # 4. Save Final File
    final_df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')

    print("\n" + "="*40)
    print(f"🎉 DONE! Saved to: {OUTPUT_FILE}")
    print("Columns included:")
    print("1. Restaurant Name")
    print("2. Match Score (Sorted High to Low)")
    print("3. Has App?")
    print("4. App Name Found")
    print("5. Location Link")
    print("="*40)

if __name__ == "__main__":
    check_apps_clean_output()