# Petfinder Scraper API Endpoints

This document describes the available API endpoints for the Petfinder Scraper server.

## Authentication

The pets endpoint requires authentication using an endpoint key. The key can be provided in two ways:
- **Query Parameter**: `?key=YOUR_KEY`
- **Header**: `X-API-Key: YOUR_KEY`

The endpoint key is stored in `endpointkey.txt` on the server.

---

## Endpoints

### Health Check

**GET** `/`

Check if the server is running.

**Response:**
```json
{
  "status": "running",
  "message": "Petfinder Scraper Server"
}
```

**Example:**
```bash
curl https://your-server.com/
```

---

### Get All Pets (CSV)

**GET** `/pets.csv`

Download all pets from the database as a CSV file. Requires endpoint key authentication.

**Authentication:** Required (endpoint key)

**Query Parameters:**
- `key` (required): Your endpoint key

**Response:**
- Content-Type: `text/csv`
- File download with filename `pets.csv`

**Example:**
```bash
# Using query parameter
curl "https://your-server.com/pets.csv?key=YOUR_KEY" -o pets.csv

# Using header
curl -H "X-API-Key: YOUR_KEY" https://your-server.com/pets.csv -o pets.csv
```

**Error Responses:**
- `401 Unauthorized`: Invalid or missing endpoint key
- `500 Internal Server Error`: Failed to read pets data

---

## CSV File Format

The pets CSV file contains the following columns:

- `link`: URL to the pet's Petfinder page
- `pet_type`: Type of pet ("dog" or "cat")
- `name`: Pet's name
- `location`: Pet's location
- `age`: Pet's age
- `gender`: Pet's gender
- `size`: Pet's size
- `color`: Pet's color
- `breed`: Pet's breed
- `spayed_neutered`: Whether the pet is spayed/neutered ("True" or "False")
- `vaccinated`: Whether the pet is vaccinated ("True" or "False")
- `special_needs`: Whether the pet has special needs ("True" or "False")
- `kids_compatible`: Whether the pet is compatible with kids ("True" or "False")
- `dogs_compatible`: Whether the pet is compatible with dogs ("True" or "False")
- `cats_compatible`: Whether the pet is compatible with cats ("True" or "False")
- `about_me`: Description of the pet (newlines replaced with `\n`)
- `image`: URL to the pet's image

---

## Error Codes

- `200 OK`: Request successful
- `401 Unauthorized`: Invalid or missing endpoint key
- `500 Internal Server Error`: Server error
