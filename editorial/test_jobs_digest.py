import unittest
from datetime import datetime, timezone, timedelta
from editorial.jobs_digest import build_digest, eligible_for_digest, editorial_opening, salary_text, select_digest_jobs
from editorial.quality_jobs.models import Job
from editorial.editorial_pipeline import x_weight

class JobsDigestTests(unittest.TestCase):
    def job(self, index=1, **changes):
        job=Job(source='test', title='Junior Automation Developer', company=f'Company {index}', location='Worldwide', direct_url=f'https://example.com/jobs/{index}', published_at=datetime.now(timezone.utc), description=f'You will build workflow {index} to connect billing records with support ticket data.', salary='$20/hour', remote_scope='worldwide', africa_eligible=True, experience_level='entry', link_status='200', fingerprint=f'test{index}')
        for key,value in changes.items(): setattr(job,key,value)
        return job
    def pool(self):
        titles=['Support Agent','UX Designer','Marketing Assistant','Data Analyst','Automation Developer','QA Engineer','Content Writer','Customer Success Associate','Junior Developer','Data Reviewer']
        return [self.job(i,title=title) for i,title in enumerate(titles)]
    def test_digest_has_real_details_and_human_title(self):
        packet=build_digest(self.pool())
        note=packet['substack_notes'][0]['text']
        self.assertIn('$20/hour',note);self.assertIn('Africa eligible',note)
        self.assertIn('https://example.com/jobs/1',note)
        self.assertNotIn('Check experience requirements',note)
        self.assertNotIn('Application angle',note)
        self.assertIn('10 roles open worldwide or in Africa',packet['newsletter_markdown'])
        self.assertLessEqual(x_weight(packet['x_posts'][0]['text']),280)
        reasons=[line for line in note.splitlines() if line.startswith('Why this one')]
        self.assertEqual(len(reasons),len(set(reasons)))
    def test_below_eight_is_held_not_padded(self):
        packet=build_digest(self.pool()[:7]);self.assertFalse(packet['x_posts']);self.assertFalse(packet['substack_notes']);self.assertTrue(packet['held'])
    def test_holds_undated_stale_protected_unknown_and_wrong_regions(self):
        for job in [self.job(published_at=None),self.job(published_at=datetime.now(timezone.utc)-timedelta(days=8)),self.job(link_status='protected'),self.job(remote_scope='unknown'),self.job(location='US only',remote_scope='us'),self.job(location='India, Philippines',remote_scope='asia')]:
            self.assertFalse(eligible_for_digest(job,datetime.now(timezone.utc)))
    def test_specialists_commission_and_vague_descriptions_excluded(self):
        for job in [self.job(title='Primary Care Physician'),self.job(description='Requires experience with DFT and molecular dynamics.'),self.job(salary='OTE $25k - $35k'),self.job(description='About us. We are a great company.')]:
            self.assertFalse(select_digest_jobs([job],datetime.now(timezone.utc)))
    def test_company_worldwide_claim_is_not_hiring_evidence(self):
        job=self.job(location='Remote',description='We serve customers worldwide.')
        self.assertFalse(eligible_for_digest(job,datetime.now(timezone.utc)))
        job.description='Candidates can apply from anywhere in the world.'
        self.assertTrue(eligible_for_digest(job,datetime.now(timezone.utc)))
        job.location='Worldwide';job.description='Headquarters: Remote - United States. Customers worldwide.'
        self.assertFalse(eligible_for_digest(job,datetime.now(timezone.utc)))
    def test_salary_collapses_equal_bounds_and_omits_unknown_level(self):
        self.assertEqual(salary_text('$170–$170/hourly'),'$170/hour')
        self.assertEqual(salary_text('$84–$84/hourly'),'$84/hour')
        self.assertEqual(salary_text('$20–$40/hourly'),'$20–$40/hour')
        packet=build_digest([self.job(i,experience_level='not_specified',salary='') for i in range(10)])
        self.assertNotIn('Pay not disclosed',packet['newsletter_markdown'])
        self.assertNotIn('Check experience',packet['newsletter_markdown'])
    def test_story_has_scene_and_does_not_claim_personal_testimonial(self):
        opening=editorial_opening(self.pool(),datetime(2026,10,11,tzinfo=timezone.utc))
        self.assertIn('Imagine',opening)
        self.assertNotIn('I applied',opening)
