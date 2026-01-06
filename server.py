"""
Petfinder Scraper Server
Continuously scrapes Petfinder search pages and maintains a database of pets.
"""

import csv
import os
import sys
import time
from threading import Thread

from flask import Flask, jsonify

from link_scraper import extract_links_from_html, load_scraping_key
from pet_scraper import scrape_pet, get_pet_csv_fields, PET_CSV, log
from verify import verify_link
from flask import request, Response

app = Flask(__name__)

# Server status
server_status = {
    "running": False,
    "current_page": 1,
    "current_pet_type": "dog",
    "total_pets_scraped": 0,
    "total_pets_verified": 0,
    "total_pets_removed": 0,
}


def get_existing_links() -> set:
    """Get all existing links from pets.csv to check for duplicates."""
    existing_links = set()
    if os.path.exists(PET_CSV):
        try:
            with open(PET_CSV, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    link = row.get("link", "").strip()
                    if link:
                        existing_links.add(link)
        except Exception as e:
            log(f"Error reading existing links: {e}")
    return existing_links


def check_link_exists(link: str) -> bool:
    """Check if a link already exists in pets.csv."""
    return link in get_existing_links()


def scrape_pets_from_page(page: int, pet_type: str) -> int:
    """
    Scrape all pets from a single search page.
    
    Args:
        page: Page number (1-10000)
        pet_type: "dog" or "cat"
        
    Returns:
        Number of new pets scraped (excluding duplicates)
    """
    url = f"https://www.petfinder.com/search/{pet_type}s-for-adoption/us/ny/newyork/?distance=anywhere&page={page}"
    log(f"Scraping page {page} for {pet_type}s: {url}")
    
    try:
        # Get links from search page
        links = extract_links_from_html(url=url)
        log(f"Found {len(links)} links on page {page} for {pet_type}s")
        
        # Get existing links to avoid duplicates
        existing_links = get_existing_links()
        new_pets_count = 0
        
        # Scrape each link
        for i, link in enumerate(links, 1):
            try:
                # Skip if already exists (check before scraping to save time)
                if link in existing_links:
                    log(f"Skipping duplicate link: {link}")
                    continue
                
                log(f"Scraping {pet_type} {i}/{len(links)}: {link}")
                scrape_pet(link, pet_type=pet_type)
                existing_links.add(link)  # Add to set to avoid duplicates in same batch
                new_pets_count += 1
                server_status["total_pets_scraped"] += 1
                
                # Small delay to avoid overwhelming the server
                time.sleep(1)
                
            except Exception as e:
                log(f"Error scraping pet {link}: {e}")
                continue
        
        log(f"Page {page} for {pet_type}s: {new_pets_count} new pets scraped")
        return new_pets_count
        
    except Exception as e:
        log(f"Error scraping page {page} for {pet_type}s: {e}")
        return 0


def verify_all_pets() -> int:
    """
    Verify all pets in pets.csv and remove invalid ones.
    
    Returns:
        Number of pets removed
    """
    log("Starting verification of all pets in CSV...")
    
    if not os.path.exists(PET_CSV):
        log("No CSV file found, skipping verification")
        return 0
    
    # Read all rows
    rows = []
    removed_count = 0
    
    try:
        with open(PET_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                link = row.get("link", "").strip()
                if not link:
                    continue
                
                # Verify the link
                log(f"Verifying link: {link}")
                if verify_link(link):
                    # Keep valid link
                    rows.append(row)
                    server_status["total_pets_verified"] += 1
                else:
                    # Remove invalid link
                    log(f"Removing invalid link: {link}")
                    removed_count += 1
                    server_status["total_pets_removed"] += 1
                
                # Small delay
                time.sleep(0.5)
        
        # Write back valid rows
        if fieldnames:
            tmp = PET_CSV + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            
            os.replace(tmp, PET_CSV)
            log(f"Verification complete: {removed_count} pets removed, {len(rows)} pets remain")
        
    except Exception as e:
        log(f"Error during verification: {e}")
    
    return removed_count


def scraping_loop():
    """Main scraping loop that runs continuously."""
    log("Starting scraping loop...")
    server_status["running"] = True
    
    while server_status["running"]:
        try:
            # Scrape pages 1-10000 for dogs and cats
            for page in range(1, 10001):
                if not server_status["running"]:
                    break
                
                server_status["current_page"] = page
                
                # Scrape dogs
                server_status["current_pet_type"] = "dog"
                scrape_pets_from_page(page, "dog")
                
                # Scrape cats
                server_status["current_pet_type"] = "cat"
                scrape_pets_from_page(page, "cat")
            
            # After reaching page 10000, verify all pets
            log("Reached page 10000, starting verification...")
            verify_all_pets()
            
            # Loop back to page 1
            log("Verification complete, looping back to page 1...")
            server_status["current_page"] = 1
            
        except Exception as e:
            log(f"Error in scraping loop: {e}")
            time.sleep(60)  # Wait before retrying


@app.route("/")
def index():
    """Health check endpoint."""
    return jsonify({
        "status": "running" if server_status["running"] else "stopped",
        "message": "Petfinder Scraper Server"
    })


@app.route("/status")
def status():
    """Get server status."""
    return jsonify(server_status)


@app.route("/start", methods=["POST"])
def start():
    """Start the scraping loop."""
    if server_status["running"]:
        return jsonify({"message": "Scraping already running"}), 400
    
    thread = Thread(target=scraping_loop, daemon=True)
    thread.start()
    return jsonify({"message": "Scraping started"})


@app.route("/stop", methods=["POST"])
def stop():
    """Stop the scraping loop."""
    server_status["running"] = False
    return jsonify({"message": "Scraping stopped"})


def verify_endpoint_key() -> bool:
    """Verify the endpoint key from request."""
    # Check for key in query parameter or header
    provided_key = request.args.get("key") or request.headers.get("X-API-Key")
    if not provided_key:
        return False
    
    try:
        expected_key = load_scraping_key()
        return provided_key == expected_key
    except Exception:
        return False


@app.route("/pets", methods=["GET"])
def get_pets():
    """
    Get all pets from pets.csv.
    Requires endpoint key authentication.
    """
    # Verify endpoint key
    if not verify_endpoint_key():
        return jsonify({"error": "Invalid or missing endpoint key"}), 401
    
    if not os.path.exists(PET_CSV):
        return jsonify({"error": "No pets data available", "pets": []}), 200
    
    try:
        # Read CSV and return as JSON
        pets = []
        with open(PET_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                pets.append(dict(row))
        
        return jsonify({
            "count": len(pets),
            "pets": pets
        })
    except Exception as e:
        log(f"Error reading pets CSV: {e}")
        return jsonify({"error": "Failed to read pets data"}), 500


@app.route("/pets.csv", methods=["GET"])
def get_pets_csv():
    """
    Get all pets from pets.csv as CSV file.
    Requires endpoint key authentication.
    """
    # Verify endpoint key
    if not verify_endpoint_key():
        return jsonify({"error": "Invalid or missing endpoint key"}), 401
    
    if not os.path.exists(PET_CSV):
        return Response("", mimetype="text/csv"), 200
    
    try:
        # Read and return CSV file directly
        with open(PET_CSV, "r", encoding="utf-8") as f:
            csv_content = f.read()
        
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=pets.csv"}
        )
    except Exception as e:
        log(f"Error reading pets CSV: {e}")
        return jsonify({"error": "Failed to read pets data"}), 500


# Start scraping loop in background thread when module is imported
# This ensures it starts with gunicorn as well
scraping_thread = Thread(target=scraping_loop, daemon=True)
scraping_thread.start()

if __name__ == "__main__":
    # Start Flask server (for local development)
    port = int(os.environ.get("PORT", 5000))
    log(f"Starting Flask server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)

