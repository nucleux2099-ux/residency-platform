
import sys
import os
from pathlib import Path

# Add app to path
sys.path.append(os.getcwd())

from app.services.csv_ingestion import ingest_patient_csv
from app.config import settings

# Mock settings paths for this test
# We need to point to the actual locations
BASE_DIR = Path("/Users/sarathchandrabhatla/Library/Mobile Documents/iCloud~md~obsidian/Documents/Thesis2099/residency-platform")
TEMPLATES_DIR = BASE_DIR / "packages/shared/templates"
SAMPLE_CSV = TEMPLATES_DIR / "patient-proforma-v3.sample.csv"
EVENT_STORE = BASE_DIR / "apps/api/data" / "repro_events.jsonl"
NOTES_ROOT = BASE_DIR / "apps/api/data" / "repro_notes"
VAULT_ROOT = BASE_DIR.parent # Assuming residency-platform is in the vault root, parent is vault

# Create dummy event store and notes root
EVENT_STORE.parent.mkdir(parents=True, exist_ok=True)
NOTES_ROOT.mkdir(parents=True, exist_ok=True)

print(f"Testing ingestion with {SAMPLE_CSV}")

with open(SAMPLE_CSV, "rb") as f:
    content = f.read()

try:
    result = ingest_patient_csv(
        content,
        EVENT_STORE,
        TEMPLATES_DIR,
        NOTES_ROOT,
        VAULT_ROOT
    )

    print("--- Ingestion Result ---")
    print(f"Total Rows: {result.total_rows}")
    print(f"Accepted: {result.accepted_rows}")
    print(f"Rejected: {result.rejected_rows}")
    if result.errors:
        print("Errors:")
        for err in result.errors:
            print(f"  Row {err.row_number}: {err.message}")

except Exception as e:
    print(f"CRITICAL FAILURE: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
if EVENT_STORE.exists():
    os.remove(EVENT_STORE)
import shutil
if NOTES_ROOT.exists():
    shutil.rmtree(NOTES_ROOT)
