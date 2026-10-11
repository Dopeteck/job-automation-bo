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
    def test_below_six_is_held_not_padded(self):
        packet=build_digest(self.pool()[:5]);self.assertFalse(packet['x_posts']);self.assertFalse(packet['substack_notes']);self.assertTrue(packet['held'])
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

    def test_feed_worldwide_tag_cannot_override_job_country(self):
        for text in ['Fully remote in the UK.', 'This is a remote role in the US.', 'Headquarters: India (remote).', 'Headquarters: Argentina, Remote.', 'Virginia, USA, Remote As an Enterprise Sales Engineer.', 'Headquarters: Berlin, Germany; Remote, Germany.', 'Most roles are done from anywhere within the country of employment.']:
            with self.subTest(text=text):
                self.assertFalse(eligible_for_digest(self.job(location='Anywhere in the World',description=text),datetime.now(timezone.utc)))
    def test_culture_copy_cannot_fill_job_reason(self):
        job=self.job(description='Our culture of flexibility means you will be recognized for your growth and impact.')
        self.assertFalse(select_digest_jobs([job],datetime.now(timezone.utc)))

    def test_named_country_and_multi_role_ads_are_not_fillers(self):
        self.assertFalse(eligible_for_digest(self.job(title='Account Executive (Kazakhstan)',location='Remote'),datetime.now(timezone.utc)))
        self.assertTrue(eligible_for_digest(self.job(title='Account Executive (Kazakhstan)'),datetime.now(timezone.utc)))
        self.assertFalse(eligible_for_digest(self.job(description='Currently we have multiple requests. You will build software.'),datetime.now(timezone.utc)))
    def test_senior_roles_cannot_dominate_digest(self):
        jobs=[self.job(i,title='Senior Software Engineer') for i in range(15)]
        self.assertLessEqual(len(select_digest_jobs(jobs,datetime.now(timezone.utc))),3)

    def test_three_juniors_are_required_and_sorted_first(self):
        jobs=self.pool()[:6]
        for job in jobs: job.experience_level='not_specified'
        self.assertTrue(build_digest(jobs)['held'])
        for job in jobs[:3]: job.title='Junior '+job.title;job.experience_level='entry'
        packet=build_digest(list(reversed(jobs)))
        self.assertTrue(packet['substack_notes'])
        selected=select_digest_jobs(jobs,datetime.now(timezone.utc))
        self.assertTrue(all(job.title.startswith('Junior') for job in selected[:3]))
        self.assertIn('Daily roles in the channel: https://t.me/RemoteJobsTechHub',packet['newsletter_markdown'])
        self.assertIn('6 roles open worldwide or in Africa',packet['newsletter_markdown'])
    def test_task_evidence_is_not_requirement_or_location_copy(self):
        from editorial.jobs_digest import role_evidence
        for description in ['Requirements: 4+ years of software development experience.', 'You will enjoy culture and flexibility while building software.']:
            self.assertFalse(role_evidence(self.job(description=description)))
        evidence=role_evidence(self.job(description='Responsibilities: You will manage support tickets and respond to customer questions.'))
        self.assertIn('manage support tickets',evidence)
        self.assertEqual(role_evidence(self.job(description='Virginia, USA, Remote You will build software for customers.')), 'You will build software for customers.')
        self.assertTrue(evidence.endswith('.'));self.assertNotIn('…',evidence)
    def test_stricter_experience_overrides_entry_tag(self):
        from editorial.jobs_digest import experience_info
        job=self.job(description='You will build workflow integrations. Requirements: 2 years experience and 5+ years of experience.')
        self.assertEqual(experience_info(job)[0],2)
        self.assertIn('5+ years',experience_info(job)[1])
    def test_state_security_and_work_authorization_restrictions(self):
        for text in ['Remote in Texas. You will build applications.', 'You must be located in Singapore.', 'US citizen required.', 'Security clearance required.', 'Authorized to work in Germany.', 'Federal government sales.']:
            self.assertFalse(eligible_for_digest(self.job(description=text),datetime.now(timezone.utc)))

    def test_lowercase_us_is_not_a_location(self):
        self.assertTrue(eligible_for_digest(self.job(description='Join our remote team. Help us build integrations for billing.'),datetime.now(timezone.utc)))
