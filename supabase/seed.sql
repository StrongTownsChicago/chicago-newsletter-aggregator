-- Synthetic seed for the local stack: invented aldermen, newsletters and users.
-- No real newsletter content, people or email addresses. The end-to-end tests
-- assert these exact rows; frontend/e2e/fixtures/db/facts.ts records the facts
-- they rely on, so change both together.
--
-- Search facts: "zoning" appears in 23 newsletters (two search pages) and no
-- other newsletter contains a word that stems to "zone".

BEGIN;

-- Sources: five wards with one alderman, ward 40 with two (an alderman change)
-- and an agency with no ward.
INSERT INTO public.sources (id, source_type, name, email_address, website, signup_url, ward_number, phone) VALUES
    (1, 'alderman', 'Jordan Example', 'ward01@example.org', 'https://ward01.example.org', NULL, '1', '312-555-0101'),
    (2, 'alderman', 'Casey Sample', 'ward02@example.org', NULL, NULL, '2', NULL),
    (3, 'alderman', 'Riley Placeholder', NULL, NULL, NULL, '10', NULL),
    (4, 'alderman', 'Sam Former', 'former40@example.org', NULL, NULL, '40', NULL),
    (5, 'alderman', 'Pat Current', 'ward40@example.org', 'https://ward40.example.org', NULL, '40', '312-555-0140'),
    (6, 'alderman', 'Morgan Fixture', NULL, NULL, NULL, '50', NULL),
    (7, 'transit_agency', 'Example Transit Agency', NULL, NULL, NULL, NULL, NULL);

SELECT setval('public.sources_id_seq', (SELECT max(id) FROM public.sources));

-- Newsletters 1 to 29. Ids are 00000000-0000-4000-8000-0000000000NN; received
-- at 17:00 UTC (midday in Chicago) so every date is the same day in both zones.
INSERT INTO public.newsletters (id, received_date, subject, from_email, source_id, plain_text, raw_html, summary, topics)
SELECT
    format('00000000-0000-4000-8000-%s', lpad(seed.number::text, 12, '0'))::uuid,
    (seed.received_on || ' 17:00:00+00')::timestamptz,
    seed.subject,
    'newsletter@example.org',
    seed.source_id,
    seed.body,
    CASE WHEN seed.has_html THEN '<p>' || seed.body || '</p>' END,
    seed.summary,
    seed.topics
FROM (VALUES
    (1, 4, '2026-06-02', 'Ward 40 update: zoning hearing on Elm Street', 'The zoning committee meets Tuesday about the Elm Street proposal. Residents can comment in person.', 'A zoning hearing on the Elm Street proposal is set for Tuesday, with public comment in person and online.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (2, 4, '2026-06-09', 'Community meeting recap and zoning next steps', 'Thank you to everyone who came out. The zoning change heads to committee next month.', 'Recap of the community meeting; the zoning change goes to committee next month.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (3, 1, '2026-06-12', 'First Ward notes: zoning for corner stores', 'We are asking for zoning that lets small corner stores open on residential blocks.', 'The office supports zoning that allows corner stores on residential blocks.', ARRAY['zoning_or_development_meeting_or_approval', 'missing_middle_housing'], true),
    (4, 4, '2026-06-16', 'Zoning map amendment filed for Oak Avenue', 'A zoning map amendment was filed for the Oak Avenue lot. Details are at the ward office.', 'A zoning map amendment was filed for the Oak Avenue lot.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (5, 2, '2026-06-23', 'Summer block party schedule', 'Block party permits are open. New protected bike lanes on Maple Street open in July.', 'Block party permits are open and the Maple Street bike lanes open in July.', ARRAY['bike_lanes'], true),
    (6, 4, '2026-06-30', 'June wrap-up: budget town hall and zoning', 'Our budget town hall is Thursday. The Elm Street zoning item was deferred.', 'A budget town hall is Thursday; the Elm Street zoning item was deferred.', ARRAY['city_budget', 'zoning_or_development_meeting_or_approval'], true),
    (7, 4, '2026-07-07', 'Zoning committee approves Elm Street plan', 'The zoning committee approved the Elm Street plan with twelve homes.', 'The Elm Street plan with twelve homes passed the zoning committee.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (8, 4, '2026-07-10', 'Street repaving and zoning office hours', 'Repaving starts on Pine Street. Zoning office hours are Friday mornings.', 'Pine Street repaving starts soon; zoning office hours are Friday mornings.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (9, 6, '2026-07-14', 'Fiftieth Ward: bike lanes and zoning survey', 'Take our survey about new bike lanes and zoning near the train station.', 'A survey asks about bike lanes and zoning near the train station.', ARRAY['bike_lanes', 'zoning_or_development_meeting_or_approval'], true),
    (10, 4, '2026-07-17', 'Accessory dwelling units and zoning', 'Coach houses are allowed again under the new zoning rules for this ward.', 'Coach houses are allowed again under the new zoning rules.', ARRAY['accessory_dwelling_units', 'zoning_or_development_meeting_or_approval'], true),
    (11, 7, '2026-07-21', 'Bus route changes this summer', 'Route 99 will run every ten minutes on weekdays starting in August.', 'Route 99 runs every ten minutes on weekdays from August.', NULL, true),
    (12, 4, '2026-07-24', 'Zoning appeal hearing date set', 'The appeal for the Birch Street building will be heard next week by the zoning board.', 'The zoning board hears the Birch Street appeal next week.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (13, 3, '2026-07-28', 'Tenth Ward plain text bulletin', 'Leaf pickup starts in October.

Call the ward office to request a tree trimming.', 'Leaf pickup starts in October and tree trimming requests go to the ward office.', NULL, false),
    (14, 4, '2026-07-31', 'Farewell from the ward office and a zoning update', 'This is my last newsletter as your alderman. The zoning work continues with the next office.', 'The outgoing alderman says goodbye; zoning work continues with the next office.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (15, 5, '2026-08-04', 'Hello from your new alderman: zoning priorities', 'I am honored to serve. My first priority is zoning that allows more homes near transit.', 'The new alderman introduces themselves and puts zoning for homes near transit first.', ARRAY['zoning_or_development_meeting_or_approval', 'missing_middle_housing'], true),
    (16, 5, '2026-08-07', 'Zoning listening session recap', 'Over sixty neighbors joined the zoning listening session at the library.', 'Over sixty neighbors joined the zoning listening session.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (17, 2, '2026-08-11', 'Back to school safety walk', 'Join us for a safety walk along the school route. New crosswalks and bike lanes are planned.', NULL, ARRAY['bike_lanes', 'street_safety_or_traffic_calming'], true),
    (18, 5, '2026-08-14', 'Four-flats and zoning reform explained', 'Here is how the four-flat zoning reform would work on our blocks.', 'An explainer on how four-flat zoning reform would work in the ward.', ARRAY['4_flats_legalization', 'zoning_or_development_meeting_or_approval'], true),
    (19, 1, '2026-08-18', 'First Ward budget and zoning roundup', 'Budget hearings start soon. A zoning change for the old warehouse is under review.', 'Budget hearings start soon and a warehouse zoning change is under review.', ARRAY['city_budget', 'zoning_or_development_meeting_or_approval'], true),
    (20, 5, '2026-08-21', 'Zoning committee agenda for September', 'Two projects from our ward are on the September zoning committee agenda.', 'Two ward projects are on the September zoning committee agenda.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (21, 6, '2026-08-25', 'Fiftieth Ward weekly bulletin with every neighborhood event, street closure, park program, library story time, farmers market date, recycling reminder and volunteer opportunity happening across the ward over the next several weeks', 'Events, closures and programs across the ward for the coming weeks.', 'A long list of events, closures and programs across the ward.', NULL, true),
    (22, 5, '2026-08-28', 'Single-stair buildings and zoning', 'We support single-stair reform alongside zoning changes for small apartment buildings.', 'Support for single-stair reform alongside zoning changes for small buildings.', ARRAY['single_stair_reform', 'zoning_or_development_meeting_or_approval'], true),
    (23, 5, '2026-09-01', 'Labor Day hours and zoning reminders', 'The ward office is closed Monday. Zoning comment deadlines are below.', 'The office closes for Labor Day; zoning comment deadlines are listed.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (24, 5, '2026-09-04', 'Zoning vote results', 'The zoning committee approved both ward projects this week.', 'Both ward projects passed the zoning committee.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (25, 2, '2026-09-08', 'Second Ward: bike lanes and a zoning question', 'Maple Street bike lanes are done. Should the zoning for the old bank change? Tell us.', 'The Maple Street bike lanes are finished and the office asks about rezoning the old bank.', ARRAY['bike_lanes', 'zoning_or_development_meeting_or_approval'], true),
    (26, 5, '2026-09-11', 'Transit funding and zoning near stations', 'State transit funding is at risk. Zoning near stations should allow more homes.', 'Transit funding is at risk; the office backs more homes near stations through zoning.', ARRAY['transit_funding', 'zoning_or_development_meeting_or_approval'], true),
    (27, 3, '2026-09-15', 'Tenth Ward fall festival', 'The fall festival is Saturday in the park with music and food trucks.', 'The fall festival is Saturday in the park.', NULL, true),
    (28, 5, '2026-09-18', 'Zoning office hours move to Wednesdays', 'Starting next week, zoning office hours move to Wednesday evenings.', 'Zoning office hours move to Wednesday evenings.', ARRAY['zoning_or_development_meeting_or_approval'], true),
    (29, 6, '2026-09-22', 'Fiftieth Ward tax assessment help', 'Volunteers can help you appeal your property tax assessment on Tuesday.', 'Volunteers help with property tax assessment appeals on Tuesday.', ARRAY['tax_policy'], true)
) AS seed (number, source_id, received_on, subject, body, summary, topics, has_html);

-- Newsletter 30: the newest, with a body that uses the markup the detail page renders.
INSERT INTO public.newsletters (id, received_date, subject, from_email, source_id, plain_text, raw_html, summary, topics) VALUES (
    '00000000-0000-4000-8000-000000000030',
    '2026-09-28 17:00:00+00',
    'First Ward September newsletter: bike lanes and zoning',
    'newsletter@example.org',
    1,
    'September in the First Ward. Protected bike lanes are coming to Lake Street. The zoning committee approved the Lake Street homes. Read more on the ward website.',
    '<h1>September in the First Ward</h1>'
        || '<p>Protected <strong>bike lanes</strong> are coming to Lake Street.</p>'
        || '<h2>Zoning</h2><p>The zoning committee approved the Lake Street homes.</p>'
        || '<table><caption>Upcoming meetings</caption><tr><th scope="col">Date</th><th scope="col">Meeting</th></tr><tr><td>October 6</td><td>Ward night</td></tr></table>'
        || '<p><img src="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%2240%22 height=%2210%22/%3E" alt="Lake Street bike lane plan"></p>'
        || '<p><a href="https://ward01.example.org/september">Read more on the ward website</a></p>',
    'Protected bike lanes are coming to Lake Street and the zoning committee approved the Lake Street homes, the office reports in its September newsletter.',
    ARRAY['bike_lanes', 'zoning_or_development_meeting_or_approval']
);

-- Users who can sign in (password "local-test-password"). The on_auth_user_created
-- trigger (migration 001) gives each a user_profiles row with notifications on.
INSERT INTO auth.users (
    instance_id, id, aud, role, email, encrypted_password, email_confirmed_at,
    raw_app_meta_data, raw_user_meta_data, created_at, updated_at,
    confirmation_token, recovery_token, email_change_token_new, email_change
)
SELECT
    '00000000-0000-0000-0000-000000000000',
    seed.id,
    'authenticated',
    'authenticated',
    seed.email,
    extensions.crypt('local-test-password', extensions.gen_salt('bf')),
    '2026-06-01 12:00:00+00',
    '{"provider": "email", "providers": ["email"]}',
    '{}',
    '2026-06-01 12:00:00+00',
    '2026-06-01 12:00:00+00',
    '', '', '', ''
FROM (VALUES
    -- Reads its rules; never changes them.
    ('aaaaaaaa-0000-4000-8000-000000000001'::uuid, 'rules-reader@example.com'),
    -- Creates, edits and deletes rules.
    ('aaaaaaaa-0000-4000-8000-000000000002'::uuid, 'rules-editor@example.com'),
    -- Unsubscribes by token.
    ('aaaaaaaa-0000-4000-8000-000000000003'::uuid, 'unsubscriber@example.com')
) AS seed (id, email);

INSERT INTO auth.identities (id, user_id, provider_id, provider, identity_data, last_sign_in_at, created_at, updated_at)
SELECT
    gen_random_uuid(),
    users.id,
    users.id::text,
    'email',
    jsonb_build_object('sub', users.id::text, 'email', users.email, 'email_verified', true),
    '2026-06-01 12:00:00+00',
    '2026-06-01 12:00:00+00',
    '2026-06-01 12:00:00+00'
FROM auth.users AS users;

INSERT INTO public.notification_rules (id, user_id, name, is_active, created_at, updated_at, topics, search_term, ward_numbers, delivery_frequency) VALUES
    ('bbbbbbbb-0000-4000-8000-000000000001', 'aaaaaaaa-0000-4000-8000-000000000001', 'Ward 40 zoning updates', true,
        '2026-06-02 12:00:00+00', '2026-06-02 12:00:00+00', ARRAY['zoning_or_development_meeting_or_approval'], 'zoning', ARRAY['40'], 'daily'),
    ('bbbbbbbb-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000001', 'Citywide street safety', false,
        '2026-06-01 12:00:00+00', '2026-06-01 12:00:00+00', ARRAY['bike_lanes', 'street_safety_or_traffic_calming'], NULL, NULL, 'weekly'),
    ('bbbbbbbb-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000002', 'First Ward bike lanes', true,
        '2026-06-01 12:00:00+00', '2026-06-01 12:00:00+00', ARRAY['bike_lanes'], NULL, ARRAY['1'], 'daily');

COMMIT;
