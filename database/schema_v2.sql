-- ============================================================
-- AI Skincare Companion App — Database Schema v2
-- PostgreSQL 16 (port 5433), database: skincare_app
-- Primary keys: auto-increment integers (SERIAL)
-- 26 tables
--
-- Changes from v1 (see review, 8 Oct 2026):
--   * All timestamps are TIMESTAMPTZ (time-zone aware)
--   * updated_at columns maintained by a trigger
--   * Google users identified by google_sub; account linking supported
--   * Allergies are structured (ingredients + user_allergies)
--   * Rule engine: step categories, severity, skin type, product types,
--     concentrations, base steps, ingredient conflicts, pregnancy safety
--   * Oiliness/dryness use the hybrid method (photo + skin quiz)
--   * routine_steps are morning OR evening (fixes the 'both' logging bug)
--   * Auth tables: refresh_tokens, email_tokens; push: user_devices
--   * Clinic managers linked to a clinic; doctor must belong to the clinic
--   * Audit logs survive admin deletion
--
-- To apply: drop and recreate the skincare_app database (it only holds
-- dummy data), run this file, then the v2 seed and verify scripts.
-- ============================================================


-- ============================================================
-- 0. HELPER: keep updated_at current on every UPDATE
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 1. USERS & PROFILES
-- ============================================================

CREATE TABLE users (
    id                  SERIAL PRIMARY KEY,
    full_name           VARCHAR(150) NOT NULL,
    email               VARCHAR(255) NOT NULL,
    email_verified      BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash       VARCHAR(255),                  -- NULL for Google-only accounts
    google_sub          VARCHAR(255) UNIQUE,           -- Google's permanent user id ("sub" claim)
    auth_provider       VARCHAR(20) NOT NULL DEFAULT 'email'
                        CHECK (auth_provider IN ('email', 'google')),  -- method used at sign-up
    phone_number        VARCHAR(30),
    date_of_birth       DATE,
    gender              VARCHAR(20)
                        CHECK (gender IN ('male', 'female', 'other', 'prefer_not_to_say')),
    profile_picture_url VARCHAR(500),
    timezone            VARCHAR(50) NOT NULL DEFAULT 'Asia/Beirut',   -- IANA name, for reminders/streaks
    last_latitude       NUMERIC(9,6) CHECK (last_latitude  BETWEEN -90  AND 90),
    last_longitude      NUMERIC(9,6) CHECK (last_longitude BETWEEN -180 AND 180),
    location_updated_at TIMESTAMPTZ,                   -- for weather-based advice
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- the sign-up method must actually be usable
    CHECK (auth_provider <> 'email'  OR password_hash IS NOT NULL),
    CHECK (auth_provider <> 'google' OR google_sub    IS NOT NULL)
);

-- emails are unique regardless of letter case (Ali@x.com = ali@x.com)
CREATE UNIQUE INDEX uq_users_email_lower ON users (LOWER(email));

CREATE TABLE user_profiles (
    id                          SERIAL PRIMARY KEY,
    user_id                     INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    skin_type                   VARCHAR(20)
                                CHECK (skin_type IN ('oily', 'dry', 'combination', 'normal', 'sensitive')),
    fitzpatrick_scale           SMALLINT CHECK (fitzpatrick_scale BETWEEN 1 AND 6),
    skin_quiz_answers           JSONB,                 -- raw answers of the onboarding skin quiz
    skin_quiz_completed_at      TIMESTAMPTZ,
    is_pregnant_or_breastfeeding BOOLEAN NOT NULL DEFAULT FALSE,  -- excludes unsafe ingredients (e.g. retinoids)
    other_allergies_notes       TEXT,                  -- allergies not in the ingredients list
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 2. INGREDIENTS & ALLERGIES (used by the recommendation engine)
-- ============================================================

CREATE TABLE ingredients (
    id                      SERIAL PRIMARY KEY,
    name                    VARCHAR(100) NOT NULL UNIQUE,   -- e.g. "Salicylic Acid"
    description             TEXT,
    avoid_during_pregnancy  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_allergies (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ingredient_id   INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, ingredient_id)
);

-- pairs that should not be used in the same time slot (e.g. retinol + AHA)
CREATE TABLE ingredient_conflicts (
    id                  SERIAL PRIMARY KEY,
    ingredient_a_id     INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    ingredient_b_id     INTEGER NOT NULL REFERENCES ingredients(id) ON DELETE CASCADE,
    reason              TEXT NOT NULL,
    CHECK (ingredient_a_id < ingredient_b_id),     -- store each pair once, in one direction
    UNIQUE (ingredient_a_id, ingredient_b_id)
);


-- ============================================================
-- 3. AI SCAN & SKIN CONCERNS
-- ============================================================

-- the AI's vocabulary: categories the system can report
CREATE TABLE skin_concerns (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(50) NOT NULL UNIQUE,   -- acne, oiliness, dryness, redness, dark_spots, wrinkles
    display_name        VARCHAR(100) NOT NULL,         -- "Dark spots"
    description         TEXT,
    detection_method    VARCHAR(10) NOT NULL DEFAULT 'photo'
                        CHECK (detection_method IN ('photo', 'hybrid'))  -- hybrid = photo + skin quiz
);

CREATE TABLE scan_results (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    image_url           VARCHAR(500) NOT NULL,         -- Cloudinary URL
    image_public_id     VARCHAR(255) NOT NULL,         -- Cloudinary id, needed to delete the image
    model_version       VARCHAR(50) NOT NULL,          -- which trained model produced this result
    overall_skin_score  NUMERIC(5,2) CHECK (overall_skin_score BETWEEN 0 AND 100),
    raw_model_output    JSONB,                         -- every raw prediction, for transparency
    scanned_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- only concerns that passed the detection threshold (or came from the quiz)
CREATE TABLE scan_result_concerns (
    id                  SERIAL PRIMARY KEY,
    scan_result_id      INTEGER NOT NULL REFERENCES scan_results(id) ON DELETE CASCADE,
    skin_concern_id     INTEGER NOT NULL REFERENCES skin_concerns(id) ON DELETE RESTRICT,
    confidence_score    NUMERIC(5,4) CHECK (confidence_score BETWEEN 0 AND 1),
    severity            VARCHAR(10) NOT NULL CHECK (severity IN ('mild', 'moderate', 'severe')),
    detection_source    VARCHAR(30) NOT NULL DEFAULT 'photo'
                        CHECK (detection_source IN ('photo', 'questionnaire', 'photo_and_questionnaire')),
    UNIQUE (scan_result_id, skin_concern_id),
    -- a confidence score is required whenever the photo model was involved
    CHECK (detection_source = 'questionnaire' OR confidence_score IS NOT NULL)
);


-- ============================================================
-- 4. RECOMMENDATION RULES & ROUTINES
-- ============================================================

-- admin-editable rules: concern (+ severity, skin type) -> routine step
CREATE TABLE concern_recommendation_mapping (
    id                          SERIAL PRIMARY KEY,
    skin_concern_id             INTEGER REFERENCES skin_concerns(id) ON DELETE CASCADE,  -- NULL = base step for everyone
    step_category               VARCHAR(20) NOT NULL
                                CHECK (step_category IN ('cleanse', 'treat', 'moisturize', 'protect')),
    step_title                  VARCHAR(100) NOT NULL,     -- "Cleanse"
    product_type                VARCHAR(100) NOT NULL,     -- "Gentle foaming gel cleanser"
    ingredient_id               INTEGER REFERENCES ingredients(id) ON DELETE RESTRICT,
    recommended_concentration   VARCHAR(50),               -- "0.5-2%"
    time_of_day                 VARCHAR(10) NOT NULL DEFAULT 'both'
                                CHECK (time_of_day IN ('morning', 'evening', 'both')),  -- 'both' is expanded into two steps
    min_severity                VARCHAR(10) NOT NULL DEFAULT 'mild'
                                CHECK (min_severity IN ('mild', 'moderate', 'severe')),
    skin_type                   VARCHAR(20)                -- NULL = any skin type
                                CHECK (skin_type IN ('oily', 'dry', 'combination', 'normal', 'sensitive')),
    priority                    SMALLINT NOT NULL DEFAULT 0, -- higher wins when two rules fill the same slot
    notes                       TEXT,
    is_active                   BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE routines (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    scan_result_id  INTEGER REFERENCES scan_results(id) ON DELETE SET NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- at most one active routine per user
CREATE UNIQUE INDEX uq_routines_one_active_per_user ON routines (user_id) WHERE is_active;

-- a snapshot of the generated routine (later rule edits don't change it)
CREATE TABLE routine_steps (
    id                          SERIAL PRIMARY KEY,
    routine_id                  INTEGER NOT NULL REFERENCES routines(id) ON DELETE CASCADE,
    mapping_id                  INTEGER REFERENCES concern_recommendation_mapping(id) ON DELETE SET NULL,  -- rule that produced it
    time_of_day                 VARCHAR(10) NOT NULL CHECK (time_of_day IN ('morning', 'evening')),
    step_order                  SMALLINT NOT NULL,
    step_category               VARCHAR(20) NOT NULL
                                CHECK (step_category IN ('cleanse', 'treat', 'moisturize', 'protect')),
    title                       VARCHAR(100) NOT NULL,
    description                 TEXT,
    product_type                VARCHAR(100) NOT NULL,
    ingredient_id               INTEGER REFERENCES ingredients(id) ON DELETE SET NULL,
    recommended_concentration   VARCHAR(50),
    UNIQUE (routine_id, time_of_day, step_order)
);

CREATE TABLE routine_logs (
    id                  SERIAL PRIMARY KEY,
    routine_step_id     INTEGER NOT NULL REFERENCES routine_steps(id) ON DELETE CASCADE,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- kept for fast streak queries
    log_date            DATE NOT NULL,                 -- the user's local date
    completed_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (routine_step_id, user_id, log_date)
);


-- ============================================================
-- 5. ACHIEVEMENTS & GAMIFICATION
-- ============================================================

CREATE TABLE achievements (
    id              SERIAL PRIMARY KEY,
    title           VARCHAR(100) NOT NULL UNIQUE,
    description     TEXT,
    icon_url        VARCHAR(500),
    criteria_type   VARCHAR(30) NOT NULL
                    CHECK (criteria_type IN ('streak_days', 'scans_completed', 'routine_adherence')),
    criteria_value  INTEGER NOT NULL CHECK (criteria_value > 0),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_achievements (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    achievement_id  INTEGER NOT NULL REFERENCES achievements(id) ON DELETE CASCADE,
    earned_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, achievement_id)
);


-- ============================================================
-- 6. CLINICS & DOCTORS
-- ============================================================

CREATE TABLE clinics (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(200) NOT NULL,
    address         VARCHAR(300),
    latitude        NUMERIC(9,6) NOT NULL CHECK (latitude  BETWEEN -90  AND 90),
    longitude       NUMERIC(9,6) NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    phone_number    VARCHAR(30),
    website         VARCHAR(500),
    opening_hours   VARCHAR(255),                      -- OSM opening_hours format
    source          VARCHAR(20) NOT NULL DEFAULT 'osm_import'
                    CHECK (source IN ('osm_import', 'admin_added')),
    osm_id          VARCHAR(50) UNIQUE,                -- "node/123" or "way/456"
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,    -- verified clinics accept in-app appointments
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_synced_at  TIMESTAMPTZ,                       -- last refresh from OSM
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source <> 'osm_import' OR osm_id IS NOT NULL)
);

CREATE TABLE doctors (
    id              SERIAL PRIMARY KEY,
    clinic_id       INTEGER NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    full_name       VARCHAR(150) NOT NULL,
    specialty       VARCHAR(100),
    bio             TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (id, clinic_id)                             -- target of the appointments composite FK
);


-- ============================================================
-- 7. ADMINS
-- ============================================================

CREATE TABLE admins (
    id              SERIAL PRIMARY KEY,
    full_name       VARCHAR(150) NOT NULL,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'moderator'
                    CHECK (role IN ('super_admin', 'moderator', 'clinic_manager')),
    clinic_id       INTEGER REFERENCES clinics(id) ON DELETE RESTRICT,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,      -- soft delete keeps audit history intact
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- clinic managers must have a clinic; other roles must not
    CHECK ((role = 'clinic_manager') = (clinic_id IS NOT NULL))
);

CREATE UNIQUE INDEX uq_admins_email_lower ON admins (LOWER(email));


-- ============================================================
-- 8. APPOINTMENTS & CALENDAR
-- ============================================================

CREATE TABLE appointments (
    id                      SERIAL PRIMARY KEY,
    user_id                 INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    clinic_id               INTEGER NOT NULL REFERENCES clinics(id) ON DELETE RESTRICT,
    doctor_id               INTEGER,
    requested_datetime      TIMESTAMPTZ NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'accepted', 'rejected', 'completed', 'cancelled')),
    notes                   TEXT,                      -- from the user
    response_note           TEXT,                      -- from the clinic manager
    responded_by_admin_id   INTEGER REFERENCES admins(id) ON DELETE SET NULL,
    responded_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- the doctor (if any) must work at the chosen clinic;
    -- if the doctor is deleted, only doctor_id is cleared (PostgreSQL 15+)
    FOREIGN KEY (doctor_id, clinic_id) REFERENCES doctors(id, clinic_id)
        ON DELETE SET NULL (doctor_id)
);

CREATE TABLE calendar_events (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           VARCHAR(150) NOT NULL,
    event_type      VARCHAR(20) NOT NULL
                    CHECK (event_type IN ('routine_reminder', 'appointment', 'custom')),
    event_datetime  TIMESTAMPTZ NOT NULL,
    appointment_id  INTEGER REFERENCES appointments(id) ON DELETE CASCADE,
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (event_type <> 'appointment' OR appointment_id IS NOT NULL)
);


-- ============================================================
-- 9. NOTIFICATIONS & DEVICES
-- ============================================================

CREATE TABLE notifications (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(30) NOT NULL
                    CHECK (type IN ('reminder', 'weather_alert', 'achievement', 'appointment_update')),
    message         TEXT NOT NULL,
    is_read         BOOLEAN NOT NULL DEFAULT FALSE,
    sent_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Firebase Cloud Messaging tokens (one user can have several devices)
CREATE TABLE user_devices (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    fcm_token       VARCHAR(512) NOT NULL UNIQUE,
    platform        VARCHAR(10) NOT NULL CHECK (platform IN ('android', 'ios')),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 10. AUTH TOKENS
-- ============================================================

-- refresh tokens for users (mobile) and admins (web); only a hash is stored
CREATE TABLE refresh_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER REFERENCES users(id)  ON DELETE CASCADE,
    admin_id        INTEGER REFERENCES admins(id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,                       -- set on logout or rotation
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (num_nonnulls(user_id, admin_id) = 1)        -- belongs to exactly one account
);

-- one-time tokens sent by email (password reset, email verification)
CREATE TABLE email_tokens (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose         VARCHAR(30) NOT NULL CHECK (purpose IN ('password_reset', 'email_verification')),
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 11. ADMIN DASHBOARD
-- ============================================================

CREATE TABLE audit_logs (
    id              SERIAL PRIMARY KEY,
    admin_id        INTEGER REFERENCES admins(id) ON DELETE SET NULL,  -- history survives admin removal
    action          VARCHAR(255) NOT NULL,
    target_table    VARCHAR(100),
    target_id       INTEGER,
    details         JSONB,                             -- e.g. {"old": {...}, "new": {...}}
    ip_address      INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE report_templates (
    id              SERIAL PRIMARY KEY,
    admin_id        INTEGER NOT NULL REFERENCES admins(id) ON DELETE CASCADE,
    name            VARCHAR(100) NOT NULL,
    report_type     VARCHAR(50) NOT NULL
                    CHECK (report_type IN ('user_activity', 'scan_trends', 'appointments', 'achievement_engagement')),
    filters         JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 12. WEATHER-BASED ADVICE (reference table)
-- ============================================================

CREATE TABLE weather_skin_tips (
    id                      SERIAL PRIMARY KEY,
    weather_condition       VARCHAR(20) NOT NULL
                            CHECK (weather_condition IN ('hot', 'cold', 'humid', 'dry', 'high_uv')),
    tip_text                TEXT NOT NULL,
    related_skin_concern_id INTEGER REFERENCES skin_concerns(id) ON DELETE SET NULL,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE
);


-- ============================================================
-- updated_at TRIGGERS
-- ============================================================

CREATE TRIGGER trg_users_updated_at          BEFORE UPDATE ON users                          FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_user_profiles_updated_at  BEFORE UPDATE ON user_profiles                  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_mapping_updated_at        BEFORE UPDATE ON concern_recommendation_mapping FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_clinics_updated_at        BEFORE UPDATE ON clinics                        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_admins_updated_at         BEFORE UPDATE ON admins                         FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER trg_appointments_updated_at   BEFORE UPDATE ON appointments                   FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- INDEXES (common lookups and foreign keys used in queries)
-- ============================================================

CREATE INDEX idx_scan_results_user_time       ON scan_results (user_id, scanned_at DESC);  -- progress charts
CREATE INDEX idx_scan_concerns_concern        ON scan_result_concerns (skin_concern_id);   -- analytics
CREATE INDEX idx_mapping_concern              ON concern_recommendation_mapping (skin_concern_id);
CREATE INDEX idx_routines_user_id             ON routines (user_id);
CREATE INDEX idx_routine_logs_user_date       ON routine_logs (user_id, log_date);         -- streaks
CREATE INDEX idx_user_allergies_user          ON user_allergies (user_id);
CREATE INDEX idx_notifications_user_unread    ON notifications (user_id, is_read);
CREATE INDEX idx_user_devices_user            ON user_devices (user_id);
CREATE INDEX idx_calendar_events_user_time    ON calendar_events (user_id, event_datetime);
CREATE INDEX idx_clinics_location             ON clinics (latitude, longitude);           -- nearby search
CREATE INDEX idx_doctors_clinic               ON doctors (clinic_id);
CREATE INDEX idx_appointments_user_id         ON appointments (user_id);
CREATE INDEX idx_appointments_clinic_status   ON appointments (clinic_id, status);
CREATE INDEX idx_refresh_tokens_user          ON refresh_tokens (user_id);
CREATE INDEX idx_refresh_tokens_admin         ON refresh_tokens (admin_id);
CREATE INDEX idx_email_tokens_user            ON email_tokens (user_id);
CREATE INDEX idx_audit_logs_admin_time        ON audit_logs (admin_id, created_at);
