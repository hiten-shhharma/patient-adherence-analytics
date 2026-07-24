"""
survival_analysis.py
----------------------
Kaplan-Meier persistency (survival) analysis.

Goes beyond a simple "% discontinued" rate: models TIME-TO-DISCONTINUATION
properly, accounting for right-censoring (patients still active at the
study cutoff haven't "failed" yet -- they're censored, not persistent
forever).

Produces:
  - Kaplan-Meier persistency curves by Insurance Status and by Supply Size
    (output/km_curve_insurance.png, output/km_curve_supply.png)
  - Log-rank test p-values quantifying whether the curves are
    statistically significantly different
  - Median persistency time (days) per group
  - A Cox Proportional Hazards model quantifying each driver's effect
    on discontinuation hazard, holding the others constant
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from lifelines import KaplanMeierFitter, CoxPHFitter
from lifelines.statistics import logrank_test, multivariate_logrank_test

OUT = "/home/claude/project/output"
plt.rcParams["font.family"] = "DejaVu Sans"

master = pd.read_csv(f"{OUT}/patient_master_analytics.csv")

# lifelines convention: duration = time observed, event_observed = 1 if the
# event (discontinuation) happened, 0 if censored (still active at cutoff)
master["duration"] = master["days_persisted"].clip(lower=1)
master["event"] = master["discontinued_flag"]

results_log = []

# ---------------------------------------------------------------------
# 1. KM curve + log-rank test: Insurance Status
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 5))
kmf = KaplanMeierFitter()
medians = {}
for status, color in [("Insured", "#1F4E78"), ("Uninsured", "#C0504D")]:
    mask = master["insurance_status"] == status
    kmf.fit(master.loc[mask, "duration"], master.loc[mask, "event"], label=status)
    kmf.plot_survival_function(ax=ax, color=color, ci_show=True)
    medians[status] = kmf.median_survival_time_

ax.set_title("Therapy Persistency by Insurance Status (Kaplan-Meier)", fontsize=13, fontweight="bold")
ax.set_xlabel("Days since therapy start")
ax.set_ylabel("Proportion still persistent")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/km_curve_insurance.png", dpi=150)
plt.close(fig)

g1 = master.loc[master["insurance_status"] == "Insured"]
g2 = master.loc[master["insurance_status"] == "Uninsured"]
lr_ins = logrank_test(g1["duration"], g2["duration"], g1["event"], g2["event"])
results_log.append({
    "comparison": "Insured vs Uninsured",
    "median_days_group1": round(medians["Insured"], 0),
    "median_days_group2": round(medians["Uninsured"], 0),
    "logrank_p_value": lr_ins.p_value,
    "significant_at_0.05": lr_ins.p_value < 0.05,
})

# ---------------------------------------------------------------------
# 2. KM curve + log-rank test: Supply Size
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 5))
kmf2 = KaplanMeierFitter()
supply_colors = {30: "#C0504D", 60: "#F2B134", 90: "#1F4E78"}
medians_supply = {}
for supply in [30, 60, 90]:
    mask = master["initial_supply_days"] == supply
    kmf2.fit(master.loc[mask, "duration"], master.loc[mask, "event"], label=f"{supply}-day supply")
    kmf2.plot_survival_function(ax=ax, color=supply_colors[supply], ci_show=True)
    medians_supply[supply] = kmf2.median_survival_time_

ax.set_title("Therapy Persistency by Initial Supply Size (Kaplan-Meier)", fontsize=13, fontweight="bold")
ax.set_xlabel("Days since therapy start")
ax.set_ylabel("Proportion still persistent")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/km_curve_supply.png", dpi=150)
plt.close(fig)

mv_supply = multivariate_logrank_test(
    master["duration"], master["initial_supply_days"], master["event"]
)
results_log.append({
    "comparison": "30 vs 60 vs 90 day supply (overall)",
    "median_days_group1": round(medians_supply[30], 0),
    "median_days_group2": round(medians_supply[90], 0),
    "logrank_p_value": mv_supply.p_value,
    "significant_at_0.05": mv_supply.p_value < 0.05,
})

# ---------------------------------------------------------------------
# 3. KM curve by Therapy Class
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8, 5))
kmf3 = KaplanMeierFitter()
classes = sorted(master["therapy_class"].unique())
cmap = plt.get_cmap("tab10")
for i, tc in enumerate(classes):
    mask = master["therapy_class"] == tc
    kmf3.fit(master.loc[mask, "duration"], master.loc[mask, "event"], label=tc)
    kmf3.plot_survival_function(ax=ax, color=cmap(i), ci_show=False)

ax.set_title("Therapy Persistency by Therapy Class (Kaplan-Meier)", fontsize=13, fontweight="bold")
ax.set_xlabel("Days since therapy start")
ax.set_ylabel("Proportion still persistent")
ax.legend(fontsize=8, loc="upper right")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/km_curve_therapy_class.png", dpi=150)
plt.close(fig)

mv_class = multivariate_logrank_test(
    master["duration"], master["therapy_class"], master["event"]
)
results_log.append({
    "comparison": "Across 6 therapy classes (overall)",
    "median_days_group1": np.nan,
    "median_days_group2": np.nan,
    "logrank_p_value": mv_class.p_value,
    "significant_at_0.05": mv_class.p_value < 0.05,
})

logrank_df = pd.DataFrame(results_log)
logrank_df.to_csv(f"{OUT}/logrank_test_results.csv", index=False)

# ---------------------------------------------------------------------
# 4. Cox Proportional Hazards model
#    Quantifies each driver's independent effect on discontinuation
#    hazard, holding the other variables constant -- answers "does
#    insurance status still matter once we control for age, supply
#    size, and therapy class?"
# ---------------------------------------------------------------------
cox_df = master[["duration", "event", "age", "insurance_status",
                  "initial_supply_days", "therapy_class", "region"]].copy()
cox_df = pd.get_dummies(cox_df, columns=["insurance_status", "therapy_class", "region"],
                         drop_first=True, dtype=float)
cox_df["supply_60"] = (master["initial_supply_days"] == 60).astype(float)
cox_df["supply_90"] = (master["initial_supply_days"] == 90).astype(float)
cox_df = cox_df.drop(columns=["initial_supply_days"])

cph = CoxPHFitter()
cph.fit(cox_df, duration_col="duration", event_col="event")

cox_summary = cph.summary.reset_index().rename(columns={"index": "covariate"})
cox_summary["hazard_ratio"] = np.exp(cox_summary["coef"])
cox_summary = cox_summary[["covariate", "coef", "hazard_ratio", "p", "coef lower 95%", "coef upper 95%"]]
cox_summary.columns = ["covariate", "log_hazard_coef", "hazard_ratio", "p_value",
                        "coef_ci_lower", "coef_ci_upper"]
cox_summary = cox_summary.sort_values("hazard_ratio", ascending=False)
cox_summary.to_csv(f"{OUT}/cox_model_results.csv", index=False)

print("=== Kaplan-Meier median persistency (days) ===")
print(f"Insured: {medians['Insured']:.0f}  |  Uninsured: {medians['Uninsured']:.0f}")
print(f"30-day supply: {medians_supply[30]:.0f}  |  60-day: {medians_supply[60]:.0f}  |  90-day: {medians_supply[90]:.0f}")
print("\n=== Log-rank test results ===")
print(logrank_df.to_string(index=False))
print(f"\nConcordance index (Cox model fit quality): {cph.concordance_index_:.3f}")
pd.DataFrame([{"concordance_index": cph.concordance_index_}]).to_csv(f"{OUT}/cox_concordance.csv", index=False)
print("\n=== Cox model — top hazard ratios ===")
print(cox_summary.head(8).to_string(index=False))
print(f"\nSaved: km_curve_insurance.png, km_curve_supply.png, km_curve_therapy_class.png,")
print("logrank_test_results.csv, cox_model_results.csv")
