import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timezone
from editorial.newsletter_story import choose_story,approved_story,record_story,worked_example,data_story,ROOT
from editorial.jobs_digest import build_digest,role_evidence

class StoryTests(unittest.TestCase):
    def jobs(self):
        from editorial.test_jobs_digest import JobsDigestTests
        return JobsDigestTests().pool()
    def test_first_story_is_documented_builder_event(self):
        jobs=self.jobs();story=choose_story(jobs,role_evidence(jobs[0]))
        self.assertEqual(story['kind'],'builder');self.assertTrue(approved_story(story))
        self.assertIn('Datadog',story['body']);self.assertNotIn('Imagine',story['body'])
        self.assertTrue(200<=len(story['body'].split())<=300)
    def test_reader_needs_permission_and_evidence(self):
        row=json.loads((ROOT/'editorial/story_bank.json').read_text())[0]
        row=dict(row,kind='reader',id='reader1',publish_consent=False)
        self.assertFalse(approved_story(row));row['publish_consent']=True;self.assertTrue(approved_story(row))
        row['evidence_ref']='';self.assertFalse(approved_story(row))
    def test_opening_goes_before_roles_with_a_lesson_and_question(self):
        p=build_digest(self.jobs());body=p['newsletter_markdown']
        self.assertLess(body.index('On 11 October'),body.index('10 remote roles worth checking'))
        self.assertIn('**The lesson:**',body);self.assertIn('May we contact you',body)
        self.assertIn('story_context',p);self.assertNotIn('evidence_ref',body)
        self.assertNotIn('Picture an evening',body)
    def test_repeated_builder_is_not_selected_again(self):
        jobs=self.jobs();first=choose_story(jobs,role_evidence(jobs[0]))
        history={'used_ids':[first['id']],'last_kind':'builder'}
        second=choose_story(jobs,role_evidence(jobs[0]),history=history)
        self.assertEqual(second['kind'],'worked_example')
        history['last_kind']='worked_example'
        third=choose_story(jobs,role_evidence(jobs[0]),history=history)
        self.assertNotEqual(third['id'],first['id']);self.assertEqual(third['kind'],'builder')
    def test_data_uses_run_counts_without_fake_market_statistics(self):
        jobs=self.jobs();audit={'pool_unique':100,'geography_pass_unique':31,'verified_shortlist':12,'issue_juniors':4}
        story=data_story(audit,jobs,role_evidence(jobs[0]));self.assertIn('100 distinct listings',story['body']);self.assertIn('31 remained',story['body'])
        self.assertIn('not an estimate',story['body']);self.assertNotIn('31 fake jobs',story['body'])
        self.assertTrue(200<=len(story['body'].split())<=300)
    def test_worked_example_labels_samples_and_does_not_invent_a_reader(self):
        jobs=self.jobs();story=worked_example(jobs[0],role_evidence(jobs[0]))
        self.assertIn('worked application example',story['body']);self.assertIn('[real support reply]',story['body'])
        self.assertIn('not a quote from a reader',story['body']);self.assertIn('Do not claim',story['body'])
        self.assertTrue(200<=len(story['body'].split())<=300)
    def test_review_and_hold_do_not_consume_story(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d);story={'id':'event','kind':'builder'}
            record_story(out,story,review=True);record_story(out,None);self.assertFalse((out/'story_history.json').exists())
            record_story(out,story);state=json.loads((out/'story_history.json').read_text())
            self.assertEqual(state['used_ids'],['event']);self.assertEqual(state['last_kind'],'builder')
    def test_hold_produces_no_story(self):
        p=build_digest(self.jobs()[:2]);self.assertTrue(p['held']);self.assertNotIn('story_context',p)
