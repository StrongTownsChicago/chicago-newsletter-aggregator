import { describe, it, expect } from 'vitest';
import { ALL_TOPICS, TOPIC_LABELS, formatTopicLabel } from '../../lib/topics';

describe('formatTopicLabel', () => {
  it.each([
    ['4_flats_legalization', '4-flats legalization'],
    ['accessory_dwelling_units', 'Accessory dwelling units (ADUs)'],
    ['street_safety_or_traffic_calming', 'Street safety & traffic calming'],
    ['zoning_or_development_meeting_or_approval', 'Zoning & development approvals'],
  ])('labels %s as %s', (topicId, expected) => {
    expect(formatTopicLabel(topicId)).toBe(expected);
  });

  it.each([
    ['parking_reform', 'Parking reform'],
    ['double__underscore_', 'Double underscore'],
    ['housing', 'Housing'],
    ['', ''],
  ])('falls back for unknown id %j', (topicId, expected) => {
    expect(formatTopicLabel(topicId)).toBe(expected);
  });

  it('does not treat inherited object keys as labels', () => {
    expect(formatTopicLabel('constructor')).toBe('Constructor');
    expect(formatTopicLabel('toString')).toBe('ToString');
  });

  it('has a label for every canonical topic and none for retired ones', () => {
    expect(Object.keys(TOPIC_LABELS).sort()).toEqual([...ALL_TOPICS].sort());
  });

  it('gives every canonical topic a distinct label without underscores', () => {
    const labels = ALL_TOPICS.map(formatTopicLabel);
    for (const label of labels) {
      expect(label).not.toContain('_');
      expect(label.length).toBeGreaterThan(0);
    }
    expect(new Set(labels).size).toBe(labels.length);
  });
});
