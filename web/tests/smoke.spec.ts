import { expect, test } from "@playwright/test";

test("smoke: home renders (light + dark screenshots)", async ({ browser }, testInfo) => {
  const context = await browser.newContext();

  const lightPage = await context.newPage();
  await lightPage.addInitScript(() => {
    window.localStorage.setItem("theme-preference", "light");
  });
  await lightPage.goto("/");
  await expect(lightPage).toHaveURL(/\/$/);
  await lightPage.waitForTimeout(250);
  await lightPage.screenshot({ path: testInfo.outputPath("home-light.png"), fullPage: true });
  await lightPage.close();

  const darkPage = await context.newPage();
  await darkPage.addInitScript(() => {
    window.localStorage.setItem("theme-preference", "dark");
  });
  await darkPage.goto("/");
  await expect(darkPage).toHaveURL(/\/$/);
  await darkPage.waitForTimeout(250);
  await darkPage.screenshot({ path: testInfo.outputPath("home-dark.png"), fullPage: true });
  await darkPage.close();
});
