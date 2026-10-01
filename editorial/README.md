# Tech Career Editorial Engine

GitHub Actions collects dated RSS stories and recent entries from the existing jobs log. It builds X posts, Substack Notes and an unpublished newsletter document. Buffer handles X and Notes posting; the newsletter is not automatically emailed.

## Drafting and quota fallback

- Set the repository secret `GEMINI_API_KEY` to a key from a Google AI Studio **Free tier** project. Do not enable paid billing if zero cost is required.
- The default model is `gemini-3.5-flash-lite`, which currently has a free tier. The retired `gemini-2.0-flash` is no longer used.
- Make one bounded Gemini request per scheduled run, after collecting source material. The API key is supplied through an HTTP header, never a URL or logs.
- HTTP 429, unavailable service, timeout, incomplete JSON, invalid source IDs/URLs select the RSS/job template fallback immediately. There are no quota retries or paid-model failovers.
- Source citations are added in code using validated source IDs. X text is shortened to fit while keeping its citation.
- The next scheduled run tries Gemini again. Missing keys also use fallback.
- Fallback keeps source URLs intact and adds concrete practical suggestions; it cannot provide the same editorial judgement as Gemini.
- Undated, stale, future-dated and irrelevant feed entries are skipped. If no items pass, queues are empty and no post is uploaded.
- Gemini free-tier pricing is determined by the key's Google project. Code cannot convert a paid project into a free project.

## Telegram pause

Telegram promotion is removed from generated text before saving.
No Telegram invitation appears before **October 15, 2026**, in Africa/Lagos.
From that date, Thursday runs may append: "Check out our Telegram for job listings: https://t.me/VettedWeb3jobs".
The publisher records the ISO week and allows at most one promotional upload per channel per week. X posts with insufficient space keep the source citation and omit the invitation.
The X profile website field is separate from post automation; a reminder is set for October 15 to add the link.

## Schedule and review

The workflow runs weekdays at **07:30 WAT** (`30 6 * * 1-5`) from the repository's default branch.
It uploads at most one X post and one Substack Note per run.
Autopublishing was enabled and verified on October 1, 2026. Both Buffer channels have one Monday–Friday slot between 09:00 and 10:00 WAT.
`BUFFER_AUTOPUBLISH=true` queues posts into Buffer's next configured slot.
With that variable absent or false, scheduled runs create unpublished Buffer drafts.
The manual `buffer_drafts` option always creates drafts, even when autopublishing is enabled.
Push checks only generate local review artifacts and do not call Buffer or Gemini.
GitHub can delay scheduled runs; account reconnections or service failures can still require maintenance.

## Secrets and optional variables

Secrets: `GEMINI_API_KEY`, `BUFFER_API_KEY`.
Variables: `PUBLICATION_NAME`, `GEMINI_MODEL`, `TELEGRAM_URL`, `TELEGRAM_PROMO_START`, `BUFFER_X_CHANNEL_ID`, `BUFFER_SUBSTACK_CHANNEL_ID`, `BUFFER_AUTOPUBLISH`.

Connected targets:
- X: @HenryMortu, channel `6abe6f09ea19ca0bde441138`
- Substack: Web3 Jobs & Tech Alpha Vault, channel `6abe70bfea19ca0bde441f84`
- Telegram: https://t.me/VettedWeb3jobs

Buffer Free currently supports 3 channels, 10 queued posts per channel and 3,000 API requests per 30 days. Use standard GitHub-hosted runners for the free public-repository workflow.

## Outputs and history

- `data/editorial/latest_digest.md`
- `data/editorial/latest_items.json`, including `drafting_mode`
- `data/editorial/x_queue.json`
- `data/editorial/substack_notes_queue.json`
- `data/editorial/buffer_state.json`, confirmed upload IDs and promotion weeks

Upload history is persisted immediately after each confirmed Buffer post, then committed even if a later step fails. The connection test is draft-only and skips its previously confirmed samples.

## Verification

Run `python -m unittest editorial.test_editorial`.
