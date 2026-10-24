import { test, expect, type Locator, type Page } from '@playwright/test';
import { EDITOR_RULE, READER_RULES, RULE_WARD_OPTIONS, RULES_EDITOR, RULES_READER } from './fixtures/db/facts';
import { signIn } from './support/auth';
import { restoreSeededNotificationPreferences } from './support/seed-state';

const ruleCards = (page: Page): Locator => page.getByTestId('notification-rule');
const ruleCard = (page: Page, name: string): Locator =>
  ruleCards(page).filter({ has: page.getByRole('heading', { name, exact: true }) });
const ruleModal = (page: Page): Locator => page.locator('#ruleModal');

test.describe('a user with rules', () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, RULES_READER, '/preferences');
  });

  test('lists their rules newest first with what each matches', async ({ page }) => {
    await expect(page.getByText(`${READER_RULES.length} of 5 rules used`)).toBeVisible();
    await expect(ruleCards(page).getByRole('heading', { level: 3 })).toHaveText(READER_RULES.map((rule) => rule.name));

    const [daily, weekly] = READER_RULES;
    const dailyCard = ruleCard(page, daily.name);
    await expect(dailyCard).toContainText('Active');
    await expect(dailyCard).toContainText(`Matches: "${daily.searchTerm}"`);
    await expect(dailyCard).toContainText(new RegExp(String.raw`Limited to Wards:\s*${daily.wards?.join(String.raw`,\s*`)}`));

    const weeklyCard = ruleCard(page, weekly.name);
    await expect(weeklyCard).toContainText('Disabled');
    await expect(weeklyCard).toContainText('Weekly Report');
    for (const label of weekly.topicLabels ?? []) {
      await expect(weeklyCard.getByText(label, { exact: true })).toBeVisible();
    }
  });

  test('editing a rule opens the modal filled in with it', async ({ page }) => {
    const [daily] = READER_RULES;
    await ruleCard(page, daily.name).getByRole('button', { name: 'Edit' }).click();

    const modal = ruleModal(page);
    await expect(modal).toBeVisible();
    await expect(modal.getByRole('heading', { name: 'Edit Notification Rule' })).toBeVisible();
    await expect(modal.getByLabel('Rule Name')).toHaveValue(daily.name);
    await expect(modal.getByLabel('Search Phrase (optional)')).toHaveValue(daily.searchTerm ?? '');
    await expect(modal.locator('input[name="wards"]:checked')).toHaveCount(daily.wards?.length ?? 0);
    await expect(modal.locator('input[name="wards"]')).toHaveCount(RULE_WARD_OPTIONS.length);

    await modal.getByRole('button', { name: 'Cancel' }).click();
    await expect(modal).toBeHidden();
  });
});

// One user's rules change through these steps, so they run in order.
test.describe.serial('a user changing their rules', () => {
  // Unique per run, so a retried test finds only its own rule.
  const newRuleName = `Ward 2 street safety ${Date.now()}`;
  const renamedRuleName = `${newRuleName} (renamed)`;

  test.beforeEach(async ({ page }) => {
    await signIn(page, RULES_EDITOR, '/preferences');
  });

  test('creates a daily rule', async ({ page }) => {
    await page.getByRole('button', { name: 'Add Rule' }).click();
    const modal = ruleModal(page);
    await modal.getByLabel('Rule Name').fill(newRuleName);
    await modal.getByLabel('Street safety & traffic calming').first().check();
    await modal.getByRole('button', { name: 'Show Wards' }).click();
    await modal.locator('label', { hasText: /^\s*2\s*$/ }).click();
    await page.getByRole('button', { name: 'Save Rule' }).click();

    await expect(page).toHaveURL(/message=Rule(\+|%20| )created/);
    const card = ruleCard(page, newRuleName);
    await expect(card).toContainText('Street safety & traffic calming');
    await expect(card).toContainText(/Limited to Wards:\s*2\s/);
    await expect(ruleCard(page, EDITOR_RULE.name)).toHaveCount(1);
  });

  test('renames the rule and turns it off', async ({ page }) => {
    await ruleCard(page, newRuleName).getByRole('button', { name: 'Edit' }).click();
    const modal = ruleModal(page);
    await modal.getByLabel('Rule Name').fill(renamedRuleName);
    await modal.getByLabel('Enable this rule').uncheck();
    await page.getByRole('button', { name: 'Save Rule' }).click();

    await expect(page).toHaveURL(/message=Rule(\+|%20| )updated/);
    await expect(ruleCard(page, newRuleName)).toHaveCount(0);
    await expect(ruleCard(page, renamedRuleName)).toContainText('Disabled');
  });

  test('keeps the rule when the delete is not confirmed', async ({ page }) => {
    const dialogShown = page.waitForEvent('dialog');
    page.once('dialog', (dialog) => dialog.dismiss());
    await ruleCard(page, renamedRuleName).getByRole('button', { name: 'Delete' }).click();

    expect((await dialogShown).message()).toBe('Are you sure you want to delete this rule?');
    await page.reload();
    await expect(ruleCard(page, renamedRuleName)).toHaveCount(1);
  });

  test('deletes the rule after confirming', async ({ page }) => {
    page.once('dialog', (dialog) => dialog.accept());
    await ruleCard(page, renamedRuleName).getByRole('button', { name: 'Delete' }).click();

    await expect(page).toHaveURL(/message=Rule(\+|%20| )deleted/);
    await expect(ruleCard(page, renamedRuleName)).toHaveCount(0);
    await expect(ruleCard(page, EDITOR_RULE.name)).toHaveCount(1);
  });

  test('turns email notifications off and on', async ({ page }) => {
    await restoreSeededNotificationPreferences(RULES_EDITOR.id);
    await page.reload();
    const toggle = page.locator('#enabled');
    await expect(toggle).toBeChecked();

    await toggle.uncheck({ force: true });
    await page.getByRole('button', { name: 'Save Preferences' }).click();
    await expect(page).toHaveURL(/message=Preferences(\+|%20| )updated/);
    await expect(toggle).not.toBeChecked();

    await toggle.check({ force: true });
    await page.getByRole('button', { name: 'Save Preferences' }).click();
    await expect(toggle).toBeChecked();
  });
});
