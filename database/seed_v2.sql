-- ============================================================
-- AI Skincare Companion App — Seed / Reference Data v2
-- Run this AFTER schema_v2.sql, on an empty database.
-- This is permanent reference data (editable later from the admin
-- dashboard). No test users here; those belong in verify_v2.sql.
-- ============================================================


-- ============================================================
-- 1. SKIN CONCERNS (the AI's vocabulary)
--    'hybrid' = photo signal + skin quiz (oiliness/dryness, Option A)
-- ============================================================

INSERT INTO skin_concerns (name, display_name, description, detection_method) VALUES
    ('acne',       'Acne',       'Breakouts caused by clogged pores, excess oil, or bacteria.',      'photo'),
    ('oiliness',   'Oiliness',   'Excess sebum production leading to a shiny/greasy appearance.',    'hybrid'),
    ('dryness',    'Dryness',    'Lack of moisture, often with flaking or a tight feeling.',         'hybrid'),
    ('redness',    'Redness',    'Visible redness or irritation across the skin.',                   'photo'),
    ('dark_spots', 'Dark spots', 'Hyperpigmentation or uneven skin tone patches.',                   'photo'),
    ('wrinkles',   'Wrinkles',   'Fine lines and loss of skin elasticity.',                          'photo');


-- ============================================================
-- 2. INGREDIENTS
--    avoid_during_pregnancy = TRUE removes the ingredient from routines
--    of users with is_pregnant_or_breastfeeding = TRUE.
-- ============================================================

INSERT INTO ingredients (name, description, avoid_during_pregnancy) VALUES
    ('Salicylic Acid',     'BHA that exfoliates inside the pore; helps with clogged pores and breakouts.', FALSE),
    ('Benzoyl Peroxide',   'Reduces acne-causing bacteria; can bleach fabrics and dry the skin.',          FALSE),
    ('Adapalene',          'Over-the-counter retinoid for acne; normalises cell turnover in the pore.',    TRUE),
    ('Retinol',            'Vitamin A derivative; boosts cell turnover and softens fine lines.',           TRUE),
    ('Niacinamide',        'Vitamin B3; helps regulate oil, calm redness and even tone.',                  FALSE),
    ('Hyaluronic Acid',    'Humectant that draws water into the skin for hydration.',                      FALSE),
    ('Ceramides',          'Lipids that repair and strengthen the skin barrier.',                          FALSE),
    ('Centella Asiatica',  'Plant extract (cica) that soothes irritation and visible redness.',             FALSE),
    ('Azelaic Acid',       'Calms redness, helps acne and fades dark spots; gentle option.',               FALSE),
    ('Vitamin C',          'Antioxidant (ascorbic acid) that brightens and fades hyperpigmentation.',      FALSE),
    ('Glycolic Acid',      'AHA that exfoliates the surface for smoother, brighter skin.',                 FALSE),
    ('Peptides',           'Support firmness; a gentle anti-aging alternative to retinoids.',              FALSE),
    ('Zinc Oxide',         'Mineral UV filter; gentle sun protection for sensitive skin.',                 FALSE);


-- ============================================================
-- 3. INGREDIENT CONFLICTS
--    Pairs that should not be applied as treatments in the same
--    time slot. LEAST/GREATEST stores each pair once (a_id < b_id).
-- ============================================================

INSERT INTO ingredient_conflicts (ingredient_a_id, ingredient_b_id, reason)
SELECT LEAST(a.id, b.id), GREATEST(a.id, b.id), v.reason
FROM (VALUES
    ('Retinol',   'Adapalene',        'Two retinoids together greatly increase irritation.'),
    ('Retinol',   'Glycolic Acid',    'Retinoid plus exfoliating acid causes over-exfoliation and irritation.'),
    ('Retinol',   'Salicylic Acid',   'Retinoid plus exfoliating acid causes over-exfoliation and irritation.'),
    ('Retinol',   'Benzoyl Peroxide', 'Benzoyl peroxide can degrade retinol and adds dryness.'),
    ('Adapalene', 'Glycolic Acid',    'Retinoid plus exfoliating acid causes over-exfoliation and irritation.'),
    ('Adapalene', 'Salicylic Acid',   'Retinoid plus exfoliating acid causes over-exfoliation and irritation.'),
    ('Vitamin C', 'Benzoyl Peroxide', 'Benzoyl peroxide oxidises vitamin C, making it less effective.'),
    ('Glycolic Acid', 'Salicylic Acid', 'Two exfoliating acids at once over-exfoliate the skin.')
) AS v(ingredient_a, ingredient_b, reason)
JOIN ingredients a ON a.name = v.ingredient_a
JOIN ingredients b ON b.name = v.ingredient_b;


-- ============================================================
-- 4. RECOMMENDATION RULES (concern_recommendation_mapping)
--
-- How the engine (built in Phase 3) will use these rules:
--   1. Start from the BASE steps (skin_concern_id IS NULL).
--   2. Add rules for each detected concern whose min_severity is at
--      or below the detected severity, and whose skin_type is NULL or
--      matches the user's skin type.
--   3. Drop rules whose ingredient the user is allergic to, or that is
--      unsafe during pregnancy (when the profile flag is set).
--   4. 'both' rules are expanded into a morning and an evening step.
--   5. cleanse / moisturize / protect: ONE step per time slot, the
--      highest priority wins (so a concern rule replaces the base step).
--   6. treat: at most one step per concern per time slot (highest
--      priority wins); if two treatments in the same slot conflict
--      (ingredient_conflicts), the lower-priority one is dropped.
--   7. Steps are ordered cleanse -> treat -> moisturize -> protect.
--   Severe concerns also show the "see a dermatologist" prompt (app rule).
-- ============================================================

-- 4a. BASE STEPS (everyone gets these unless a concern rule replaces them)
INSERT INTO concern_recommendation_mapping
    (skin_concern_id, step_category, step_title, product_type, ingredient_id,
     recommended_concentration, time_of_day, min_severity, skin_type, priority, notes)
VALUES
    (NULL, 'cleanse',    'Cleanse',     'Gentle, fragrance-free cleanser',            NULL, NULL, 'both',    'mild', NULL, 0,
        'Removes dirt and oil without stripping the skin barrier.'),
    (NULL, 'moisturize', 'Moisturize',  'Fragrance-free moisturizer',                 NULL, NULL, 'both',    'mild', NULL, 0,
        'Keeps the skin barrier hydrated and healthy.'),
    (NULL, 'protect',    'Sunscreen',   'Broad-spectrum sunscreen SPF 30+',           NULL, NULL, 'morning', 'mild', NULL, 0,
        'Daily UV protection; the most important anti-aging and anti-spot step.');

-- 4b. CONCERN RULES
INSERT INTO concern_recommendation_mapping
    (skin_concern_id, step_category, step_title, product_type, ingredient_id,
     recommended_concentration, time_of_day, min_severity, skin_type, priority, notes)
SELECT sc.id, v.step_category, v.step_title, v.product_type, i.id,
       v.concentration, v.time_of_day, v.min_severity, NULL, v.priority, v.notes
FROM (VALUES
    -- concern,    category,     title,                 product type,                               ingredient,          concentration, time,      min sev,    prio, notes
    -- ACNE
    ('acne',       'cleanse',    'Cleanse',             'Salicylic acid foaming cleanser',          'Salicylic Acid',    '0.5-2%',      'both',    'mild',     10, 'Helps unclog pores and reduce breakouts.'),
    ('acne',       'treat',      'Spot Treatment',      'Benzoyl peroxide spot treatment gel',      'Benzoyl Peroxide',  '2.5-5%',      'evening', 'mild',     10, 'Apply thinly on active spots only.'),
    ('acne',       'treat',      'Acne Treatment',      'Adapalene gel',                            'Adapalene',         '0.1%',        'evening', 'moderate', 20, 'Start 2-3 nights a week; expect some dryness at first.'),
    -- OILINESS
    ('oiliness',   'treat',      'Oil Control Serum',   'Niacinamide serum',                        'Niacinamide',       '2-5%',        'morning', 'mild',      5, 'Regulates sebum production.'),
    ('oiliness',   'moisturize', 'Moisturize',          'Oil-free gel moisturizer',                 NULL,                NULL,          'both',    'mild',     10, 'Hydrates without adding shine.'),
    -- DRYNESS
    ('dryness',    'cleanse',    'Cleanse',             'Cream or hydrating cleanser',              NULL,                NULL,          'both',    'mild',      5, 'Cleans without stripping natural oils.'),
    ('dryness',    'treat',      'Hydrating Serum',     'Hyaluronic acid serum (on damp skin)',     'Hyaluronic Acid',   NULL,          'morning', 'mild',      5, 'Restores and locks in hydration.'),
    ('dryness',    'moisturize', 'Deep Moisturize',     'Rich cream moisturizer',                   'Ceramides',         NULL,          'both',    'mild',     12, 'Repairs the skin barrier.'),
    -- REDNESS
    ('redness',    'treat',      'Soothing Serum',      'Soothing serum or cream',                  'Centella Asiatica', NULL,          'morning', 'mild',      5, 'Calms irritation and reduces visible redness.'),
    ('redness',    'treat',      'Redness Treatment',   'Azelaic acid cream or gel',                'Azelaic Acid',      '10%',         'evening', 'moderate', 15, 'Reduces persistent redness; gentle option.'),
    ('redness',    'protect',    'Sunscreen',           'Mineral sunscreen SPF 30+',                'Zinc Oxide',        NULL,          'morning', 'mild',      5, 'Mineral filters are less irritating for reactive skin.'),
    -- DARK SPOTS
    ('dark_spots', 'treat',      'Brightening Serum',   'Vitamin C serum',                          'Vitamin C',         '10-20%',      'morning', 'mild',     10, 'Helps fade hyperpigmentation over time.'),
    ('dark_spots', 'treat',      'Spot Fading Treatment','Azelaic acid cream or gel',               'Azelaic Acid',      '10%',         'evening', 'moderate', 12, 'Fades stubborn spots; safe during pregnancy.'),
    ('dark_spots', 'protect',    'Sunscreen',           'Broad-spectrum sunscreen SPF 50',          NULL,                NULL,          'morning', 'mild',     10, 'UV exposure darkens spots; high protection is essential.'),
    -- WRINKLES
    ('wrinkles',   'treat',      'Anti-Aging Treatment','Retinol serum or cream',                   'Retinol',           '0.25-0.5%',   'evening', 'mild',     15, 'Promotes cell turnover; start 2-3 nights a week.'),
    ('wrinkles',   'treat',      'Firming Serum',       'Peptide serum',                            'Peptides',          NULL,          'evening', 'mild',      5, 'Gentle alternative when retinol is not suitable.'),
    ('wrinkles',   'protect',    'Sunscreen',           'Broad-spectrum sunscreen SPF 50',          NULL,                NULL,          'morning', 'mild',     10, 'Prevents further UV-driven aging.')
) AS v(concern, step_category, step_title, product_type, ingredient,
       concentration, time_of_day, min_severity, priority, notes)
JOIN skin_concerns sc ON sc.name = v.concern
LEFT JOIN ingredients i ON i.name = v.ingredient;   -- LEFT: some steps have no specific ingredient


-- ============================================================
-- 5. ACHIEVEMENTS (starter gamification set)
-- ============================================================

INSERT INTO achievements (title, description, criteria_type, criteria_value) VALUES
    ('First Scan',      'Complete your very first skin scan.',   'scans_completed',   1),
    ('3-Day Streak',    'Log your routine 3 days in a row.',     'streak_days',       3),
    ('7-Day Streak',    'Log your routine 7 days in a row.',     'streak_days',       7),
    ('30-Day Streak',   'Log your routine 30 days in a row.',    'streak_days',       30),
    ('Consistent Care', 'Complete 20 routine logs in total.',    'routine_adherence', 20),
    ('Skin Tracker',    'Complete 10 skin scans over time.',     'scans_completed',   10);


-- ============================================================
-- 6. WEATHER-BASED SKIN TIPS
-- ============================================================

INSERT INTO weather_skin_tips (weather_condition, tip_text, related_skin_concern_id)
SELECT v.condition, v.tip, sc.id
FROM (VALUES
    ('hot',     'High heat increases oil production — consider a lightweight, oil-free moisturizer today.',        'oiliness'),
    ('cold',    'Cold air can strip moisture — layer on a richer moisturizer to prevent dryness.',                 'dryness'),
    ('humid',   'High humidity can clog pores — a gentle double cleanse tonight is a good idea.',                  'acne'),
    ('dry',     'Low humidity air can irritate sensitive skin — a soothing, fragrance-free product may help today.', 'redness'),
    ('high_uv', 'High UV levels accelerate visible aging — don''t skip sunscreen today.',                          'wrinkles'),
    ('high_uv', 'Strong sun can darken existing spots — reapply sunscreen every 2 hours outdoors.',                'dark_spots')
) AS v(condition, tip, concern)
JOIN skin_concerns sc ON sc.name = v.concern;


-- ============================================================
-- QUICK CHECK: expected counts
--   skin_concerns 6 | ingredients 13 | ingredient_conflicts 8
--   mapping 20 (3 base + 17 concern) | achievements 6 | weather tips 6
-- ============================================================

SELECT 'skin_concerns' AS table_name, COUNT(*) FROM skin_concerns
UNION ALL SELECT 'ingredients',          COUNT(*) FROM ingredients
UNION ALL SELECT 'ingredient_conflicts', COUNT(*) FROM ingredient_conflicts
UNION ALL SELECT 'mapping (total)',      COUNT(*) FROM concern_recommendation_mapping
UNION ALL SELECT 'mapping (base)',       COUNT(*) FROM concern_recommendation_mapping WHERE skin_concern_id IS NULL
UNION ALL SELECT 'achievements',         COUNT(*) FROM achievements
UNION ALL SELECT 'weather_skin_tips',    COUNT(*) FROM weather_skin_tips;
