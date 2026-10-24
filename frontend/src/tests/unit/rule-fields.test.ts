import { describe, it, expect } from 'vitest';
import { readRuleFields } from '../../lib/server/rule-fields';

const buildForm = (entries: [string, string][]) => {
  const formData = new FormData();
  for (const [name, value] of entries) formData.append(name, value);
  return formData;
};

describe('readRuleFields', () => {
  it('reads a daily rule with a trimmed phrase, topics and wards', () => {
    const result = readRuleFields(buildForm([
      ['topics', 'housing'],
      ['search_term', '  bike lanes  '],
      ['wards', ' 1 '],
      ['wards', ''],
      ['is_active', 'on'],
      ['delivery_frequency', 'daily'],
    ]));
    expect(result).toEqual({
      fields: {
        topics: ['housing'],
        search_term: 'bike lanes',
        ward_numbers: ['1'],
        is_active: true,
        delivery_frequency: 'daily',
      },
    });
  });

  it('treats a missing or unknown frequency as daily', () => {
    for (const frequency of [undefined, 'monthly']) {
      const entries: [string, string][] = [['topics', 'housing']];
      if (frequency) entries.push(['delivery_frequency', frequency]);
      expect(readRuleFields(buildForm(entries)).fields?.delivery_frequency, frequency).toBe('daily');
    }
  });

  it('stores no wards and no phrase when none are given', () => {
    const { fields } = readRuleFields(buildForm([['topics', 'housing'], ['search_term', '   ']]));
    expect(fields).toMatchObject({ search_term: null, ward_numbers: null, is_active: false });
  });

  it('requires a topic or phrase on a daily rule', () => {
    expect(readRuleFields(buildForm([]))).toEqual({
      error: 'Please specify at least one topic or search phrase',
    });
  });

  it('rejects a phrase over the length limit', () => {
    const { error } = readRuleFields(buildForm([['search_term', 'x'.repeat(101)]]));
    expect(error).toBe('Search phrase must be under 100 characters');
  });

  it('drops the phrase from a weekly rule', () => {
    const { fields } = readRuleFields(buildForm([
      ['topics', 'transit'],
      ['search_term', 'bus'],
      ['delivery_frequency', 'weekly'],
    ]));
    expect(fields).toMatchObject({ search_term: null, ward_numbers: null, delivery_frequency: 'weekly' });
  });

  it('requires a topic on a weekly rule', () => {
    const { error } = readRuleFields(buildForm([['search_term', 'bus'], ['delivery_frequency', 'weekly']]));
    expect(error).toBe('At least one topic is required for weekly summaries');
  });

  it('rejects ward filters on a weekly rule', () => {
    const { error } = readRuleFields(buildForm([
      ['topics', 'transit'],
      ['wards', '5'],
      ['delivery_frequency', 'weekly'],
    ]));
    expect(error).toMatch(/^Ward filters cannot be applied to weekly summaries/);
  });
});
