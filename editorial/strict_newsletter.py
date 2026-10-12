"""Fail-closed implementation of the author's newsletter editorial contract."""
import hashlib
import json
import logging
import os
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import geonamescache
from editorial.jobs_digest import GEO,TASK
from editorial.digest_sources import collect_expanded,cached_pool,still_open,CREDITS
from editorial.newsletter_story import load_json
from editorial.quality_jobs.config import Settings
from editorial.quality_jobs.pipeline import process
from editorial.quality_jobs.classify import classify
from editorial.quality_jobs.text import clean_text,canonicalize_url,fingerprint
from editorial.editorial_pipeline import x_weight

OUT=ROOT/'data/editorial'
TELEGRAM='https://t.me/RemoteJobsTechHub'
STATE_CODES=set(geonamescache.GeonamesCache().get_us_states())
STATE_CODE_RE=re.compile(r'\b(?:'+ '|'.join(sorted(STATE_CODES))+r')\b')
CITY_NAMES={x['name'].casefold() for x in geonamescache.GeonamesCache().get_cities().values()}
PERIODS={'hour':'hour','hourly':'hour','hr':'hour','year':'year','yearly':'year','annual':'year','annually':'year','month':'month','monthly':'month','week':'week','weekly':'week','day':'day','daily':'day'}
DUTIES_UNKNOWN='Duties not clearly described - read the full posting.'
BOILER=re.compile(r'culture|benefits|flexibility|ownership|recognized|interview|assessment|screening|application process|application instructions|application form|submit.{0,30}application|complete profile|your profile|your wallet|regular.{0,20}communication|timely.{0,20}communication|teamwork|communicat.{0,40}(?:team|stakeholder)|work.{0,20}founders|opportunity to learn',re.I)
TASK_ALIASES={'review':'check','analyze':'examine','analyse':'examine','annotate':'label','create':'produce','manage':'handle','maintain':'keep','develop':'build','build':'develop','implement':'put in place','optimize':'improve','optimise':'improve','write':'draft','respond':'reply','verify':'confirm','evaluate':'assess','monitor':'track','complete':'finish','configure':'set up','resolve':'address','curate':'select','design':'plan','test':'check','assist':'help','provide':'deliver','answer':'respond to','track':'monitor','edit':'revise','label':'annotate','debug':'find and fix bugs in','support':'help with'}


def listing_text(job):
    text=clean_text(job.description,30000)
    # These earlier collector annotations are source metadata, not employer wording.
    return re.sub(r'\s*(?:Employer seniority:|Working timezone offsets:|Accepted timezone offsets).*$', '',text,flags=re.I)


def cleaned_title(value):
    value=value.replace('|',' - ')
    value=''.join(c for c in value if not unicodedata.category(c).startswith('S'))
    value=re.sub(r'\|',' - ',value)
    value=re.sub(r'\s*[-–—,]\s*Remote\s*(?:[-–—,]\s*(?:Contract|Contact))?\s*$','',value,flags=re.I)
    value=re.sub(r'\s*[-–—]\s*(?:Contract|Contact|Remote)\s*$','',value,flags=re.I)
    value=re.sub(r'\s+',' ',value).strip(' -–—,')
    return value.title() if value.isupper() else value


def experience(job):
    text=listing_text(job)
    matches=list(re.finditer(r'\b(\d+)(?:\s*[-–]\s*(\d+))?\s*\+?\s+years?(?:\s+of)?\s+(?:[a-z-]+\s+){0,6}experience\b',text,re.I))
    strict=max(matches,key=lambda x:int(x.group(2) or x.group(1))) if matches else None
    years=int(strict.group(2) or strict.group(1)) if strict else None
    senior=bool(re.search(r'\b(?:senior|sr\.?|lead|principal|head|director)\b',job.title,re.I))
    entry=bool(re.search(r'\b(?:no (?:prior |professional )?experience(?: required)?|entry.level|zero experience)\b',text+' '+job.title,re.I))
    junior_title=bool(re.search(r'\bjunior\b',job.title,re.I))
    if senior or (years is not None and years>=5):return (3,years or 99),'Senior'+(' - '+strict.group(0) if strict else ' - years not stated'),False
    if years is not None:
        group=0 if years==0 else 1 if years<=2 else 2
        return (group,years),strict.group(0),group<=1
    if entry:return (0,0),'Entry level - no prior experience stated as required',True
    if junior_title:return (1,99),'Junior - years not stated',True
    return (4,99),'Experience not stated',False


def category(job):
    title=job.title.lower()
    if re.search(r'annotat|moderator|moderation|ai train|data capture',title):return 'AI data work'
    if re.search(r'qa|tester|quality assurance',title):return 'QA'
    if re.search(r'support|customer success|customer service',title):return 'Support'
    if re.search(r'developer|engineer|software|automation',title):return 'Engineering'
    if re.search(r'design|ux|ui',title):return 'Design'
    if re.search(r'marketing|content|editor|social|sales development|sdr',title):return 'Marketing'
    if re.search(r'data|analyst',title):return 'Data'
    if re.search(r'assistant|admin|coordinator',title):return 'Admin'
    return 'Other'


def eligibility_basis(job):
    text=listing_text(job)
    patterns=[r'\b(?:work|working|hire|hiring|apply|applicants|candidates|applications|open to)\b[^.!?]{0,65}\b(?:anywhere in the world|worldwide|all countries|from any country|across Africa|anywhere in Africa)\b',
              r'\b(?:worldwide|global)\s+(?:hiring|applicants|candidates|applications)\b',
              r'\b(?:remote work|work remotely)\s+from\s+anywhere\b']
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if match:
            quote=match.group(0).strip()
            if re.search(r'customer|client|user|product|market|serve|service',quote,re.I):continue
            if len(quote.split())<=12:return quote
            # Keep an exact, complete eligibility phrase instead of truncating a sentence.
            suffix=re.search(r'(?:anywhere in the world|from any country|all countries|across Africa|anywhere in Africa|worldwide)',quote,re.I)
            if suffix:return suffix.group(0)
    return ''


def location_restriction(job):
    text=listing_text(job)
    if re.search(r'\b(?:citizens?(?:hip)?|clearance|federal|government|hybrid|on.site|residents|must (?:be )?(?:located|based)|authorized to work|eligible to work in|within the country of employment)\b',text,re.I):return 'Location, citizenship, government, on-site or work-authorization restriction'
    if re.search(r'\bFED\b',job.title,re.I):return 'Federal role'
    if job.work_hours or re.search(r'\b(?:EST|EDT|CST|CDT|PST|PDT|EET|EEST|CET|CEST|UTC|GMT)\b|time.?zone.{0,60}(?:only|required|must|overlap)|(?:must|required|at least).{0,60}overlap|(?:work|working|business).{0,25}hours.{0,20}(?:US|UK|Pacific|Eastern)|(?:remote|work).{0,50}one day per week',text,re.I):return 'Time-zone-only or hybrid hours requirement needs review'
    if STATE_CODE_RE.search(job.location) or STATE_CODE_RE.search(job.title):return 'US state abbreviation in the work location/title'
    for match in STATE_CODE_RE.finditer(text):
        if re.search(r'\b(?:remote|location|based|located|reside|residents|hiring|work)\b',text[max(0,match.start()-45):match.end()+10],re.I):return 'US state abbreviation in the work restriction'
    if GEO.search(job.location) or GEO.search(job.title):return 'Country, state or region in the work location/title'
    words=re.findall(r'[\wÀ-ÿ]+',job.location.casefold())
    if any(' '.join(words[i:i+n]) in CITY_NAMES for i in range(len(words)) for n in range(1,5)):return 'City in the work location'
    for m in GEO.finditer(text):
        context=text[max(0,m.start()-70):m.end()+40]
        if re.search(r'\b(?:remote|work location|job location|position location|reside|based|located|location:|hiring|eligible)\b',context,re.I):return 'Country/state restriction in the listing text'
    for m in re.finditer(r'\b(?:remote in|remote from|work location:|job location:|position location:|based in|located in|work from)\s+([\wÀ-ÿ ,.-]{1,80})',text,re.I):
        words=re.findall(r'[\wÀ-ÿ]+',m.group(1).casefold())[:6]
        if any(' '.join(words[:n]) in CITY_NAMES for n in range(1,5)):return 'City-based work restriction in the listing'
    if re.search(r'insurance|banking|\bbank\b|government contractor',text+' '+job.company,re.I) and (GEO.search(text) or re.search(r'\b(?:FDIC|NMLS|Ncontracts|Comergence|Encompass|surplus lines|Fannie Mae|Freddie Mac|401k)\b',text,re.I)):
        return 'Traditional employer names US systems or jurisdictions despite a worldwide tag'
    return ''


def contract_type(job):
    text=job.employment_type+' '+job.title
    for pattern,label in [(r'intern','Internship'),(r'part.?time','Part-time'),(r'full.?time','Full-time'),(r'contract|freelance','Contract')]:
        if re.search(pattern,text,re.I):return label
    return 'Not stated'


def pay_info(job):
    salary=clean_text(job.salary)
    currency=job.pay_currency.upper() if job.pay_currency else ''
    found=re.search(r'\b(USD|PHP|INR|EUR|GBP|CAD|AUD|NGN|ZAR|KES|BRL)\b',salary,re.I)
    if found:currency=found.group(1).upper()
    if not currency and re.search(r'\bUSD\b|US dollars',listing_text(job),re.I):currency='USD'
    period=PERIODS.get(job.pay_period.lower(),'')
    if not period:
        found=re.search(r'\b(hourly|hour|hr|annually|annual|yearly|year|monthly|month|weekly|week|daily|day)\b',salary,re.I)
        if found:period=PERIODS[found.group(1).lower()]
    nums=[float(x.replace(',','')) for x in re.findall(r'\d[\d,]*(?:\.\d+)?',salary)]
    low=job.pay_min if job.pay_min is not None else nums[0] if nums else None
    high=job.pay_max if job.pay_max is not None else nums[1] if len(nums)>1 else low
    return currency,period,low,high


def pay_label(job):
    currency,period,low,high=pay_info(job)
    if low is None:return 'Pay not stated'
    def number(x):return f'{x:,.0f}' if x==int(x) else f'{x:,.2f}'.rstrip('0').rstrip('.')
    amount=number(low) if low==high else number(low)+'-'+number(high)
    return f'{currency} {amount}/{period}'


def duty_candidates(job):
    text=listing_text(job)
    heading=re.search(r'(?:Key |Your |Main )?Responsibilities\s*:??|What you(?:.ll| will) (?:do|own)',text,re.I)
    start=heading.end() if heading else None
    end=len(text)
    if heading:
        stop=re.search(r'\b(?:Requirements|Qualifications|Required Skills|What We Offer|Benefits|How to Apply|Application Process)\b',text[start:],re.I)
        if stop:end=start+stop.start()
    scoped=text[start:end] if heading else ''
    candidates=[line for line in job.evidence_lines if scoped and clean_text(line) in scoped]
    candidates+=re.split(r'(?<=[.!?;])\s+|[•\n]',scoped)
    candidates+=re.findall(r'\b(?:You will|You.ll)\b[^.!?]{15,250}[.!?]',text,re.I)
    return [clean_text(x,1000).strip(' -:;') for x in candidates if x]


def task_matches(job,line):
    patterns={'AI data work':r'annotat|label|moderat|review|content|accuracy|evaluat|capture|record|data',
              'Support':r'customer|ticket|inquir|support|repl|email|escalat',
              'QA':r'test|bug|defect|reproduc|software|fix',
              'Engineering':r'code|coding|software|application|system|API|integration|feature|debug|framework|infrastructure',
              'Design':r'design|layout|interface|visual|prototype|creative',
              'Marketing':r'content|post|campaign|advert|marketing|SEO|article|edit|leads|CRM',
              'Data':r'data|analys|report|model|accuracy|metric',
              'Admin':r'record|vendor|schedule|invoice|admin|tracker|document|organis|organiz|report'}
    return bool(re.search(patterns.get(category(job),r'(?!)'),line,re.I))


def why_line(job):
    for raw in duty_candidates(job):
        if BOILER.search(raw) or re.search(r'requirement|years?.{0,40}experience|skills|ability|proficiency|must have|\.\.\.|…|headquarters|location:',raw,re.I):continue
        if not task_matches(job,raw):continue
        raw=re.sub(r'^(?:In this role[, ]*)?(?:You will|You.ll)\s+','',raw,flags=re.I)
        raw=re.sub(r'^Responsibilities\s*:?\s*','',raw,flags=re.I).strip()
        match=re.match(r'([A-Za-z]+)\b',raw)
        if not match or match.group(1).lower() not in TASK_ALIASES:continue
        if len(raw.split())>22:continue # Never cut off a task sentence.
        verb=TASK_ALIASES[match.group(1).lower()]
        line='You '+verb+' '+raw[match.end():].strip().rstrip('.;!')+'.'
        line=re.sub(r'\s+',' ',line)
        if len(line.split())<25 and len(line.split())>=5:return line
    return DUTIES_UNKNOWN


def hold_reasons(job,now,seen):
    reasons=[];text=listing_text(job);title=cleaned_title(job.title)
    if not text or not job.direct_url or not job.source:reasons.append('Missing full description, application URL or source')
    if not job.company.strip() or job.company.casefold() in {'unknown','confidential','remote company',job.source.casefold()}:reasons.append('Company cannot be identified from the listing')
    if not title or len(title.split())>=8 or title.casefold() in {'remote','contact','remote contact','remote, contact','job','remote job','various roles'}:reasons.append('Vague or overlong title needs confirmation')
    restriction=location_restriction(job)
    if restriction:reasons.append(restriction)
    if not eligibility_basis(job):reasons.append('Source tag only - verify eligibility in the employer listing')
    if re.search(r'\brecruiter\b|recruitment agency|staffing agency|on behalf of.{0,20}client|our client.{0,40}(?:hiring|seeking|looking)|commission|\bOTE\b',job.title+' '+text+' '+job.salary,re.I) or job.is_referral or job.source.casefold()=='mercor':reasons.append('Recruiter, referral or commission role')
    if re.search(r'\bunpaid\b|pay to apply|application fee|registration fee|(?:must|need to|required to|purchase|buy).{0,40}(?:equipment|laptop|computer)|(?:pay|send).{0,25}(?:deposit|fee)',text,re.I):reasons.append('Fees, equipment purchase or unpaid work')
    currency,period,low,high=pay_info(job)
    if low is None and high is not None:reasons.append('[CONFIRM: complete pay range]')
    if low is not None:
        if not currency or not period:reasons.append('[CONFIRM: pay currency and period]')
        if currency and currency!='USD' and not job.location_reviewed:reasons.append('Non-USD pay - independent location review required')
        if low<=0 or high<low:reasons.append('Invalid pay range')
        elif high>3*low:reasons.append('Maximum pay exceeds three times the minimum')
        if experience(job)[2] and period=='hour' and high>40:reasons.append('Entry/junior pay exceeds USD 40/hour and needs verification')
        if period=='year' and (contract_type(job) in {'Part-time','Internship'} or re.search(r'part.?time|intern',job.title,re.I)) and not job.pay_reviewed:reasons.append('Annual intern/part-time pay requires workload and pay verification')
    key=job.fingerprint or fingerprint(job.title,job.company)
    if key in seen or canonicalize_url(job.direct_url) in seen:reasons.append('Featured in one of the last four issues')
    if not job.published_at:reasons.append('[CONFIRM: original posted date]')
    elif not now-timedelta(days=21)<=job.published_at<=now:reasons.append('Outside the 21-day posting window')
    if job.active_status=='closed' or (job.expires_at and job.expires_at<=now):reasons.append('Listing is closed or expired')
    if job.link_status not in {'200','redirect'}:reasons.append('Application page has not passed the live link check')
    duties=duty_candidates(job)
    if duties and all(not task_matches(job,line) for line in duties):reasons.append('Title and described duties do not match')
    return list(dict.fromkeys(reasons))


def story_from_notes(notes,used):
    confirms=[]
    if not notes or not notes.get('notes'):
        return None,['[CONFIRM: supply true STORY NOTES: the moment, who found or tried what, how, and what you did next]']
    for field in ('id','finder','how_found','draft','lesson','reply_prompt'):
        if not notes.get(field):confirms.append('[CONFIRM: '+field.replace('_',' ')+']')
    if notes.get('approved') is not True:confirms.append('[CONFIRM: author approval of the first-person story]')
    body=notes.get('draft','')
    if not 250<=len(body.split())<=350:confirms.append('[CONFIRM: a 250-350-word story supported by the notes]')
    if not re.search(r'\bI\b',body) or re.search(r'our newsletter|this channel',body,re.I):confirms.append('[CONFIRM: first-person author voice]')
    if notes.get('id') in used:confirms.append('[CONFIRM: a new story; this one was already used]')
    if notes.get('kind')=='reader' and notes.get('publish_consent') is not True:confirms.append('[CONFIRM: reader permission to feature the story]')
    if '[CONFIRM:' in body:confirms.append('[CONFIRM: resolve the story placeholders]')
    if notes.get('reply_prompt','').count('?')!=1:confirms.append('[CONFIRM: one story-related reply question]')
    if notes.get('finder') and notes['finder'] not in body:confirms.append('[CONFIRM: identify who found or tried it, exactly as supplied]')
    if notes.get('how_found') and notes['how_found'] not in body:confirms.append('[CONFIRM: state how it happened, exactly as supplied]')
    if any(len(re.split(r'(?<=[.!?])\s+',p))>3 for p in body.split('\n\n') if p):confirms.append('[CONFIRM: short paragraphs of one to three sentences]')
    if confirms:return None,confirms
    return {'id':notes['id'],'kind':notes.get('kind','author'),'body':body,'lesson':notes['lesson'],'question':notes['reply_prompt']},[]


def role_entry(job):
    source={'RemoteOK':'Remote OK','WeWorkRemotely':'We Work Remotely'}.get(job.source,job.source)
    basis=eligibility_basis(job)
    return (f'{cleaned_title(job.title)} - {job.company}\n'
            f'{clean_text(job.location)} | Eligibility basis: "{basis}"\n'
            f'Experience: {experience(job)[1]}\nPay: {pay_label(job)}\nContract type: {contract_type(job)}\n'
            f'Why this one: {why_line(job)}\nApply: [Apply on {source} ->]({job.direct_url})')


def build_issue(jobs,now=None,story_notes=None,previous_issues=None,story_history=None,history_complete=True):
    now=now or datetime.now(timezone.utc)
    seen=set()
    if previous_issues is not None:
        for row in previous_issues[-4:]:seen.update(row.get('fingerprints',[]));seen.update(row.get('urls',[]))
    held=[];valid=[];keys=set();companies=Counter();groups=Counter();reasons_used=set()
    for job in sorted(jobs,key=lambda j:(experience(j)[0],-j.quality_score)):
        reasons=hold_reasons(job,now,seen)
        key=job.fingerprint or fingerprint(job.title,job.company);why=why_line(job)
        if key in keys:reasons.append('Duplicate role across sources')
        if companies[job.company.casefold()]>=2:reasons.append('Maximum two roles per company')
        if groups[category(job)]>=3:reasons.append('Maximum three roles per category')
        if why!=DUTIES_UNKNOWN and why in reasons_used:reasons.append('Repeated why-line')
        if not reasons and len(valid)>=10:reasons.append('Held after the ten-role issue limit')
        if reasons:held.append({'title':job.title,'company':job.company,'reasons':reasons,'source_tag_only':not eligibility_basis(job)});continue
        valid.append(job);keys.add(key);companies[job.company.casefold()]+=1;groups[category(job)]+=1
        if why!=DUTIES_UNKNOWN:reasons_used.add(why)
    story,confirms=story_from_notes(story_notes,(story_history or {}).get('used_ids',[]))
    if not history_complete:confirms.append('[CONFIRM: confirm previous-issue history is complete, or provide missing manually published issues]')
    if previous_issues is None:confirms.append('[CONFIRM: supply PREVIOUS ISSUES, or explicitly confirm this is the first issue]')
    if not jobs:confirms.append('[CONFIRM: supply CANDIDATE ROLES with full descriptions]')
    juniors=sum(experience(j)[2] for j in valid)
    title=f'Remote roles this week: {len(valid)} worth checking'
    subtitle=f'{len(valid)} remote roles worth checking this week, including {juniors} entry/junior roles.'
    credits=sorted({CREDITS.get(j.source,j.source) for j in valid})
    footer=('Before you apply: recheck the eligible location on the employer page.\n'
            'Confirm the required experience, working hours and contract type.\n'
            'Check the pay currency and period; do not pay to apply.\n\n'+(story['question'] if story else '[CONFIRM: one reply prompt tied to the true story]')+'\n\n'+TELEGRAM+'\n\nSource credits: '+'; '.join(credits))
    newsletter='# '+title+'\n\n'+subtitle+'\n\n'
    if story:newsletter+=story['body']+'\n\n**The lesson: '+story['lesson']+'**\n\n'
    else:newsletter+='STORY NEEDED\n\n'
    newsletter+='\n\n'.join(role_entry(j) for j in valid)+'\n\n'+footer
    prose=(story['body']+' '+story['lesson']+' '+story['question'] if story else '')+' '+ ' '.join(why_line(j) for j in valid)+' '+ '\n'.join(footer.splitlines()[:3])
    sentences=re.split(r'(?<=[.!?])\s+',prose)
    count_match=re.fullmatch(r'(\d+) remote roles worth checking this week, including (\d+) entry/junior roles\.',subtitle)
    checks={'Counts match subtitle':bool(count_match and int(count_match.group(1))==len(valid) and int(count_match.group(2))==juniors and newsletter.count('\nApply: ')==len(valid)),'At least three entry/junior':juniors>=3,'Six to ten roles':6<=len(valid)<=10,
            'Sorted by required experience':[experience(j)[0] for j in valid]==sorted(experience(j)[0] for j in valid),
            'No emojis':not any(unicodedata.category(c)=='So' for c in newsletter),
            'No duplicates':len(keys)==len(valid),'Credits appear once':newsletter.count('Source credits:')==1,
            'Every why-line is a complete task sentence':all(why_line(j)!=DUTIES_UNKNOWN and why_line(j).endswith('.') and len(why_line(j).split())<25 for j in valid),
            'Every eligibility claim has listing evidence':all(eligibility_basis(j) and len(eligibility_basis(j).split())<=12 for j in valid),
            'Nothing from HOLD rules appears in roles':all(not hold_reasons(j,now,seen) for j in valid),
            'Story and previous-issue inputs complete':story is not None and not confirms and previous_issues is not None,
            'Title under 70 characters':len(title)<70,
            'Average sentence under 25 words':sum(len(s.split()) for s in sentences)/max(1,len(sentences))<25}
    failed=[label for label,ok in checks.items() if not ok]
    review='REVIEW NOTES\n\n'+('\n'.join(confirms) if confirms else 'CONFIRM items: none.')+'\nAssumptions: none; source tags do not establish Africa eligibility.\n\nHELD FOR REVIEW\n'
    review+='\n'.join('- '+cleaned_title(h['title'])+' - '+h['company']+': '+'; '.join(h['reasons']) for h in held) or 'None.'
    unclear=[cleaned_title(j.title)+' - '+j.company+': '+DUTIES_UNKNOWN for j in valid if why_line(j)==DUTIES_UNKNOWN]
    if unclear:review+='\n\nDUTY VERIFICATION NEEDED\n'+'\n'.join(unclear)
    review+='\n\nSource-tag-only eligibility: '+str(sum(h['source_tag_only'] for h in held))+' listings held for employer-text verification.\n\nPASS/FAIL\n'
    review+='\n'.join(('PASS' if ok else 'FAIL')+' - '+label for label,ok in checks.items())
    packet={'held':bool(failed),'newsletter_markdown':newsletter,'review_notes':review,'x_posts':[],'substack_notes':[],
            'selected':valid,'held_roles':held,'checks':checks,'story_context':{'id':story['id'],'kind':story['kind']} if story else None}
    if failed:
        reasons=', '.join(failed)
        packet['newsletter_markdown']=('STORY NEEDED\nPlease supply the author\'s true story notes.\n\n' if not story else '')+'ISSUE HELD\n'+reasons+f'\n{len(valid)} roles and {juniors} entry/junior roles passed. Nothing queued.\n\n'+review
        return packet
    body_id=hashlib.sha256(newsletter.encode()).hexdigest()[:20]
    common={'id':'strict-note-'+body_id,'source_id':body_id,'content_kind':'jobs_digest','job_fingerprints':[j.fingerprint or fingerprint(j.title,j.company) for j in valid],
            'job_urls':[canonicalize_url(j.direct_url) for j in valid],'source_published_at':now.isoformat()}
    packet['substack_notes']=[dict(common,text=newsletter)]
    first=valid[0];text=cleaned_title(first.title)+'\n'+first.company+'\n'+first.location+'\nEligibility: '+eligibility_basis(first)+'\n'+first.direct_url
    if first.source in CREDITS:text+='\n'+CREDITS[first.source]
    if x_weight(text)<=280:packet['x_posts']=[dict(common,id='strict-x-'+body_id,text=text,job_fingerprints=[common['job_fingerprints'][0]],job_urls=[canonicalize_url(first.direct_url)])]
    return packet


def record_issue(out,notes,review=False):
    if review or not notes:return
    path=out/'issue_history.json';history=load_json(path,[])
    issue=notes[0]
    if not any(row['id']==issue['id'] for row in history):history.append({'id':issue['id'],'fingerprints':issue.get('job_fingerprints',[]),'urls':issue.get('job_urls',[]),'created_at':issue.get('source_published_at')})
    path.write_text(json.dumps(history[-4:],indent=2)+'\n')


def main():
    OUT.mkdir(parents=True,exist_ok=True);logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    settings=replace(Settings.from_env(),max_per_run=150,max_per_source=60,max_job_age_days=21,min_quality_score=6,allowed_remote_scopes=frozenset({'worldwide','africa'}),mercor_referral_url='',link_check_enabled=True)
    now=datetime.now(timezone.utc);pool=cached_pool(collect_expanded(settings),OUT/'candidate_pool.json',now)
    # Pre-screen cheaply, but preserve every held listing in the review report.
    pre=[];preheld=[]
    for job in pool:
        job.fingerprint=job.fingerprint or fingerprint(job.title,job.company)
        job.description=listing_text(job)
        job.link_status='200' # temporary for the pre-screen only; live checks follow
        reasons=[x for x in hold_reasons(job,now,set()) if 'Application page' not in x]
        job.link_status='unchecked'
        if reasons:preheld.append({'title':job.title,'company':job.company,'reasons':reasons,'source_tag_only':not eligibility_basis(job)})
        else:pre.append(classify(job))
    selected,rejected=process(pre,settings)
    active=[]
    for job in selected:
        if still_open(job,settings,now):active.append(job)
        else:preheld.append({'title':job.title,'company':job.company,'reasons':['Current application availability could not be verified'],'source_tag_only':False})
    for job in rejected:preheld.append({'title':job.title,'company':job.company,'reasons':job.quality_reasons or ['Failed scoring or live link checks'],'source_tag_only':False})
    notes=None
    if os.getenv('TELEGRAM_DRAFT_BOT_TOKEN'):
        from editorial.story_inbox import selected_notes
        notes=selected_notes(os.environ['TELEGRAM_DRAFT_BOT_TOKEN'],load_json(OUT/'story_history.json',{}).get('used_ids',[]))
    # Legacy public story input remains a fallback only. Personal notes belong in the encrypted inbox.
    if notes is None:notes=load_json(ROOT/'editorial/story_notes.json',None)
    history=load_json(OUT/'issue_history.json',None)
    history_policy=load_json(ROOT/'editorial/history_policy.json',{})
    packet=build_issue(active,now,notes,history,load_json(OUT/'story_history.json',{}),history_complete=history_policy.get('confirmed_complete') is True)
    if preheld:
        lines='\n'.join('- '+cleaned_title(h['title'])+' - '+h['company']+': '+'; '.join(h['reasons']) for h in preheld)
        packet['review_notes']+='\n\nHELD DURING SOURCE CHECKS\n'+lines
        if packet['held']:packet['newsletter_markdown']+='\n\nHELD DURING SOURCE CHECKS\n'+lines
    (OUT/'latest_digest.md').write_text(packet['newsletter_markdown']+('' if packet['held'] else '\n\n'+packet['review_notes'])+'\n')
    (OUT/'review_notes.md').write_text(packet['review_notes']+'\n')
    (OUT/'story_context.json').write_text(json.dumps(packet['story_context'],indent=2)+'\n')
    for filename,key in [('x_queue.json','x_posts'),('substack_notes_queue.json','substack_notes')]:
        (OUT/filename).write_text(json.dumps(packet[key],ensure_ascii=False,indent=2)+'\n')
    evidence={'held':packet['held'],'checks':packet['checks'],'jobs':[{'title':j.title,'company':j.company,'url':j.direct_url,'eligibility_basis':eligibility_basis(j),'experience':experience(j)[1],'why':why_line(j)} for j in packet['selected']],
              'held_roles':packet['held_roles']+preheld,'story':packet['story_context']}
    (OUT/'latest_items.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(f'Strict newsletter: held={packet["held"]}; roles={len(packet["selected"])}; Notes={len(packet["substack_notes"])}; X={len(packet["x_posts"])}.')

if __name__=='__main__':main()
