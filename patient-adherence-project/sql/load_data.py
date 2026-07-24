"""
load_data.py
Loads patients.csv and refills.csv into the MySQL `therapy_adherence` database.
Run AFTER schema.sql has been applied.
"""
import pandas as pd
import pymysql

conn = pymysql.connect(
    host="localhost",
    user="analytics_user",
    password="Analytics@2026",
    database="therapy_adherence",
    local_infile=True,
)
cur = conn.cursor()

patients = pd.read_csv("/home/claude/project/data/patients.csv")
refills = pd.read_csv("/home/claude/project/data/refills.csv")

# --- load patients ---
patient_rows = list(patients.itertuples(index=False, name=None))
cur.executemany(
    """INSERT INTO patients
       (patient_id, age, gender, region, insurance_status, therapy_class,
        initial_supply_days, therapy_start_date)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
    patient_rows,
)
conn.commit()
print(f"Loaded {cur.rowcount if cur.rowcount != -1 else len(patient_rows)} patients (batch insert)")

# --- load refills in chunks ---
refill_rows = list(refills.itertuples(index=False, name=None))
CHUNK = 2000
for i in range(0, len(refill_rows), CHUNK):
    chunk = refill_rows[i:i + CHUNK]
    cur.executemany(
        """INSERT INTO refills
           (refill_id, patient_id, fill_number, fill_date, days_supply, gap_from_expected_days)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        chunk,
    )
    conn.commit()

cur.execute("SELECT COUNT(*) FROM patients")
print("patients rows in DB:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM refills")
print("refills rows in DB:", cur.fetchone()[0])

cur.close()
conn.close()
