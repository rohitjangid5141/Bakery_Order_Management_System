import csv
import time
import random
import re
from urllib.parse import quote
from playwright.sync_api import sync_playwright, TimeoutError

def build_search_url(query):
    """
    Build the JustDial search URL from user query.
    Format: https://www.justdial.com/{City}/{Category}
    """
    # Split the query and assume first part is category, last part is city
    parts = query.strip().split()
    if 'in' in parts:
        in_index = parts.index('in')
        category = ' '.join(parts[:in_index])
        city = ' '.join(parts[in_index+1:])
    else:
        # If no 'in', treat whole query as category in Mumbai (default)
        category = query
        city = 'Mumbai'
    
    # Replace spaces with hyphens and format URL
    category_formatted = category.replace(' ', '-')
    city_formatted = city.replace(' ', '-')
    
    return f"https://www.justdial.com/{city_formatted}/{category_formatted}"

def handle_popups(page):
    """
    Handle common popups, cookie banners, and overlays.
    """
    # Wait a bit for popups to load
    time.sleep(2)
    
    # Try to close common close buttons
    popup_selectors = [
        'button[title="Close"]',
        'div[aria-label="Close"]',
        'span[aria-label="Close"]',
        '.close',
        '.popup_close',
        '.modal_close',
        '.overlay_close',
        'button[aria-label="Close"]',
        'i[class*="close"]',
        'span[class*="close"]'
    ]
    
    for selector in popup_selectors:
        try:
            close_button = page.locator(selector)
            if close_button.count() > 0:
                close_button.first.click(timeout=3000)
                print(f"Closed popup with selector: {selector}")
                time.sleep(1)
        except:
            pass  # Continue to next selector if this one fails

def extract_phone_numbers(page):
    """
    Extract phone numbers by clicking 'Show Number' buttons.
    """
    phone_numbers = []
    
    # Look for "Show Number" buttons - common patterns
    show_number_selectors = [
        'text="Show Number"',
        'text="View Number"',
        'text="Click to view"',
        '.mobilesv',
        '.showmob',
        '[title="Show Number"]',
        '[data-title="Show Number"]',
        '.tel_mob',
        '.phone_show_btn'
    ]
    
    for selector in show_number_selectors:
        try:
            show_buttons = page.locator(selector)
            count = show_buttons.count()
            
            for i in range(count):
                try:
                    btn = show_buttons.nth(i)
                    if btn.is_visible() and btn.is_enabled():
                        btn.click()
                        # Wait for number to appear
                        page.wait_for_load_state("networkidle", timeout=5000)
                        
                        # Look for revealed phone numbers
                        phone_selectors = [
                            '.tel',
                            '.mobileshown',
                            '[class*="tel"]',
                            '[class*="phone"]',
                            'span:has-text(/[0-9]{5}/)',  # Numbers with at least 5 digits
                            '.jtabsbphn'
                        ]
                        
                        for phone_sel in phone_selectors:
                            phone_elements = page.locator(phone_sel)
                            for j in range(phone_elements.count()):
                                try:
                                    phone_elem = phone_elements.nth(j)
                                    if phone_elem.is_visible():
                                        phone_text = phone_elem.text_content().strip()
                                        # Extract phone numbers using regex
                                        phone_matches = re.findall(r'\b\d{5,}\b', phone_text)
                                        for match in phone_matches:
                                            if match not in phone_numbers:
                                                phone_numbers.append(match)
                                except:
                                    continue
                        
                        # Add delay between clicks
                        time.sleep(random.uniform(2, 6))
                        
                except:
                    continue  # Continue to next button if current one fails
        except:
            continue  # Continue to next selector if this one fails
    
    return ', '.join(phone_numbers) if phone_numbers else 'N/A'

def scrape_justdial(search_query, max_pages=10):
    """
    Main function to scrape JustDial for business listings.
    """
    results = []
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Set user agent to avoid detection
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        
        # Build and navigate to search URL
        search_url = build_search_url(search_query)
        print(f"Navigating to: {search_url}")
        page.goto(search_url, wait_until="networkidle")
        
        # Handle initial popups
        handle_popups(page)
        
        # Check for CAPTCHA
        page_content = page.text_content()
        if "captcha" in page_content.lower():
            print("CAPTCHA detected! Stopping execution.")
            browser.close()
            return results
        
        current_page = 1
        
        while current_page <= max_pages:
            print(f"Scraping page {current_page}...")
            
            # Check for CAPTCHA on each page
            page_content = page.text_content()
            if "captcha" in page_content.lower():
                print("CAPTCHA detected! Stopping execution.")
                break
            
            # Handle infinite scroll by scrolling multiple times
            last_height = page.evaluate("document.body.scrollHeight")
            scroll_count = 0
            max_scrolls = 3  # Limit scrolls per page
            
            while scroll_count < max_scrolls:
                # Scroll to bottom
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait for new content to load
                time.sleep(3)
                
                # Check new height
                new_height = page.evaluate("document.body.scrollHeight")
                
                if new_height == last_height:
                    break  # No more content loading
                    
                last_height = new_height
                scroll_count += 1
            
            # Find business listings - common selectors
            listing_selectors = [
                '.store-details',
                '.result',
                '.cntanr',
                '[class*="result"]',
                '[class*="listing"]',
                '.jpb'
            ]
            
            current_listings = None
            for selector in listing_selectors:
                elements = page.locator(selector)
                if elements.count() > 0:
                    current_listings = elements
                    break
            
            if current_listings:
                count = current_listings.count()
                print(f"Found {count} listings on page {current_page}")
                
                for i in range(count):
                    try:
                        listing = current_listings.nth(i)
                        
                        # Extract business name
                        name_selectors = [
                            'h2',
                            '.lng_cont_name',
                            '.shop_details .jcn',
                            '[class*="name"]',
                            '.jrn'
                        ]
                        
                        name = 'N/A'
                        for name_sel in name_selectors:
                            try:
                                name_elem = listing.locator(name_sel).first
                                if name_elem.count() > 0:
                                    name = name_elem.text_content().strip()
                                    if name:
                                        break
                            except:
                                continue
                        
                        # Extract location/address
                        location_selectors = [
                            '.cont_fl_addr',
                            '.jadd',
                            '[class*="addr"]',
                            '.ml_5',
                            '.address'
                        ]
                        
                        location = 'N/A'
                        for loc_sel in location_selectors:
                            try:
                                loc_elem = listing.locator(loc_sel).first
                                if loc_elem.count() > 0:
                                    location = loc_elem.text_content().strip()
                                    if location:
                                        break
                            except:
                                continue
                        
                        # Extract phone numbers
                        # Temporarily focus on this listing to extract its phone
                        phone = extract_phone_numbers(listing.page)
                        
                        # If the above doesn't work, try within the listing context
                        if phone == 'N/A':
                            # Create a new context for phone extraction within this listing
                            phone = extract_phone_numbers_from_element(page, listing)
                        
                        business_data = {
                            'name': name,
                            'location': location,
                            'phone': phone
                        }
                        
                        results.append(business_data)
                        print(f"Scraped: {name[:30]}..." if len(name) > 30 else f"Scraped: {name}")
                        
                    except Exception as e:
                        print(f"Error scraping listing {i+1}: {str(e)}")
                        continue
            
            # Check for next page
            next_selectors = [
                'text="Next"',
                '.next_btn',
                'a[title="Next"]',
                'a:has-text("Next")',
                '.jd_fl_r'
            ]
            
            next_button_found = False
            for next_sel in next_selectors:
                try:
                    next_btn = page.locator(next_sel).first
                    if next_btn.count() > 0 and next_btn.is_visible() and next_btn.is_enabled():
                        # Check if it's actually a next page link
                        href = next_btn.get_attribute('href')
                        if href and ('page' in href.lower() or str(current_page + 1) in href):
                            print("Moving to next page...")
                            next_btn.click()
                            page.wait_for_load_state("networkidle")
                            handle_popups(page)
                            current_page += 1
                            next_button_found = True
                            break
                except:
                    continue
            
            if not next_button_found:
                print("No more pages to scrape.")
                break
            
            # Add delay between pages
            time.sleep(random.uniform(3, 7))
        
        browser.close()
    
    return results

def extract_phone_numbers_from_element(page, listing_element):
    """
    Extract phone numbers from within a specific listing element.
    """
    phone_numbers = []
    
    # Try to click any show number buttons within this element
    show_buttons = listing_element.locator('text="Show Number"').or_(listing_element.locator('.mobilesv'))
    
    for i in range(show_buttons.count()):
        try:
            btn = show_buttons.nth(i)
            if btn.is_visible() and btn.is_enabled():
                btn.click(timeout=3000)
                time.sleep(2)
                
                # Look for phone numbers in the listing after clicking
                phone_selectors = [
                    '.tel',
                    '.mobileshown',
                    '[class*="tel"]',
                    '[class*="phone"]',
                    'span:has-text(/[0-9]{5}/)'
                ]
                
                for phone_sel in phone_selectors:
                    phone_elements = listing_element.locator(phone_sel)
                    for j in range(phone_elements.count()):
                        try:
                            phone_elem = phone_elements.nth(j)
                            if phone_elem.is_visible():
                                phone_text = phone_elem.text_content().strip()
                                phone_matches = re.findall(r'\b\d{5,}\b', phone_text)
                                for match in phone_matches:
                                    if match not in phone_numbers:
                                        phone_numbers.append(match)
                        except:
                            continue
        except:
            continue
    
    return ', '.join(phone_numbers) if phone_numbers else 'N/A'

def save_to_csv(data, filename='justdial_scraped_data.csv'):
    """
    Save scraped data to CSV file.
    """
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Name', 'Location', 'Phone Numbers']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for item in data:
            writer.writerow({
                'Name': item['name'],
                'Location': item['location'],
                'Phone Numbers': item['phone']
            })
    
    print(f"Data saved to {filename}")

def main():
    """
    Main function to run the scraper.
    """
    search_query = input("Enter search query (e.g., 'restaurants in Mumbai'): ").strip()
    
    pages_input = input("Enter number of pages to scrape (default 10): ").strip()
    if pages_input:
        try:
            max_pages = int(pages_input)
        except ValueError:
            max_pages = 10
    else:
        max_pages = 10
    
    print(f"Starting to scrape '{search_query}' for {max_pages} pages...")
    
    results = scrape_justdial(search_query, max_pages)
    
    if results:
        save_to_csv(results)
        print(f"Scraping completed! Found {len(results)} listings.")
    else:
        print("No data was scraped. Check your search query or try again later.")

if __name__ == "__main__":
    main()