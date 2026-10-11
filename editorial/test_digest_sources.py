import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import patch,Mock
from editorial.digest_sources import cached_pool,featured_keys,record_featured,still_open,himalayas,employer_board
from editorial.jobs_digest import build_digest,eligible_for_digest,experience_info
from editorial.quality_jobs.models import Job
from editorial.quality_jobs.config import Settings

class SupplyTests(unittest.TestCase):
    def job(self,i=0,**extra):
        params=dict(source='test',title='Junior Support Agent',company=f'Company{i}',location='Worldwide',direct_url=f'https://example.com/{i}',description=f'You will respond to customer ticket queue {i} and resolve account issues.',published_at=datetime.now(timezone.utc),africa_eligible=True,remote_scope='worldwide',fingerprint=f'key{i}',link_status='200')
        params.update(extra);return Job(**params)
    def test_ladder_five_with_one_junior_and_stated_experience(self):
        jobs=[self.job()]+[self.job(i,title='Support Associate',description=f'You will manage ticket queue {i} and resolve customer issues. Requires 3 years of experience.') for i in range(1,5)]
        p=build_digest(jobs);self.assertFalse(p.get('held'));self.assertIn('5 roles',p['newsletter_markdown']);self.assertIn('smaller early-career issue',p['newsletter_markdown'])
        jobs[1].description='You will manage ticket queue 1 and resolve customer issues.'
        self.assertTrue(build_digest(jobs)['held'])
    def test_ladder_does_not_accept_zero_juniors_or_senior_filler(self):
        jobs=[self.job(i,title='Support Associate',description=f'You will manage ticket queue {i} and resolve customer issues. Requires 3 years of experience.') for i in range(5)]
        self.assertTrue(build_digest(jobs)['held'])
        jobs[0]=self.job();jobs[1].title='Senior Support Associate'
        self.assertTrue(build_digest(jobs)['held'])
    def test_support_keyword_is_not_entry_evidence(self):
        self.assertNotEqual(experience_info(self.job(title='Customer Support Agent',experience_level='entry'))[0],0)
    def test_21_day_window_and_expiry(self):
        now=datetime.now(timezone.utc)
        self.assertTrue(eligible_for_digest(self.job(published_at=now-timedelta(days=20)),now))
        self.assertFalse(eligible_for_digest(self.job(published_at=now-timedelta(days=22)),now))
        self.assertFalse(eligible_for_digest(self.job(expires_at=now-timedelta(seconds=1)),now))
    def test_cache_preserves_first_seen_and_rechecks_missing_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'pool.json';now=datetime.now(timezone.utc);j=self.job(published_at=None,scraped_at=now-timedelta(days=10),active_status='active')
            cached_pool([j],path,now);fresh=self.job(published_at=None,active_status='active')
            pool=cached_pool([fresh],path,now);self.assertEqual(pool[0].scraped_at,j.scraped_at)
            self.assertEqual(cached_pool([],path,now)[0].active_status,'needs_recheck')
    def test_featured_ledger_reserves_delivery_but_not_hold(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);record_featured(out,{'held':True});self.assertFalse((out/'featured_jobs.json').exists())
            record_featured(out,{'substack_notes':[{'job_fingerprints':['a']}]});self.assertEqual(featured_keys(out),{'a'})
    @patch('editorial.digest_sources.requests.get')
    def test_200_closed_page_is_not_open(self,get):
        r=Mock();r.text='<main>This job is closed.<a href="/apply">Apply</a></main>';get.return_value=r
        self.assertFalse(still_open(self.job(),Settings.from_env(),datetime.now(timezone.utc)))
        r.text='<main>Job not found.</main>';self.assertFalse(still_open(self.job(),Settings.from_env(),datetime.now(timezone.utc)))
    @patch('editorial.digest_sources.get_json')
    def test_himalayas_missing_or_restricted_location_is_not_worldwide(self,get):
        get.return_value={'jobs':[{'title':'Junior Support Agent','companyName':'Company','applicationLink':'https://example.com'}, {'title':'Junior Support Agent','locationRestrictions':[{'name':'United States'}]}]}
        self.assertFalse(himalayas(Settings.from_env()))
    @patch('editorial.digest_sources.get_json')
    def test_greenhouse_update_is_not_publication_date(self,get):
        get.return_value={'jobs':[{'id':1,'title':'Junior Support Agent','location':{'name':'Worldwide'},'content':'You will resolve customer questions.','absolute_url':'https://example.com','updated_at':'2026-10-11T00:00:00Z'}]}
        job=employer_board({'provider':'greenhouse','slug':'test','company':'Company'},Settings.from_env())[0]
        self.assertIsNone(job.published_at);self.assertEqual(job.active_status,'active')

    def test_quote_rejects_company_blurbs_application_prompts_and_vague_work(self):
        from editorial.jobs_digest import role_evidence
        for text in ['About our company. We deliver innovative services.', 'You will work directly with the founders.', 'Complete AI Interview (approx. 15/20 minutes).', 'Complete profile - Set up your wallet once you have applied.', 'Lead with what matters, then give more details if I ask.']:
            self.assertFalse(role_evidence(self.job(description=text)))
        j=self.job(description='About our company.',evidence_lines=['Review customer reports and flag content that breaks moderation guidelines.'])
        self.assertIn('flag content',role_evidence(j))
    def test_hybrid_and_unpaid_cannot_use_worldwide_metadata(self):
        now=datetime.now(timezone.utc)
        for text in ['Work From Home option available one day per week.', 'This internship is unpaid.', 'Help run on-site events.']:
            self.assertFalse(eligible_for_digest(self.job(description=text),now))
    def test_longer_experience_requirement_overrides_structured_entry_label(self):
        j=self.job(description='You will build software. Requires 4+ years of software development experience. Employer seniority: Entry-level role.')
        self.assertNotEqual(experience_info(j)[0],0);self.assertFalse(build_digest([j]*5).get('substack_notes'))

    def test_manual_review_does_not_consume_weekly_supply(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)
            record_featured(out,{'substack_notes':[{'job_fingerprints':['review-only']}]},review=True)
            self.assertFalse(featured_keys(out))
