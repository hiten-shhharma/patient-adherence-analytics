"""
statistical_tests.py
----------------------
Formal significance testing to back up the driver claims with p-values,
not just descriptive percentages.

  - Chi-square test of independence: discontinuation vs. each categorical
    driver (insurance status, supply size, therapy class, region, age band)
  - Welch's t-test: PDC (Proportion of Days Covered) for insured vs.
    uninsured patients
"""

import pandas as pd
from scipy.stats import chi2_contingency, ttest_ind

OUT = "/home/claude/project/output"
master = pd.read_csv(f"{OUT}/patient_master_analytics.csv")

results = []

def chi_square_driver(col):
    table = pd.crosstab(master[col], master["discontinued_flag"])
    chi2, p, dof, _ = chi2_contingency(table)
    results.append({
        "test": f"Chi-square: discontinuation vs {col}",
        "statistic": round(chi2, 2),
        "p_value": p,
        "significant_at_0.05": p < 0.05,
    })

for col in ["insurance_status", "initial_supply_days", "therapy_class", "region", "age_band"]:
    chi_square_driver(col)

# Welch's t-test: PDC, insured vs uninsured
pdc_insured = master.loc[master["insurance_status"] == "Insured", "pdc"]
pdc_uninsured = master.loc[master["insurance_status"] == "Uninsured", "pdc"]
t_stat, p_val = ttest_ind(pdc_insured, pdc_uninsured, equal_var=False)
results.append({
    "test": "Welch t-test: PDC, Insured vs Uninsured",
    "statistic": round(t_stat, 2),
    "p_value": p_val,
    "significant_at_0.05": p_val < 0.05,
})

df = pd.DataFrame(results)
df.to_csv(f"{OUT}/statistical_tests.csv", index=False)
print(df.to_string(index=False))
