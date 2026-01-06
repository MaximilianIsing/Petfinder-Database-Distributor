"""
Link verification function to check if a Petfinder pet link is valid.
Uses pet_scraper to scrape the link and checks if enough data was retrieved.
"""

from pet_scraper import scrape_pet_data_only


def verify_link(link: str) -> bool:
    """
    Verify if a Petfinder pet link is valid.
    Uses pet_scraper to scrape the link and checks if enough data was retrieved.
    
    Args:
        link: The pet URL to verify
        
    Returns:
        True if link is valid (<3 fields failed to be read), False if invalid (>=3 fields failed)
    """
    try:
        # Scrape the pet data using pet_scraper (without saving to CSV)
        # Returns (data, failed_count)
        data, fields_failed = scrape_pet_data_only(link)
        
        total_fields = 15  # Total expected fields
        
        # Return False if 3 or more fields failed to be read
        if fields_failed >= 3:
            print(f"Link invalid: {fields_failed} fields failed to be read (out of {total_fields})")
            return False
        
        print(f"Link valid: Only {fields_failed} fields failed to be read (out of {total_fields})")
        return True
                
    except Exception as e:
        print(f"Error verifying link {link}: {e}")
        return False


if __name__ == "__main__":
    # Test with a sample link
    test_link = "https://www.petfinder.com/dog/brahndi-2b34ab68-c16c-364a-a958-cc72d149da94/ny/new-york/shelter-chic-ny1286/details/"
    print(f"Verifying link: {test_link}")
    is_valid = verify_link(test_link)
    print(f"Link is valid: {is_valid}")

