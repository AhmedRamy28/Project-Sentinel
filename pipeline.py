import csv
from datetime import date, timedelta
from pathlib import Path

import requests

from generate_sentinel_log import generate_sentinel_log

API_KEY = "gGscoHYJYRJ0dJdEebDQp6uHAqP3SQaaVixYeZhw"
BASE_URL = "https://api.nasa.gov/neo/rest/v1/feed"
LOG_PATH = Path("data/raw/ground_station_log.csv")
IDS_PATH = Path("data/raw/extracted_ids.txt")
OUTPUT_PATH = Path("data/processed/clean_data.csv")

FIELDNAMES = [
    "neo_reference_id", "name",
    "max_diameter_km", "miss_distance_km", "miss_distance_lunar",
    "relative_velocity_kph", "absolute_magnitude_h",
    "size_to_distance_ratio", "scaled_size_to_distance_ratio",
    "approach_category", "priority_watch",
    "is_potentially_hazardous_asteroid",
    "observatory_code", "confidence_score",
]


def get_date_windows():
    """Build two adjacent 7-day (start, end) date-string windows ending today"""
    today = date.today()
    window1 = (today - timedelta(days=7)).isoformat(), today.isoformat()
    window2 = (today - timedelta(days=14)).isoformat(), (today - timedelta(days=8)).isoformat()
    return [window1, window2]


def safe_float(value, default=None):
    """Cast value to float; return default if the cast fails """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def fetch_neo_data(date_windows):
    """Pull and merge NEO records from the NeoWs feed across the given date windows """
    all_records = []
    for start_date, end_date in date_windows:
        params = {
            "start_date": start_date,
            "end_date": end_date,
            "api_key": API_KEY,
        }
        try:
            response = requests.get(BASE_URL, params=params)
            response.raise_for_status()
            payload = response.json()
        except requests.exceptions.RequestException as e:
            print(f"API call failed for {start_date} to {end_date}: {e}")
            continue

        for date_str, objects_on_date in payload["near_earth_objects"].items():
            all_records.extend(objects_on_date)
    print(f"Pulled {len(all_records)} total records across {len(date_windows)} windows.")
    return  all_records


def extract_and_log_ids(all_records):
    """Extract unique NEO ids, save them to disk, and generate the matching ground log"""
    neo_ids = [str(obj["neo_reference_id"]) for obj in all_records]
    neo_ids = list(dict.fromkeys(neo_ids))

    IDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    IDS_PATH.write_text("\n".join(neo_ids), encoding="utf8")
    print(f"Extracted {len(neo_ids)} unique NEO ids.")

    generate_sentinel_log(neo_ids, output_path=LOG_PATH)
    return neo_ids


def filter_cohort(all_records):
    """Drop records with an empty close_approach_data list """
    return [record for record in all_records if record["close_approach_data"]]


def impute_missing_magnitude(records):
    """Fill missing absolute_magnitude_h with the cohort median"""
    mags = [r["absolute_magnitude_h"] for r in records if r.get("absolute_magnitude_h") is not None]
    mags_sorted = sorted(mags)
    median_mag = mags_sorted[len(mags_sorted) // 2]

    for record in records:
        if record.get("absolute_magnitude_h") is None:
            record["absolute_magnitude_h"] = median_mag
    return records

def engineer_features(records):
    """Derive size_to_distance_ratio, approach_category, and priority_watch per record """
    for record in records:
        max_d = record["estimated_diameter"]["kilometers"]["estimated_diameter_max"]
        miss_lunar = safe_float(record["close_approach_data"][0]["miss_distance"]["lunar"])
        miss_km = safe_float(record["close_approach_data"][0]["miss_distance"]["kilometers"])
        velocity = safe_float(record["close_approach_data"][0]["relative_velocity"]["kilometers_per_hour"])

        record["max_diameter_km"] = max_d
        record["miss_distance_km"] = miss_km
        record["miss_distance_lunar"] = miss_lunar
        record["relative_velocity_kph"] = velocity
        record["size_to_distance_ratio"] = max_d / miss_lunar if miss_lunar else 0.0

        if miss_lunar <= 5:
            record["approach_category"] = "very_close"
        elif miss_lunar <= 20:
            record["approach_category"] = "close"
        elif miss_lunar <= 60:
            record["approach_category"] = "moderate"
        else:
            record["approach_category"] = "distant"

        record["priority_watch"] = 1 if (max_d >= 0.14 and miss_lunar <= 10) else 0

    return records


def join_ground_log(records, log_path=LOG_PATH):
    """Attach observatory_code and confidence_score from the ground-station log, by neo_id"""
    with open(log_path) as f:
        log_lookup = {row["neo_id"]: row for row in csv.DictReader(f)}

    for record in records:
        log_row = log_lookup.get(record["neo_reference_id"])
        record["observatory_code"] = log_row["observatory_code"] if log_row else None
        record["confidence_score"] = log_row["confidence_score"] if log_row else None
    return records


def scale_ratio(records):
    """Min-max scale size_to_distance_ratio into scaled_size_to_distance_ratio"""
    ratios = [r["size_to_distance_ratio"] for r in records]
    min_x, max_x = ratios[0], ratios[0]
    for x in ratios:
        if x < min_x:
            min_x = x
        if x > max_x:
            max_x = x

    for record in records:
        if max_x != min_x:
            record["scaled_size_to_distance_ratio"] = (record["size_to_distance_ratio"] - min_x) / (max_x - min_x)
        else:
            record["scaled_size_to_distance_ratio"] = 0.0
    return records


def validate(records):
    """Cross-tabulate priority_watch against is_potentially_hazardous_asteroid"""
    crosstab = {(True, True): 0, (True, False): 0, (False, True): 0, (False, False): 0}
    for record in records:
        key = (bool(record["priority_watch"]), record["is_potentially_hazardous_asteroid"])
        crosstab[key] += 1
    return crosstab


def write_clean_data(records, output_path=OUTPUT_PATH):
    """Write final records to data/processed/clean_data.csv"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    print(f"Wrote {len(records)} records to {output_path}")


def main():
    """Run the full Project Sentinel pipeline end-to-end"""
    date_windows = get_date_windows()
    all_records = fetch_neo_data(date_windows)
    extract_and_log_ids(all_records)
    cleaned = filter_cohort(all_records)
    cleaned = impute_missing_magnitude(cleaned)
    cleaned = engineer_features(cleaned)
    cleaned = join_ground_log(cleaned)
    cleaned = scale_ratio(cleaned)

    crosstab = validate(cleaned)
    print("Validation crosstab (priority_watch, is_potentially_hazardous_asteroid):", crosstab)

    n_total = len(cleaned)
    n_flagged = sum(1 for r in cleaned if r["priority_watch"] == 1)
    pct_reduction = (1 - (n_flagged / n_total)) * 100
    print(f"n_total={n_total} n_flagged={n_flagged} pct_workload_reduction={pct_reduction:.1f}%")

    write_clean_data(cleaned)


if __name__ == "__main__":
    main()