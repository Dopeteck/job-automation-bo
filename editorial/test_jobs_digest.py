import unittest
from datetime import datetime, timezone, timedelta
from editorial.jobs_digest import build_digest, eligible_for_digest, editorial_opening
from editorial.quality_jobs.models import Job
from editorial.editorial_pipeline import x_weight

class JobsDigestTests(unittest.TestCase):
    def job(self, **changes):
        job=Job(source='test', title='Junior Automation Developer', company='Example', location='Worldwide', direct_url='https://example.com/jobs/1', published_at=datetime.now(timezone.utc), salary='$20/hour', remote_scope='worldwide', africa_eligible=True, experience_level='entry', link_status='200', fingerprint='test')
        for key,value in changes.items(): setattr(job,key,value)
        return job
    def test_digest_preserves_real_pay_location_and_application(self):
        packet=build_digest([self.job()])
        note=packet['substack_notes'][0]['text']
        self.assertIn('$20/hour',note); self.assertIn('Africa eligible',note)
        self.assertIn('https://example.com/jobs/1',note)
        self.assertNotIn('Source:',note)
        self.assertLessEqual(x_weight(packet['x_posts'][0]['text']),280)
    def test_holds_undated_stale_protected_and_unknown_jobs(self):
        for job in [self.job(published_at=None),self.job(published_at=datetime.now(timezone.utc)-timedelta(days=8)), self.job(link_status='protected'),self.job(remote_scope='unknown')]:
            self.assertFalse(build_digest([job])['x_posts'])
    def test_regional_job_never_claims_africa_eligibility(self):
        packet=build_digest([self.job(location='US only',remote_scope='us',africa_eligible=False, salary='')])
        self.assertNotIn('Africa eligible',packet['substack_notes'][0]['text'])
        self.assertIn('US only',packet['substack_notes'][0]['text'])
        self.assertIn('Pay not disclosed',packet['substack_notes'][0]['text'])

    def test_editorial_pay_angle_uses_actual_shortlist(self):
        jobs=[self.job(salary=''),self.job(salary='$20/hour')]
        openings={editorial_opening(jobs,datetime(2026,1,day,tzinfo=timezone.utc)) for day in range(1,29)}
        self.assertTrue(any('1 of the 2 listings' in value for value in openings))
        self.assertFalse(any('not classified as worldwide' in value for value in openings))
