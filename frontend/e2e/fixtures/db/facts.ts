// What supabase/seed.sql puts in the local database, for exact assertions in
// the end-to-end specs. Change the seed and this file together.

/** Newsletter ids in the seed are numbered 1 to 30. */
export const seededNewsletterId = (number: number): string =>
  `00000000-0000-4000-8000-${String(number).padStart(12, '0')}`;

export const NEWSLETTER_COUNT = 30;
export const ALL_NEWSLETTER_IDS = Array.from({ length: NEWSLETTER_COUNT }, (_, index) => seededNewsletterId(index + 1));

/** The newest newsletter, first on the home page; its body uses headings, a table, an image and a link. */
export const FEATURED_NEWSLETTER = {
  id: seededNewsletterId(30),
  subject: 'First Ward September newsletter: bike lanes and zoning',
  sourceName: 'Jordan Example',
  ward: 1,
  receivedDate: 'September 28, 2026',
  topicLabels: ['Bike lanes', 'Zoning & development approvals'],
  bodyHeading: 'September in the First Ward',
  bodyLink: { name: 'Read more on the ward website', href: 'https://ward01.example.org/september' },
  sourcePhone: '312-555-0101',
  sourceEmail: 'ward01@example.org',
};

/** Has no raw_html, so the detail page shows its plain text. */
export const PLAIN_TEXT_NEWSLETTER = {
  id: seededNewsletterId(13),
  subject: 'Tenth Ward plain text bulletin',
  bodyLines: ['Leaf pickup starts in October.', 'Call the ward office to request a tree trimming.'],
};

/** Has no summary. */
export const NO_SUMMARY_NEWSLETTER = { id: seededNewsletterId(17), subject: 'Back to school safety walk' };

export const LONG_SUBJECT_NEWSLETTER = {
  id: seededNewsletterId(21),
  subject:
    'Fiftieth Ward weekly bulletin with every neighborhood event, street closure, park program, library story time, farmers market date, recycling reminder and volunteer opportunity happening across the ward over the next several weeks',
};

/** Stored before ingestion sanitized markup: its HTML has a script and an onerror handler that set `data-unsafe-markup-ran` on <html>. */
export const UNSAFE_MARKUP_NEWSLETTER = { id: seededNewsletterId(27), subject: 'Tenth Ward fall festival' };

/** From a source with no ward. */
export const AGENCY_NEWSLETTER = {
  id: seededNewsletterId(11),
  subject: 'Bus route changes this summer',
  sourceName: 'Example Transit Agency',
};

/** Home page order is newest first; these are the first and last newsletters on page 2. */
export const HOME_PAGE_TWO = { firstSubject: 'Accessory dwelling units and zoning', count: 10 };

export const SEARCH_WORD = 'zoning';
export const SEARCH_WORD_MATCHES = 23;
/** Matches on the second search page (20 per page). */
export const SEARCH_WORD_SECOND_PAGE_MATCHES = 3;

/** The search timeline for SEARCH_WORD, month by month. */
export const SEARCH_WORD_TIMELINE = [
  { month: '2026-06', label: 'Jun 2026', newsletters: 5, wards: 2 },
  { month: '2026-07', label: 'Jul 2026', newsletters: 6, wards: 2 },
  { month: '2026-08', label: 'Aug 2026', newsletters: 6, wards: 2 },
  { month: '2026-09', label: 'Sep 2026', newsletters: 6, wards: 3 },
];

/** Newsletters tagged bike_lanes. */
export const BIKE_LANES_TOPIC = { id: 'bike_lanes', label: 'Bike lanes', newsletters: 5 };

/** Ward dropdown labels on /search, in order. */
export const WARD_OPTION_LABELS = [
  'Ward 1 – Jordan Example',
  'Ward 2 – Casey Sample',
  'Ward 10 – Riley Placeholder',
  'Ward 40 – Pat Current, Sam Former',
  'Ward 50 – Morgan Fixture',
];

export const WARD_1 = { ward: 1, alderman: 'Jordan Example', newsletters: 3, zoningNewsletters: 3 };

/** A ward with two alderman sources, newest first, whose newsletters are merged. */
export const WARD_40 = {
  ward: 40,
  aldermen: ['Pat Current', 'Sam Former'],
  newsletters: 18,
  latestSubject: 'Zoning office hours move to Wednesdays',
  formerAldermanSubject: 'Farewell from the ward office and a zoning update',
};

/** A ward with no source in the seed. */
export const WARD_WITHOUT_ALDERMAN = 3;

/** Password of every seeded user. */
export const SEED_USER_PASSWORD = 'local-test-password';

export interface SeedUser {
  id: string;
  email: string;
}

/** Reads its rules; no test changes them. */
export const RULES_READER: SeedUser = { id: 'aaaaaaaa-0000-4000-8000-000000000001', email: 'rules-reader@example.com' };
/** Creates, edits and deletes rules. */
export const RULES_EDITOR: SeedUser = { id: 'aaaaaaaa-0000-4000-8000-000000000002', email: 'rules-editor@example.com' };
/** Unsubscribes by token. */
export const UNSUBSCRIBER: SeedUser = { id: 'aaaaaaaa-0000-4000-8000-000000000003', email: 'unsubscriber@example.com' };

/** RULES_READER's rules, newest first as the preferences page lists them. */
export const READER_RULES = [
  { name: 'Ward 40 zoning updates', active: true, frequency: 'daily', searchTerm: 'zoning', wards: ['40'] },
  { name: 'Citywide street safety', active: false, frequency: 'weekly', topicLabels: ['Bike lanes', 'Street safety & traffic calming'] },
];

export const EDITOR_RULE = { name: 'First Ward bike lanes', topicLabel: 'Bike lanes', wards: ['1'] };

/** Wards offered by the rule modal's ward picker: those with a source. */
export const RULE_WARD_OPTIONS = ['1', '2', '10', '40', '50'];
