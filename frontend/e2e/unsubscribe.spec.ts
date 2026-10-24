import { test, expect } from '@playwright/test';
import { UNSUBSCRIBER } from './fixtures/db/facts';
import { restoreSeededNotificationPreferences } from './support/seed-state';
import { mintUnsubscribeToken } from './support/unsubscribe-token';

test('a valid link asks to confirm, then unsubscribes once', async ({ page }) => {
  await restoreSeededNotificationPreferences(UNSUBSCRIBER.id);
  const token = await mintUnsubscribeToken(UNSUBSCRIBER.id);
  await page.goto(`/unsubscribe?token=${token}`);

  await expect(page.getByRole('heading', { name: 'Confirm Unsubscribe', level: 1 })).toBeVisible();
  await page.getByRole('link', { name: 'Yes, Unsubscribe' }).click();
  await expect(page.getByRole('heading', { name: 'Successfully Unsubscribed', level: 1 })).toBeVisible();

  await page.goto(`/unsubscribe?token=${token}`);
  await expect(page.getByRole('heading', { name: 'Already Unsubscribed', level: 1 })).toBeVisible();
});

test('a link signed with another key is refused', async ({ page }) => {
  const token = await mintUnsubscribeToken(UNSUBSCRIBER.id, 'some-other-secret');
  await page.goto(`/unsubscribe?token=${token}&confirm=true`);

  await expect(page.getByRole('heading', { name: 'Unsubscribe Error', level: 1 })).toBeVisible();
  await expect(page.getByText('This unsubscribe link is invalid or has expired.')).toBeVisible();
});

test('the API refuses a malformed token', async ({ request }) => {
  const response = await request.post('/api/notifications/unsubscribe', { data: { token: 'not-a-token' } });

  expect(response.status()).toBe(400);
  expect(await response.json()).toEqual({ error: 'Invalid or expired token' });
});
