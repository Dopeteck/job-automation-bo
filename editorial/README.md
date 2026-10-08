# Tech Career Editorial Engine

The X/Substack editorial workflow is independent of the Telegram jobs scraper and Make scenarios.

## Production schedule and targets

GitHub Actions runs weekdays at 10:30 WAT (`30 9 * * 1-5`). Buffer uses each channel's next available morning slot. GitHub scheduled runs can be delayed; the October 8 run started at 17:40 WAT. This is not an exact-time delivery guarantee.

At most one X post/thread and one Substack Note are uploaded per run. `BUFFER_AUTOPUBLISH=true` queues them. Otherwise they remain drafts. Manual `buffer_drafts=true` always creates drafts. A thread queue limit holds X and lets Notes continue.

- X: @HenryMortu, channel `6abe6f09ea19ca0bde441138`
- Substack Notes: Web3 Jobs & Tech Alpha Vault, channel `6abe70bfea19ca0bde441f84`
- Telegram invitation: https://t.me/RemoteJobsTechHub

## Configuration

Repository secrets: `GEMINI_API_KEY`, `BUFFER_API_KEY`. Never put these values in code, URLs or logs.

Optional variables: `PUBLICATION_NAME`, `GEMINI_MODEL`, `TELEGRAM_URL`, `TELEGRAM_PROMO_START`, `BUFFER_X_CHANNEL_ID`, `BUFFER_SUBSTACK_CHANNEL_ID`, `BUFFER_AUTOPUBLISH`.

The configured model is `gemini-3.5-flash-lite`. Use a Google AI Studio free-tier project when zero API spending is required. There are no paid-model failovers or quota retry loops. Code does not control the project's billing tier or provider quotas.

Sources are configured in `editorial/sources.json`. Dated, relevant news must be within 72 hours. Older-year findings require an explicit source-backed current/future event. Undated, stale and irrelevant stories are excluded.

Source URLs stay in internal evidence. Social posts name sources without outbound article links. Telegram promotion is removed before October 15, 2026, Africa/Lagos. After that date, Thursday runs may add one invitation per channel per ISO week. The X profile website field is separate.

## Review outputs

`data/editorial/latest_digest.md` is a newsletter draft, not an automatically emailed article. `latest_items.json` records source evidence and drafting mode. `x_queue.json` and `substack_notes_queue.json` feed Buffer. `buffer_state.json` stores confirmation and deduplication history. History is saved after each confirmed upload and committed even if another channel fails.

## October 8 pipeline review

The production path is GitHub Actions → source collector → Gemini or reviewed fallback → per-platform formatting → Buffer queue. Make is not part of this X/Notes pipeline.

- RSS evidence retains up to 2,200 characters; accessible article evidence retains up to 9,000 characters. Article extraction also supports a publisher's `main` container. Only configured HTTPS source hosts are fetched.
- Duplicate tracked URLs and near-identical headlines are collapsed across feeds. Stories already uploaded to both platforms are removed before generation.
- Gemini receives recent confirmed post openings to avoid repeating hooks and exercises. X can be one standalone post or a deliberate 2–3 part thread. Notes get their own hook and 150–230 word target. Hypothetical scenarios, useful tension and grounded editorial opinions are allowed; fake experiences and outrage are not.
- Overlength X outputs are rejected, never silently truncated. Thin outputs and long verbatim source passages fail the generation quality check.
- Quota, timeout, service and validation errors still make one immediate transition to free local fallback. Fallback uses reviewed, topic-matched practice guides instead of copying RSS descriptions. The Note identifies the current source context and labels the exercise as editorial advice. It cannot produce an original detailed news summary without Gemini. Unsupported topics and repeated guides are held rather than padded into daily posts; each guide is uploaded once per platform.
- Title-only job stubs from the old jobs log are no longer automatically published as editorial articles. The separate quality jobs scraper is unchanged.
- The publisher checks source age before upload, records confirmed post IDs and due times, and holds further uploads when its recorded queue extends more than 48 hours. This uses confirmed upload history, not a live inventory of posts manually added in Buffer.
- A mutation is recorded as pending before the request. An unconfirmed timeout, invalid response or service failure blocks automatic repeat attempts for that channel. Check Buffer, then reconcile `pending_uploads` with confirmed IDs before clearing it. This prevents duplicate posting after a lost response; it is a deliberate maintenance stop, not an automatic recovery guarantee.
- X and Notes delivery are isolated. A channel error does not suppress the other channel, and a genuine publishing failure produces a failed run with a safe error message.
- GitHub's run summary shows generation mode and per-channel delivery counts. Green means the run completed, not that Gemini was used or that Buffer already published the scheduled post.
- Main-branch code changes now run tests automatically without calling Gemini or Buffer. Scheduled runs and the manual draft option retain their existing behaviour. Runs have a ten-minute timeout.
- Buffer sends **Substack Notes**. Full newsletter Markdown is a review artifact; it is not automatically emailed or published as a Substack article.

Verification: `python -m unittest editorial.test_editorial` covers quota/service fallback, source deduplication, stale output, copied/thin output, standalone and thread limits, promotion, confirmed upload history and ambiguous publishing failures.
