"""
Petfinder Scraper Server
Continuously scrapes Petfinder search pages and maintains a database of pets.
"""

import csv
import gc
import json
import os
import sys
import time
import subprocess
from threading import Thread

from flask import Flask, jsonify

# Optional import for memory monitoring
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from link_scraper import extract_links_from_html, load_scraping_key
from pet_scraper import scrape_pet, get_pet_csv_fields, PET_CSV, log
from verify import verify_link
from flask import request, Response

app = Flask(__name__)

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

# Progress file to persist scraping state
PROGRESS_FILE = os.path.join(DATA_DIR, "scraping_progress.json")

# Server status
server_status = {
    "running": False,
    "current_page": 1,
    "current_pet_type": "dog",
    "total_pets_scraped": 0,
    "total_pets_verified": 0,
    "total_pets_removed": 0,
}

# Track pet scraping timestamps for rate calculation
pet_scraping_timestamps = []


def ensure_playwright_installed():
    """Ensure Playwright Chromium is installed at runtime."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Try to launch chromium - if it fails, install it
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                log("Playwright Chromium is already installed")
            except Exception:
                log("Playwright Chromium not found, installing...")
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], 
                             check=False, capture_output=True)
                log("Playwright Chromium installation attempted")
    except Exception as e:
        log(f"Error checking/installing Playwright: {e}")


# Ensure Playwright is installed when server starts
ensure_playwright_installed()


# Cache for existing links to avoid reading CSV repeatedly
_existing_links_cache = None
_existing_links_cache_time = 0
CACHE_TTL = 300  # Cache for 5 minutes

def get_existing_links(force_refresh: bool = False) -> set:
    """
    Get all existing links from pets.csv to check for duplicates.
    Uses caching to reduce memory pressure.
    """
    global _existing_links_cache, _existing_links_cache_time
    
    # Return cached version if still valid
    if not force_refresh and _existing_links_cache is not None:
        if time.time() - _existing_links_cache_time < CACHE_TTL:
            return _existing_links_cache
    
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
    
    # Update cache
    _existing_links_cache = existing_links
    _existing_links_cache_time = time.time()
    
    return existing_links


def check_link_exists(link: str) -> bool:
    """Check if a link already exists in pets.csv."""
    return link in get_existing_links()


def save_progress(page: int = None, pet_type: str = None, mode: str = "scraping", verification_link: str = None) -> None:
    """
    Save scraping/verification progress to disk.
    
    Args:
        page: Current page number (for scraping mode)
        pet_type: Current pet type ("dog" or "cat", for scraping mode)
        mode: Current mode ("scraping" or "verification")
        verification_link: Current link being verified (for verification mode)
    """
    try:
        progress = {
            "mode": mode,
            "timestamp": time.time()
        }
        
        if mode == "scraping":
            progress["page"] = page
            progress["pet_type"] = pet_type
        elif mode == "verification":
            progress["verification_link"] = verification_link
        
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f)
    except Exception as e:
        log(f"Error saving progress: {e}")


def load_progress() -> tuple[str, int, str, str]:
    """
    Load scraping/verification progress from disk.
    
    Returns:
        Tuple of (mode, page, pet_type, verification_link).
        - mode: "scraping" or "verification"
        - page: Current page number (for scraping mode)
        - pet_type: Current pet type (for scraping mode)
        - verification_link: Current link being verified (for verification mode)
        Returns ("scraping", 1, "dog", None) if no progress file exists.
    """
    if not os.path.exists(PROGRESS_FILE):
        return "scraping", 1, "dog", None
    
    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)
            mode = progress.get("mode", "scraping")
            
            if mode == "verification":
                verification_link = progress.get("verification_link", None)
                log(f"Loaded progress: mode=verification, last_link={verification_link}")
                return "verification", None, None, verification_link
            else:
                # Scraping mode
                page = progress.get("page", 1)
                pet_type = progress.get("pet_type", "dog")
                # Ensure valid values
                if page < 1 or page > 10000:
                    page = 1
                if pet_type not in ["dog", "cat"]:
                    pet_type = "dog"
                log(f"Loaded progress: mode=scraping, page={page}, pet_type={pet_type}")
                return "scraping", page, pet_type, None
    except Exception as e:
        log(f"Error loading progress: {e}")
        return "scraping", 1, "dog", None


def reset_progress() -> None:
    """Reset progress file (called after reaching page 10000 and verification)."""
    try:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        log("Progress reset to page 1")
    except Exception as e:
        log(f"Error resetting progress: {e}")


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
        
        # Get existing links to avoid duplicates (use cache)
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
                
                # Track timestamp for rate calculation
                pet_scraping_timestamps.append(time.time())
                
                # Force garbage collection every 5 pets to free memory
                if i % 5 == 0:
                    gc.collect()
                
                # Small delay to avoid overwhelming the server
                time.sleep(1)
                
            except Exception as e:
                log(f"Error scraping pet {link}: {e}")
                continue
        
        # Refresh cache after scraping (new pets were added)
        if new_pets_count > 0:
            get_existing_links(force_refresh=True)
        
        # Force garbage collection after page
        gc.collect()
        
        log(f"Page {page} for {pet_type}s: {new_pets_count} new pets scraped")
        return new_pets_count
        
    except Exception as e:
        log(f"Error scraping page {page} for {pet_type}s: {e}")
        gc.collect()  # Clean up on error
        return 0


def verify_all_pets(resume_from_link: str = None) -> int:
    """
    Verify all pets in pets.csv and remove invalid ones.
    Can resume from a specific link if verification was interrupted.
    
    Args:
        resume_from_link: Link to resume verification from (None to start from beginning)
    
    Returns:
        Number of pets removed
    """
    log("Starting verification of all pets in CSV...")
    if resume_from_link:
        log(f"Resuming verification from link: {resume_from_link}")
    
    if not os.path.exists(PET_CSV):
        log("No CSV file found, skipping verification")
        return 0
    
    # Clean up any incomplete temp files from previous crashes
    tmp_file = PET_CSV + ".tmp"
    if os.path.exists(tmp_file):
        log("Found incomplete temp file from previous verification, removing it...")
        try:
            os.remove(tmp_file)
        except Exception as e:
            log(f"Warning: Could not remove temp file: {e}")
    
    # Read all rows
    all_rows = []
    removed_count = 0
    start_verifying = resume_from_link is None
    
    try:
        # First pass: read all rows and find resume point
        with open(PET_CSV, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                link = row.get("link", "").strip()
                if not link:
                    continue
                
                # If resuming, skip until we find the resume point
                if not start_verifying:
                    if link == resume_from_link:
                        start_verifying = True
                        # Include this link in verification (it was saved as progress but may not have been verified)
                    else:
                        # Keep rows before resume point (assuming they were verified before crash)
                        all_rows.append(row)
                        continue
                
                # Verify the link
                log(f"Verifying link: {link}")
                
                # Save progress BEFORE verification (so we can resume even if verification fails)
                save_progress(mode="verification", verification_link=link)
                
                if verify_link(link):
                    # Keep valid link
                    all_rows.append(row)
                    server_status["total_pets_verified"] += 1
                else:
                    # Remove invalid link
                    log(f"Removing invalid link: {link}")
                    removed_count += 1
                    server_status["total_pets_removed"] += 1
                
                # Force garbage collection every 10 pets during verification
                if len(all_rows) % 10 == 0:
                    gc.collect()
                
                # Small delay
                time.sleep(0.5)
        
        # Write back valid rows
        if fieldnames:
            tmp = PET_CSV + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            
            # Atomic replace
            os.replace(tmp, PET_CSV)
            log(f"Verification complete: {removed_count} pets removed, {len(all_rows)} pets remain")
            
            # Refresh cache after verification (links may have been removed)
            get_existing_links(force_refresh=True)
        
        # Force garbage collection after verification
        gc.collect()
        
    except Exception as e:
        log(f"Error during verification: {e}")
        gc.collect()  # Clean up on error
        # Progress is already saved, so we can resume from the last saved link
        raise  # Re-raise to allow scraping_loop to handle it
    
    return removed_count


def get_memory_usage_mb() -> float:
    """Get current memory usage in MB."""
    if not PSUTIL_AVAILABLE:
        return 0.0
    try:
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024
    except Exception:
        return 0.0


def scraping_loop():
    """Main scraping loop that runs continuously."""
    log("Starting scraping loop...")
    server_status["running"] = True
    
    # Track start time for periodic restarts
    loop_start_time = time.time()
    last_memory_check = time.time()
    MEMORY_CHECK_INTERVAL = 300  # Check memory every 5 minutes
    RESTART_INTERVAL = 3600  # Restart loop every hour to prevent memory leaks
    
    # Load progress from disk (resume from where we left off)
    mode, start_page, start_pet_type, verification_link = load_progress()
    
    # If we were in verification mode, resume verification first
    if mode == "verification":
        log(f"Resuming verification from link: {verification_link}")
        try:
            verify_all_pets(resume_from_link=verification_link)
            log("Verification complete, resetting to page 1...")
            reset_progress()
            start_page = 1
            start_pet_type = "dog"
            mode = "scraping"
        except Exception as e:
            log(f"Error during verification resume: {e}")
            # If verification fails, reset and start from page 1
            reset_progress()
            start_page = 1
            start_pet_type = "dog"
            mode = "scraping"
    
    if mode == "scraping":
        log(f"Resuming scraping from page {start_page}, pet_type: {start_pet_type}")
    
    while server_status["running"]:
        try:
            # Check if we need to restart the loop (every hour) to prevent memory leaks
            elapsed = time.time() - loop_start_time
            if elapsed >= RESTART_INTERVAL:
                log(f"Restarting scraping loop after {elapsed/3600:.1f} hours to prevent memory leaks")
                # Save current progress before restarting
                if mode == "scraping":
                    save_progress(page=start_page, pet_type=start_pet_type, mode="scraping")
                # Force garbage collection
                gc.collect()
                # Break to restart the loop
                break
            
            # Periodic memory monitoring
            if time.time() - last_memory_check >= MEMORY_CHECK_INTERVAL:
                memory_mb = get_memory_usage_mb()
                log(f"Memory usage: {memory_mb:.1f} MB")
                last_memory_check = time.time()
                
                # If memory is very high (>2GB), force cleanup
                if memory_mb > 2048:
                    log("High memory usage detected, forcing aggressive cleanup...")
                    gc.collect()
                    get_existing_links(force_refresh=True)  # Clear cache
                    gc.collect()
            
            # Scrape pages from start_page to 10000 for dogs and cats
            for page in range(start_page, 10001):
                if not server_status["running"]:
                    break
                
                server_status["current_page"] = page
                
                # Determine which pet types to scrape based on where we're resuming
                pet_types_to_scrape = []
                if page == start_page and start_pet_type:
                    # On the first page, start from the saved pet_type
                    if start_pet_type == "dog":
                        pet_types_to_scrape = ["dog", "cat"]
                    else:
                        # We were on cats, so only scrape cats for this page
                        pet_types_to_scrape = ["cat"]
                else:
                    # Normal flow: scrape both dogs and cats
                    pet_types_to_scrape = ["dog", "cat"]
                
                # Scrape each pet type
                for pet_type in pet_types_to_scrape:
                    if not server_status["running"]:
                        break
                    
                    server_status["current_pet_type"] = pet_type
                    scrape_pets_from_page(page, pet_type)
                    
                    # Save progress after each page/pet_type combination
                    save_progress(page=page, pet_type=pet_type, mode="scraping")
                    
                    # Periodic memory cleanup every 10 pages
                    if page % 10 == 0:
                        gc.collect()
                        log(f"Memory cleanup after page {page}")
                
                # Reset start_page after first iteration to ensure normal flow
                if page == start_page:
                    start_page = 1
                
                # Periodic cache refresh every 50 pages to prevent stale data
                if page % 50 == 0:
                    get_existing_links(force_refresh=True)
                    gc.collect()
                    log(f"Refreshed link cache after page {page}")
            
            # After reaching page 10000, verify all pets
            log("Reached page 10000, starting verification...")
            try:
                verify_all_pets(resume_from_link=None)  # Start from beginning
            except Exception as e:
                log(f"Error during verification: {e}")
                # If verification fails, save progress so we can resume
                # The progress file will contain the last verified link
                raise  # Re-raise to be caught by outer try-except
            
            # Reset progress and loop back to page 1
            log("Verification complete, looping back to page 1...")
            reset_progress()
            start_page = 1
            start_pet_type = "dog"
            server_status["current_page"] = 1
            
        except Exception as e:
            log(f"Error in scraping loop: {e}")
            # Progress is already saved, so we can resume from where we left off
            gc.collect()  # Clean up on error
            time.sleep(60)  # Wait before retrying
        
        # If we broke out of the loop (for restart), restart it
        if server_status["running"]:
            log("Restarting scraping loop...")
            loop_start_time = time.time()
            last_memory_check = time.time()
            # Reload progress to continue from where we left off
            mode, start_page, start_pet_type, verification_link = load_progress()


@app.route("/")
def index():
    """Health check endpoint."""
    return jsonify({
        "status": "running" if server_status["running"] else "stopped",
        "message": "Petfinder Scraper Server"
    })


@app.route("/health")
def health():
    """Health check endpoint for Render."""
    return jsonify({
        "status": "running" if server_status["running"] else "stopped",
        "message": "Petfinder Scraper Server"
    }), 200


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


@app.route("/rate", methods=["GET"])
def get_scraping_rate():
    """
    Get the rate of pet retrieval in the past 15 minutes.
    No authentication required.
    
    Returns:
        JSON with rate (pets per minute) and count of pets in last 15 minutes
    """
    global pet_scraping_timestamps
    
    current_time = time.time()
    fifteen_minutes_ago = current_time - (15 * 60)  # 15 minutes in seconds
    
    # Clean up old timestamps (older than 15 minutes)
    pet_scraping_timestamps = [ts for ts in pet_scraping_timestamps if ts >= fifteen_minutes_ago]
    
    # Count pets scraped in the last 15 minutes
    pets_in_last_15_min = len(pet_scraping_timestamps)
    
    # Calculate rate: pets per minute
    rate = pets_in_last_15_min / 15.0
    
    return jsonify({
        "rate": round(rate, 2),  # Round to 2 decimal places
        "pets_in_last_15_minutes": pets_in_last_15_min,
        "unit": "pets per minute"
    })


# Start scraping loop in background thread when module is imported
# This ensures it starts with gunicorn as well
scraping_thread = Thread(target=scraping_loop, daemon=True)
scraping_thread.start()

if __name__ == "__main__":
    # Start Flask server (for local development)
    port = int(os.environ.get("PORT", 5000))
    log(f"Starting Flask server on port {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)

