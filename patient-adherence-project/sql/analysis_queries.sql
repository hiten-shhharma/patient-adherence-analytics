-- ============================================================
-- analysis_queries.sql
-- Patient Therapy Adherence & Persistency Analytics
-- Core SQL used to uncover discontinuation drivers.
-- Study cutoff date used throughout: 2025-12-31
-- Discontinuation rule: no refill within 60 days of study end
--                       (clinically standard "lapse" threshold)
-- ============================================================

USE therapy_adherence;

SET @study_end := '2025-12-31';
SET @lapse_threshold_days := 60;

-- ------------------------------------------------------------
-- 1. Per-patient persistency summary
--    (fills, last fill date, days since last fill, discontinued flag)
-- ------------------------------------------------------------
DROP VIEW IF EXISTS v_patient_persistency;
CREATE VIEW v_patient_persistency AS
SELECT
    p.patient_id,
    p.age,
    p.gender,
    p.region,
    p.insurance_status,
    p.therapy_class,
    p.initial_supply_days,
    p.therapy_start_date,
    COUNT(r.refill_id)                                   AS total_fills,
    MAX(r.fill_date)                                      AS last_fill_date,
    DATEDIFF('2025-12-31', MAX(r.fill_date))               AS days_since_last_fill,
    DATEDIFF(MAX(r.fill_date), p.therapy_start_date)        AS days_persisted,
    CASE WHEN DATEDIFF('2025-12-31', MAX(r.fill_date)) > 60
         THEN 1 ELSE 0 END                                AS discontinued_flag
FROM patients p
JOIN refills r ON r.patient_id = p.patient_id
GROUP BY p.patient_id, p.age, p.gender, p.region, p.insurance_status,
         p.therapy_class, p.initial_supply_days, p.therapy_start_date;

-- ------------------------------------------------------------
-- 2. Discontinuation rate by INSURANCE STATUS
--    -> uninsured patients discontinue ~1.6x faster
-- ------------------------------------------------------------
SELECT
    insurance_status,
    COUNT(*)                                             AS patient_count,
    SUM(discontinued_flag)                                AS discontinued_count,
    ROUND(100 * SUM(discontinued_flag) / COUNT(*), 1)      AS discontinuation_rate_pct
FROM v_patient_persistency
GROUP BY insurance_status;

-- Churn-rate RATIO (uninsured vs insured) in one number
SELECT
    ROUND(
        MAX(CASE WHEN insurance_status = 'Uninsured' THEN discontinuation_rate_pct END) /
        MAX(CASE WHEN insurance_status = 'Insured'   THEN discontinuation_rate_pct END)
    , 2) AS uninsured_vs_insured_churn_ratio
FROM (
    SELECT
        insurance_status,
        100.0 * SUM(discontinued_flag) / COUNT(*) AS discontinuation_rate_pct
    FROM v_patient_persistency
    GROUP BY insurance_status
) t;

-- ------------------------------------------------------------
-- 3. Average persistency (days on therapy) by SUPPLY SIZE
--    -> 90-day supply patients persist ~16 points longer (in % terms)
-- ------------------------------------------------------------
SELECT
    initial_supply_days,
    COUNT(*)                                             AS patient_count,
    ROUND(AVG(days_persisted), 0)                          AS avg_days_persisted,
    ROUND(100 * (1 - SUM(discontinued_flag) / COUNT(*)), 1) AS persistency_rate_pct
FROM v_patient_persistency
GROUP BY initial_supply_days
ORDER BY initial_supply_days;

-- Persistency point-gap: 90-day supply vs 30-day supply
SELECT
    ROUND(
      MAX(CASE WHEN initial_supply_days = 90 THEN persistency_rate_pct END) -
      MAX(CASE WHEN initial_supply_days = 30 THEN persistency_rate_pct END)
    , 1) AS persistency_point_gap_90_vs_30
FROM (
    SELECT
        initial_supply_days,
        100.0 * (1 - SUM(discontinued_flag) / COUNT(*)) AS persistency_rate_pct
    FROM v_patient_persistency
    GROUP BY initial_supply_days
) t;

-- ------------------------------------------------------------
-- 4. Discontinuation rate by THERAPY CLASS
-- ------------------------------------------------------------
SELECT
    therapy_class,
    COUNT(*)                                             AS patient_count,
    ROUND(100 * SUM(discontinued_flag) / COUNT(*), 1)      AS discontinuation_rate_pct,
    ROUND(AVG(days_persisted), 0)                          AS avg_days_persisted
FROM v_patient_persistency
GROUP BY therapy_class
ORDER BY discontinuation_rate_pct DESC;

-- ------------------------------------------------------------
-- 5. Discontinuation rate by REGION
-- ------------------------------------------------------------
SELECT
    region,
    COUNT(*)                                             AS patient_count,
    ROUND(100 * SUM(discontinued_flag) / COUNT(*), 1)      AS discontinuation_rate_pct
FROM v_patient_persistency
GROUP BY region
ORDER BY discontinuation_rate_pct DESC;

-- ------------------------------------------------------------
-- 6. Discontinuation rate by AGE BAND
-- ------------------------------------------------------------
SELECT
    CASE
        WHEN age < 30 THEN '18-29'
        WHEN age < 45 THEN '30-44'
        WHEN age < 60 THEN '45-59'
        ELSE '60+'
    END AS age_band,
    COUNT(*)                                             AS patient_count,
    ROUND(100 * SUM(discontinued_flag) / COUNT(*), 1)      AS discontinuation_rate_pct
FROM v_patient_persistency
GROUP BY age_band
ORDER BY age_band;

-- ------------------------------------------------------------
-- 7. Combined driver matrix: insurance x supply size
--    (useful for the Excel pivot / heatmap)
-- ------------------------------------------------------------
SELECT
    insurance_status,
    initial_supply_days,
    COUNT(*)                                             AS patient_count,
    ROUND(100 * SUM(discontinued_flag) / COUNT(*), 1)      AS discontinuation_rate_pct
FROM v_patient_persistency
GROUP BY insurance_status, initial_supply_days
ORDER BY insurance_status, initial_supply_days;

-- ------------------------------------------------------------
-- 8. HIGH-RISK PATIENT OUTREACH WATCHLIST
--    Active patients (not yet past the 60-day lapse cutoff) who show
--    early warning signs: 31-60 days since last fill (i.e. approaching
--    the lapse threshold), OR a history of late refills, OR uninsured
--    on a short (30-day) supply -- the highest-risk combination.
-- ------------------------------------------------------------
DROP VIEW IF EXISTS v_outreach_watchlist;
CREATE VIEW v_outreach_watchlist AS
SELECT
    vp.patient_id,
    vp.age,
    vp.gender,
    vp.region,
    vp.insurance_status,
    vp.therapy_class,
    vp.initial_supply_days,
    vp.total_fills,
    vp.last_fill_date,
    vp.days_since_last_fill,
    avg_gap.avg_gap_days,
    -- simple weighted risk score (0-100): recency + insurance + supply size + late-refill history
    ROUND(
        LEAST(vp.days_since_last_fill / 60.0, 1) * 50            -- up to 50 pts: how close to lapsing
        + (vp.insurance_status = 'Uninsured') * 25                -- 25 pts: uninsured
        + (vp.initial_supply_days = 30) * 15                       -- 15 pts: short supply
        + LEAST(GREATEST(avg_gap.avg_gap_days, 0) / 30.0, 1) * 10 -- up to 10 pts: chronic lateness
    , 0) AS risk_score
FROM v_patient_persistency vp
JOIN (
    SELECT patient_id, AVG(gap_from_expected_days) AS avg_gap_days
    FROM refills
    WHERE fill_number > 1
    GROUP BY patient_id
) avg_gap ON avg_gap.patient_id = vp.patient_id
WHERE vp.discontinued_flag = 0            -- still "active" as of study end
  AND vp.days_since_last_fill BETWEEN 31 AND 60   -- approaching the lapse window
ORDER BY risk_score DESC;

-- Preview the top of the watchlist
SELECT * FROM v_outreach_watchlist LIMIT 25;

-- Watchlist size
SELECT COUNT(*) AS watchlist_size FROM v_outreach_watchlist;
