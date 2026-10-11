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
from editorial.quality_jobs.text import shorten
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


def build_digest(jobs, now=None):
    now = now or datetime.now(timezone.utc)
    jobs = [job for job in jobs if eligible_for_digest(job, now)][:5]
    week = now.astimezone(ZoneInfo('Africa/Lagos')).strftime('%G-W%V')
    packet = {'newsletter_markdown': f'# {BRAND} — {week}\n\n', 'x_posts': [], 'substack_notes': []}
    if not jobs:
        packet['newsletter_markdown'] += 'No dated, accessible vacancy passed the job checks. Nothing queued.\n'
        return packet
    promo = now.astimezone(ZoneInfo('Africa/Lagos')).date().isoformat() >= '2026-10-15'
    intro = f'{len(jobs)} remote roles worth checking this week.\n\nRemote does not always mean worldwide. Read the location and experience requirements before applying.'
    sections = []
    for job in jobs:
        strengths = []
        if job.africa_eligible: strengths.append('Africa eligibility supported by the listing')
        if job.experience_level == 'entry': strengths.append('lower stated experience requirements')
        if job.salary: strengths.append('pay disclosed')
        if not strengths: strengths.append('location requirements listed')
        section = f'{shorten(job.title, 110)} — {shorten(job.company, 60)}\n{detail(job)}\nWhy consider it: {"; ".join(strengths[:2])}.\nApply: {job.effective_url}'
        if job.is_referral:
            section += '\nReferral link: we may earn if you are accepted and start paid work.'
        sections.append(section)
    note = intro + '\n\n' + '\n\n'.join(sections) + '\n\nSave the roles that fit you. Tailor one application to the requirements rather than sending the same CV everywhere.'
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
