# Chop Shop website: launch checklist

The website is plain files in this `site/` folder. There is nothing to build.

All the values you fill in live in one file: `site/config.js`.
Until a value is filled in, the matching button on the site shows "Coming soon" and does nothing.

## Preview the site on your computer

1. Open a terminal in the project folder.
2. Run: `python -m http.server 8080 --directory site`
3. Open http://localhost:8080 in your browser.
4. Stop it with Ctrl+C when you are done.

## Check nothing is broken

Run: `python -m pytest tests/test_site.py`

It checks that links between pages work, that the prices on the page are right, and that the legal pages carry the "Draft" notice.

## What each config key does

Open `site/config.js`. Put each value between the quotes.

| Key | What goes in it | If left empty, a visitor sees |
|---|---|---|
| `discordUrl` | Invite link to your Discord server. Not used by any page yet; safe to fill in or leave empty. | Nothing changes. |
| `freeClipUrl` | Where people ask for a free clip (Discord invite or a form). | The "Get my free clip" buttons say "Coming soon". |
| `links.clip` | Payment Link for a single clip. | "Buy one" says "Coming soon". |
| `links.pack10` | Payment Link for the pack of 10. | "Buy 10" says "Coming soon". |
| `links.pack30` | Payment Link for the pack of 30. | "Buy 30" says "Coming soon". |
| `links.starter` | Payment Link for Starter. | "Start Starter" says "Coming soon". |
| `links.pro` | Payment Link for Pro. | "Go Pro" says "Coming soon". |
| `managedUrl` | A way to contact you about Managed: a `mailto:you@example.com` link or a Discord invite. | The "By invitation — ask us" button is replaced by "Coming soon". |
| `examples` | Real clips you may show. See step 5. | The examples section is hidden. |

## Launch steps

Tick each box as you finish it. Do them in order.

### 1. Stripe: five products and five Payment Links

- [ ] Create a Stripe account if you do not have one. Finish whatever Stripe asks so you can take real payments.

Create these five products. Follow Stripe's current documentation for the exact clicks (search for "Stripe Payment Links").

| Config key | Product name (suggested) | Price | Type |
|---|---|---|---|
| `clip` | Single clip | $2 | One-time, customer can adjust the quantity |
| `pack10` | Pack of 10 clips | $15 | One-time |
| `pack30` | Pack of 30 clips | $36 | One-time |
| `starter` | Starter | $9 per month | Recurring monthly |
| `pro` | Pro | $19 per month | Recurring monthly |

Managed ($149 per month) has no public Payment Link. Customers contact you instead (see step 1e).

- [ ] **1a. In Stripe test mode, create the five products** with the prices above, and **one Payment Link for each product**. On every link:
  - [ ] Add two custom text fields and make both required.
    - Field 1 label: `Your channel link`
    - Field 2 label: `Stream link (YouTube or Twitch VOD)`
  - [ ] Turn on the box where the customer must agree to your terms of service. Follow Stripe's documentation for where the terms of service URL is set. Use the address of your `terms.html` page once the site is live (steps 3 and 4). If it is not live yet, finish the link later.
- [ ] **1b. Make one test purchase** with a test-mode link (see Stripe's documentation for test mode). Confirm where the two field answers appear in your Stripe Dashboard.
- [ ] **1c. Switch to live mode and create the same five products and five Payment Links again.** Test-mode links do not take real money, so the live ones are the ones the site needs. Copy each live link. Give each live link the same two required fields and the terms box as the test ones.
- [ ] **1d. Paste the five LIVE-mode links into `site/config.js`.** Do not use the test-mode ones.

```js
links: {
  clip: "https://buy.stripe.com/...",
  pack10: "https://buy.stripe.com/...",
  pack30: "https://buy.stripe.com/...",
  starter: "https://buy.stripe.com/...",
  pro: "https://buy.stripe.com/..."
},
```

- [ ] **1e. Set `managedUrl`** to a way to reach you, for example `"mailto:you@example.com"` or your Discord invite link.
- [ ] **1f. Contact address:** replace the text `address coming soon` in the footers of index.html, terms.html and privacy.html with a mailto link to your address.
- [ ] **1g. Check the buttons on the local preview** (see "Preview the site on your computer" above). The five buy buttons and the Managed button should now be clickable instead of saying "Coming soon".

### 2. Free clips

- [ ] Create a Discord server, or a simple form, where people ask for their free clip. Ask for the same two things: channel link and stream link.
- [ ] Paste its address into `freeClipUrl` in `site/config.js`.
- [ ] If you made a Discord server, also paste its invite into `discordUrl`.

### 3. Hosting (Cloudflare Pages)

- [ ] Put the website on a static host. Cloudflare Pages works. Follow Cloudflare's current documentation for the exact clicks (search for "Cloudflare Pages Git integration").
- [ ] Connect your own GitHub repository (the one the `fork` remote points to, not the original).
- [ ] Pick the branch to publish. The site was built on the branch `chop-shop-site`. Either merge that branch into the branch your host publishes from, or point the host at the branch that contains the `site/` folder. Do this before deploying.
- [ ] Set the build command to empty (nothing).
- [ ] Set the output directory to `site`.
- [ ] Save and wait for the first deploy. Open the address it gives you and check the page loads.

Every time you push a change to that branch, the site updates.

### 4. Domain

- [ ] Buy a domain name from any registrar.
- [ ] Add it to your Cloudflare Pages project and point it at the site. Follow Cloudflare's current documentation for custom domains.
- [ ] Open the domain and check the site loads.
- [ ] If you finished Stripe links before the domain existed, go back and set the terms of service URL on each Payment Link (see Stripe's documentation).

### 5. Examples (only with written permission)

- [ ] Add an entry to `examples` in `site/config.js` only for a clip whose owner agreed in writing. A Discord message or email counts. Keep a copy.

```js
examples: [
  { streamer: "Streamer name", channelUrl: "https://...", videoUrl: "https://..." }
]
```

No entries means the examples section stays hidden. That is fine.

### 6. Remove the "Draft" notice from the legal pages

- [ ] Have `site/terms.html` and `site/privacy.html` reviewed (ideally by a lawyer).
- [ ] After review, remove the line `<p class="draft-note">...Draft...</p>` from both pages.
- [ ] The site test currently requires that notice. When you remove it, also update `test_legal_pages_have_draft_notice` in `tests/test_site.py`, or the test will fail.

### 7. Final check

- [ ] Preview locally (top of this page) and click every button. None should say "Coming soon" unless you meant it.
- [ ] Run `python -m pytest tests/test_site.py`. It should pass.
- [ ] Push to `fork`, wait for the deploy, and click through the live site once.

## How an order reaches you

1. A customer clicks a buy button and pays on Stripe.
2. The payment is recorded in your Stripe Dashboard, with the two answers the customer typed: their channel link and their stream link. If you want an email for each payment, turn on Stripe's payment notification emails in your Stripe settings.
3. Open the stream link and confirm it is on the channel the customer gave. If it is not their channel, do not run it, and refund the order.
4. You run that stream in the local Chop Shop app.
5. You send the finished clips back to the customer.

Free-clip requests come to wherever `freeClipUrl` points (your Discord or form) and are handled the same way from step 3.

Returning customers send each new stream link to the contact address in the footer, and say which channel it is for. Handle it the same way from step 3.

## Rules

- Never add an `examples` entry without the clip owner's written agreement.
- Never commit secrets. Payment Links are public and safe to commit. Stripe keys are not and are never needed here.
