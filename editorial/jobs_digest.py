"""Weekly remote-job digest, using the Telegram scraper's curation rules.
No news summaries, generated vacancies, extra credentials or paid AI calls.
"""
import hashlib
import json
import os
import sys
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editorial.quality_jobs.config import Settings
from editorial.quality_jobs.sources import collect
from editorial.quality_jobs.pipeline import process
from editorial.quality_jobs.text import shorten, clean_text
from editorial.editorial_pipeline import x_weight

OUT = ROOT / 'data/editorial'
BRAND = 'Remote Jobs Worldwide'
TELEGRAM = 'https://t.me/RemoteJobsTechHub'
TAGLINE = 'Curated remote AI, tech & Web3 jobs. Location restrictions clear; Africa-eligible roles flagged.'


def eligible_for_digest(job, now):
    published = job.published_at
    if published and published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return bool(published and now - timedelta(days=7) <= published <= now
                and job.link_status in {'200', 'redirect'}
                and job.remote_scope != 'unknown')


def detail(job):
    location = shorten(job.location, 110) or job.remote_scope
    level = {'entry': 'Entry level', 'senior': 'Senior'}.get(job.experience_level, 'Check experience requirements')
    flag = ' | Africa eligible' if job.africa_eligible else ''
    return f'{location}{flag}\n{level} | {shorten(job.salary, 90) if job.salary else "Pay not disclosed"}'



def editorial_opening(jobs, now):
    missing_pay = sum(not job.salary for job in jobs)
    restricted = sum(job.remote_scope != 'worldwide' for job in jobs)
    angles = [
        '“Remote” is a working arrangement, not a passport. Before you spend an evening rewriting your CV, check whether the employer can hire in your country. The location details below are the first filter.',
        'A generic CV is quick to send. It also leaves the employer to guess why you fit. Pick one role below, find its most important requirement and put evidence of that skill near the top of your application.',
    ]
    if missing_pay:
        angles.append(f'{missing_pay} of the {len(jobs)} listings below do not disclose pay. Would you spend an hour on an application without knowing the rate? Ask for the range early, especially before a substantial unpaid task.')
    if restricted:
        angles.append(f'{restricted} of these {len(jobs)} remote listings are not classified as worldwide. The catch is eligibility, not your CV. Check the exact countries before you apply; a remote label does not remove a hiring restriction.')
    if any(job.experience_level == 'senior' for job in jobs):
        angles.append('An AI role is not automatically a beginner opportunity. This shortlist includes senior work. Read the experience label before applying, and focus your effort on roles where you can show the required skills.')
    return angles[int(now.astimezone(ZoneInfo('Africa/Lagos')).strftime('%V')) % len(angles)]


def build_digest(jobs, now=None):
    now = now or datetime.now(timezone.utc)
    jobs = [job for job in jobs if eligible_for_digest(job, now)][:5]
    week = now.astimezone(ZoneInfo('Africa/Lagos')).strftime('%G-W%V')
    packet = {'newsletter_markdown': f'# {BRAND} — {week}\n\n', 'x_posts': [], 'substack_notes': []}
    if not jobs:
        packet['newsletter_markdown'] += 'No dated, accessible vacancy passed the job checks. Nothing queued.\n'
        return packet
    promo = now.astimezone(ZoneInfo('Africa/Lagos')).date().isoformat() >= '2026-10-15'
    intro = f'{len(jobs)} remote roles worth checking this week.\n\n' + editorial_opening(jobs, now)
    sections = []
    for job in jobs:
        title = job.title.lower()
        if any(word in title for word in ('support', 'customer')):
            tip = 'Application angle: prepare one example of how you diagnosed a problem and explained the solution clearly.'
        elif any(word in title for word in ('automation', 'developer', 'engineer')):
            tip = 'Application angle: link one relevant project and explain what you built, what broke and how you fixed it.'
        elif any(word in title for word in ('ai', 'research', 'data', 'analyst')):
            tip = 'Application angle: show a relevant analysis or work sample, including how you checked its accuracy.'
        elif any(word in title for word in ('sales', 'marketing')):
            tip = 'Application angle: use one concrete example with a measurable result. Explain your contribution.'
        else:
            tip = 'Application angle: choose one requirement from the listing and show evidence that you have done it before.'
        section = f'{shorten(job.title, 110)} — {shorten(job.company, 60)}\n{detail(job)}'
        description = clean_text(job.description, 12000)
        if description:
            section += '\nListing excerpt: ' + shorten(description, 260)
        section += f'\n{tip}\nApply: {job.effective_url}'
        if job.is_referral:
            section += '\nReferral link: we may earn if you are accepted and start paid work.'
        sections.append(section)
    note = intro + '\n\n' + '\n\n'.join(sections) + '\n\nBefore you apply: check eligible countries, working hours and whether the pay is a salary, contractor rate or commission. “Remote” alone answers none of those questions.\n\nWhich role fits your experience? Reply with the role and the requirement you are unsure about.'
    if promo: note += '\n\nDaily job listings: ' + TELEGRAM
    packet['newsletter_markdown'] += note + '\n'
    job_keys = [job.fingerprint for job in jobs]
    source_id = hashlib.sha256('|'.join(job_keys).encode()).hexdigest()[:20]
    common = {'source_id': source_id, 'content_kind': 'jobs_digest', 'job_fingerprints': job_keys,
              'source_published_at': now.isoformat(), 'promotion_week': week if promo else None}
    packet['substack_notes'] = [dict(common, id='note-jobs-'+week+'-'+source_id, text=note)]
    # Free Buffer plan: use a standalone X post, avoiding its queued-thread limit.
    job = jobs[0]
    fields = [shorten(job.title, 70), shorten(job.company, 40), shorten(job.location, 60),
              'Africa eligible' if job.africa_eligible else 'Check country eligibility',
              shorten(job.salary, 55) if job.salary else 'Pay not disclosed', job.effective_url]
    x = '\n'.join(fields)
    if job.is_referral: x += '\nReferral link'
    while x_weight(x) > 280:
        fields[0] = shorten(fields[0], max(15, len(fields[0])-10))
        fields[2] = shorten(fields[2], max(15, len(fields[2])-10))
        x = '\n'.join(fields) + ('\nReferral link' if job.is_referral else '')
        if len(fields[0]) <= 15 and len(fields[2]) <= 15: raise ValueError('Job cannot fit X safely')
    packet['x_posts'] = [dict(common, id='x-jobs-'+week+'-'+source_id, text=x, job_fingerprints=[job.fingerprint])]
    return packet


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    state = json.loads((OUT/'buffer_state.json').read_text()) if (OUT/'buffer_state.json').exists() else {}
    seen = {fingerprint for row in state.get('confirmed_uploads', {}).values()
            if not row.get('draft') for fingerprint in row.get('job_fingerprints', [])}
    settings = replace(Settings.from_env(), max_per_run=12, max_per_source=3,
                       mercor_referral_url='https://t.mercor.com/H06sH', link_check_enabled=True)
    selected, rejected = process(collect(settings), settings, existing_fingerprints=seen)
    outputs = build_digest(selected)
    (OUT/'latest_digest.md').write_text(outputs['newsletter_markdown'])
    for file, key in [('x_queue.json','x_posts'), ('substack_notes_queue.json','substack_notes')]:
        (OUT/file).write_text(json.dumps(outputs[key], ensure_ascii=False, indent=2)+'\n')
    evidence = [{'title': j.title, 'company': j.company, 'link': j.direct_url,
                 'location': j.location, 'africa_eligible': j.africa_eligible,
                 'published_at': j.published_at.isoformat() if j.published_at else None,
                 'link_status': j.link_status} for j in selected]
    (OUT/'latest_items.json').write_text(json.dumps({'jobs': evidence, 'news': [], 'drafting_mode':'curated_jobs'}, indent=2))
    print(f'Job digest: {len(outputs["substack_notes"])} Notes; {len(outputs["x_posts"])} X posts. No tech-news copy generated.')

if __name__ == '__main__': main()
