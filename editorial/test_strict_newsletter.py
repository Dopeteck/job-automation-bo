import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from editorial.strict_newsletter import build_issue,eligibility_basis,hold_reasons,why_line,role_entry,cleaned_title,experience,record_issue,story_from_notes,DUTIES_UNKNOWN
from editorial.quality_jobs.models import Job

class StrictTests(unittest.TestCase):
    def job(self,i=0,**change):
        titles=['Junior Support Agent','Junior QA Tester','Junior Content Editor','Software Developer','Data Analyst','Design Assistant','Support Agent','Junior Administrator']
        lines=['Respond to customer tickets and resolve account questions.','Review software bugs and test fixes before deployment.','Review articles and edit content for clarity.','Develop software integrations and maintain application systems.','Analyze business data and review reporting accuracy.','Create visual layouts and design website interfaces.','Answer customer emails and resolve billing questions.','Manage administrative records and maintain document trackers.']
        j=Job(source='Himalayas',title=titles[i%8],company=f'Company {i}',location='Worldwide',direct_url=f'https://example.com/job/{i}',description='Candidates can apply from anywhere in the world. Responsibilities: '+lines[i%8]+' Requirements: '+('1 year of experience.' if i<3 else '3 years of experience.'),salary='USD 20-30/hour',employment_type='Full-time',published_at=datetime.now(timezone.utc),link_status='200',active_status='active',fingerprint=f'role{i}',africa_eligible=True,remote_scope='worldwide',evidence_lines=[lines[i%8]])
        for k,v in change.items():setattr(j,k,v)
        return j
    def notes(self):
        # Synthetic author-supplied fixture; never used as production story notes.
        paragraphs=['I read the exact location line in a draft on my desk. I found a country restriction beside a worldwide tag while reading the full listing. I checked the application page and removed the role before sending the issue.',
          'I kept the wording from the listing in my notes so the location check could be reviewed. I compared that line with the tag rather than deciding from the word remote. I added a check that keeps a restricted vacancy out of the shortlist.',
          'I then looked at the experience requirement and the work described in the same posting. I kept those details together rather than taking a title from one place and a seniority label from another. I used the stricter requirement where they disagreed.',
          'I changed the draft after that check and kept a record of the removed role. You can make the same check before writing an application: open the employer page, find the work location and read the required experience. If a detail is unclear, ask about it before spending time on a work sample.',
          'I want the shortlist to help you choose a few suitable applications each week. Read the task line only after checking whether the employer can hire you where you live. Keep one genuine example of relevant work ready, and use it for a role whose stated requirements fit your experience.']
        paragraphs.append('I kept the check beside the listing so it could be repeated before the next issue. You can keep your own short record of the country line and the requirement you checked.')
        return {'id':'test-story','kind':'author','approved':True,'notes':'Author-supplied fixture matching the draft.','finder':'I found','how_found':'while reading the full listing','draft':'\n\n'.join(paragraphs),'lesson':'Check the employer’s location before preparing an application.','reply_prompt':'Which location line has stopped an application for you? Reply with the exact wording.'}
    def pool(self):return [self.job(i) for i in range(6)]
    def test_ready_format_and_checks(self):
        p=build_issue(self.pool(),story_notes=self.notes(),previous_issues=[])
        self.assertFalse(p['held'],p['checks']);self.assertTrue(all(p['checks'].values()))
        n=p['newsletter_markdown'];self.assertIn('6 remote roles worth checking this week, including 3 entry/junior roles.',n)
        self.assertIn('**The lesson:',n);self.assertEqual(n.count('Source credits:'),1)
        self.assertEqual(n.count('Contract type:'),6);self.assertIn('[Apply on Himalayas ->]',n)
    def test_source_tag_cannot_establish_eligibility(self):
        j=self.job(description='Responsibilities: Respond to customer tickets. Requirements: 1 year of experience.')
        self.assertFalse(eligibility_basis(j));self.assertTrue(any('Source tag only' in r for r in hold_reasons(j,datetime.now(timezone.utc),set())))
    def test_source_annotated_entry_is_not_employer_experience(self):
        j=self.job(title='Customer Support Agent',description='Candidates can apply worldwide. Responsibilities: Respond to customer tickets. Employer seniority: Entry-level role.')
        self.assertEqual(experience(j)[1],'Experience not stated');self.assertFalse(experience(j)[2])
    def test_country_city_timezone_and_hybrid_hold(self):
        for extra in ['Must be based in Singapore.','Remote in Tokyo.','Applicants must be residents.','Work in EST business hours.','This role is hybrid.','Security clearance is required.','Federal contractor.']:
            j=self.job(description=self.job().description+' '+extra)
            self.assertTrue(hold_reasons(j,datetime.now(timezone.utc),set()),extra)
    def test_pay_anomalies(self):
        for salary in ['USD 30-100/hour','USD 41/hour','PHP 40000-50000/month','USD 100-401/month']:
            self.assertTrue(any('pay' in r.lower() or 'USD' in r or 'Non-USD' in r for r in hold_reasons(self.job(salary=salary),datetime.now(timezone.utc),set())),salary)
        self.assertIn('USD 20/hour',role_entry(self.job(salary='USD 20-20/hour')))
    def test_annual_intern_and_part_time_pay_hold(self):
        j=self.job(title='Junior Marketing Intern',salary='USD 20000-50000/year')
        self.assertTrue(any('Annual' in r for r in hold_reasons(j,datetime.now(timezone.utc),set())))
    def test_referral_recruiter_and_fees_hold(self):
        for j in [self.job(referral_url='https://example.com/ref'),self.job(title='Junior Recruiter'),self.job(description=self.job().description+' You must purchase equipment.')]:
            self.assertTrue(hold_reasons(j,datetime.now(timezone.utc),set()))
    def test_duties_are_scoped_and_paraphrased(self):
        j=self.job();line=why_line(j);self.assertTrue(line.startswith('You reply'));self.assertLess(len(line.split()),25);self.assertTrue(line.endswith('.'))
        j.evidence_lines=['Maintain regular communication with the remote team.'];j.description='Candidates can apply worldwide. Responsibilities: Maintain regular communication with the remote team.'
        self.assertEqual(why_line(j),DUTIES_UNKNOWN)
        j.evidence_lines=['Complete AI Interview.'];j.description='Candidates can apply worldwide. Application process: Complete AI Interview.'
        self.assertEqual(why_line(j),DUTIES_UNKNOWN)
    def test_wrong_duties_match_is_held(self):
        j=self.job(title='Video Content Moderator',description='Candidates can apply worldwide. Responsibilities: Create advertising trailers and website layouts.',evidence_lines=['Create advertising trailers and website layouts.'])
        self.assertTrue(any('do not match' in r for r in hold_reasons(j,datetime.now(timezone.utc),set())))
    def test_three_junior_and_six_roles_are_strict(self):
        p=build_issue(self.pool()[:5],story_notes=self.notes(),previous_issues=[]);self.assertTrue(p['held']);self.assertFalse(p['substack_notes']);self.assertIn('ISSUE HELD',p['newsletter_markdown'])
        p=build_issue([self.job(i,description=self.job(i).description.replace('1 year','3 years')) for i in range(6)],story_notes=self.notes(),previous_issues=[]);self.assertTrue(p['held'])
    def test_missing_story_and_history_stop_publication(self):
        p=build_issue(self.pool());self.assertTrue(p['held']);self.assertIn('STORY NEEDED',p['newsletter_markdown']);self.assertIn('PREVIOUS ISSUES',p['review_notes'])
        self.assertFalse(p['x_posts']);self.assertFalse(p['substack_notes'])
    def test_story_needs_real_author_approval(self):
        n=self.notes();n['approved']=False;story,confirms=story_from_notes(n,[]);self.assertIsNone(story);self.assertTrue(confirms)
        n=self.notes();n['draft']=n['draft'].replace('I found','Someone found');self.assertIsNone(story_from_notes(n,[])[0])
    def test_title_cleaning(self):
        self.assertEqual(cleaned_title('🌎 Software Engineer | Remote - Contract'),'Software Engineer')
        self.assertEqual(cleaned_title('QA TESTER - Contact'),'Qa Tester')
    def test_last_four_issues_only(self):
        history=[{'id':str(i),'fingerprints':['role0'] if i==0 else [],'urls':[]} for i in range(5)]
        p=build_issue(self.pool(),story_notes=self.notes(),previous_issues=history);self.assertFalse(p['held'])
        history[-1]['fingerprints']=['role0'];p=build_issue(self.pool(),story_notes=self.notes(),previous_issues=history);self.assertTrue(p['held']);self.assertIn('last four issues',p['review_notes'])
    def test_sort_unknown_last_and_senior_title_as_senior(self):
        unknown=self.job(title='Support Agent',description='Candidates can apply worldwide. Responsibilities: Respond to customer tickets.')
        senior=self.job(title='Senior Support Agent',description=unknown.description)
        self.assertGreater(experience(unknown)[0],experience(senior)[0])
    def test_company_and_category_limits(self):
        jobs=[self.job(i,title='Junior Support Agent',description='Candidates can apply worldwide. Responsibilities: Respond to customer ticket '+str(i)+'. Requirements: 1 year of experience.',evidence_lines=['Respond to customer ticket '+str(i)+'.']) for i in range(7)]
        p=build_issue(jobs,story_notes=self.notes(),previous_issues=[]);self.assertLessEqual(len(p['selected']),3)
    def test_review_does_not_consume_issue_history(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);note={'id':'issue','job_fingerprints':['a'],'job_urls':[]}
            record_issue(out,[note],review=True);self.assertFalse((out/'issue_history.json').exists())
            record_issue(out,[note]);record_issue(out,[note]);self.assertEqual(len(json.loads((out/'issue_history.json').read_text())),1)

    def test_worldwide_customers_are_not_candidate_eligibility(self):
        for text in ['We work with customers worldwide.', 'Our remote team serves clients worldwide.']:
            self.assertFalse(eligibility_basis(self.job(description=text)))
    def test_us_state_abbreviation_is_not_missed(self):
        self.assertTrue(hold_reasons(self.job(location='Remote - TX'),datetime.now(timezone.utc),set()))
    def test_unconfirmed_manual_history_holds_issue(self):
        p=build_issue(self.pool(),story_notes=self.notes(),previous_issues=[],history_complete=False)
        self.assertTrue(p['held']);self.assertIn('manually published issues',p['review_notes'])
