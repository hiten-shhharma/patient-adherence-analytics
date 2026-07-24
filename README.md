# Patient Therapy Adherence & Persistency Analytics

**Stack:** MySQL · Python (pandas) · Excel (openpyxl)

An end-to-end healthcare analytics pipeline analyzing medication adherence and
persistency across **2,000 simulated patients** and **16,657 refill events**.
Built to mirror a real pharmacy/PBM (Pharmacy Benefit Manager) analytics
workflow: raw dispensing data → SQL data model → Python adherence metrics →
client-ready Excel dashboard with a prioritized outreach list.


---

## Headline results

| Metric | Value |
|---|---|
| Patients analyzed | 2,000 |
| Refill events analyzed | 16,657 |
| Uninsured vs. insured churn ratio | **~1.6x** — uninsured patients discontinue therapy roughly 1.6x faster |
| 90-day vs. 30-day supply persistency gap | **~16 points** — patients started on a 90-day supply persist ~16 pts longer |
| Overall average PDC (Proportion of Days Covered) | 0.89 |
| Cox model: uninsured hazard ratio (controlling for age/supply/therapy class) | **3.93x**, p < 0.001 |
| Log-rank test, insured vs. uninsured persistency curves | p = 1.8 × 10⁻⁸³ (highly significant) |
| Predictive model (logistic regression) ROC-AUC on held-out patients | 0.763 |
| Patients on the ML-ranked outreach watchlist | 315 |

These are the two headline findings the résumé bullet references, and both
are reproducible end-to-end from the raw synthetic data through SQL and
Python — and now backed by formal statistical testing, not just descriptive
percentages.

---

## Advanced analytics layer

Beyond the core SQL/Python/Excel pipeline, the project now includes a
proper statistical and machine-learning layer:

- **Kaplan-Meier survival analysis** (`python/survival_analysis.py`) —
  models *time-to-discontinuation* rather than a flat discontinuation
  rate, correctly handling right-censoring (patients still active at the
  study cutoff haven't "failed" — they're censored, not persistent
  forever). Produces persistency curves by insurance status, supply size,
  and therapy class.
- **Log-rank significance tests** — quantify whether the persistency
  curves are statistically different (all three comparisons come back
  highly significant, p < 0.001).
- **Cox Proportional Hazards model** — isolates each driver's *independent*
  effect on discontinuation risk while holding the others constant (e.g.,
  does insurance status still matter once you control for age, supply
  size, and therapy class? — yes, hazard ratio ≈ 3.9x).
- **Chi-square and Welch's t-tests** (`python/statistical_tests.py`) —
  formal significance testing for every categorical driver and for the
  PDC gap between insured/uninsured patients.
- **Predictive model** (`python/predictive_model.py`) — a logistic
  regression trained on a 75/25 train/test split to predict P(discontinued)
  from patient features, evaluated with ROC-AUC, precision, recall, and a
  confusion matrix. Its predicted probabilities now drive the Outreach
  Watchlist's risk scores, replacing the earlier rule-based heuristic.

---

## Project structure

```
project/
├── data/
│   └── generate_data.py          # synthetic data generator (patients.csv, refills.csv)
├── sql/
│   ├── schema.sql                 # MySQL DDL (patients, refills tables)
│   ├── load_data.py               # loads CSVs into MySQL
│   └── analysis_queries.sql       # SQL views + discontinuation-driver queries
├── python/
│   ├── adherence_analysis.py      # PDC calc, persistency calc, driver tables, watchlist
│   ├── survival_analysis.py       # Kaplan-Meier curves, log-rank tests, Cox PH model
│   ├── predictive_model.py        # logistic regression discontinuation-risk model
│   └── statistical_tests.py       # chi-square / t-test significance testing
├── excel/
│   └── build_excel_dashboard.py   # builds the client-ready Excel dashboard (6 tabs)
└── output/
    ├── Patient_Therapy_Adherence_Dashboard.xlsx
    ├── patient_master_analytics.csv
    ├── outreach_watchlist.csv      # now ML-ranked
    ├── km_curve_*.png               # Kaplan-Meier persistency curves
    ├── roc_curve.png
    ├── logrank_test_results.csv
    ├── cox_model_results.csv
    ├── model_performance.csv / model_feature_importance.csv
    ├── statistical_tests.csv
    └── driver_*.csv                # one CSV per driver breakdown
```

---

## How the pipeline works

### 1. Data generation (`data/generate_data.py`)
Simulates 2,000 patients across 6 therapy classes (Hypertension, Diabetes,
Hyperlipidemia, Depression/Anxiety, Osteoporosis, Asthma/COPD), 5 regions,
and 3 initial supply sizes (30/60/90 days). Each patient's refill history is
generated with a survival-style process: after every fill, a probability of
continuing therapy is computed from the patient's attributes (insurance
status, supply size, age, therapy class, region), producing realistic,
non-uniform churn patterns rather than random noise.

### 2. SQL data model (`sql/schema.sql`, `sql/analysis_queries.sql`)
Two tables (`patients`, `refills`) with a foreign key relationship. The
analysis queries build a `v_patient_persistency` view (per-patient fill
counts, last-fill date, discontinuation flag) and a `v_outreach_watchlist`
view (risk-scored, currently-active patients approaching the lapse
threshold), plus GROUP BY breakdowns by insurance, supply size, therapy
class, region, and age band.

**Discontinuation rule:** a patient is flagged as discontinued if more than
60 days have passed since their last fill as of the study cutoff
(2025-12-31) — the clinically standard "lapse" threshold used in real PBM
adherence reporting.

### 3. Python analysis (`python/adherence_analysis.py`)
Pulls from MySQL (falls back to the CSVs if MySQL isn't running) and computes:
- **PDC (Proportion of Days Covered)** — the industry-standard adherence
  metric: total days covered by dispensed supply (de-duplicated for
  overlapping fills) ÷ days in the observation window.
- **Persistency** — days on therapy before a 60-day gap.
- **Discontinuation-driver tables** by insurance, supply size, therapy
  class, region, and age band.
- **A risk-scored outreach watchlist**: active patients 31–60 days since
  their last fill, scored 0–100 on recency, insurance status, supply size,
  and refill punctuality, and bucketed into Low/Medium/High priority tiers.

### 4. Excel dashboard (`excel/build_excel_dashboard.py`)
A 6-tab workbook:
- **Executive Summary** — KPI cards and key findings, computed with live
  Excel formulas (not hardcoded numbers).
- **Discontinuation Drivers** — one table per driver (insurance, supply
  size, therapy class, region, age band), each cell a `COUNTIFS` /
  `AVERAGEIFS` formula reading from the Patient Data sheet, plus a bar
  chart.
- **Outreach Watchlist** — the prioritized patient list, ranked by the
  logistic regression model's predicted discontinuation probability, with
  conditional formatting (color-coded priority tier and risk-score
  heatmap).
- **Survival Analysis** — embedded Kaplan-Meier persistency curves
  (insurance status, supply size, therapy class), log-rank test results,
  and the Cox Proportional Hazards model's hazard ratios.
- **Predictive Model** — the logistic regression's performance metrics
  (accuracy, ROC-AUC, precision/recall), an embedded ROC curve, top
  predictive features with odds ratios, and the chi-square/t-test
  significance results.
- **Patient Data** — the full 2,000-row source table every formula above
  reads from, so the whole workbook recalculates if the data changes.

### 5. Statistical rigor
Every headline claim is backed by a formal test, not just a descriptive
percentage: chi-square tests for each categorical driver, a Welch's t-test
for the PDC gap, log-rank tests for the survival curves, and a Cox model
isolating each driver's independent effect. All come back statistically
significant (p < 0.001 in every case), and the Cox model shows insurance
status remains the dominant driver (hazard ratio ≈ 3.9x) even after
controlling for age, supply size, and therapy class.

---

## Running it yourself

```bash
# 1. Generate the synthetic dataset
python3 data/generate_data.py

# 2. Stand up MySQL (adjust for your own MySQL instance/credentials)
mysql -u root < sql/schema.sql
python3 sql/load_data.py              # uses user 'analytics_user' — update credentials as needed

# 3. Run the SQL driver analysis directly (optional, for a quick look)
mysql -u root < sql/analysis_queries.sql

# 4. Run the Python analysis (writes CSVs to output/)
python3 python/adherence_analysis.py

# 5. Run the survival analysis (Kaplan-Meier curves, Cox model)
python3 python/survival_analysis.py

# 6. Train and evaluate the predictive model (updates the watchlist)
python3 python/predictive_model.py

# 7. Run formal significance tests
python3 python/statistical_tests.py

# 8. Build the Excel dashboard
python3 excel/build_excel_dashboard.py
```

Requires: MySQL 8.0+, Python 3 with `pandas`, `pymysql`, `openpyxl`,
`lifelines`, `scikit-learn`, `matplotlib`, `scipy`.

Run steps 4–7 in that order — step 6 (`predictive_model.py`) overwrites
`outreach_watchlist.csv` with model-ranked scores, and step 8 reads the
outputs of all of them.

---

