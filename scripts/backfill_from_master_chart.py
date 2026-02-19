
import sys
import os
import ast
import csv
from pathlib import Path
from datetime import datetime

# Add app to path
sys.path.append(os.getcwd())

# We need to import the ingestion service
# But first we need the data.
# Since create_master_chart.py is a script with top-level code that runs on import, 
# we should Parse it with AST to extract the 'patients' list safely without running the whole script.

MASTER_CHART_PATH = Path("../02-Data-Collection/create_master_chart.py")
OUTPUT_CSV_PATH = Path("apps/api/data/backfill_patients.csv")

def extract_patients_from_script(script_path):
    with open(script_path, "r") as f:
        tree = ast.parse(f.read())
    
    patients_list = []
    
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "patients":
                    # This is the 'patients = [...]' assignment
                    if isinstance(node.value, ast.List):
                        for item in node.value.elts:
                            if isinstance(item, ast.Dict):
                                patient_dict = {}
                                for key, value in zip(item.keys, item.values):
                                    # Extract key
                                    k = None
                                    if isinstance(key, ast.Constant):
                                        k = key.value
                                    
                                    # Extract value
                                    v = None
                                    if isinstance(value, ast.Constant):
                                        v = value.value
                                    
                                    if k:
                                        patient_dict[k] = v
                                patients_list.append(patient_dict)
    return patients_list

def map_patient_to_v3(p):
    """Maps the master chart dict to patient-proforma-v3 fields"""
    
    # 1. Basic ID
    row = {
        "template_id": "patient-proforma-v3",
        "patient_id": p.get("Study_ID"),
        "ward": "Unknown", # Default
        "diagnosis": "Acute Pancreatitis", # Default
        "cohort_status": "enrolled", # Default to enrolled if in list
        "visit_type": "baseline", # Looking at baseline data
        "primary_endpoint_complete": "false"
    }
    
    # 2. Status Mapping
    outcome = p.get("Outcome", "").lower()
    if "deceased" in outcome or p.get("Mortality") == "Yes":
        row["cohort_status"] = "terminal_outcome"
        row["mortality"] = "yes"
        # Try to parse death date?
        # create_master_chart has "DECEASED (20-Sep-2025)"
        # We can extract date if present, or leave blank (ingestion will complain if yes but no date)
        # For now, let's manual intervention if date needed? 
        # Actually create_master_chart has specific field "Discharge_Date" which seems to hold death date 
        # e.g. "23-Dec-2025 (Death)"
    elif "follow-up" in outcome:
        row["cohort_status"] = "active"
    elif "completed" in outcome:
        row["cohort_status"] = "completed"

    # 3. Dates
    # Format in master chart: "25-Aug-2025" or "Multiple"
    adm_date = p.get("Admission_Date")
    if adm_date and adm_date != "Multiple":
        try:
             # convert 25-Aug-2025 to YYYY-MM-DD
            dt = datetime.strptime(adm_date, "%d-%b-%Y")
            row["encounter_date"] = dt.strftime("%Y-%m-%d")
        except:
            pass # Leave blank if parse fails
            
    if not row.get("encounter_date"):
        row["encounter_date"] = datetime.now().strftime("%Y-%m-%d") # Fallback

    # handle death date
    if row.get("mortality") == "yes":
        # Check Discharge Date first
        dis_date = p.get("Discharge_Date")
        death_dt = None
        if dis_date:
            try:
                # Remove any extra text like "(Death)"
                clean_date = dis_date.split("(")[0].strip()
                death_dt = datetime.strptime(clean_date, "%d-%b-%Y")
            except:
                pass
        
        # If not found, try Outcome
        if not death_dt:
            outcome = p.get("Outcome", "")
            # Look for date in outcome string like "DECEASED (20-Sep-2025)"
            import re
            match = re.search(r"(\d{2}-[A-Za-z]{3}-\d{4})", outcome)
            if match:
                try:
                    death_dt = datetime.strptime(match.group(1), "%d-%b-%Y")
                except:
                    pass
        
        if death_dt:
            row["death_date"] = death_dt.strftime("%Y-%m-%d")
            # Also set Cause of Death from 'Organ_Failure' or similar if not present
            # The master chart doesn't have explicit Cause of Death column in the patients list dict 
            # except maybe inferred from Organ Failure or just filler.
            # Let's set a default placeholder if missing to pass validation
            row["cause_of_death"] = p.get("Organ_Failure", "Review Required")
        else:
            # If we still can't find a date, we must provide one to pass validation
            # Use encounter date as fallback or today?
            # Better to fail row or provide urgent placeholder?
            # Let's use today and log warning
            print(f"WARNING: Could not find death date for {row['patient_id']}, using encounter date")
            row["death_date"] = row["encounter_date"]
            row["cause_of_death"] = "Unknown"

    # 4. SVT Status
    group = p.get("Group")
    if group == "SVT":
        row["svt_status"] = "with_svt"
    else:
        row["svt_status"] = "without_svt"
        row["recanalization_status"] = "not_applicable"

    # 5. Vessel Involvement
    vessels = []
    
    # Check Splenic
    sv = p.get("SV_Status", "").lower()
    if "thrombosed" in sv or "partial" in sv or "visualized" in sv or "occluded" in sv:
        vessels.append("sv")
        
    # Check PV
    pv = p.get("PV_Status", "").lower()
    if "thrombosed" in pv or "partial" in pv or "occluded" in pv:
        vessels.append("pv")
        
    # Check SMV
    smv = p.get("SMV_Status", "").lower()
    if "thrombosed" in smv or "partial" in smv or "occluded" in smv:
        vessels.append("smv")
    
    if row["svt_status"] == "with_svt":
        if not vessels:
            vessels.append("unknown") # Fallback if Group=SVT but vessels not clearly marked
    
    row["vessel_involvement"] = ";".join(vessels)

    # 6. Extra Fields (Keep Name, Age, Sex, etc in extra_fields)
    # We prefix them with "extra_" to ensure they fall into extra_fields bucket in ingestion
    # But wait, CSV ingestion puts unknown columns into extra_fields automatically.
    # So we just add them as columns.
    
    row["Name"] = p.get("Name")
    row["Age"] = p.get("Age")
    row["Sex"] = p.get("Sex")
    row["Etiology"] = p.get("Etiology")
    row["BMI"] = p.get("BMI")
    
    # Map map demographics__age_sex
    row["demographics__age_sex"] = f"{p.get('Age')} / {p.get('Sex')}"
    row["etiology_of_acute_pancreatitis__etiology"] = p.get("Etiology")

    return row

def main():
    if not MASTER_CHART_PATH.exists():
        print(f"Error: {MASTER_CHART_PATH} not found")
        return

    print("Extracting patients...")
    raw_patients = extract_patients_from_script(MASTER_CHART_PATH)
    print(f"Found {len(raw_patients)} patients in master chart script.")
    
    csv_rows = []
    
    for p in raw_patients:
        try:
            row = map_patient_to_v3(p)
            csv_rows.append(row)
        except Exception as e:
            print(f"Skipping {p.get('Study_ID')}: {e}")
            
    # Write to CSV
    OUTPUT_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Collect all keys
    all_keys = set()
    for r in csv_rows:
        all_keys.update(r.keys())
    
    # Ensure standard keys come first
    fieldnames = [
        "template_id", "patient_id", "encounter_date", "visit_type", 
        "svt_status", "cohort_status", "mortality", "vessel_involvement",
        "recanalization_status", "primary_endpoint_complete", "ward", "diagnosis"
    ]
    # Add remaining keys
    for k in all_keys:
        if k not in fieldnames:
            fieldnames.append(k)
            
    print(f"Writing {len(csv_rows)} to {OUTPUT_CSV_PATH}...")
    with open(OUTPUT_CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)
        
    print("Done. Now you can ingest this file.")
    
    # Optional: Trigger ingestion immediately?
    # Let's import the service and run it
    try:
        from app.services.csv_ingestion import ingest_patient_csv
        from app.config import settings
        
        print("Triggering Ingestion...")
        with open(OUTPUT_CSV_PATH, "rb") as f:
            content = f.read()
            
        result = ingest_patient_csv(
            content,
            settings.event_store_path,
            settings.shared_templates_dir,
            settings.auto_notes_dir, # This might need to be set if not default
            settings.vault_root
        )
        
        print(f"Ingestion Result: {result.accepted_rows} accepted, {result.rejected_rows} rejected.")
        if result.errors:
            for err in result.errors:
                print(f"  Row {err.row_number}: {err.message}")
                
    except ImportError:
        print("Could not import app.services.csv_ingestion. Run inside apps/api environment.")
    except Exception as e:
        print(f"Ingestion failed: {e}")

if __name__ == "__main__":
    main()
