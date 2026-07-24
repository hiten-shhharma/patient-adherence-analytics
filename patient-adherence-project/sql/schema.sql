-- ============================================================
-- schema.sql
-- Patient Therapy Adherence & Persistency Analytics
-- MySQL 8.0 schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS therapy_adherence;
USE therapy_adherence;

DROP TABLE IF EXISTS refills;
DROP TABLE IF EXISTS patients;

-- ------------------------------------------------------------
-- patients: one row per simulated patient
-- ------------------------------------------------------------
CREATE TABLE patients (
    patient_id           VARCHAR(10)  PRIMARY KEY,
    age                  TINYINT UNSIGNED NOT NULL,
    gender               ENUM('M', 'F') NOT NULL,
    region               VARCHAR(20)  NOT NULL,
    insurance_status     ENUM('Insured', 'Uninsured') NOT NULL,
    therapy_class        VARCHAR(40)  NOT NULL,
    initial_supply_days  SMALLINT UNSIGNED NOT NULL,
    therapy_start_date   DATE NOT NULL,
    INDEX idx_patients_insurance (insurance_status),
    INDEX idx_patients_therapy_class (therapy_class),
    INDEX idx_patients_region (region)
) ENGINE=InnoDB;

-- ------------------------------------------------------------
-- refills: one row per dispensing / refill event (15,000+ rows)
-- ------------------------------------------------------------
CREATE TABLE refills (
    refill_id               VARCHAR(15) PRIMARY KEY,
    patient_id               VARCHAR(10) NOT NULL,
    fill_number               SMALLINT UNSIGNED NOT NULL,
    fill_date                 DATE NOT NULL,
    days_supply                SMALLINT UNSIGNED NOT NULL,
    gap_from_expected_days     INT NOT NULL,
    CONSTRAINT fk_refills_patient
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
        ON DELETE CASCADE,
    INDEX idx_refills_patient (patient_id),
    INDEX idx_refills_fill_date (fill_date)
) ENGINE=InnoDB;
