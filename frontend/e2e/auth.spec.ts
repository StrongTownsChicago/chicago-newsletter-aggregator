import { test, expect } from '@playwright/test';
import { RULES_READER, SEED_USER_PASSWORD } from './fixtures/db/facts';
import { signIn } from './support/auth';

test('signs in, shows the account in the header, and signs out', async ({ page }) => {
  await signIn(page, RULES_READER);

  await page.getByTestId('signout-button').click();

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByTestId('user-email')).toHaveCount(0);
  await expect(page.getByTestId('signin-link')).toBeVisible();
});

test('a wrong password keeps the visitor on the sign-in page with an error', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Email address').fill(RULES_READER.email);
  await page.getByLabel('Password').fill('not-the-password');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL(/\/login\?error=/);
  await expect(page.getByText('Invalid login credentials')).toBeVisible();
  await expect(page.getByTestId('user-email')).toHaveCount(0);
});

test('the preferences page sends signed-out visitors to sign in, then back', async ({ page }) => {
  await page.goto('/preferences');
  await expect(page).toHaveURL('/login?next=%2Fpreferences');

  await page.getByLabel('Email address').fill(RULES_READER.email);
  await page.getByLabel('Password').fill(SEED_USER_PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page).toHaveURL('/preferences');
  await expect(page.getByRole('heading', { name: 'Notification Preferences', level: 1 })).toBeVisible();
});

test('signing up opens the preferences page ready to create a first alert', async ({ page }) => {
  // Unique per attempt, so a retry doesn't hit "already registered".
  const email = `new-reader-${Date.now()}@example.com`;
  await page.goto('/signup');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password').fill(SEED_USER_PASSWORD);
  await page.getByRole('button', { name: 'Create account' }).click();

  await expect(page).toHaveURL('/preferences?welcome=1');
  await expect(page.getByTestId('user-email')).toHaveText(email);
  await expect(page.getByTestId('welcome-banner')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Create Your First Alert' })).toBeVisible();
});

test('signing up with a registered email shows an error', async ({ page }) => {
  await page.goto('/signup');
  await page.getByLabel('Email address').fill(RULES_READER.email);
  await page.getByLabel('Password').fill(SEED_USER_PASSWORD);
  await page.getByRole('button', { name: 'Create account' }).click();

  await expect(page).toHaveURL(/\/signup\?error=/);
  await expect(page.getByTestId('user-email')).toHaveCount(0);
});
