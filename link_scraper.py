"""
Link scraper to extract pet links from Petfinder search page HTML.
Extracts links from the search results by calling the scraping server.
"""

import os
import requests
from playwright.sync_api import sync_playwright

SCRAPING_KEY_FILE = "endpointkey.txt"
SCRAPING_SERVER_URL = "https://petfinder-scraper.onrender.com/scrape-js"


def load_scraping_key() -> str:
    """Load the scraping API key from endpointkey.txt."""
    try:
        with open(SCRAPING_KEY_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
        if not key:
            raise ValueError("Scraping key file is empty")
        return key
    except FileNotFoundError:
        raise FileNotFoundError(f"Scraping key file not found: {SCRAPING_KEY_FILE}")
    except Exception as e:
        raise Exception(f"Error reading scraping key: {e}")


def fetch_html_from_server(url: str, key: str, wait_timeout: int = 20, additional_wait: int = 5) -> str:
    """
    Fetch HTML content from the scraping server using the JavaScript endpoint.
    
    Args:
        url: The URL to scrape
        key: The API key for authentication
        wait_timeout: Maximum time to wait for page load in seconds (default: 20)
        additional_wait: Additional time to wait after page load for JS execution in seconds (default: 5)
        
    Returns:
        HTML content as string
    """
    try:
        response = requests.get(
            SCRAPING_SERVER_URL,
            params={
                "url": url,
                "key": key,
                "wait_timeout": wait_timeout,
                "additional_wait": additional_wait
            },
            timeout=120  # Longer timeout for JS rendering
        )
        
        if response.status_code == 200:
            html_content = response.text
            return html_content
        elif response.status_code == 401:
            error_msg = response.json().get("error", "Authentication failed")
            raise Exception(f"Authentication failed: {error_msg}")
        else:
            error_msg = response.json().get("error", f"HTTP {response.status_code}")
            raise Exception(f"Scraping server error: {error_msg}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Error connecting to scraping server: {e}")


def extract_links_from_html(html_content: str = None, url: str = None) -> list:
    """
    Extract pet links from HTML content.
    
    Args:
        html_content: HTML content as string (if provided, uses this directly)
        url: URL to scrape (if html_content not provided, fetches from server)
        
    Returns:
        List of pet URLs
    """
    links = []
    
    # If HTML content not provided, fetch from server
    if html_content is None:
        if url is None:
            url = "https://www.petfinder.com/search/dogs-for-adoption/us/ny/newyork/?distance=anywhere&page=2"
        
        print(f"Fetching HTML from scraping server for: {url}")
        key = load_scraping_key()
        html_content = fetch_html_from_server(url, key)
        print(f"Successfully fetched HTML ({len(html_content)} characters)")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        try:
            # Load the HTML content
            page.set_content(html_content, wait_until="domcontentloaded")
            page.wait_for_timeout(500)  # Small wait for any dynamic content
            
            # Extract links using the specific XPaths provided
            xpaths = [
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[1]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[2]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[3]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[5]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[5]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[6]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[9]/div[2]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[9]/div[4]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[9]/div[5]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[10]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[11]/div/div[1]/div/div[3]/div/a",
                "/html/body/div[2]/div/div/section/section/main/div/section/div/div[2]/div[12]/div/div[1]/div/div[3]/div/a",
            ]
            
            for i, xpath in enumerate(xpaths, 1):
                try:
                    # Get the href attribute from the link
                    href = page.evaluate("""
                        (xpath) => {
                            const result = document.evaluate(
                                xpath,
                                document,
                                null,
                                XPathResult.FIRST_ORDERED_NODE_TYPE,
                                null
                            );
                            const element = result.singleNodeValue;
                            if (element && element.tagName === 'A') {
                                return element.href || element.getAttribute('href') || '';
                            }
                            return '';
                        }
                    """, xpath)
                    
                    if href:
                        # Make sure it's a full URL
                        if href.startswith('/'):
                            href = f"https://www.petfinder.com{href}"
                        links.append(href)
                        print(f"Found link {i}: {href}")
                    else:
                        print(f"No link found at XPath {i}")
                        
                except Exception as e:
                    print(f"Error extracting link {i}: {e}")
            
        finally:
            page.close()
            context.close()
            browser.close()
    
    return links


if __name__ == "__main__":
    print("Extracting links from Petfinder search page...")
    url = "https://www.petfinder.com/search/dogs-for-adoption/us/ny/newyork/?distance=anywhere&page=2"
    links = extract_links_from_html(url=url)
    print(f"\nTotal links found: {len(links)}")
    print("\nAll links:")
    for i, link in enumerate(links, 1):
        print(f"{i}. {link}")

