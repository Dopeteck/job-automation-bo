"""Bounded public feeds, employer boards and Telegram preview inputs for the digest."""
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from editorial.quality_jobs.models import Job
from editorial.quality_jobs.sources import _date, fetch_remotive, fetch_remoteok, fetch_weworkremotely, fetch_mercor
from editorial.quality_jobs.text import clean_text, canonicalize_url, fingerprint

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]
ROLE_QUERIES = ('customer support', 'community moderator', 'content moderator', 'QA tester',
                'sales development', 'virtual assistant', 'administrative assistant',
                'data annotation', 'AI training', 'intern', 'junior', 'coordinator', 'associate', 'trainee')
TARGET = re.compile(r'\b(?:support|customer success|community|moderator|moderation|QA|quality assurance|test(?:er|ing)?|sales development|SDR|assistant|admin|annotation|AI trainer|AI training|intern(?:ship)?|coordinator|associate|trainee|junior|entry.level)\b', re.I)
CREDITS = {'Himalayas':'Himalayas: https://himalayas.app', 'Jobicy':'Jobicy: https://jobicy.com',
           'RemoteOK':'Remote OK: https://remoteok.com', 'Remotive':'Remotive: https://remotive.com'}


def get_json(url, settings, params=None):
    r = requests.get(url, params=params, timeout=settings.request_timeout_seconds,
                     headers={'User-Agent': settings.user_agent})
    r.raise_for_status()
    return r.json()


def himalayas(settings):
    jobs = []
    for query in ROLE_QUERIES:
        data = get_json('https://himalayas.app/jobs/api/search', settings,
                        {'q':query, 'worldwide':'true', 'sort':'recent', 'page':1})
        for row in data.get('jobs', []):
            # Missing restriction metadata is unknown, not worldwide.
            if 'locationRestrictions' not in row or row['locationRestrictions']: continue
            expiry = _date(row.get('expiryDate'))
            if expiry and expiry <= datetime.now(timezone.utc): continue
            job = Job(source='Himalayas', title=clean_text(row.get('title'),160),
                      company=clean_text(row.get('companyName'),120), location='Worldwide',
                      direct_url=row.get('applicationLink',''), source_job_id=str(row.get('guid','')),
                      published_at=_date(row.get('pubDate')), description=clean_text(row.get('description'),12000),
                      employment_type=clean_text(row.get('employmentType')))
            job.evidence_lines=[clean_text(str(li),800) for li in BeautifulSoup(row.get('description',''),'html.parser').select('li')]
            job.active_status='active'; job.expires_at=expiry
            zones=row.get('timezoneRestrictions',[])
            if zones and not any(float(z) in {-1,0,1,2,3,4} for z in zones): continue
            if zones and len(zones)<20: job.work_hours='Accepted timezone offsets (UTC): '+', '.join(map(str,zones))
            # Structured seniority is evidence, but years/title checks still take precedence.
            seniority=row.get('seniority',[])
            if 'Entry-level' in seniority: job.experience_level='entry';job.description+=' Employer seniority: Entry-level role.'
            if row.get('minSalary') is not None:
                job.salary=f"{row.get('currency') or ''} {row['minSalary']}–{row.get('maxSalary') or row['minSalary']}/{row.get('salaryPeriod') or 'annual'}"
            jobs.append(job)
    return jobs


def jobicy(settings):
    data=get_json('https://jobicy.com/api/v2/remote-jobs',settings,{'count':100,'geo':'anywhere'})
    jobs=[]
    for row in data.get('jobs',[]):
        if not TARGET.search(str(row.get('jobTitle',''))):continue
        job=Job(source='Jobicy',source_job_id=str(row.get('id','')),title=clean_text(row.get('jobTitle'),160),
                company=clean_text(row.get('companyName'),120),location=clean_text(row.get('jobGeo'),160),
                direct_url=row.get('url',''),published_at=_date(row.get('pubDate')),
                description=clean_text(row.get('jobDescription'),12000))
        if row.get('jobLevel') in {'Junior','Entry-Level','Entry-level'}:job.description+=' Employer seniority: Entry-level role.'
        job.evidence_lines=[clean_text(str(li),800) for li in BeautifulSoup(row.get('jobDescription',''),'html.parser').select('li')]
        job.active_status='active';jobs.append(job)
    return jobs


def employer_board(board, settings):
    provider,slug=board['provider'],board['slug']
    urls={'greenhouse':f'https://boards-api.greenhouse.io/v1/boards/{slug}/jobs',
          'lever':f'https://api.lever.co/v0/postings/{slug}',
          'ashby':f'https://api.ashbyhq.com/posting-api/job-board/{slug}'}
    data=get_json(urls[provider],settings,{'content':'true'} if provider=='greenhouse' else {'mode':'json'} if provider=='lever' else None)
    rows=data if isinstance(data,list) else data.get('jobs',[])
    jobs=[]
    for row in rows:
        title=row.get('title') or row.get('text','')
        if not TARGET.search(title):continue
        if provider=='greenhouse':
            location=(row.get('location') or {}).get('name','');desc=row.get('content','');url=row.get('absolute_url','')
            # updated_at is NOT the original publication date.
            published=_date(row.get('first_published'))
        elif provider=='lever':
            cats=row.get('categories') or {};location=cats.get('location','')
            desc=row.get('descriptionPlain','')+' '+ ' '.join(clean_text(x.get('content','')) for x in row.get('lists',[]))
            desc+=' '+clean_text(row.get('additionalPlain',''));url=row.get('hostedUrl','');published=_date(row.get('createdAt'))
        else:
            if not row.get('isListed',True):continue
            location=row.get('location','');desc=row.get('descriptionPlain') or row.get('descriptionHtml','')
            address=(row.get('address') or {}).get('postalAddress') or {}
            location+=' '+ ' '.join(str(address.get(k) or '') for k in ('addressRegion','addressCountry'))
            url=row.get('jobUrl') or row.get('applyUrl','');published=_date(row.get('publishedAt'))
        job=Job(source='Employer board',title=clean_text(title,160),company=board['company'],
                location=clean_text(location,200),direct_url=url,published_at=published,description=clean_text(desc,12000),source_job_id=str(row.get('id','')))
        raw=row.get('content') or row.get('descriptionHtml') or ' '.join(x.get('content','') for x in row.get('lists',[]))
        job.evidence_lines=[clean_text(str(li),800) for li in BeautifulSoup(raw,'html.parser').select('li')]
        job.active_status='active';jobs.append(job)
    return jobs


def _fetch_expanded(settings):
    tasks=[('RemoteOK',lambda:fetch_remoteok(settings)),
           ('WeWorkRemotely',lambda:fetch_weworkremotely(settings)),('Mercor',lambda:fetch_mercor(settings)),
           ('Himalayas',lambda:himalayas(settings)),('Jobicy',lambda:jobicy(settings))]
    boards=json.loads((ROOT/'editorial/employer_boards.json').read_text())
    tasks += [(b['company'],lambda b=b:employer_board(b,settings)) for b in boards]
    def run(task):
        name,fetch=task
        try:
            jobs=fetch();LOG.info('source=%s fetched=%s',name,len(jobs));return jobs
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            LOG.warning('source=%s failed=%s',name,type(exc).__name__);return []
    with ThreadPoolExecutor(max_workers=6) as ex:
        return [job for batch in ex.map(run,tasks) for job in batch]


def collect_expanded(settings):
    path=ROOT/'data/editorial/source_snapshot.json'
    now=datetime.now(timezone.utc)
    if path.exists():
        snapshot=json.loads(path.read_text())
        checked=_date(snapshot.get('checked_at'))
        if checked and timedelta(0)<=now-checked<timedelta(hours=24):
            LOG.info('Using public feed snapshot fetched within 24 hours.')
            return [deserialize(row) for row in snapshot.get('jobs',[])]
    jobs=_fetch_expanded(settings)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'checked_at':now.isoformat(),'jobs':[serialize(j) for j in jobs]})+'\n')
    return jobs


def serialize(job):
    row=asdict(job)
    for key in ('published_at','scraped_at','expires_at'):
        row[key]=row[key].isoformat() if row[key] else None
    return row


def deserialize(row):
    fields=Job.__dataclass_fields__
    row={k:v for k,v in row.items() if k in fields}
    for key in ('published_at','scraped_at','expires_at'):
        if key in row:row[key]=_date(row[key])
    return Job(**row)


def cached_pool(fresh, path, now):
    old=json.loads(path.read_text()) if path.exists() else []
    rows={canonicalize_url(row['direct_url']):row for row in old}
    for job in fresh:
        key=canonicalize_url(job.direct_url)
        if key in rows:job.scraped_at=_date(rows[key].get('scraped_at')) or job.scraped_at
        rows[key]=serialize(job)
    fresh_keys={canonicalize_url(job.direct_url) for job in fresh}
    pool=[]
    for key,row in rows.items():
        job=deserialize(row)
        date=job.published_at or job.scraped_at
        if not date or not now-timedelta(days=21)<=date<=now:continue
        if key not in fresh_keys:job.active_status='needs_recheck'
        pool.append(job)
    path.write_text(json.dumps([serialize(j) for j in pool],indent=2)+'\n')
    return pool


def still_open(job,settings,now):
    if job.expires_at and job.expires_at<=now:return False
    if job.active_status=='active':return True # present in a current public vacancy feed
    try:
        r=requests.get(job.direct_url,timeout=settings.request_timeout_seconds,headers={'User-Agent':settings.user_agent})
        r.raise_for_status()
        soup=BeautifulSoup(r.text,'html.parser');main=soup.select_one('main') or soup
        text=clean_text(str(main),20000)
        if re.search(r'job (?:is |has been )?(?:closed|expired|filled)|no longer accepting applications|position (?:has been filled|is closed)|not accepting applications',text,re.I):return False
        # A live page alone is insufficient; require a current application action.
        actions=main.select('a,button,input[type=submit]')
        return any(re.search(r'\bapply\b',a.get_text(' ',strip=True) or a.get('value',''),re.I) and (a.get('href') or a.name in {'button','input'}) for a in actions)
    except requests.RequestException:return False


def telegram_urls(settings,now):
    """Read public channel previews only; never message or join a group."""
    urls=set();before=None
    for _ in range(4):
        try:
            r=requests.get('https://t.me/s/RemoteJobsTechHub',params={'before':before} if before else None,
                           timeout=settings.request_timeout_seconds,headers={'User-Agent':settings.user_agent});r.raise_for_status()
            soup=BeautifulSoup(r.text,'html.parser');messages=soup.select('.tgme_widget_message')
            if not messages:break
            ids=[];old=False
            for msg in messages:
                try:ids.append(int(msg.get('data-post','').split('/')[-1]))
                except ValueError:pass
                time=msg.select_one('time');date=_date(time.get('datetime')) if time else None
                if not date or date<now-timedelta(days=21):old=True;continue
                content=msg.select_one('.tgme_widget_message_text')
                if content:
                    for a in content.select('a[href]'):
                        url=a['href']
                        if urlsplit(url).scheme in {'http','https'} and urlsplit(url).hostname not in {'t.me','telegram.me'}:urls.add(canonicalize_url(url))
            if old or not ids:break
            before=min(ids)
        except requests.RequestException:break
    return urls


def featured_keys(out):
    state=json.loads((out/'buffer_state.json').read_text()) if (out/'buffer_state.json').exists() else {}
    keys={k for row in state.get('confirmed_uploads',{}).values() if not row.get('draft') for k in row.get('job_fingerprints',[])}
    ledger=json.loads((out/'featured_jobs.json').read_text()) if (out/'featured_jobs.json').exists() else {}
    keys.update(ledger.get('fingerprints',[]))
    return keys


def record_featured(out,packet,review=False):
    """Reserve a privately delivered newsletter issue too; hold notices reserve nothing."""
    if review or packet.get('held'):return
    keys=featured_keys(out)
    keys.update(k for row in packet.get('substack_notes',[]) for k in row.get('job_fingerprints',[]))
    (out/'featured_jobs.json').write_text(json.dumps({'fingerprints':sorted(keys)},indent=2)+'\n')
