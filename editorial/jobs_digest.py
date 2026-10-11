"""Weekly remote-job digest, using the Telegram scraper's curation rules.
No news summaries, generated vacancies, extra credentials or paid AI calls.
"""
import hashlib
import json
import os
import re
import pycountry
import sys
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from editorial.quality_jobs.classify import classify
from editorial.quality_jobs.config import Settings
from editorial.quality_jobs.sources import collect
from editorial.quality_jobs.pipeline import process
from editorial.quality_jobs.text import shorten, clean_text
from editorial.editorial_pipeline import x_weight

OUT = ROOT / 'data/editorial'
BRAND = 'Remote Jobs Worldwide'
TELEGRAM = 'https://t.me/RemoteJobsTechHub'
TAGLINE = 'Curated remote AI, tech & Web3 jobs. Location restrictions clear; Africa-eligible roles flagged.'


MIN_ROLES = 6
MIN_JUNIOR_ROLES = 3
MAX_ROLES = 10
SPECIALIST = re.compile(r'\b(physician|medical doctor|surgeon|clinical|atomistic|molecular dynamics|density functional|DFT|postdoctoral|ph\.?d|principal scientist)\b', re.I)
COMMISSION = re.compile(r'\b(commission|OTE|on.target earnings)\b', re.I)



COUNTRY_NAMES = {name.lower() for country in pycountry.countries for name in (country.name, getattr(country, 'common_name', ''), getattr(country, 'official_name', '')) if name}
COUNTRY_NAMES.update({'us','usa','u.s.','u.s.a.','uk','u.k.','england','scotland','wales','northern ireland','turkey','south korea','north korea','russia','vietnam','bolivia','venezuela','taiwan','iran','laos','syria','tanzania','brunei','moldova','europe','emea','apac','latam','north america'})
US_STATES = set('Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|District of Columbia'.lower().split('|'))
GEO = re.compile(r'(?<!\w)(?:'+ '|'.join(re.escape(name) for name in sorted(COUNTRY_NAMES | US_STATES,key=len,reverse=True)) + r')(?!\w)', re.I)
TASK = re.compile(r'\b(?:own(?:s|ing)?|manag(?:e|es|ing)|respond(?:s|ing)?|analy[sz](?:e|es|ing)|design(?:s|ing)?|build(?:s|ing)?|develop(?:s|ing)?|maintain(?:s|ing)?|resolv(?:e|es|ing)|support(?:s|ing)?|implement(?:s|ing)?|creat(?:e|es|ing)|test(?:s|ing)?|debug(?:s|ging)?|curat(?:e|es|ing)|review(?:s|ing)?|evaluat(?:e|es|ing)|train(?:s|ing)?|writ(?:e|es|ing)|monitor(?:s|ing)?|deliver(?:s|ing)?|process(?:es|ing)?|optimi[sz](?:e|es|ing)|configur(?:e|es|ing)|integrat(?:e|es|ing)|deploy(?:s|ing)?|triag(?:e|es|ing)|investigat(?:e|es|ing)|automat(?:e|es|ing)|lead(?:s|ing)?)\b', re.I)
FLUFF = re.compile(r'\b(?:culture|flexibility|ownership|recognized|currently|please check)\b|meaningful work|global team that|opportunity to learn|share your preferences', re.I)


def explicit_worldwide(job):
    return bool(re.search(r'\b(?:worldwide|anywhere in the world|all countries)\b',job.location,re.I) or re.search(r'\b(?:work|hire|hiring|apply|applicants|candidates)\b[^.!?]{0,45}\b(?:anywhere in the world|worldwide|all countries)\b',job.description,re.I))


def location_conflict(job):
    text = clean_text(job.description,12000)
    if re.search(r'\b(?:citizens?(?:hip)?|clearance|federal|must be located in|authorized to work in)\b',text,re.I) or re.search(r'\bFED\b',job.title,re.I):
        return True
    if GEO.search(job.location): return True
    for match in GEO.finditer(text):
        around = text[max(0,match.start()-65):match.end()+40]
        if re.search(r'\b(?:remote|work location|job location|position location|must reside|must be based|based in|located in|location:)\b',around,re.I):
            return True
    return False


def experience_info(job):
    matches = list(re.finditer(r'\b(\d+)(?:\s*[-–]\s*(\d+))?\+?\s+years?(?:\s+of)?\s+(?:relevant\s+|professional\s+)?experience\b',job.description,re.I))
    strict = max(matches,key=lambda m:int(m.group(2) or m.group(1))) if matches else None
    years = int(strict.group(2) or strict.group(1)) if strict else None
    senior = bool(re.search(r'\b(?:senior|sr\.?|lead|principal|head|director)\b',job.title,re.I)) or (years is not None and years >= 5)
    junior = not senior and (years is None or years <= 2) and (job.experience_level == 'entry' or bool(re.search(r'\b(?:junior|entry.level|intern|trainee|graduate)\b',job.title,re.I)))
    label = strict.group(0) if strict else ('Senior' if senior else 'Entry level' if junior else 'Experience not stated')
    if senior and strict: label = 'Senior | '+label
    return (0 if junior else 2 if senior else 1), label


def audience_eligible(job):
    if location_conflict(job): return False
    if GEO.search(job.title) and not explicit_worldwide(job): return False
    if re.search(r'multiple requests|multiple positions|various roles', job.description, re.I):
        return False
    if SPECIALIST.search(job.title + ' ' + job.description):
        return False
    # High-risk pay arrangements require a separate employer review; hold them.
    if COMMISSION.search(job.salary + ' ' + job.description):
        return False
    if job.company.lower() == 'credit wellness, llc':
        return False
    if job.remote_scope not in {'worldwide', 'africa'} or not job.africa_eligible:
        return False
    if job.remote_scope == 'worldwide':
        country = r'(?:united states|u\.?s\.?a?\.?|u\.?k\.?|canada|colombia|brazil|india|philippines|germany|austria|argentina|mexico|poland|australia|europe|united kingdom)'
        conflict = re.search(r'\bremote\b[^.!?]{0,28}\b'+country+r'\b|\b'+country+r'\b[^.!?]{0,12}\(?remote\b|within the country of employment', job.description, re.I)
        if conflict: return False
        conflict = re.search(r'\b(?:remote\s*[-,:]\s*|remote,\s*|must (?:reside|be based) in\s+|based in\s+|eligible to work in\s+)(?:the\s+)?(?:united states|u\.?s\.?|canada|colombia|brazil|india|philippines|europe|united kingdom)\b', job.description, re.I)
        if conflict: return False
        location = re.search(r'\b(worldwide|anywhere|global|all countries)\b', job.location, re.I)
        hiring = re.search(r'\b(?:work|hire|hiring|apply|applicants|candidates)\b[^.!?]{0,45}\b(?:anywhere in the world|worldwide|all countries)\b', job.description, re.I)
        if not location and not hiring:
            return False
    return True


def eligible_for_digest(job, now):
    published = job.published_at
    if published and published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return bool(audience_eligible(job) and published and now - timedelta(days=7) <= published <= now
                and job.link_status in {'200', 'redirect'})


def salary_text(value):
    value = clean_text(value)
    value = re.sub(r'(\$[\d,.]+)\s*[–—-]\s*\1(?=\D|$)', r'\1', value)
    return value.replace('/hourly', '/hour')


def role_evidence(job):
    text = clean_text(job.description, 12000)
    text = re.sub(r'Headquarters:.*?(?=\b(?:About|Responsibilities|What|In this|You will|You’ll|You\'ll)\b)', '', text, flags=re.I)
    pieces = re.split(r'(?<=[.!?;])\s+|[•\n]', text)
    for piece in pieces:
        piece = piece.strip()
        # Trim heading fragments before the task; do not quote location metadata.
        start = re.search(r"\b(?:You will|You'll|You’ll|In this role|As (?:a|an)|What you(?:'ll|’ll) do|Responsibilities)\b",piece,re.I)
        if start: piece = piece[start.start():]
        if not 25 <= len(piece) <= 650 or FLUFF.search(piece) or not TASK.search(piece): continue
        if re.search(r'\b(?:requirements|years? experience|years? of experience|proficiency|must have)\b',piece,re.I): continue
        if GEO.search(piece) or re.search(r'headquarters|location:',piece,re.I): continue
        if len(piece.split()) <= 22:
            return piece if piece.endswith(('.', '!', '?')) else piece + '.'
        # Prefer a complete task clause to a chopped quotation.
        for clause in re.split(r'[;:]|, (?=and |including |with )',piece):
            if 5 <= len(clause.split()) <= 22 and TASK.search(clause) and not FLUFF.search(clause):
                return clause.strip(' ,;:') + '.'
    return ''


def detail(job):
    location = shorten(job.location, 100)
    if location.lower() in {'', 'remote'}:
        location = 'Worldwide' if job.remote_scope == 'worldwide' else 'Africa — check listed countries'
    fields = [location + ' | Africa eligible', experience_info(job)[1]]
    if job.salary: fields.append(salary_text(job.salary))
    return '\n'.join(fields)


def category(job):
    title = job.title.lower()
    for name, terms in [('Support', ('support','customer success')), ('Design', ('design','ux','ui')), ('Marketing', ('marketing','content','seo','growth')), ('Data', ('data','analyst','annotation','transcription')), ('Tech', ('developer','engineer','automation','qa','software'))]:
        if any(term in title for term in terms): return name
    return 'Other'


def select_digest_jobs(jobs, now):
    pool = [job for job in jobs if eligible_for_digest(job, now) and role_evidence(job)]
    pool.sort(key=lambda job: (experience_info(job)[0], category(job) == 'Other', -job.quality_score))
    selected, companies, keys, reasons, counts = [], {}, set(), set(), {}
    senior_count = 0
    # First pass provides role variety; second fills up to ten without inventing it.
    for cap in (2, 4):
        for job in pool:
            key = job.fingerprint or job.direct_url
            group = category(job)
            reason = role_evidence(job).lower()
            senior = experience_info(job)[0] == 2
            if senior and senior_count >= 3: continue
            if key in keys or reason in reasons or companies.get(job.company,0) >= 2 or counts.get(group,0) >= cap:
                continue
            selected.append(job); keys.add(key); reasons.add(reason)
            senior_count += int(senior)
            companies[job.company] = companies.get(job.company,0)+1
            counts[group] = counts.get(group,0)+1
            if len(selected) == MAX_ROLES: return sorted(selected,key=lambda job:experience_info(job)[0])
    return sorted(selected,key=lambda job:experience_info(job)[0])


def editorial_opening(jobs, now):
    stories = [
        'Imagine this: it is 10 p.m. You finally find a role that sounds right. You rewrite the first paragraph of your CV, open the application, then see the line you missed: US residents only. You close the tab. The time is gone, and the job was never yours to apply for.\n\nThat is why this shortlist starts with eligibility. Every role below has evidence of worldwide or Africa hiring. Country-specific Africa roles still need a country check before you apply.',
        'Picture an evening with twelve job tabs open. One is an old advert. One needs a medical licence. Another promises a big number that turns out to be commission. After an hour, you have not sent a single useful application.\n\nA longer list would not have helped. A better filter would. This week we have removed those detours and kept roles with evidence that applicants in Africa can apply.',
        'Imagine finding two jobs before bed. The first has a glamorous title but tells you almost nothing about the work. The second names the task you would do and a skill you can prove. You spend twenty minutes preparing one relevant example for the second.\n\nThat is the point of the “why this one” lines below: a detail from the actual work, so you can decide where your effort belongs.',
    ]
    return stories[int(now.astimezone(ZoneInfo('Africa/Lagos')).strftime('%V')) % len(stories)]


def build_digest(jobs, now=None):
    now = now or datetime.now(timezone.utc)
    jobs = select_digest_jobs(jobs, now)
    week = now.astimezone(ZoneInfo('Africa/Lagos')).strftime('%G-W%V')
    title = f'Remote jobs this week: {len(jobs)} roles open worldwide or in Africa'
    packet = {'newsletter_markdown': f'# {title}\n\n', 'x_posts': [], 'substack_notes': []}
    juniors = sum(experience_info(job)[0] == 0 for job in jobs)
    if len(jobs) < MIN_ROLES or juniors < MIN_JUNIOR_ROLES:
        packet['newsletter_markdown'] = f'# Digest held for review\n\n{len(jobs)} suitable roles passed, including {juniors} entry/junior roles. Required: at least {MIN_ROLES} roles and {MIN_JUNIOR_ROLES} entry/junior roles. Nothing queued.\n'
        packet['held'] = True
        packet['qualifying_roles'] = len(jobs)
        return packet
    promo = True  # User explicitly requested the newsletter funnel now.
    intro = f'{len(jobs)} remote roles worth checking this week.\n\n' + editorial_opening(jobs, now)
    sections = []
    for job in jobs:
        section = f'{shorten(job.title, 110)} — {shorten(job.company, 60)}\n{detail(job)}'
        section += f'\nWhy this one — the actual work: “{role_evidence(job)}”\nApply: {job.effective_url}'
        if job.is_referral:
            section += '\nReferral link: we may earn if you are accepted and start paid work.'
        sections.append(section)
    note = intro + '\n\n' + '\n\n'.join(sections) + '\n\nBefore you apply: check eligible countries, working hours and whether the pay is a salary, contractor rate or commission. “Remote” alone answers none of those questions.\n\nWhich role fits your experience? Reply with the role and the requirement you are unsure about.'
    note += '\n\nDaily roles in the channel: ' + TELEGRAM
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
              shorten(salary_text(job.salary), 55) if job.salary else '', job.effective_url]
    x = '\n'.join(field for field in fields if field)
    if job.is_referral: x += '\nReferral link'
    while x_weight(x) > 280:
        fields[0] = shorten(fields[0], max(15, len(fields[0])-10))
        fields[2] = shorten(fields[2], max(15, len(fields[2])-10))
        x = '\n'.join(field for field in fields if field) + ('\nReferral link' if job.is_referral else '')
        if len(fields[0]) <= 15 and len(fields[2]) <= 15: raise ValueError('Job cannot fit X safely')
    packet['x_posts'] = [dict(common, id='x-jobs-'+week+'-'+source_id, text=x, job_fingerprints=[job.fingerprint])]
    return packet


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    state = json.loads((OUT/'buffer_state.json').read_text()) if (OUT/'buffer_state.json').exists() else {}
    seen = {fingerprint for row in state.get('confirmed_uploads', {}).values()
            if not row.get('draft') for fingerprint in row.get('job_fingerprints', [])}
    settings = replace(Settings.from_env(), max_per_run=60, max_per_source=15,
                       allowed_remote_scopes=frozenset({'worldwide', 'africa'}),
                       mercor_referral_url='https://t.mercor.com/H06sH', link_check_enabled=True)
    candidates = collect(settings)
    # Gate the audience before the expensive checking/ranking stage.
    candidates = [job for job in candidates if audience_eligible(classify(job))]
    selected, rejected = process(candidates, settings, existing_fingerprints=seen)
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
