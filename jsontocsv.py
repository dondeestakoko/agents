import json
import csv

# ---- INPUT / OUTPUT FILES ----
json_file = "emails_classified.json"
csv_file = "emails_classified.csv"

# ---- LOAD JSON ----
with open(json_file, "r", encoding="utf-8") as f:
    data = json.load(f)

# ---- WRITE CSV ----
with open(csv_file, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)

    # CSV HEADER
    writer.writerow(["id", "categorie", "subject", "urgence", "synthese"])

    # ROWS WITH AUTO-INCREMENT ID
    for i, item in enumerate(data, start=1):
        writer.writerow([
            i,
            item.get("categorie", ""),
            item.get("subject", ""),
            item.get("urgence", ""),
            item.get("synthese", "")
        ])

print("✔️ CSV file created:", csv_file)
