# Visual regression

The frontend has a deterministic Chromium screenshot gate in GitHub Actions.
It runs in the `mcr.microsoft.com/playwright:v1.62.1-noble` image pinned to
digest `sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e`,
matching the exact `@playwright/test` version in `package-lock.json`.

The suite covers seven representative states:

- Russian desktop landing page with stable decision statistics;
- Georgian mobile landing page and expanded navigation;
- English legislation list with deliberately long legal titles;
- Georgian empty guide registry;
- Russian invalid-credentials message;
- English expired/missing password-reset token on mobile.

All API responses used by the suite are local fixtures. Viewports, timezone,
locale, color scheme, device scale and reduced-motion preference are pinned.
The test waits for the selected UI language and self-hosted fonts before taking
a screenshot. It also fails on horizontal overflow.

## Normal CI use

Run the committed baseline without modifying it:

```bash
cd frontend
npm ci
npm run build
npm run test:visual
```

On failure, the `Deterministic visual regression` job uploads `test-results`
and the HTML report as a 14-day `visual-regression-<run-id>` artifact. Review
the expected image, actual image and diff before deciding whether the change is
a regression.

## Intentional baseline update

Baselines are product evidence, not disposable build output. Update them only
for an intentional reviewed UI change and use the same pinned Linux image as
CI. From PowerShell in `frontend`:

```powershell
docker run --rm --ipc=host `
  --volume "${PWD}:/work" `
  --volume infohub-visual-node-modules:/work/node_modules `
  --volume infohub-visual-next:/work/.next `
  --workdir /work `
  mcr.microsoft.com/playwright@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e `
  bash -lc "npm ci && npm run build && npm run test:visual:update"
```

Inspect every changed PNG before committing it. Never update snapshots merely
to make a failing job green.
