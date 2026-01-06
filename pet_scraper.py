"""
Petfinder scraper for individual pet pages.
Scrapes pet information and stores it in a CSV file.

Run (Linux-friendly):
  pip install playwright
  playwright install chromium
  python pet_scraper.py
"""

import csv
import os
import re
import sys
import time
from contextlib import suppress
from typing import Dict

import requests
from playwright.sync_api import sync_playwright


# Data directory for persistent storage (mounted Render Disk)
# Use /data on Render (Linux), or local "data" directory for development (Windows)
if sys.platform == "win32":
    # On Windows, always use local "data" directory
    DATA_DIR = "data"
elif os.path.exists("/data") and os.access("/data", os.W_OK):
    # On Linux/Render, use /data if it exists and is writable
    DATA_DIR = "/data"
else:
    # Fallback to local "data" directory
    DATA_DIR = "data"

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

PET_CSV = os.path.join(DATA_DIR, "pets.csv")
LOG_PATH = os.path.join(DATA_DIR, "pet_scraper.log")
SCRAPING_KEY_FILE = "scrapingkey.txt"
SCRAPING_SERVER_URL = "https://petfinder-scraper.onrender.com/scrape"


def load_scraping_key() -> str:
    """Load the scraping API key from scrapingkey.txt."""
    try:
        with open(SCRAPING_KEY_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if not key:
            raise ValueError("Scraping key file is empty")
        return key
    except FileNotFoundError:
        log(f"Error: {SCRAPING_KEY_FILE} not found")
        raise
    except Exception as e:
        log(f"Error reading scraping key: {e}")
        raise


def fetch_html_from_server(url: str, key: str) -> str:
    """
    Fetch HTML content from the scraping server.
    
    Args:
        url: The URL to scrape
        key: The API key for authentication
        
    Returns:
        HTML content as string
    """
    try:
        log(f"Fetching HTML from scraping server for: {url}")
        response = requests.get(
            SCRAPING_SERVER_URL,
            params={"url": url, "key": key},
            timeout=60
        )
        
        if response.status_code == 200:
            html_content = response.text
            log(f"Successfully fetched HTML ({len(html_content)} characters)")
            return html_content
        elif response.status_code == 401:
            error_msg = response.json().get("error", "Authentication failed")
            log(f"Error: Authentication failed - {error_msg}")
            raise Exception(f"Authentication failed: {error_msg}")
        else:
            error_msg = response.json().get("error", f"HTTP {response.status_code}")
            log(f"Error from scraping server: {error_msg}")
            raise Exception(f"Scraping server error: {error_msg}")
    except requests.exceptions.RequestException as e:
        log(f"Error connecting to scraping server: {e}")
        raise


# XPaths for pet information
XPATHS = {
    "location": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[1]/div/div[1]/div/p",
    "age": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[3]/div/div[1]/div/div[1]/div[1]/div",
    "gender": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[3]/div/div[1]/div/div[1]/div[2]/span",
    "size": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[3]/div/div[1]/div/div[1]/div[3]/div",
    "color": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[3]/div/div[1]/div/div[2]/div/span",
    "breed": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[2]/div[2]/div/div",
    "spayed_neutered": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[4]/div/div/div[1]/div",
    "vaccinated": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[4]/div/div/div[2]/div",
    "special_needs": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[4]/div/div/div[3]/div",
    "kids_compatible": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/section/ul/div[1]/div/p[3]",
    "dogs_compatible": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/section/ul/div[2]/div/p[3]",
    "cats_compatible": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/section/ul/div[3]/div/p[3]",
    "about_me": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[4]/div",
    "name": "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[3]/div[1]/div/div[1]/h2",
}


def log(msg: str) -> None:
    """Log message to console and log file."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ""
    text = text.strip()
    # Remove trailing asterisks often used as footnote markers
    text = re.sub(r"\*+$", "", text).strip()
    return text


def get_text(page, xpath: str, field_name: str = "") -> str:
    """Get text from page element using XPath. Gets element[0].innerText."""
    try:
        # Use JavaScript evaluation to match browser console $x() behavior
        # This ensures we get element[0].innerText exactly as in the browser
        # Pass XPath as a parameter to avoid escaping issues
        raw = page.evaluate("""
            (xpath) => {
                const result = document.evaluate(
                    xpath,
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                const element = result.singleNodeValue;
                return element ? (element.innerText || '') : '';
            }
        """, xpath)
        result = clean_text(raw)
        if not result and field_name:
            log(f"Warning: Empty result for field '{field_name}' with XPath: {xpath[:50]}...")
        return result
    except Exception as e:
        if field_name:
            log(f"Warning: Error getting '{field_name}': {e}")
        return ""


def get_image_src(page, xpath: str, field_name: str = "") -> str:
    """Get image src URL from img element using XPath. Gets element[0].src."""
    try:
        # Use JavaScript evaluation to get the src attribute of an img tag
        src = page.evaluate("""
            (xpath) => {
                const result = document.evaluate(
                    xpath,
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                const element = result.singleNodeValue;
                if (element && element.tagName === 'IMG') {
                    return element.src || element.getAttribute('src') || '';
                }
                return '';
            }
        """, xpath)
        return src.strip() if src else ""
    except Exception as e:
        if field_name:
            log(f"Warning: Error getting '{field_name}' image: {e}")
        return ""


def click_show_more_if_exists(page, button_xpath: str) -> None:
    """Check if show more button exists and click it if it does."""
    with suppress(Exception):
        # Check if button exists using JavaScript
        button_exists = page.evaluate("""
            (xpath) => {
                const result = document.evaluate(
                    xpath,
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                );
                const element = result.singleNodeValue;
                return element !== null && element.offsetParent !== null;
            }
        """, button_xpath)
        
        if button_exists:
            # Click the button using Playwright locator
            try:
                button_locator = page.locator(f"xpath={button_xpath}")
                if button_locator.is_visible(timeout=3000):
                    button_locator.click(timeout=5000)
                    page.wait_for_timeout(500)  # Wait for content to expand
                    del button_locator
            except Exception:
                pass  # Button might have disappeared or not be clickable


def parse_boolean(text: str) -> bool:
    """Parse boolean from text. Returns True if text contains positive indicators."""
    if not text:
        return False
    text_lower = text.lower().strip()
    # Check for positive indicators
    positive_indicators = ["yes", "true", "✓", "check", "checked", "y"]
    negative_indicators = ["no", "false", "✗", "unchecked", "n"]
    
    for neg in negative_indicators:
        if neg in text_lower:
            return False
    for pos in positive_indicators:
        if pos in text_lower:
            return True
    
    # Default: if text exists and doesn't explicitly say no, assume True
    return bool(text_lower)


def extract_name_from_about(text: str) -> str:
    """Extract name from 'About {name}' format."""
    if not text:
        return ""
    # Remove "About" prefix if present
    text = text.strip()
    if text.lower().startswith("about"):
        text = text[5:].strip()  # Remove "About" and whitespace
    return text


def _scrape_pet_page(page, pet_link: str, scraping_key: str) -> Dict[str, str]:
    """
    Internal function to scrape information from a single pet page.
    
    Args:
        page: Playwright page object
        pet_link: URL to the pet's page
        
    Returns:
        Dictionary containing scraped pet information
    """
    data = {
        "link": pet_link,
        "location": "",
        "age": "",
        "gender": "",
        "size": "",
        "color": "",
        "breed": "",
        "spayed_neutered": False,
        "vaccinated": False,
        "special_needs": False,
        "kids_compatible": False,
        "dogs_compatible": False,
        "cats_compatible": False,
        "about_me": "",
        "name": "",
        "image": "",
    }
    
    # Fetch HTML from scraping server
    html_content = fetch_html_from_server(pet_link, scraping_key)
    
    # Load the HTML into Playwright page
    log(f"Loading HTML into page...")
    page.set_content(html_content, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)  # Small wait for any dynamic content
    
    log(f"Starting to scrape fields...")
    
    # Scrape all fields
    try:
        # Image (get src from img tag)
        image_xpath = "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[1]/div/div[2]/div/div[1]/img"
        data["image"] = get_image_src(page, image_xpath, "image")
        
        data["location"] = get_text(page, XPATHS["location"], "location")
        data["age"] = get_text(page, XPATHS["age"], "age")
        data["gender"] = get_text(page, XPATHS["gender"], "gender")
        data["size"] = get_text(page, XPATHS["size"], "size")
        data["color"] = get_text(page, XPATHS["color"], "color")
        data["breed"] = get_text(page, XPATHS["breed"], "breed")
        
        # Boolean fields
        spayed_text = get_text(page, XPATHS["spayed_neutered"], "spayed_neutered")
        data["spayed_neutered"] = parse_boolean(spayed_text)
        
        vaccinated_text = get_text(page, XPATHS["vaccinated"], "vaccinated")
        data["vaccinated"] = parse_boolean(vaccinated_text)
        
        special_needs_text = get_text(page, XPATHS["special_needs"], "special_needs")
        data["special_needs"] = parse_boolean(special_needs_text)
        
        kids_text = get_text(page, XPATHS["kids_compatible"], "kids_compatible")
        data["kids_compatible"] = parse_boolean(kids_text)
        
        dogs_text = get_text(page, XPATHS["dogs_compatible"], "dogs_compatible")
        data["dogs_compatible"] = parse_boolean(dogs_text)
        
        cats_text = get_text(page, XPATHS["cats_compatible"], "cats_compatible")
        data["cats_compatible"] = parse_boolean(cats_text)
        
        # About me (get everything in the div)
        # Check for "Show more" button and click it if it exists
        show_more_button_xpath = "/html/body/div[2]/div/div/section/section/main/main/div/div[1]/section/section[4]/div/button[2]"
        click_show_more_if_exists(page, show_more_button_xpath)
        data["about_me"] = get_text(page, XPATHS["about_me"], "about_me")
        
        # Name (extract from "About {name}" format)
        name_text = get_text(page, XPATHS["name"], "name")
        data["name"] = extract_name_from_about(name_text)
        
    except Exception as e:
        log(f"Warning: Error scraping fields from {pet_link}: {e}")
        # Continue with partial data
    
    return data


def get_pet_csv_fields() -> list:
    """Return the ordered field names for pets.csv."""
    return [
        "link",
        "name",
        "location",
        "age",
        "gender",
        "size",
        "color",
        "breed",
        "spayed_neutered",
        "vaccinated",
        "special_needs",
        "kids_compatible",
        "dogs_compatible",
        "cats_compatible",
        "about_me",
        "image",
    ]


def save_pet_to_csv(pet_data: Dict[str, str], csv_path: str = PET_CSV) -> None:
    """
    Save or update pet data in CSV file.
    Uses link as the unique identifier.
    """
    # Replace actual newlines in about_me with literal \n string to keep it on one line
    if "about_me" in pet_data and pet_data["about_me"]:
        pet_data["about_me"] = pet_data["about_me"].replace("\n", "\\n").replace("\r", "\\n")
    
    ordered_fields = get_pet_csv_fields()
    
    rows = []
    found = False
    pet_link = pet_data.get("link", "").strip()
    
    # Read all rows, preserving order
    if os.path.exists(csv_path):
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    if r.get("link", "").strip() == pet_link:
                        # Update existing row
                        found = True
                        updated_row = {col: "" for col in ordered_fields}
                        for col in ordered_fields:
                            if col in pet_data:
                                # Convert boolean to string
                                val = pet_data[col]
                                if isinstance(val, bool):
                                    updated_row[col] = "True" if val else "False"
                                else:
                                    updated_row[col] = str(val) if val is not None else ""
                            else:
                                # Preserve existing value if not in new data
                                updated_row[col] = r.get(col, "")
                        rows.append(updated_row)
                    else:
                        # Preserve other rows
                        normalized_row = {col: r.get(col, "") for col in ordered_fields}
                        rows.append(normalized_row)
        except Exception as e:
            log(f"Error reading CSV file {csv_path}: {e}")
            raise
    
    # If not found, append new row
    if not found:
        row = {col: "" for col in ordered_fields}
        for col in ordered_fields:
            if col in pet_data:
                val = pet_data[col]
                if isinstance(val, bool):
                    row[col] = "True" if val else "False"
                else:
                    row[col] = str(val) if val is not None else ""
        rows.append(row)
    
    # Write to temporary file first, then atomically replace
    tmp = csv_path + ".tmp"
    row_count = len(rows)
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            # QUOTE_MINIMAL automatically quotes fields containing newlines, commas, or quotes
            writer = csv.DictWriter(
                f, 
                fieldnames=ordered_fields,
                quoting=csv.QUOTE_MINIMAL
            )
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        
        # Clear rows from memory before atomic replace
        del rows
        
        # Atomic replace
        os.replace(tmp, csv_path)
        log(f"Updated CSV: {csv_path} (wrote {row_count} rows)")
    except Exception as e:
        log(f"Error writing CSV file {csv_path}: {e}")
        # Try to clean up temp file
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


def scrape_pet(pet_link: str) -> Dict[str, str]:
    """
    Scrape information from a single pet page.
    This is the main function to be called externally.
    
    Args:
        pet_link: URL to the pet's page
        
    Returns:
        Dictionary containing scraped pet information
    """
    # Load scraping key
    try:
        scraping_key = load_scraping_key()
    except Exception as e:
        log(f"Fatal error loading scraping key: {e}")
        raise
    
    # Use Playwright just to parse the HTML (we don't need to navigate)
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(
                headless=True,  # Headless is fine since we're just parsing HTML
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )
        except Exception as e:
            log(f"Fatal error launching browser: {e}")
            raise
        
        try:
            context = browser.new_context()
            page = context.new_page()
        except Exception as e:
            log(f"Fatal error creating context/page: {e}")
            try:
                browser.close()
            except Exception:
                pass
            raise
        
        try:
            # Scrape the pet data using the scraping server
            data = _scrape_pet_page(page, pet_link, scraping_key)
            
            # Save to CSV
            save_pet_to_csv(data)
            
            return data
        finally:
            try:
                page.close()
            except Exception:
                pass
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    # Example usage
    if len(sys.argv) > 1:
        pet_url = sys.argv[1]
        log(f"Scraping pet: {pet_url}")
        try:
            result = scrape_pet(pet_url)
            log(f"Successfully scraped: {result.get('name', 'Unknown')}")
        except Exception as e:
            log(f"Error scraping pet: {e}")
    else:
        print("Usage: python pet_scraper.py <pet_url>")
        print("Example: python pet_scraper.py https://www.petfinder.com/pet/12345/")

