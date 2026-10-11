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
from editorial.digest_sources import collect_expanded, cached_pool, still_open, telegram_urls, featured_keys, CREDITS
from concurrent.futures import ThreadPoolExecutor
import logging
from editorial.quality_jobs.pipeline import process
from editorial.quality_jobs.text import shorten, clean_text
from editorial.editorial_pipeline import x_weight

OUT = ROOT / 'data/editorial'
BRAND = 'Remote Jobs Worldwide'
TELEGRAM = 'https://t.me/RemoteJobsTechHub'
TAGLINE = 'Early-career remote work open worldwide or across Africa. Junior roles first; experience and location limits clear.'


MIN_ROLES = 5
MIN_JUNIOR_ROLES = 3
MAX_ROLES = 10
SPECIALIST = re.compile(r'\b(physician|medical doctor|surgeon|clinical|atomistic|molecular dynamics|density functional|DFT|postdoctoral|ph\.?d|principal scientist)\b', re.I)
COMMISSION = re.compile(r'\b(commission|OTE|on.target earnings)\b', re.I)



COUNTRY_NAMES = {name.lower() for country in pycountry.countries for name in (country.name, getattr(country, 'common_name', ''), getattr(country, 'official_name', '')) if name}
COUNTRY_NAMES.update({'usa','u.s.','u.s.a.','uk','u.k.','england','scotland','wales','northern ireland','turkey','south korea','north korea','russia','vietnam','bolivia','venezuela','taiwan','iran','laos','syria','tanzania','brunei','moldova','europe','emea','apac','latam','north america'})
US_STATES = set('Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|District of Columbia'.lower().split('|'))
GEO = re.compile(r'(?<!\w)(?:'+ '|'.join(re.escape(name) for name in sorted(COUNTRY_NAMES | US_STATES,key=len,reverse=True)) + r'|(?-i:US))(?!\w)', re.I)
TASK = re.compile(r'\b(?:own(?:s|ing)?|manag(?:e|es|ing)|respond(?:s|ing)?|analy[sz](?:e|es|ing)|design(?:s|ing)?|build(?:s|ing)?|develop(?:s|ing)?|maintain(?:s|ing)?|resolv(?:e|es|ing)|support(?:s|ing)?|implement(?:s|ing)?|creat(?:e|es|ing)|test(?:s|ing)?|debug(?:s|ging)?|curat(?:e|es|ing)|review(?:s|ing)?|evaluat(?:e|es|ing)|train(?:s|ing)?|writ(?:e|es|ing)|monitor(?:s|ing)?|deliver(?:s|ing)?|process(?:es|ing)?|optimi[sz](?:e|es|ing)|configur(?:e|es|ing)|integrat(?:e|es|ing)|deploy(?:s|ing)?|triag(?:e|es|ing)|investigat(?:e|es|ing)|automat(?:e|es|ing)|lead(?:s|ing)?)\b', re.I)
FLUFF = re.compile(r'\b(?:culture|flexibility|ownership|recognized|currently|please check)\b|meaningful work|global team that|opportunity to learn|share your preferences', re.I)


def explicit_worldwide(job):
    return bool(re.search(r'\b(?:worldwide|anywhere in the world|all countries)\b',job.location,re.I) or re.search(r'\b(?:work|hire|hiring|apply|applicants|candidates)\b[^.!?]{0,45}\b(?:anywhere in the world|worldwide|all countries)\b',job.description,re.I))


def location_conflict(job):
    text = clean_text(job.description,12000)
    if re.search(r'hybrid|on.site|work from (?:home|office).{0,45}one day|WFH.{0,35}one day|on-site events',text,re.I): return True
    if re.search(r'\b(?:citizens?(?:hip)?|clearance|federal|must be located in|authorized to work in)\b',text,re.I) or re.search(r'\bFED\b',job.title,re.I):
        return True
    if GEO.search(job.location): return True
    for match in GEO.finditer(text):
        around = text[max(0,match.start()-65):match.end()+40]
        if re.search(r'\b(?:remote|work location|job location|position location|must reside|must be based|based in|located in|location:)\b',around,re.I):
            return True
    return False


def experience_info(job):
    matches = list(re.finditer(r'\b(\d+)(?:\s*[-–]\s*(\d+))?\+?\s+years?(?:\s+of)?\s+(?:[a-z-]+\s+){0,6}experience\b',job.description,re.I))
    strict = max(matches,key=lambda m:int(m.group(2) or m.group(1))) if matches else None
    years = int(strict.group(2) or strict.group(1)) if strict else None
    senior = bool(re.search(r'\b(?:senior|sr\.?|lead|principal|head|director)\b',job.title,re.I)) or (years is not None and years >= 5)
    explicit_entry = bool(re.search(r'\b(?:junior|entry.level|intern(?:ship)?|trainee|graduate|apprentice)\b',job.title,re.I) or re.search(r'no (?:prior |professional )?experience|required experience: none|entry.level role|no specialized technical experience',job.description,re.I))
    junior = not senior and (years is None or years <= 2) and explicit_entry
    label = strict.group(0) if strict else ('Senior' if senior else 'Entry level' if junior else 'Experience not stated')
    if senior and strict: label = 'Senior | '+label
    return (0 if junior else 2 if senior else 1), label


def audience_eligible(job):
    if location_conflict(job): return False
    if GEO.search(job.title) and not explicit_worldwide(job): return False
    if re.search(r'multiple requests|multiple positions|various roles', job.description, re.I):
        return False
    if re.search(r'\bunpaid\b',job.description,re.I):return False
    if re.search(r'crypto.*trader|rates trader|financial expert|security onion|CBRN|equity research analyst|civil / structural engineer',job.title,re.I): return False
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
    published = job.published_at or (job.scraped_at if job.active_status == 'active' else None)
    if job.active_status == 'closed' or (job.expires_at and job.expires_at <= now): return False
    if published and published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return bool(audience_eligible(job) and published and now - timedelta(days=21) <= published <= now
                and job.link_status in {'200', 'redirect'})


def salary_text(value):
    value = clean_text(value)
    value = re.sub(r'(\$[\d,.]+)\s*[–—-]\s*\1(?=\D|$)', r'\1', value)
    return value.replace('/hourly', '/hour')


def role_evidence(job):
    text = clean_text(job.description,12000)
    # Start with duties when a heading exists. Company biographies cannot supply evidence.
    heading=re.search(r"(?:Key |Your |Main )?Responsibilities(?:\s*:)?|What you(?:'ll|’ll) (?:do|own)",text,re.I)
    if heading:
        text=text[heading.end():]
        text=re.split(r'\b(?:Requirements|Qualifications|What We Offer|Required Skills|Experience and Skills|Benefits)\b',text,flags=re.I)[0]
    verbs=r'(?:own|manage|respond|analy[sz]e|design|build|develop|maintain|resolve|support|implement|create|test|debug|curate|review|evaluate|train|write|monitor|deliver|process|optimi[sz]e|configure|integrate|deploy|triage|investigate|automate|lead|assist|provide|coordinate|answer|track|complete|edit|communicate|fact.check)'
    anchor=re.compile(r"^(?:(?:In this role[, ]*)?(?:You will|You’ll|You'll|You would|Your job is)|As .{1,90}?you will|The .{1,80}?will (?:be responsible|involve)|"+verbs+r")\b",re.I)
    pieces=job.evidence_lines + re.split(r'(?<=[.!?;])\s+|[•\n]',text)
    for piece in pieces:
        piece=piece.strip(' -:;')
        start=re.search(r"\b(?:You will|You’ll|You'll|In this role)\b",piece,re.I)
        if start and GEO.search(piece[:start.start()]):piece=piece[start.start():]
        piece=re.sub(r'^(?:In this role[, ]*)?(?:Responsibilities|Key Responsibilities)\s*[:,-]?\s*','',piece,flags=re.I)
        if not 25 <= len(piece) <= 650 or FLUFF.search(piece) or not anchor.search(piece):continue
        if not TASK.search(piece) and not re.search(r'\b(?:assist|provide|coordinate|answer|track|complete|edit|communicate)\b',piece,re.I):continue
        if re.search(r'with the founders|help train next.generation|then give more details|if I ask|introduce yourself|cover letter|application|interview|assessment|screening call|complete profile|your profile|your wallet|once you.ve applied',piece,re.I):continue
        if re.search(r'\b(?:requirements|years? experience|years? of experience|proficiency|must have|skills|ability|requires|looking to|looking for|training from)\b',piece,re.I):continue
        if GEO.search(piece) or re.search(r'headquarters|location:|application URL',piece,re.I):continue
        if len(piece.split())<=30:return piece.rstrip('.')+'.'
        for clause in re.split(r'[;:]|, (?=and |including |with )',piece):
            if 5<=len(clause.split())<=30 and anchor.search(clause.strip()) and not FLUFF.search(clause):
                return clause.strip(' ,;:.')+'.'
    return ''


def detail(job):
    location = shorten(job.location, 100)
    if location.lower() in {'', 'remote'}:
        location = 'Worldwide' if job.remote_scope == 'worldwide' else 'Africa — check listed countries'
    fields = [location + ' | Africa eligible', experience_info(job)[1]]
    if job.salary: fields.append(salary_text(job.salary))
    if job.work_hours: fields.append(job.work_hours)
    return '\n'.join(fields)


def category(job):
    title = job.title.lower()
    for name, terms in [('Support', ('support','customer success')), ('Design', ('design','ux','ui')), ('Marketing', ('marketing','content','seo','growth')), ('Data', ('data','analyst','annotation','transcription')), ('Tech', ('developer','engineer','automation','qa','software'))]:
        if any(term in title for term in terms): return name
    return 'Other'


def early_career(job):
    priority, label = experience_info(job)
    if priority == 0: return True
    years = re.findall(r'\b(\d+)(?:\s*[-–]\s*(\d+))?\+?\s+years?(?:\s+of)?\s+(?:[a-z-]+\s+){0,6}experience\b',job.description,re.I)
    return priority != 2 and bool(years) and max(int(b or a) for a,b in years) <= 3


def select_digest_jobs(jobs, now):
    pool = [job for job in jobs if eligible_for_digest(job, now) and role_evidence(job)]
    pool.sort(key=lambda job: (experience_info(job)[0], not early_career(job), not job.telegram_featured, category(job) == 'Other', -job.quality_score))
    selected, companies, keys, reasons, counts = [], {}, set(), set(), {}
    senior_count = 0
    # First pass provides role variety; second fills up to ten without inventing it.
    for cap in (2, MAX_ROLES):
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
    # The smaller issue contains only verified junior or explicitly 1–3-year roles.
    ideal = len(jobs) >= 6 and sum(experience_info(j)[0] == 0 for j in jobs) >= 3
    if not ideal: jobs = [j for j in jobs if early_career(j)]
    week = now.astimezone(ZoneInfo('Africa/Lagos')).strftime('%G-W%V')
    title = f'Remote jobs this week: {len(jobs)} roles open worldwide or in Africa'
    packet = {'newsletter_markdown': f'# {title}\n\n', 'x_posts': [], 'substack_notes': []}
    juniors = sum(experience_info(job)[0] == 0 for job in jobs)
    if len(jobs) < MIN_ROLES or (not ideal and juniors < 1):
        packet['newsletter_markdown'] = f'# Digest held for review\n\n{len(jobs)} suitable roles passed, including {juniors} entry/junior roles. Required: at least {MIN_ROLES} roles, at least 1 verified entry/junior role, and only stated 1–3-year requirements in the smaller issue. Nothing queued.\n'
        packet['held'] = True
        packet['qualifying_roles'] = len(jobs)
        return packet
    promo = True  # User explicitly requested the newsletter funnel now.
    intro = f'{len(jobs)} remote roles worth checking this week, including {juniors} entry/junior roles.\n\n'
    if not ideal: intro += 'A smaller early-career issue: the other roles ask for up to three years of experience.\n\n'
    intro += editorial_opening(jobs, now)
    sections = []
    for job in jobs:
        section = f'{shorten(job.title, 110)} — {shorten(job.company, 60)}\n{detail(job)}'
        section += f'\nWhy this one — the actual work: “{role_evidence(job)}”\nApply: {job.effective_url}'
        if job.source in CREDITS: section += '\nListing credit: '+CREDITS[job.source]
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
    if job.source in CREDITS:
        fields.insert(-1,CREDITS[job.source]); x = '\n'.join(field for field in fields if field)
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
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    seen = featured_keys(OUT)
    settings = replace(Settings.from_env(), max_per_run=100, max_per_source=40, max_job_age_days=21, min_quality_score=6,
                       allowed_remote_scopes=frozenset({'worldwide', 'africa'}),
                       mercor_referral_url='https://t.mercor.com/H06sH', link_check_enabled=True)
    now = datetime.now(timezone.utc)
    fresh = collect_expanded(settings)
    candidates = cached_pool(fresh,OUT/'candidate_pool.json',now)
    channel_links=telegram_urls(settings,now)
    # Previously posted Telegram jobs are input, but must pass the new checks.
    reused=sum(j.direct_url.rstrip('/') in channel_links for j in candidates)
    print(f'Telegram preview: {len(channel_links)} links; {reused} full listings matched.')
    from editorial.quality_jobs.text import canonicalize_url
    for job in candidates: job.telegram_featured=canonicalize_url(job.effective_url) in channel_links or canonicalize_url(job.direct_url) in channel_links
    candidates = [job for job in candidates if job.source != 'Remotive' and audience_eligible(classify(job))]
    selected, rejected = process(candidates, settings, existing_fingerprints=seen)
    with ThreadPoolExecutor(max_workers=8) as executor:
        active=list(executor.map(lambda j:still_open(j,settings,now),selected))
    selected=[job for job,open_now in zip(selected,active) if open_now]
    for job in selected:job.active_status='active'
    outputs = build_digest(selected)
    outputs['tagline']=TAGLINE
    (OUT/'latest_digest.md').write_text(outputs['newsletter_markdown'])
    for file, key in [('x_queue.json','x_posts'), ('substack_notes_queue.json','substack_notes')]:
        (OUT/file).write_text(json.dumps(outputs[key], ensure_ascii=False, indent=2)+'\n')
    evidence = [{'title': j.title, 'company': j.company, 'link': j.direct_url,
                 'location': j.location, 'africa_eligible': j.africa_eligible,
                 'published_at': j.published_at.isoformat() if j.published_at else None,
                 'link_status': j.link_status, 'active_status':j.active_status, 'experience':experience_info(j)[1],
                 'telegram_input':j.direct_url.rstrip('/') in channel_links} for j in selected]
    (OUT/'latest_items.json').write_text(json.dumps({'jobs': evidence, 'news': [], 'drafting_mode':'curated_jobs', 'held':outputs.get('held',False), 'featured_count':len(outputs['substack_notes'][0]['job_fingerprints']) if outputs['substack_notes'] else 0}, indent=2))
    print(f'Job digest: {len(outputs["substack_notes"])} Notes; {len(outputs["x_posts"])} X posts. No tech-news copy generated.')

if __name__ == '__main__': main()
