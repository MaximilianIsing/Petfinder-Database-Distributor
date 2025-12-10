"""
24/7 scraper service for College Board BigFuture.
Loops through colleges, scrapes data via Playwright, computes derived SAT/ACT 50th
percentiles and college score (same weighting as rateCollege), and upserts to scanned.csv.

Run (Linux-friendly):
  pip install playwright rapidfuzz
  playwright install chromium
  python scraper_service.py
"""

import csv
import json
import os
import re
import time
from contextlib import suppress
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rapidfuzz import fuzz
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright


# Data directory for persistent storage (mounted Render Disk)
# Use /data on Render (Linux), or local "data" directory for development (Windows)
import sys
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

SCANNED_CSV = os.path.join(DATA_DIR, "scanned.csv")
INPUT_CSV = os.path.join(DATA_DIR, "university_data.csv")
PROGRESS_JSON = os.path.join(DATA_DIR, "scraper_progress.json")
SLUG_CACHE = os.path.join(DATA_DIR, "slug_cache.json")
LOG_PATH = os.path.join(DATA_DIR, "scraper.log")
URL_MISSES_LOG = os.path.join(DATA_DIR, "slug_misses.log")
SLEEP_BETWEEN_COLLEGES = 15  # seconds


XPATHS = {
    # Overview
    "college_type": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[1]/div/div/div/div[2]",
    "avg_after_aid": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[3]/div/div/div/div[2]",
    "graduation_rate": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[5]/div/div/div/div[2]",
    "college_board_code": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/div[2]/div[2]",
    # Tabs
    "tab_admissions": "/html/body/div[1]/div/main/div[2]/div/div[4]/div[2]/div/div/div/ul/li[2]/a",
    "tab_academics": "/html/body/div[1]/div/main/div[2]/div/div[4]/div[2]/div/div/div/ul/li[3]/a",
    "tab_costs": "/html/body/div[1]/div/main/div[2]/div/div[4]/div[2]/div/div/div/ul/li[4]/a",
    "tab_campus": "/html/body/div[1]/div/main/div[2]/div/div[4]/div[2]/div/div/div/ul/li[5]/a",
    # Admissions
    "acceptance_rate": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/section[1]/div/ul/li[1]/div/div/div/div[2]",
    "sat_range": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/section[1]/div/ul/li[3]/div/div/div/div[2]",
    "act_range": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/section[1]/div/ul/li[4]/div/div/div/div[2]",
    "rd_due_date": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/section[1]/div/ul/li[2]/div/div/div/div[2]",
    "test_optional": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/section[3]/div/div/ul/li[4]/span[2]",
    "gpa_optional": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/section[3]/div/div/ul/li[1]/span[2]",
    # Academics
    "num_majors": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[2]/div/div/div/div[2]",
    "student_faculty_ratio": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[3]/div/div/div/div[2]",
    "retention_rate": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[4]/div/div/div/div[2]",
    # Costs
    "pct_receiving_aid": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[2]/div/div/div/div[2]",
    "avg_after_aid_costs": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[1]/div/div/div/div[2]",
    "avg_aid_package": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[3]/div/div/div/div[2]",
    # Campus Life
    "setting": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[1]/div/div/div/div[2]",
    "undergrad_students": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[2]/div/div/div/div[2]",
    "avg_housing_cost": "/html/body/div[1]/div/main/div[2]/div/div[5]/div/div[1]/div[1]/section/div/ul/li[3]/div/div/div/div[2]",
}


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)  # Flush to ensure immediate output
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()  # Ensure log file is written immediately


def log_slug_miss(name: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(URL_MISSES_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {name}\n")


def load_progress() -> int:
    if not os.path.exists(PROGRESS_JSON):
        return 0
    with open(PROGRESS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return int(data.get("index", 0))


def save_progress(idx: int) -> None:
    with open(PROGRESS_JSON, "w", encoding="utf-8") as f:
        json.dump({"index": idx}, f)


def load_slug_cache() -> Dict[str, str]:
    if not os.path.exists(SLUG_CACHE):
        return {}
    with open(SLUG_CACHE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_slug_cache(cache: Dict[str, str]) -> None:
    with open(SLUG_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def normalize_name(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^\w\s]", " ", name)
    name = re.sub(r"\b(university|college|institute|school|of|the|at)\b", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def slugify_name(name: str) -> str:
    slug = name.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug).strip("-")
    return slug


def read_colleges(path: str) -> List[dict]:
    colleges = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            colleges.append(row)
    return colleges


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    # Remove trailing asterisks often used as footnote markers
    text = re.sub(r"\*+$", "", text).strip()
    return text


def get_text(page, xpath: str) -> str:
    with suppress(PlaywrightTimeoutError):
        raw = page.locator(f"xpath={xpath}").inner_text(timeout=7000)
        return clean_text(raw)
    return ""


def get_text_fallback(page, primary_xpath: str, fallback_xpath: Optional[str] = None) -> str:
    text = get_text(page, primary_xpath)
    if text:
        return text
    if fallback_xpath:
        return get_text(page, fallback_xpath)
    return ""


def parse_percent(text: str):
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) / 100 if m else None


def parse_range(text: str):
    m = re.search(r"(\d{2,4})\s*[–-]\s*(\d{2,4})", text)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def parse_ratio(text: str):
    m = re.search(r"(\d+(?:\.\d+)?)\s*:\s*(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    num, den = float(m.group(1)), float(m.group(2))
    return num / den if den else None


def parse_int(text: str):
    m = re.search(r"([\d,]+)", text)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def parse_money(text: str):
    m = re.search(r"\$?\s*([\d,]+(?:\.\d+)?)", text)
    if not m:
        return None
    val = m.group(1).replace(",", "")
    return float(val) if "." in val else int(val)


def compute_college_score(fields):
    acceptance_rate = fields.get("acceptance_rate_pct")
    sat50 = fields.get("sat_50th_percentile")
    act50 = fields.get("act_50th_percentile")
    grad = fields.get("graduation_rate")
    retention = fields.get("retention_rate")
    earnings = None  # not scraped here
    enrollment = fields.get("undergrad_students_num")
    ratio = fields.get("student_faculty_ratio_num")

    acceptanceNorm = 0
    if acceptance_rate is not None and 0 <= acceptance_rate <= 1:
        acceptanceNorm = 1 - acceptance_rate
        if acceptance_rate < 0.2:
            acceptanceNorm = min(1, acceptanceNorm * 1.2)

    satNorm = 0
    if sat50:
        satNorm = max(0, min(1, (sat50 - 400) / (1600 - 400)))

    actNorm = 0
    if act50:
        actNorm = max(0, min(1, (act50 - 1) / (36 - 1)))

    testNorm = max(satNorm, actNorm)

    graduationNorm = grad if grad is not None else 0
    retentionNorm = retention if retention is not None else 0

    earningsNorm = 0
    if earnings:
        earningsNorm = max(0, min(1, (earnings - 30000) / (150000 - 30000)))

    enrollmentNorm = 0
    if enrollment:
        if 5000 <= enrollment <= 30000:
            enrollmentNorm = 0.8 + (0.2 * (1 - abs(enrollment - 15000) / 15000))
        elif enrollment > 30000:
            enrollmentNorm = 0.7
        else:
            enrollmentNorm = min(0.6, enrollment / 5000)

    ratioNorm = 0
    if ratio:
        ratioNorm = max(0, min(1, 1 - (ratio - 5) / 20))

    WEIGHTS = {
        "selectivity": 0.30,
        "testScores": 0.25,
        "graduation": 0.15,
        "retention": 0.10,
        "earnings": 0.10,
        "enrollment": 0.05,
        "facultyRatio": 0.05,
    }

    composite = (
        WEIGHTS["selectivity"] * acceptanceNorm
        + WEIGHTS["testScores"] * testNorm
        + WEIGHTS["graduation"] * graduationNorm
        + WEIGHTS["retention"] * retentionNorm
        + WEIGHTS["earnings"] * earningsNorm
        + WEIGHTS["enrollment"] * enrollmentNorm
        + WEIGHTS["facultyRatio"] * ratioNorm
    )

    return round(composite * 100)


def best_result_by_name(results, target_name: str) -> Optional[str]:
    target_norm = normalize_name(target_name)
    best = None
    best_score = 0
    for href, label in results:
        score = fuzz.token_sort_ratio(target_norm, normalize_name(label))
        if score > best_score:
            best_score = score
            best = href
    if best_score >= 85:
        return best
    return None


def swap_college_university(name: str) -> str:
    """Swap 'college' and 'university' in the name."""
    name = name.replace("College", "TEMP_SWAP", 1)
    name = name.replace("University", "College", 1)
    name = name.replace("TEMP_SWAP", "University", 1)
    name = name.replace("college", "temp_swap", 1)
    name = name.replace("university", "college", 1)
    name = name.replace("temp_swap", "university", 1)
    return name


def resolve_url(page, name: str, slug_cache: Dict[str, str]) -> Tuple[Optional[str], Optional[str]]:
    """Resolve URL and return (url, actual_name_used). Returns (None, None) if not found."""
    key = name.lower()
    if key in slug_cache:
        url = slug_cache[key]
        # Try to extract name from URL or use original
        # Since cached, we assume original name was used unless we track it separately
        return url, name

    # Try direct slug with original name
    slug = slugify_name(name)
    direct = f"https://bigfuture.collegeboard.org/colleges/{slug}"
    try:
        page.goto(direct, wait_until="domcontentloaded", timeout=12000)
        if "bigfuture.collegeboard.org/colleges/" in page.url and page.locator("main").is_visible():
            # Extract actual name from page
            actual_name = name
            try:
                # Try to get name from h1 on the page
                h1 = page.locator("h1").first
                if h1.is_visible(timeout=2000):
                    actual_name = h1.inner_text().strip()
            except PlaywrightTimeoutError:
                pass
            slug_cache[key] = page.url
            save_slug_cache(slug_cache)
            return page.url, actual_name
    except PlaywrightTimeoutError:
        pass

    # Fallback: search flow with original name
    try:
        page.goto("https://bigfuture.collegeboard.org/college-search", wait_until="domcontentloaded", timeout=12000)
        search_input = page.get_by_placeholder("Search by college name")
        search_input.fill(name, timeout=5000)
        search_input.press("Enter")
        page.wait_for_timeout(1500)
        links = page.locator("a[href*='/colleges/']").all()
        results = []
        for link in links[:10]:
            href = link.get_attribute("href") or ""
            label = link.inner_text().strip()
            if "/colleges/" in href:
                results.append((href if href.startswith("http") else f"https://bigfuture.collegeboard.org{href}", label))
        chosen = best_result_by_name(results, name)
        if chosen:
            # Extract the actual name from the best match result
            actual_name = name
            for href, label in results:
                if href == chosen:
                    actual_name = label
                    break
            slug_cache[key] = chosen
            save_slug_cache(slug_cache)
            return chosen, actual_name
    except PlaywrightTimeoutError:
        pass

    # Retry with swapped college/university
    swapped_name = swap_college_university(name)
    if swapped_name != name:
        # Try direct slug with swapped name
        slug_swapped = slugify_name(swapped_name)
        direct_swapped = f"https://bigfuture.collegeboard.org/colleges/{slug_swapped}"
        try:
            page.goto(direct_swapped, wait_until="domcontentloaded", timeout=12000)
            if "bigfuture.collegeboard.org/colleges/" in page.url and page.locator("main").is_visible():
                # Extract actual name from page
                actual_name = swapped_name
                try:
                    # Try to get name from h1 on the page
                    h1 = page.locator("h1").first
                    if h1.is_visible(timeout=2000):
                        actual_name = h1.inner_text().strip()
                except PlaywrightTimeoutError:
                    pass
                slug_cache[key] = page.url
                save_slug_cache(slug_cache)
                return page.url, actual_name
        except PlaywrightTimeoutError:
            pass

        # Try search with swapped name
        try:
            page.goto("https://bigfuture.collegeboard.org/college-search", wait_until="domcontentloaded", timeout=12000)
            search_input = page.get_by_placeholder("Search by college name")
            search_input.fill(swapped_name, timeout=5000)
            search_input.press("Enter")
            page.wait_for_timeout(1500)
            links = page.locator("a[href*='/colleges/']").all()
            results = []
            for link in links[:10]:
                href = link.get_attribute("href") or ""
                label = link.inner_text().strip()
                if "/colleges/" in href:
                    results.append((href if href.startswith("http") else f"https://bigfuture.collegeboard.org{href}", label))
            chosen = best_result_by_name(results, name)
            if chosen:
                slug_cache[key] = chosen
                save_slug_cache(slug_cache)
                # Extract the actual name from the best match result
                actual_name = swapped_name
                for href, label in results:
                    if href == chosen:
                        actual_name = label
                        break
                return chosen, actual_name
        except PlaywrightTimeoutError:
            pass

    return None, None


def scrape_one(page, url: str) -> Dict[str, str]:
    data = {}
    page.goto(url, wait_until="networkidle", timeout=20000)

    # Overview
    data["college_type"] = get_text(page, XPATHS["college_type"])
    data["avg_after_aid"] = get_text(page, XPATHS["avg_after_aid"])
    data["graduation_rate"] = get_text(page, XPATHS["graduation_rate"])
    data["college_board_code"] = get_text(page, XPATHS["college_board_code"])

    # Admissions
    page.locator(f"xpath={XPATHS['tab_admissions']}").click(timeout=7000)
    page.wait_for_timeout(1200)
    data["acceptance_rate"] = get_text(page, XPATHS["acceptance_rate"])
    data["sat_range"] = get_text_fallback(
        page,
        XPATHS["sat_range"],
        "//li[.//text()[contains(translate(., 'sat range', 'SAT RANGE'), 'SAT RANGE')]]//*[self::div or self::span][last()]",
    )
    data["act_range"] = get_text_fallback(
        page,
        XPATHS["act_range"],
        "//li[.//text()[contains(translate(., 'act range', 'ACT RANGE'), 'ACT RANGE')]]//*[self::div or self::span][last()]",
    )
    data["rd_due_date"] = get_text(page, XPATHS["rd_due_date"])
    data["test_optional"] = get_text(page, XPATHS["test_optional"])
    data["gpa_optional"] = get_text(page, XPATHS["gpa_optional"])

    # Academics
    page.locator(f"xpath={XPATHS['tab_academics']}").click(timeout=7000)
    page.wait_for_timeout(800)
    data["num_majors"] = get_text(page, XPATHS["num_majors"])
    data["student_faculty_ratio"] = get_text(page, XPATHS["student_faculty_ratio"])
    data["retention_rate"] = get_text(page, XPATHS["retention_rate"])

    # Costs
    page.locator(f"xpath={XPATHS['tab_costs']}").click(timeout=7000)
    page.wait_for_timeout(800)
    data["pct_receiving_aid"] = get_text(page, XPATHS["pct_receiving_aid"])
    data["avg_after_aid_costs"] = get_text(page, XPATHS["avg_after_aid_costs"])
    data["avg_aid_package"] = get_text(page, XPATHS["avg_aid_package"])

    # Campus Life
    page.locator(f"xpath={XPATHS['tab_campus']}").click(timeout=7000)
    page.wait_for_timeout(800)
    data["setting"] = get_text(page, XPATHS["setting"])
    data["undergrad_students"] = get_text(page, XPATHS["undergrad_students"])
    data["avg_housing_cost"] = get_text(page, XPATHS["avg_housing_cost"])

    # Derived fields
    # College type split
    if data.get("college_type"):
        raw_ct = data["college_type"]
        if "." in raw_ct:
            left, right = [p.strip() for p in raw_ct.split(".", 1)]
            data["college_years"] = parse_int(left)
            data["college_type"] = right
        else:
            if "•" in raw_ct:
                parts = [p.strip() for p in raw_ct.split("•") if p.strip()]
            else:
                parts = [p.strip() for p in re.split(r"[•|\-]", raw_ct) if p.strip()]
            for p in parts:
                if "year" in p:
                    data["college_years"] = parse_int(p)
            if parts:
                data["college_type"] = parts[-1]

    data["avg_after_aid_val"] = parse_money(data.get("avg_after_aid", ""))
    data["avg_after_aid_costs_val"] = parse_money(data.get("avg_after_aid_costs", ""))
    data["avg_aid_package_val"] = parse_money(data.get("avg_aid_package", ""))
    data["avg_housing_cost_val"] = parse_money(data.get("avg_housing_cost", ""))
    data["pct_receiving_aid_pct"] = parse_percent(data.get("pct_receiving_aid", ""))

    sat_low, sat_high = parse_range(data.get("sat_range", ""))
    act_low, act_high = parse_range(data.get("act_range", ""))
    data["sat_25th_percentile"] = sat_low
    data["sat_75th_percentile"] = sat_high
    data["act_25th_percentile"] = act_low
    data["act_75th_percentile"] = act_high
    data["sat_50th_percentile"] = round((sat_low + sat_high) / 2) if sat_low and sat_high else None
    data["act_50th_percentile"] = round((act_low + act_high) / 2) if act_low and act_high else None
    data["acceptance_rate_pct"] = parse_percent(data.get("acceptance_rate", ""))
    data["graduation_rate_pct"] = parse_percent(data.get("graduation_rate", ""))
    data["retention_rate_pct"] = parse_percent(data.get("retention_rate", ""))
    data["undergrad_students_num"] = parse_int(data.get("undergrad_students", ""))
    data["student_faculty_ratio_num"] = parse_ratio(data.get("student_faculty_ratio", ""))
    data["num_majors_num"] = parse_int(data.get("num_majors", ""))
    data["college_board_code_num"] = parse_int(data.get("college_board_code", ""))

    data["college_score"] = compute_college_score(
        {
            "acceptance_rate_pct": data["acceptance_rate_pct"],
            "sat_50th_percentile": data["sat_50th_percentile"],
            "act_50th_percentile": data["act_50th_percentile"],
            "graduation_rate": data["graduation_rate_pct"],
            "retention_rate": data["retention_rate_pct"],
            "undergrad_students_num": data["undergrad_students_num"],
            "student_faculty_ratio_num": data["student_faculty_ratio_num"],
        }
    )

    return data


def get_scanned_csv_fields() -> List[str]:
    """Return the ordered field names for scanned.csv (cleaned/refined schema)."""
    return [
        "name",
        "college_type",
        "college_years",
        "acceptance_rate_pct",
        "sat_25th_percentile",
        "sat_75th_percentile",
        "sat_50th_percentile",
        "act_25th_percentile",
        "act_75th_percentile",
        "act_50th_percentile",
        "graduation_rate_pct",
        "retention_rate_pct",
        "pct_receiving_aid_pct",
        "avg_after_aid_val",
        "avg_after_aid_costs_val",
        "avg_aid_package_val",
        "avg_housing_cost_val",
        "undergrad_students_num",
        "student_faculty_ratio_num",
        "num_majors_num",
        "college_board_code_num",
        "college_score",
        # keep key categorical/text identifiers
        "setting",
        "rd_due_date",
        "test_optional",
        "gpa_optional",
    ]


def upsert_csv(name: str, fields: Dict[str, str], csv_path: str = SCANNED_CSV, original_name: Optional[str] = None) -> None:
    """Upsert CSV row. If original_name is provided, use it to find the row, then update name."""
    # Keep only cleaned/refined fields (no raw text money/percent/range strings)
    ordered_fields = get_scanned_csv_fields()

    rows = []
    found = False
    search_name = (original_name or name).lower()
    
    # Read all rows, preserving order
    if os.path.exists(csv_path):
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            for r in reader:
                if r.get("name", "").strip().lower() == search_name:
                    # Update matching row in place, preserving existing values when scraped value is missing
                    found = True
                    updated_row = {col: r.get(col, "") for col in ordered_fields}
                    updated_row["name"] = name
                    for k, v in fields.items():
                        if k in updated_row:
                            # Only update if we have a new value (not None, not empty string)
                            # Preserve existing value if scraped value is missing
                            if v is not None and v != "":
                                updated_row[k] = v
                            # If existing value is empty but we have None, keep empty (don't overwrite)
                    rows.append(updated_row)
                else:
                    # Preserve other rows, normalized to ordered_fields structure
                    normalized_row = {col: r.get(col, "") for col in ordered_fields}
                    rows.append(normalized_row)

    # If not found, append new row (shouldn't happen if init was run)
    if not found:
        row = {col: "" for col in ordered_fields}
        row["name"] = name
        for k, v in fields.items():
            if k in row:
                row[k] = "" if v is None else v
        rows.append(row)

    tmp = csv_path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ordered_fields)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, csv_path)


def main():
    colleges = read_colleges(INPUT_CSV)
    start_idx = load_progress()
    slug_cache = load_slug_cache()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )

        idx = start_idx
        while True:
            college = colleges[idx % len(colleges)]
            name = college.get("name", "").strip()
            try:
                url, actual_name = resolve_url(page, name, slug_cache)
                if not url:
                    log(f"Skip (no URL found): {name}")
                    log_slug_miss(name)
                else:
                    data = scrape_one(page, url)
                    # Use actual_name (may be swapped) to update the CSV
                    # This ensures the name matches what's on College Board
                    upsert_csv(actual_name, data, original_name=name)
                    if actual_name != name:
                        log(f"Scraped {name} -> {url} (name updated to: {actual_name})")
                    else:
                        log(f"Scraped {name} -> {url}")
            except Exception as e:  # noqa: BLE001
                log(f"Error scraping {name}: {e}")

            idx += 1
            save_progress(idx)
            time.sleep(SLEEP_BETWEEN_COLLEGES)

        browser.close()


if __name__ == "__main__":
    main()

