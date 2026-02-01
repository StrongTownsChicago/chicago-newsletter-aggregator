import { test, expect } from '@playwright/test';

test('can view newsletter detail', async ({ page }) => {
  await page.goto('/');
  
  const firstCardTitle = page.getByTestId('newsletter-title').first();
  if (await firstCardTitle.count() > 0) {
    const titleText = await firstCardTitle.innerText();
    await firstCardTitle.locator('a').click();
    
    await expect(page).toHaveURL(/\/newsletter\/.+/);
    await expect(page.getByTestId('newsletter-detail')).toBeVisible();
    await expect(page.getByTestId('newsletter-detail-title')).toHaveText(titleText);
    await expect(page.getByTestId('newsletter-detail-content')).toBeVisible();
  }
});

test('can return home from detail page', async ({ page }) => {
    // Navigate directly if we have no cards, but let's assume we want to test the back link
    await page.goto('/');
    const firstCard = page.getByTestId('newsletter-title').first();
    if (await firstCard.count() > 0) {
        await firstCard.locator('a').click();
        await page.getByRole('link', { name: /back to newsletters/i }).click();
        await expect(page).toHaveURL(/\/$/);
    }
});
