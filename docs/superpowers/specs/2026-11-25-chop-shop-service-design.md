# Chop Shop: clips as a service — design

Date: 2026-11-25. Status: draft, awaiting owner approval.

Legend: **[owner]** = the owner said or chose this. **[call]** = the designer's
call, not yet confirmed; the owner can overrule any of them.

## Intent

Turn AutoClip, a local single-user clipping tool, into **Chop Shop**: a paid
service where streamers turn their own streams into Shorts, Reels and TikToks.
[owner]

Why: the owner wants income from the tool they already run for their own Shorts
channel (@ChopShopCo). They expect marketing to be the hard part, so the plan
must make finding and converting customers concrete. [owner]

## Goals

1. A business plan. [owner]
2. A robust marketing plan; the owner names this as their weak spot. [owner]
3. A website that shows streamers the value of short-form clips and takes
   payment per clip or by monthly subscription through Stripe links. [owner]
4. The whole app is called Chop Shop. [owner]
5. Self-serve is the target product: a streamer signs up, pays, submits a
   stream and gets clips without the owner doing anything. The owner can also
   step in and help a customer by hand. [owner]

## Non-goals

- Posting to TikTok, Instagram or YouTube on the customer's behalf. Customers
  download files. [call: those APIs are approval-gated; revisit after launch]
- A mobile app, team accounts, or an affiliate system in the product. [call]
- Running several videos at once. One GPU, one job at a time, as today. [call]
- Renaming the Python package or the `~/.autoclip` data folder. [call: this is
  a fork of artbyjazi/autoclip, and an internal rename makes every upstream fix
  a merge conflict]

## Anti-goals

- Clipping content the customer does not own. The service must not become a
  re-upload mill; that invites takedowns and Stripe account risk.
- Exposing today's local app to the internet. Every one of its endpoints is an
  unauthenticated admin endpoint.
- Monthly costs that exist before revenue does.
- Any change that breaks the owner's current local workflow for their channel.

## Constraints

- Clipping needs the owner's GPU PC; hosting must not need a GPU. [owner chose
  "I don't know", designer picked this]
- Python 3.11/3.12 only (MediaPipe). Windows is the worker machine.
- The local app must never be restarted with `--reload` during a job.
- `origin` is upstream and is never pushed to; pushes go to the `fork` remote.
- MIT licence and the original author's copyright notice stay in place.
- Payment uses Stripe Payment Links, not a custom checkout. [owner]

## Approaches considered

**A. Hosted site, owner's PC as the worker (chosen).** A small hosted web app
holds the marketing pages, accounts, clip balances, Stripe crediting and the
order queue. The owner's PC runs a worker that pulls paid orders, clips them
with the existing pipeline, and uploads results. Costs about $5-10 a month.
The owner can review any order before it is released. Limits: one job at a
time, and orders wait while the PC is off.

**B. Everything in the cloud.** Same site, but the worker runs on rented GPUs
around the clock. Removes the "PC is off" limit and allows parallel jobs.
Costs roughly $0.30-0.80 per GPU hour plus more build and operations work
before the first sale. Rejected for launch: cost before revenue.

**C. Put the local app behind a login and a tunnel.** Smallest build, but the
whole product goes down with the PC, and a mistake in the login exposes the
owner's machine. Rejected.

A is built so that B is a later move of the worker, not a rebuild: the worker
only talks to the site over HTTPS, so it can run anywhere.

## The product, as a customer sees it

1. Lands on chopshop site. Sees what clips do for a channel, real examples from
   @ChopShopCo, pricing, and a "Sign in with Twitch" button.
2. Signs in. [call: Twitch login first, Google/YouTube second. No passwords to
   store, every streamer has one, and it tells us which channel they own.]
3. Pastes a link to one of their own VODs. The site checks that the VOD belongs
   to the signed-in channel. [call: this is the ownership guard]
4. The order is queued. They see their place in line and get an email when it
   is ready.
5. They see their candidate clips as low-resolution previews, ranked, with
   titles and hashtags. [call]
6. They unlock clips to download. Every account can unlock **one clip per day
   free**. [owner] Beyond that, an unlock spends a paid credit or counts
   against a subscription's limits.
7. They download the clips, each with a suggested title, description and
   hashtags.

### Pricing: freemium [owner]

The owner set the shape: first clip each day is free; then pay per clip or buy
clip packs; then subscriptions with per-day and per-month limits. The numbers
below are the designer's starting point, to be tested in the business plan.

Revised 2026-11-25 after reading competitor pricing pages (StreamLadder
$15-39, Eklipse $24.99-39.99, OpusClip $15-29 a month) and measuring the
owner's PC at 1.24 minutes of processing per minute of video. See the Chop Shop
Business Plan document for the reasoning.

| Tier | Price [call] | Clips | Stream per order | Streams / month | Queue |
|---|---|---|---|---|---|
| Free | $0 | 1 per day, with a Chop Shop end tag | 60 min | 4 | after paid |
| Per clip | $2 | 1 clean clip | 60 min | - | paid |
| Packs | 10 for $15, 30 for $36 | never expire | 60 min | - | paid |
| Starter | $9 / month | 3 per day, 40 per month | 60 min | 8 | paid |
| Pro | $19 / month | 10 per day, 150 per month | 2 hours | 16 | first |
| Managed | $149 / month | Pro limits, owner reviews every clip (max 10 customers) | 2 hours | 16 | first |

Rules that follow from freemium on one GPU [call]:

- The cost is per VOD processed, not per clip unlocked, so free accounts are
  limited by VODs: one VOD in the queue at a time and a maximum VOD length.
  Paid orders always run before free ones.
- The free clip carries a short Chop Shop end tag. Every free clip a streamer
  posts is then an advert for the service; paid clips are clean.
- "Per day" resets at midnight in the customer's time zone. A subscription
  unlock must be inside both the daily and the monthly limit. Pack credits are
  used only after the day's free clip and any subscription allowance.
- One free account per Twitch or YouTube channel, which the sign-in enforces.

### Assumptions the owner has not confirmed

Used for planning until the owner says otherwise.

- Goal of roughly $2,000 a month within six months, about ten hours a week,
  marketing budget under $100 a month, no existing streamer contacts.
- No examples the owner has the right to show yet. The marketing plan's first
  step is free clips for five to ten small streamers in exchange for
  permission and a testimonial.
- The PC is on most of the day; customer orders run before the owner's own
  jobs; the site promises clips within 24 hours.
- The service keeps the Chop Shop name. The existing YouTube channel moves
  toward showing customers' clips with permission.

### Credit rules [call]

- Pack credits never expire. Monthly allowance credits expire at the end of
  the billing month and do not roll over.
- Cancelling a plan keeps pack credits and drops the remaining allowance at
  period end.
- A refund or chargeback removes the unspent credits from that payment. Clips
  already unlocked stay unlocked; an account with a chargeback is blocked from
  new orders until the owner clears it.
- The ledger therefore records which payment each credit came from, and the
  webhook handles: checkout completed, invoice paid, subscription deleted,
  charge refunded, dispute created.

### Founding-customer mode (step 3) [call]

- A purchase buys a fixed pack of clips from one VOD. If the VOD yields fewer
  good clips than paid for, the remainder carries to the customer's next VOD.
- YouTube and Twitch VOD links are accepted. Twitch ingest work is therefore
  part of step 3, not step 5.
- No accounts exist yet, so ownership is checked by hand: the order form asks
  for the channel and has a required "this is my content" box, and the owner
  confirms the VOD is on that channel before running it.

### Cost per job [call]

Customer jobs use the local model (Ollama), the same as the owner's current
`local-model-progress` work, so a free preview costs queue time and no cash.
A paid model is offered only on the managed tier, where the price covers it.
Free accounts are capped at one queued VOD at a time and at a maximum VOD
length set after throughput is measured in step 3.

## How it is built

Two programs in this repository.

### 1. The site (new, hosted)

A small FastAPI app in a new top-level `site/` folder, deployed to one small
always-on machine with a persistent disk. [call: FastAPI because the repo
already uses it; SQLite on the disk because one small box does not need a
database server]

It owns:

- **Marketing pages**: home, pricing, examples, FAQ, terms, privacy. Static
  HTML and CSS in the Chop Shop brand (black, gold, off-white; assets in
  `chopShop art/`). [call: no framework, these pages have no state]
- **Accounts**: Twitch sign-in, session cookie.
- **Balance**: a ledger table of credit and debit rows per account. The balance
  is the sum. Every change has a reason and a reference.
- **Stripe**: each Payment Link is opened with the account id attached as
  `client_reference_id`. A webhook endpoint verifies Stripe's signature and, on
  a completed payment or a paid subscription invoice, adds credits. The Stripe
  event id is stored so a repeated webhook cannot credit twice.
- **Orders**: one row per submitted VOD, with status
  `queued → working → review → ready` or `failed`.
- **Customer dashboard**: submit a VOD, see orders, preview, unlock, download.
  Server-rendered pages with a little script. [call]
- **Worker API**: endpoints only the worker can call, guarded by a secret
  token: claim the next order, report progress, register finished clips, mark
  done or failed.
- **Owner page**: every order and account, a button to add free credits, and a
  switch per account for "hold for my review before release".

### 2. The worker (new command in the existing app)

`chopshop worker` runs on the owner's PC next to the existing local app. It:

1. Asks the site for the next order.
2. Ingests the VOD link with the existing ingest stage.
3. Runs the existing pipeline through the existing job queue, so it shares the
   one-at-a-time rule with the owner's own jobs.
4. Exports the top clips three ways: a low-resolution preview, a clean file,
   and a clean file with the Chop Shop end tag for free unlocks.
   [call: top 10 per VOD to start]
5. Uploads both to file storage and tells the site.
6. If the account is on "hold for review", it stops at `review`. The owner
   opens the job in the existing review screen, fixes trims and captions,
   and clicks release, which re-exports and uploads.

The existing local app, its screens and its CLI keep working unchanged for the
owner's own channel.

### File storage

Finished clips go to S3-compatible object storage; customers download through
short-lived signed links, and only clean files they have unlocked get a link.
[call: Cloudflare R2, because it has a free tier and no download fees]
Source VODs never leave the owner's PC. Clips are deleted after 30 days. [call]

### The rename

User-facing only: the name in the UI, page titles, README and docs, a
`chopshop` command alongside `autoclip`, and the API title. The Python package,
environment variables and data folder keep their names. Licence and credit to
the original author stay.

## Order of work

Each step is useful on its own, and money can come in after step 3.

1. **Business plan** (shared document).
2. **Marketing plan** (shared document): who to reach, where, with what
   message, on what weekly schedule, with a 90-day calendar.
3. **Website with Stripe links**, launched in "founding customer" mode: the
   customer pays, submits a VOD through a form, and the owner runs the job in
   the local app and sends the clips. No accounts yet. This tests demand and
   price before the self-serve build.
4. **Rename** to Chop Shop.
5. **Self-serve**: accounts, balance, Stripe webhook, orders, worker, storage,
   dashboard, owner page.

## What the owner must supply

The designer cannot create these on the owner's behalf.

- A Stripe account, with the products and Payment Links created in it.
- A domain name.
- Accounts for hosting, Cloudflare R2, an email sender, and a Twitch developer
  application (for sign-in).
- Terms of service and privacy policy sign-off. Drafts will be provided, but
  they are not legal advice.

## Left to the builder

- Hosting provider and deploy method for the site.
- Table and endpoint names; session handling details.
- Watermark look and preview resolution.
- Email sender and wording.
- Whether Twitch VOD links need changes in the ingest stage (the `sources.type`
  column currently only allows `youtube` and `upload`).
- Tests: at minimum, one test each for webhook signature rejection, duplicate
  webhook not double-crediting, unlock with zero balance refused, and the
  worker token being required.

## Open risks

- **Throughput is unmeasured.** How long a 4-hour stream takes on the owner's
  PC sets how many customers the service can hold. Measure before setting plan
  sizes.
- **Twitch VODs expire** (7 to 60 days depending on account type), so orders
  must be ingested promptly.
- **Music in streams** can still trigger claims on the customer's uploads.
  The FAQ should say so.
- **The owner's own channel** clips other creators' streams. The service site
  should show only examples the owner has the right to show, or the pitch
  to streamers is undermined.
