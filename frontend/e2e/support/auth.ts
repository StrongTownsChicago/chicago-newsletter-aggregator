import { expect, type Page } from '@playwright/test';
import { SEED_USER_PASSWORD, type SeedUser } from '../fixtures/db/facts';

/** Signs in through the login form and waits for the redirect to `next`. */
export async function signIn(page: Page, user: SeedUser, next = '/'): Promise<void> {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel('Email address').fill(user.email);
  await page.getByLabel('Password').fill(SEED_USER_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page).toHaveURL(next);
  // Page scripts (e.g. the rule modal's) are wired by the load event.
  await page.waitForLoadState('load');
  await expect(page.getByTestId('user-email')).toHaveText(user.email);
}
