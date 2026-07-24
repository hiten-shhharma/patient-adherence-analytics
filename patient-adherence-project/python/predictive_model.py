"""
predictive_model.py
----------------------
Replaces the rule-based risk score with a proper predictive model:
logistic regression predicting P(discontinued) from patient features,
trained/evaluated with a held-out test split.

Outputs:
  - Model performance (accuracy, ROC-AUC, precision/recall) on a held-out
    test set -- output/model_performance.csv
  - Feature importance / odds ratios -- output/model_feature_importance.csv
  - ROC curve plot -- output/roc_curve.png
  - A recalculated outreach watchlist where `risk_score` is now the
    model's predicted probability of discontinuation (0-100 scale),
    still filtered to currently-active patients -- output/outreach_watchlist.csv
    (overwrites the rule-based version from adherence_analysis.py)
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (roc_auc_score, roc_curve, accuracy_score,
                              precision_score, recall_score, f1_score,
                              confusion_matrix)

OUT = "/home/claude/project/output"
RNG_SEED = 42

master = pd.read_csv(f"{OUT}/patient_master_analytics.csv")

# ---------------------------------------------------------------------
# 1. Feature engineering
# ---------------------------------------------------------------------
features = master[[
    "patient_id", "age", "insurance_status", "initial_supply_days",
    "therapy_class", "region", "gender", "avg_gap_days", "discontinued_flag"
]].copy()

X = pd.get_dummies(
    features.drop(columns=["patient_id", "discontinued_flag"]),
    columns=["insurance_status", "therapy_class", "region", "gender"],
    drop_first=True, dtype=float
)
feature_names = X.columns.tolist()
y = features["discontinued_flag"]

# ---------------------------------------------------------------------
# 2. Train/test split + scaling
# ---------------------------------------------------------------------
X_train, X_test, y_train, y_test, id_train, id_test = train_test_split(
    X, y, features["patient_id"], test_size=0.25, random_state=RNG_SEED, stratify=y
)

scaler = StandardScaler()
X_train_s = scaler.fit_transform(X_train)
X_test_s = scaler.transform(X_test)

# ---------------------------------------------------------------------
# 3. Fit logistic regression
# ---------------------------------------------------------------------
model = LogisticRegression(max_iter=1000, random_state=RNG_SEED)
model.fit(X_train_s, y_train)

y_pred = model.predict(X_test_s)
y_proba = model.predict_proba(X_test_s)[:, 1]

metrics = {
    "accuracy": accuracy_score(y_test, y_pred),
    "roc_auc": roc_auc_score(y_test, y_proba),
    "precision": precision_score(y_test, y_pred),
    "recall": recall_score(y_test, y_pred),
    "f1_score": f1_score(y_test, y_pred),
}
tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
metrics.update({"true_positives": int(tp), "false_positives": int(fp),
                 "true_negatives": int(tn), "false_negatives": int(fn)})

perf_df = pd.DataFrame([metrics])
perf_df.to_csv(f"{OUT}/model_performance.csv", index=False)

# ---------------------------------------------------------------------
# 4. Feature importance (standardized coefficients -> odds ratios)
# ---------------------------------------------------------------------
coefs = pd.DataFrame({
    "feature": feature_names,
    "coefficient": model.coef_[0],
})
coefs["odds_ratio"] = np.exp(coefs["coefficient"])
coefs["abs_coefficient"] = coefs["coefficient"].abs()
coefs = coefs.sort_values("abs_coefficient", ascending=False).drop(columns="abs_coefficient")
coefs.to_csv(f"{OUT}/model_feature_importance.csv", index=False)

# ---------------------------------------------------------------------
# 5. ROC curve plot
# ---------------------------------------------------------------------
fpr, tpr, _ = roc_curve(y_test, y_proba)
fig, ax = plt.subplots(figsize=(6, 6))
ax.plot(fpr, tpr, color="#1F4E78", linewidth=2, label=f"Logistic Regression (AUC = {metrics['roc_auc']:.3f})")
ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Random baseline")
ax.set_xlabel("False Positive Rate")
ax.set_ylabel("True Positive Rate")
ax.set_title("ROC Curve — Discontinuation Prediction Model", fontsize=12, fontweight="bold")
ax.legend(loc="lower right")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(f"{OUT}/roc_curve.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------------
# 6. Score EVERY patient (full dataset) with the fitted model, rebuild
#    the outreach watchlist using predicted probability as risk_score
# ---------------------------------------------------------------------
X_full_s = scaler.transform(X)
master["ml_discontinuation_probability"] = model.predict_proba(X_full_s)[:, 1]

active = master[master["discontinued_flag"] == 0].copy()
watchlist = active[
    (active["days_since_last_fill"] >= 31) & (active["days_since_last_fill"] <= 60)
].copy()
watchlist["risk_score"] = (watchlist["ml_discontinuation_probability"] * 100).round(0)
watchlist["priority_tier"] = pd.cut(
    watchlist["risk_score"], bins=[-1, 40, 65, 100], labels=["Low", "Medium", "High"]
)

wl_cols = ["patient_id", "age", "gender", "region", "insurance_status", "therapy_class",
           "initial_supply_days", "total_fills", "last_fill_date", "days_since_last_fill",
           "pdc", "risk_score", "priority_tier"]
watchlist = watchlist[wl_cols].sort_values("risk_score", ascending=False).reset_index(drop=True)
watchlist.to_csv(f"{OUT}/outreach_watchlist.csv", index=False)

master.to_csv(f"{OUT}/patient_master_analytics.csv", index=False)

print("=== Model performance (held-out test set, n={}) ===".format(len(y_test)))
for k, v in metrics.items():
    print(f"  {k}: {v}")

print("\n=== Top 10 predictive features (by |coefficient|, standardized) ===")
print(coefs.head(10).to_string(index=False))

print(f"\nWatchlist rebuilt with ML risk scores: {len(watchlist)} patients")
print("Saved: model_performance.csv, model_feature_importance.csv, roc_curve.png, outreach_watchlist.csv (updated)")
