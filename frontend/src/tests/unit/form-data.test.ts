import { describe, it, expect } from 'vitest';
import { formText, formTexts } from '../../lib/server/form-data';

const upload = () => new File(['contents'], 'upload.txt', { type: 'text/plain' });

const buildForm = (entries: [string, string | File][]) => {
  const formData = new FormData();
  for (const [name, value] of entries) formData.append(name, value);
  return formData;
};

describe('formText', () => {
  it('returns the text of a field', () => {
    expect(formText(buildForm([['email', 'a@example.com']]), 'email')).toBe('a@example.com');
  });

  it('returns an empty string for an empty field', () => {
    expect(formText(buildForm([['email', '']]), 'email')).toBe('');
  });

  it('returns undefined for a missing field', () => {
    expect(formText(buildForm([]), 'email')).toBeUndefined();
  });

  it('treats an uploaded File as missing', () => {
    expect(formText(buildForm([['email', upload()]]), 'email')).toBeUndefined();
  });

  it('returns the first value of a repeated field', () => {
    expect(formText(buildForm([['topic', 'Crime'], ['topic', 'Housing']]), 'topic')).toBe('Crime');
  });
});

describe('formTexts', () => {
  it('returns every text value in order', () => {
    expect(formTexts(buildForm([['topics', 'Crime'], ['topics', 'Housing']]), 'topics'))
      .toEqual(['Crime', 'Housing']);
  });

  it('keeps empty strings', () => {
    expect(formTexts(buildForm([['wards', ''], ['wards', '1']]), 'wards')).toEqual(['', '1']);
  });

  it('returns an empty list for a missing field', () => {
    expect(formTexts(buildForm([]), 'topics')).toEqual([]);
  });

  it('drops uploaded Files and keeps the text values', () => {
    expect(formTexts(buildForm([['topics', 'Crime'], ['topics', upload()], ['topics', 'Housing']]), 'topics'))
      .toEqual(['Crime', 'Housing']);
  });
});
