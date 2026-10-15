# Forma design direction

Forma turns a lesson request into a short explanatory animation. The interface should make the next action obvious and reveal secondary information only when requested.

## Shared theme

All pages use the same dark theme and shared header. Define colors in `app/globals.css`, and use those variables rather than adding page-specific palettes.

- Background: `#09090c`.
- Surface: `#141419`.
- Raised surface: `#1b1b23`.
- Main text: `#f2f1f6`.
- Secondary text: `#a5a3b1`.
- Accent: `#c6bef5`, a muted violet.

Use the Forma wordmark and rounded geometric F in `app/components/brand.tsx`. The icon follows the same construction. Avoid exposing the renderer's name as the product name.

Typography uses locally hosted Geist across the landing page and studio, with Segoe UI and system sans fallbacks. Large headings have medium weight and close letter spacing. Body text stays comfortably readable. Controls use 8px corners; large surfaces use 16px. Avoid uppercase labels, decorative statistics, repeated cards, and long marketing sections.

## Layout and motion

The landing page has one headline, one primary action, and a large circle-to-wave motion study. The diagram explains a real relationship, runs slowly, and can be paused or explored with its keyboard-accessible timeline. Respect reduced-motion preferences. Keep other page motion to a brief entrance and feedback after user actions. Design dials: visual variance 6, motion 3, density 2. Preserve the Forma brand and routes when refining the page.

The studio starts with a centered heading and one compact prompt composer that grows with its text. Use a 24px radius for this composer and a round send control. Quality, sharing consent, and search remain under Options in its toolbar. Options close on outside click or Escape. Keep the studio background plain so requests and video output remain the focus. Move the composer toward the top when a job is active. Display one active generation stage. Show video output only when available, with lesson information under a single disclosure.

Keep the same colors, controls, borders, focus states, and logo on future pages. Check both desktop and mobile layouts before delivery.
