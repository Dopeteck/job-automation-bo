## Story-led newsletter format (2026-10-12)

The email-ready newsletter starts with a 200–300-word grounded opening, then one practical lesson, the curated jobs, one reply question and the Telegram CTA. Substack Notes gets the short opening hook; X keeps its existing compact vacancy format.

`editorial/story_bank.json` contains two documented builder events from the actual pipeline history. Entries need an ID, kind, approved flag, evidence reference, body, lesson and question. Reader entries additionally require explicit `publish_consent: true`; do not set approval or consent without the actual reader's permission and a verified account of the event. Evidence stays in the internal record rather than being printed as a story source footer.

`editorial/newsletter_story.py` rotates unused approved builder/reader stories with measured run analysis and a worked application example based on one selected vacancy. Application examples are clearly marked, use placeholders for real evidence and never invent a client's result or a reader success. Run analysis names each actual funnel stage and never equates rejected listings with scams or implies that the counts represent the entire market.

`data/editorial/story_history.json` records story IDs after scheduled private delivery. Manual previews and held issues do not consume stories. `story_context.json` accompanies the review artifact. If no true reader story is available, the automation continues with documented events, current measurements or a worked example. No paid AI call or new credential is required for this feature.

## Current weekly supply rules (2026-10-11)

The digest keeps the Remote Jobs Worldwide brand and leads with early-career work open worldwide or across Africa.
- Retain candidates for 21 days; exclude expired vacancies. A current vacancy feed or a checked application action is required; a page returning HTTP 200 alone is insufficient.
- Prefer 6–10 roles with at least three explicit entry/junior roles. If unavailable, allow 5–10 roles with at least one explicit junior and only stated requirements of up to three years for every other role. Unknown experience and senior roles cannot fill the smaller issue.
- Himalayas runs fourteen role-type searches. Jobicy supplies its worldwide feed. Remote OK and WWR remain inputs; 41 verified Greenhouse, Lever and Ashby boards supply employer vacancies. Company inclusion never implies that every role is Africa eligible.
- Preserve restrictive country/state, citizenship, clearance, hybrid/on-site and unpaid checks. Empty or missing geography metadata is never assumed worldwide; Himalayas' documented empty restriction array is accepted, but contradictory listing text overrides it. Reject timezones with no African offset overlap; show narrower offset requirements.
- Public Telegram previews are optional input. Match posted application URLs against full source listings and prioritize matches after experience checks. Local previews returned Site Unavailable; the GitHub live check successfully read 53 application links and matched seven full listings. No private Telegram messages are read.
- Persist the source snapshot and rolling pool in GitHub Actions cache. Cache public feeds for 24 hours. Persist featured fingerprints in data/editorial/featured_jobs.json after successful scheduled private newsletter delivery, and merge confirmed public Buffer upload history. Manual review drafts and hold notices reserve nothing; repeated previews do not exhaust weekly supply.
- Source credits and canonical application URLs are required for Himalayas, Jobicy and Remote OK. No image explanation or AI-news source footer is restored. Working Nomads is disabled because its terms prohibit competitive service use; Remotive is disabled for newsletter redistribution pending explicit permission.
- Unknown employer publication dates stay unknown; the 21-day retention period uses first observation on a current employer feed. Greenhouse updated_at is not treated as a publication date.
- Responsibility evidence prioritizes actual listing bullets, excludes company biography and application instructions, and uses complete sentences/clauses. Prefer the stricter stated experience requirement over a feed seniority label.
- GitHub push events run tests only. Manual runs and Mondays at 09:30 UTC generate a private Telegram review draft and optional Buffer drafts. The newsletter email itself is not automatically sent.

Earlier notes below are historical and superseded wherever they conflict.

## Early-career issue gate (current)

An issue may contain 6–10 qualifying roles but must include at least three evidence-supported entry/junior roles, sorted before other roles. Unknown experience is labelled “Experience not stated”. Conflicting experience statements use the stricter number; an entry tag never overrides a senior title or five-year requirement. Titles/counts are generated from the final shortlist.

Country/region names use ISO country data plus aliases and all US state names. Work-location context, citizenship, clearance, federal/FED and work-authorisation restrictions override worldwide tags. A country in a title needs explicit worldwide eligibility and still cannot override a body restriction. Task excerpts require an action verb, omit headers, requirements and culture/flexibility/ownership/recognized/currently/please-check boilerplate, and prefer complete sentences or task clauses. If there is no usable responsibility, hold the role. The channel CTA now appears on every newsletter/Note by explicit user request, overriding the earlier link pause for that content.

## Weekly digest selection contract

The newsletter needs 8–10 dated, reachable roles with explicit worldwide or Africa hiring evidence. Regional restrictions outside Africa, generic remote labels, narrow clinical/scientific roles, and commission/OTE listings are excluded before ranking. Conflicting country restrictions override worldwide feed tags. Role responsibilities/requirements must support a distinct short quoted reason; vague descriptions cannot fill the quota. Prefer support, tech, data, design and marketing; select across categories and cap any employer at two roles. Equal salary bounds collapse; unknown pay/experience placeholders are omitted. Short imagined scenes provide context without false personal testimonials. Referral disclosures and the reader-reply prompt remain.

A shortlist below eight queues nothing on X or Substack and sends a private hold-status file instead of a publishable newsletter. No quota padding. Candidate checking now covers a larger eligible pool and the Remotive feed requests 1,000 items; We Work Remotely RSS region metadata is parsed. Publication URLs and Telegram job-channel automation are unchanged.

## Private newsletter delivery

Each scheduled or manual generation sends `latest_digest.md` as a plain-text file to the configured personal Telegram bot chat. Delivery never uses the public channel destination. Add repository secrets `TELEGRAM_DRAFT_BOT_TOKEN` (BotFather token) and `TELEGRAM_DRAFT_CHAT_ID` (your positive numeric personal chat ID); start that bot privately first. Missing configuration is reported explicitly. Telegram getChat must confirm a private chat and matching ID before sending; successful identical files are deduplicated. An empty job shortlist is held. API errors fail the delivery step visibly, while draft artifacts and history are still saved. Never commit the token.

Newsletter style: a hypothetical scenario, actual listing excerpts, job-specific application advice, and a practical closing question. No invented personal success stories, salaries, employer requirements or reader testimonials. Application links remain necessary for a jobs digest.

# Remote Jobs Worldwide

Production now runs `jobs_digest.py` every Monday at 09:30 UTC. It uses a copy of the Telegram scraper curation modules from Dopeteck/quality-job-scraper (reviewed October 11, 2026). The two collectors independently fetch current vacancies; this is not a digest of confirmed Telegram messages. It keeps region and experience restrictions visible, prioritizes AI and entry roles, includes disclosed pay, and permits AfricaEligible only when supported. Undated vacancies and protected/unavailable application pages are excluded from social digests. Confirmed job fingerprints prevent repeat social digests. No Gemini call is needed.

Buffer publishes one standalone X listing and one Substack Note with up to five roles. `latest_digest.md` is an email-ready draft, not an automatically emailed Substack newsletter. `JOBS_ONLY=true` prevents old tech-news queues from entering the production publisher. A shortage produces no post rather than invented vacancies. The original tech-news generator remains for reference and unit coverage but is no longer the workflow entry point. Telegram promotion remains paused until October 15.

Brand tagline: Curated remote AI, tech & Web3 jobs. Location restrictions clear; Africa-eligible roles flagged. Keep existing addresses and handles until separately changed.

# Tech Career Editorial Engine

The X/Substack editorial workflow is independent of the Telegram jobs scraper and Make scenarios.

## Production schedule and targets

GitHub Actions runs weekdays at 10:30 WAT (`30 9 * * 1-5`). Buffer uses each channel's next available morning slot. GitHub scheduled runs can be delayed; the October 8 run started at 17:40 WAT. This is not an exact-time delivery guarantee.

At most one X post/thread and one Substack Note are uploaded per run. `BUFFER_AUTOPUBLISH=true` queues them. Otherwise they remain drafts. Manual `buffer_drafts=true` always creates drafts. A thread queue limit holds X and lets Notes continue.

- X: @HenryMortu, channel `6abe6f09ea19ca0bde441138`
- Substack Notes: Web3 Jobs & Tech Alpha Vault, channel `6abe70bfea19ca0bde441f84`
- Telegram invitation: https://t.me/RemoteJobsTechHub

## Configuration

Repository secrets: `GEMINI_API_KEY`, `BUFFER_API_KEY`. Never put these values in code, URLs or logs. Images need no additional API key or paid image service.

Optional variables: `PUBLICATION_NAME`, `GEMINI_MODEL`, `TELEGRAM_URL`, `TELEGRAM_PROMO_START`, `BUFFER_X_CHANNEL_ID`, `BUFFER_SUBSTACK_CHANNEL_ID`, `BUFFER_AUTOPUBLISH`.

The configured model is `gemini-3.5-flash-lite`. Use a Google AI Studio free-tier project when zero API spending is required. There are no paid-model failovers or quota retry loops. Code does not control the project's billing tier or provider quotas.

Sources are configured in `editorial/sources.json`. Dated, relevant news must be within 72 hours. Older-year findings require an explicit source-backed current/future event. Undated, stale and irrelevant stories are excluded.

Source URLs stay in internal evidence. Published copy has no Source/Sources footer, image credits or illustrative-exercise disclaimers. Provenance remains internal. Generation and final delivery both clean legacy copy. Telegram promotion is removed before October 15, 2026, Africa/Lagos. After that date, Thursday runs may add one invitation per channel per ISO week. The X profile website field is separate.

## Review outputs

`data/editorial/latest_digest.md` is a newsletter draft, not an automatically emailed article. `latest_items.json` records source evidence and drafting mode. `x_queue.json` and `substack_notes_queue.json` feed Buffer. `buffer_state.json` stores confirmation and deduplication history. History is saved after each confirmed upload and committed even if another channel fails.

## October 8 pipeline review

The production path is GitHub Actions → source collector → Gemini or reviewed fallback → per-platform formatting → Buffer queue. Make is not part of this X/Notes pipeline.

- RSS evidence retains up to 2,200 characters; accessible article evidence retains up to 9,000 characters. Article extraction also supports a publisher's `main` container. Only configured HTTPS source hosts are fetched.
- Duplicate tracked URLs and near-identical headlines are collapsed across feeds. Stories already uploaded to both platforms are removed before generation.
- Gemini receives recent confirmed post openings to avoid repeating hooks and exercises. X can be one standalone post or a deliberate 2–3 part thread. Notes get their own hook and 150–230 word target. Hypothetical scenarios, useful tension and grounded editorial opinions are allowed; fake experiences and outrage are not.
- Overlength X outputs are rejected, never silently truncated. Thin outputs and long verbatim source passages fail the generation quality check.
- Quota, timeout, service and validation errors still make one immediate transition to free local fallback. Fallback uses reviewed, topic-matched practice guides instead of copying RSS descriptions. The Note introduces hypothetical tasks naturally without a separate source footer or exercise disclaimer. It cannot produce an original detailed news summary without Gemini. Unsupported topics and repeated guides are held rather than padded into daily posts; each guide is uploaded once per platform.
- Title-only job stubs from the old jobs log are no longer automatically published as editorial articles. The separate quality jobs scraper is unchanged.
- The publisher checks source age before upload, records confirmed post IDs and due times, and holds further uploads when its recorded queue extends more than 48 hours. This uses confirmed upload history, not a live inventory of posts manually added in Buffer.
- A mutation is recorded as pending before the request. An unconfirmed timeout, invalid response or service failure blocks automatic repeat attempts for that channel. Check Buffer, then reconcile `pending_uploads` with confirmed IDs before clearing it. This prevents duplicate posting after a lost response; it is a deliberate maintenance stop, not an automatic recovery guarantee.
- X and Notes delivery are isolated. A channel error does not suppress the other channel, and a genuine publishing failure produces a failed run with a safe error message.
- GitHub's run summary shows generation mode and per-channel delivery counts. Green means the run completed, not that Gemini was used or that Buffer already published the scheduled post.
- Main-branch code changes now run tests automatically without calling Gemini or Buffer. Scheduled runs and the manual draft option retain their existing behaviour. Runs have a ten-minute timeout.
- Buffer sends **Substack Notes**. Full newsletter Markdown is a review artifact; it is not automatically emailed or published as a Substack article.

Verification: `python -m unittest editorial.test_editorial` covers quota/service fallback, source deduplication, stale output, copied/thin output, standalone and thread limits, promotion, confirmed upload history and ambiguous publishing failures.

## Reviewed images and reach experiment

`publishers/image_library.json` contains 21 individually checked Pexels stock photos for coding, remote work, workflow planning, interviews, infrastructure and hardware. Each entry records the photographer, original photo page, license, review time, dimensions and a descriptive alt text. These are illustrative photos, not photographs of the reported event. The library was selected directly from public photo pages, not through the Pexels API. The ordinary Pexels License permits social use without attribution links; source/creator/license records remain in the repository. No generated images, random news-site image scraping, Unsplash API automation, additional credentials or changes to the existing website are involved.

The publisher selects a topic from the actual post text. `EDITORIAL_IMAGE_PERCENT` defaults to 50, using a stable source-ID hash assignment shared by both channels. This approximates half of eligible posts over time, not exactly half of every small batch. Unmatched topics and exhausted pools remain text-only. An image won't be reused on the same platform within 14 days. Photos containing identifiable people are excluded from fraud/scam/negative-context posts. Accessibility alt text describes only what is visible, without stock labels or credits. X threads attach the photo to the first post only; Substack Notes attach it directly rather than adding a link preview.

Before upload, the publisher downloads at most 4 MB from the allowlisted Pexels image host, disallows redirects, checks MIME type, dimensions and actual image decoding. Failures fall back to text. Only an explicit media-related Buffer mutation rejection allows one text-only retry; timeouts and ambiguous responses retain the existing duplicate-prevention hold. Public CDN URLs need to remain reachable until Buffer publishes; an image removed after the upload check is still an external failure risk.

Manual `buffer_drafts=true` runs set image selection to 100% for unpublished media review and use a separate draft deduplication namespace. This does not alter the normal 50% assignment. Repository variable `EDITORIAL_IMAGE_PERCENT=0` disables future images; `100` enables all eligible posts.

Every confirmed upload records `media_variant`, selection/fallback reason, image ID/topic, creator, source page, license and Buffer asset IDs when returned. Buffer can process media asynchronously, so an empty asset-ID list at creation is not proof that an image is absent; check its preview in Buffer. The run summary counts submitted posts with images, text-only posts and media fallbacks. These records support comparing impressions, follows and subscriptions in Buffer/native analytics. They do not automatically fetch performance or claim that images caused an increase. Manually attached seed images are recorded under `manual_media_updates` and also participate in the 14-day cooldown. For a first review, compare similar topics and time slots after two weeks and extend the sample if too few posts have been published. Replies and restacks must still be done on the platforms; Buffer cannot automate Substack replies.

References: https://www.pexels.com/legal-pages/license/ ; https://developers.buffer.com/examples/create-image-post.html ; https://developers.buffer.com/guides/hosting-media.html ; https://support.buffer.com/articles/using-substack-with-buffer-lDbUYyIq4R
