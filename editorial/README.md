# Tech Career Editorial Engine

Extends the existing Telegram/job automation into an editorial growth system.

## Outputs

- `data/editorial/latest_digest.md` — long-form Substack newsletter draft
- `data/editorial/x_queue.json` — X drafts
- `data/editorial/substack_notes_queue.json` — Substack Note drafts
- `data/editorial/latest_items.json` — sourced facts/jobs behind the drafts

## Roles of each platform

- Telegram: real-time, high-volume jobs
- X: discovery and short insights
- Substack Notes: recurring useful observations
- Substack newsletter: deeper tech/career intelligence and monetization

## First-run safety

Keep `BUFFER_AUTOPUBLISH=false` until the generated drafts are reviewed.

## GitHub configuration

Secrets:
- `GEMINI_API_KEY` (optional; fallback drafting works without it)
- `BUFFER_API_KEY` (needed only when autopublishing is enabled)

Variables:
- `PUBLICATION_NAME`
- `TELEGRAM_URL`
- `GEMINI_MODEL` (optional)
- `BUFFER_X_CHANNEL_ID`
- `BUFFER_SUBSTACK_CHANNEL_ID`
- `BUFFER_AUTOPUBLISH` (`false` first)

The Buffer publisher uses `createPost` with `mode: addToQueue`, so Buffer controls the next posting slot.

## Connected brand targets

- X: `@HenryMortu`
- Substack: `https://substack.com/@web3jobtechalphavault`
- Telegram: `https://t.me/VettedWeb3jobs`

Buffer still needs the X and Substack channels connected in its Channels page before automated publishing can be enabled.
