"""
adherence_analysis.py
----------------------
Patient Therapy Adherence & Persistency Analytics
Python / pandas layer.

Pulls patients + refills from MySQL (falls back to local CSVs if the
DB isn't reachable), computes:

  1. PDC (Proportion of Days Covered) -- the industry-standard
     medication adherence metric.
  2. Persistency (days on therapy before a 60-day lapse / discontinuation).
  3. Discontinuation-driver breakdowns (insurance, supply size,
     therapy class, region, age band).
  4. A risk-scored patient outreach watchlist.

Outputs CSVs into /home/claude/project/output/ which are then fed into
the Excel dashboard builder (build_excel_dashboard.py).
"""

import os
import pandas as pd
import numpy as np
from datetime import date

STUDY_END = pd.Timestamp("2025-12-31")
LAPSE_THRESHOLD_DAYS = 60

OUTPUT_DIR = "/home/claude/project/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------
# 1. Load data (MySQL first, CSV fallback)
# ---------------------------------------------------------------------
def load_data():
    try:
        import pymysql
        conn = pymysql.connect(
            host="localhost",
            user="analytics_user",
            password="Analytics@2026",
            database="therapy_adherence",
        )
        patients = pd.read_sql("SELECT * FROM patients", conn)
        refills = pd.read_sql("SELECT * FROM refills", conn)
        conn.close()
        print("Loaded data from MySQL (therapy_adherence).")
    except Exception as e:
        print(f"MySQL unavailable ({e}); falling back to CSV files.")
        patients = pd.read_csv("/home/claude/project/data/patients.csv")
        refills = pd.read_csv("/home/claude/project/data/refills.csv")

    patients["therapy_start_date"] = pd.to_datetime(patients["therapy_start_date"])
    refills["fill_date"] = pd.to_datetime(refills["fill_date"])
    return patients, refills


# ---------------------------------------------------------------------
# 2. PDC (Proportion of Days Covered)
#    PDC = (days covered by supply, within the observation window,
#           deduplicated for overlap) / (days in observation window)
#    Observation window = therapy_start_date -> last_fill_date + last_supply
#    (industry-standard PDC calculation)
# ---------------------------------------------------------------------
def compute_pdc(patients: pd.DataFrame, refills: pd.DataFrame) -> pd.DataFrame:
    records = []
    refills_sorted = refills.sort_values(["patient_id", "fill_date"])

    for pid, grp in refills_sorted.groupby("patient_id"):
        start = grp["fill_date"].min()
        # build day-covered set using intervals, merging overlaps
        intervals = []
        for _, r in grp.iterrows():
            s = r["fill_date"]
            e = r["fill_date"] + pd.Timedelta(days=int(r["days_supply"]) - 1)
            intervals.append((s, e))
        intervals.sort()
        merged = []
        for s, e in intervals:
            if merged and s <= merged[-1][1] + pd.Timedelta(days=1):
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        covered_days = sum((e - s).days + 1 for s, e in merged)

        obs_end = min(grp["fill_date"].max() + pd.Timedelta(days=int(grp["days_supply"].iloc[-1]) - 1), STUDY_END)
        obs_days = (obs_end - start).days + 1
        pdc = min(covered_days / obs_days, 1.0) if obs_days > 0 else np.nan

        records.append({"patient_id": pid, "pdc": round(pdc, 4), "obs_days": obs_days,
                         "covered_days": covered_days})

    return pd.DataFrame(records)


# ---------------------------------------------------------------------
# 3. Persistency (discontinuation flag, days persisted)
# ---------------------------------------------------------------------
def compute_persistency(refills: pd.DataFrame) -> pd.DataFrame:
    agg = refills.groupby("patient_id").agg(
        total_fills=("refill_id", "count"),
        first_fill_date=("fill_date", "min"),
        last_fill_date=("fill_date", "max"),
    ).reset_index()

    agg["days_since_last_fill"] = (STUDY_END - agg["last_fill_date"]).dt.days
    agg["days_persisted"] = (agg["last_fill_date"] - agg["first_fill_date"]).dt.days
    agg["discontinued_flag"] = (agg["days_since_last_fill"] > LAPSE_THRESHOLD_DAYS).astype(int)
    return agg


# ---------------------------------------------------------------------
# 4. Late-refill behavior (for the risk score)
# ---------------------------------------------------------------------
def compute_avg_gap(refills: pd.DataFrame) -> pd.DataFrame:
    late = refills[refills["fill_number"] > 1]
    avg_gap = late.groupby("patient_id")["gap_from_expected_days"].mean().reset_index()
    avg_gap.columns = ["patient_id", "avg_gap_days"]
    return avg_gap


# ---------------------------------------------------------------------
# 5. Discontinuation driver tables
# ---------------------------------------------------------------------
def driver_tables(master: pd.DataFrame) -> dict:
    tables = {}

    def rate_table(group_col):
        g = master.groupby(group_col).agg(
            patient_count=("patient_id", "count"),
            discontinued_count=("discontinued_flag", "sum"),
            avg_pdc=("pdc", "mean"),
            avg_days_persisted=("days_persisted", "mean"),
        ).reset_index()
        g["discontinuation_rate_pct"] = (100 * g["discontinued_count"] / g["patient_count"]).round(1)
        g["persistency_rate_pct"] = (100 - g["discontinuation_rate_pct"]).round(1)
        g["avg_pdc"] = g["avg_pdc"].round(3)
        g["avg_days_persisted"] = g["avg_days_persisted"].round(0)
        return g.sort_values("discontinuation_rate_pct", ascending=False)

    tables["by_insurance"] = rate_table("insurance_status")
    tables["by_supply"] = rate_table("initial_supply_days")
    tables["by_therapy_class"] = rate_table("therapy_class")
    tables["by_region"] = rate_table("region")

    master["age_band"] = pd.cut(
        master["age"], bins=[17, 29, 44, 59, 120],
        labels=["18-29", "30-44", "45-59", "60+"]
    )
    tables["by_age_band"] = rate_table("age_band")

    # headline KPI numbers (mirrors the resume bullet)
    ins = tables["by_insurance"].set_index("insurance_status")["discontinuation_rate_pct"]
    churn_ratio = round(ins.get("Uninsured", np.nan) / ins.get("Insured", np.nan), 2)

    supply = tables["by_supply"].set_index("initial_supply_days")["persistency_rate_pct"]
    persistency_gap = round(supply.get(90, np.nan) - supply.get(30, np.nan), 1)

    tables["headline_kpis"] = pd.DataFrame([
        {"metric": "Uninsured vs Insured churn ratio", "value": f"{churn_ratio}x"},
        {"metric": "90-day vs 30-day supply persistency gap", "value": f"+{persistency_gap} pts"},
        {"metric": "Total patients", "value": len(master)},
        {"metric": "Total refill events", "value": int(master["total_fills"].sum())},
        {"metric": "Overall discontinuation rate", "value": f"{round(100*master['discontinued_flag'].mean(),1)}%"},
        {"metric": "Overall average PDC", "value": round(master["pdc"].mean(), 3)},
    ])

    return tables


# ---------------------------------------------------------------------
# 6. Prioritized outreach watchlist
# ---------------------------------------------------------------------
def build_watchlist(master: pd.DataFrame) -> pd.DataFrame:
    active = master[master["discontinued_flag"] == 0].copy()
    at_risk = active[
        (active["days_since_last_fill"] >= 31) & (active["days_since_last_fill"] <= 60)
    ].copy()

    at_risk["risk_score"] = (
        (at_risk["days_since_last_fill"].clip(upper=60) / 60.0) * 50
        + (at_risk["insurance_status"] == "Uninsured").astype(int) * 25
        + (at_risk["initial_supply_days"] == 30).astype(int) * 15
        + (at_risk["avg_gap_days"].clip(lower=0) / 30.0).clip(upper=1) * 10
    ).round(0)

    at_risk["priority_tier"] = pd.cut(
        at_risk["risk_score"], bins=[-1, 40, 65, 100],
        labels=["Low", "Medium", "High"]
    )

    cols = ["patient_id", "age", "gender", "region", "insurance_status",
            "therapy_class", "initial_supply_days", "total_fills",
            "last_fill_date", "days_since_last_fill", "avg_gap_days",
            "pdc", "risk_score", "priority_tier"]
    return at_risk[cols].sort_values("risk_score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------
# main
# ---------------------------------------------------------------------
def main():
    patients, refills = load_data()

    pdc_df = compute_pdc(patients, refills)
    persistency_df = compute_persistency(refills)
    gap_df = compute_avg_gap(refills)

    master = (
        patients
        .merge(persistency_df, on="patient_id", how="left")
        .merge(pdc_df, on="patient_id", how="left")
        .merge(gap_df, on="patient_id", how="left")
    )
    master["avg_gap_days"] = master["avg_gap_days"].fillna(0)

    tables = driver_tables(master)
    watchlist = build_watchlist(master)

    # ---- save everything ----
    master.to_csv(f"{OUTPUT_DIR}/patient_master_analytics.csv", index=False)
    watchlist.to_csv(f"{OUTPUT_DIR}/outreach_watchlist.csv", index=False)
    for name, df in tables.items():
        df.to_csv(f"{OUTPUT_DIR}/driver_{name}.csv", index=False)

    print("\n=== HEADLINE KPIs ===")
    print(tables["headline_kpis"].to_string(index=False))
    print(f"\nWatchlist size: {len(watchlist)} patients")
    print(f"\nAll outputs written to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
