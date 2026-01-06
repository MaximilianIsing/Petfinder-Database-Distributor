# Petfinder Scraper API Documentation

Welcome to the Petfinder Scraper API documentation. This API provides access to a continuously updated database of adoptable pets from Petfinder.

---

## Authentication

The pets endpoint requires authentication using an endpoint key. The key can be provided in two ways:

- **Query Parameter**: `?key=YOUR_KEY`
- **Header**: `X-API-Key: YOUR_KEY`

> **Note:** The endpoint key is stored securely on the server and is required for accessing pet data.

---

## API Endpoints

### Health Check

**Endpoint:** `GET /`

Check if the server is running and healthy.

**Response:**
```json
{
  "status": "running",
  "message": "Petfinder Scraper Server"
}
```

**Example Request:**
```bash
curl https://petfinder-database-distributor.onrender.com/
```

**Response Codes:**
- `200 OK` - Server is running

---

### Get All Pets (CSV)

**Endpoint:** `GET /pets.csv`

Download all pets from the database as a CSV file. This endpoint requires authentication.

**Authentication:** Required (endpoint key)

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `key` | string | Yes | Your endpoint key for authentication |

**Headers:**
| Header | Value | Description |
|--------|-------|-------------|
| `X-API-Key` | `YOUR_KEY` | Alternative way to provide authentication |

**Response:**
- **Content-Type:** `text/csv`
- **Content-Disposition:** `attachment; filename=pets.csv`
- **Body:** CSV file containing all pet records

**Example Requests:**

Using query parameter:
```bash
curl "https://petfinder-database-distributor.onrender.com/pets.csv?key=YOUR_KEY" -o pets.csv
```

Using header:
```bash
curl -H "X-API-Key: YOUR_KEY" \
     https://petfinder-database-distributor.onrender.com/pets.csv \
     -o pets.csv
```

**Response Codes:**
- `200 OK` - Successfully retrieved pets data
- `401 Unauthorized` - Invalid or missing endpoint key
- `500 Internal Server Error` - Server error while reading data

---

## CSV File Format

The pets CSV file contains the following columns:

| Column | Type | Description |
|--------|------|-------------|
| `link` | string | URL to the pet's Petfinder page |
| `pet_type` | string | Type of pet: `"dog"` or `"cat"` |
| `name` | string | Pet's name |
| `location` | string | Pet's location |
| `age` | string | Pet's age (e.g., "Adult", "Young", "Senior") |
| `gender` | string | Pet's gender (e.g., "Male", "Female") |
| `size` | string | Pet's size (e.g., "Large", "Medium", "Small") |
| `color` | string | Pet's color/coloring |
| `breed` | string | Pet's breed |
| `spayed_neutered` | string | Whether the pet is spayed/neutered: `"True"` or `"False"` |
| `vaccinated` | string | Whether the pet is vaccinated: `"True"` or `"False"` |
| `special_needs` | string | Whether the pet has special needs: `"True"` or `"False"` |
| `kids_compatible` | string | Whether the pet is compatible with kids: `"True"` or `"False"` |
| `dogs_compatible` | string | Whether the pet is compatible with dogs: `"True"` or `"False"` |
| `cats_compatible` | string | Whether the pet is compatible with cats: `"True"` or `"False"` |
| `about_me` | string | Description of the pet (newlines replaced with `\n`) |
| `image` | string | URL to the pet's image |

> **Note:** Boolean values are stored as strings (`"True"` or `"False"`). The `about_me` field may contain escaped newline characters (`\n`) to keep the CSV format valid.

---

## Error Codes

| Status Code | Description |
|-------------|-------------|
| `200 OK` | Request successful |
| `401 Unauthorized` | Invalid or missing endpoint key |
| `500 Internal Server Error` | Server error occurred |

---

## Data Updates

The database is continuously updated by scraping Petfinder search pages. The scraper:

- Scrapes pages 1-10,000 for both dogs and cats
- Verifies all entries periodically to remove invalid links
- Prevents duplicate entries by checking pet links
- Updates the CSV file in real-time

---

## Example Usage

### Python

```python
import requests

# Your endpoint key
API_KEY = "your-endpoint-key-here"
BASE_URL = "https://petfinder-database-distributor.onrender.com"

# Health check
response = requests.get(f"{BASE_URL}/")
print(response.json())

# Get pets CSV
response = requests.get(
    f"{BASE_URL}/pets.csv",
    params={"key": API_KEY}
)

if response.status_code == 200:
    with open("pets.csv", "wb") as f:
        f.write(response.content)
    print("Successfully downloaded pets.csv")
else:
    print(f"Error: {response.status_code}")
    print(response.text)
```

### JavaScript/Node.js

```javascript
const https = require('https');
const fs = require('fs');

const API_KEY = 'your-endpoint-key-here';
const BASE_URL = 'petfinder-database-distributor.onrender.com';

// Get pets CSV
const options = {
  hostname: BASE_URL,
  path: `/pets.csv?key=${API_KEY}`,
  method: 'GET'
};

const req = https.request(options, (res) => {
  if (res.statusCode === 200) {
    const file = fs.createWriteStream('pets.csv');
    res.pipe(file);
    file.on('finish', () => {
      file.close();
      console.log('Successfully downloaded pets.csv');
    });
  } else {
    console.error(`Error: ${res.statusCode}`);
  }
});

req.on('error', (e) => {
  console.error(`Problem with request: ${e.message}`);
});

req.end();
```


**Last Updated:** January 2026
