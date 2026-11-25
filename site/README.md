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
| `contactEmail` | Your public contact email address. | "address coming soon" in the footer and on the legal pages. |
| `discordUrl` | Invite link to your Discord server. | Nothing uses it yet beyond the config. |
| `freeClipUrl` | Where people ask for a free clip (Discord invite or a form). | The "Get my free clip" buttons say "Coming soon". |
| `links.clip` | Payment Link for a single clip. | "Buy one" says "Coming soon". |
| `links.pack10` | Payment Link for the pack of 10. | "Buy 10" says "Coming soon". |
| `links.pack30` | Payment Link for the pack of 30. | "Buy 30" says "Coming soon". |
| `links.starter` | Payment Link for Starter. | "Start Starter" says "Coming soon". |
| `links.pro` | Payment Link for Pro. | "Go Pro" says "Coming soon". |
| `managedUrl` | A way to contact you about Managed: a `mailto:you@example.com` link or a Discord invite. | The Managed button says "Coming soon". |
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

Managed ($149 per month) has no public Payment Link. Customers contact you instead (see step 1d).

- [ ] **1a. Create the five products** with the prices above.
- [ ] **1b. Create one Payment Link for each product.** On every link:
  - [ ] Add two custom text fields and make both required.
    - Field 1 label: `Your channel link`
    - Field 2 label: `Stream link (YouTube or Twitch VOD)`
  - [ ] Turn on the box where the customer must agree to your terms of service. Stripe will ask for a terms page address. Use the address of your `terms.html` page once the site is live (step 3 and 4). If it is not live yet, finish the link later.
  - [ ] Copy the link Stripe gives you.
- [ ] **1c. Paste the five links into `site/config.js`:**

```js
links: {
  clip: "https://buy.stripe.com/...",
  pack10: "https://buy.stripe.com/...",
  pack30: "https://buy.stripe.com/...",
  starter: "https://buy.stripe.com/...",
  pro: "https://buy.stripe.com/..."
},
```

- [ ] **1d. Set `managedUrl`** to a way to reach you, for example `"mailto:you@example.com"` or your Discord invite link.
- [ ] **1e. Set `contactEmail`** to the address you want to show in the footer.
- [ ] **1f. Test a purchase** with Stripe's test mode first (see Stripe's documentation), then switch to live mode and repeat for real.

### 2. Free clips

- [ ] Create a Discord server, or a simple form, where people ask for their free clip. Ask for the same two things: channel link and stream link.
- [ ] Paste its address into `freeClipUrl` in `site/config.js`.
- [ ] If you made a Discord server, also paste its invite into `discordUrl`.

### 3. Hosting (Cloudflare Pages)

- [ ] Put the website on a static host. Cloudflare Pages works. Follow Cloudflare's current documentation for the exact clicks (search for "Cloudflare Pages Git integration").
- [ ] Connect your own GitHub repository (the one the `fork` remote points to, not the original).
- [ ] Pick the branch to publish.
- [ ] Set the build command to empty (nothing).
- [ ] Set the output directory to `site`.
- [ ] Save and wait for the first deploy. Open the address it gives you and check the page loads.

Every time you push a change to that branch, the site updates.

### 4. Domain

- [ ] Buy a domain name from any registrar.
- [ ] Add it to your Cloudflare Pages project and point it at the site. Follow Cloudflare's current documentation for custom domains.
- [ ] Open the domain and check the site loads.
- [ ] If you finished Stripe links before the domain existed, go back and set the terms page address on each Payment Link.

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
2. Stripe emails you the payment. The email includes the two fields the customer filled in: their channel link and their stream link.
3. You run that stream in the local Chop Shop app.
4. You send the finished clips back to the customer.

Free-clip requests come to wherever `freeClipUrl` points (your Discord or form) and are handled the same way from step 3.

## Rules

- Never add an `examples` entry without the clip owner's written agreement.
- Never commit secrets. Payment Links are public and safe to commit. Stripe keys are not and are never needed here.
