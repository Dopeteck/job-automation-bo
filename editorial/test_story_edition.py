import unittest
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from editorial.story_edition import build_story_edition
from editorial.strict_newsletter import record_issue,story_from_notes

class StoryEditionTests(unittest.TestCase):
    def packet(self):
        from editorial.test_strict_newsletter import StrictTests
        notes=StrictTests().notes();story,_=story_from_notes(notes,[])
        held={'held':True,'review_notes':'FAIL - Six to ten roles','held_roles':[]}
        return notes,story,held
    def test_story_edition_is_independent_of_jobs_gate(self):
        notes,story,held=self.packet()
        packet=build_story_edition(story,notes,held,datetime.now(timezone.utc),'https://t.me/example')
        self.assertFalse(packet['held']);self.assertTrue(packet['jobs_held'])
        self.assertEqual(packet['edition_type'],'story');self.assertEqual(packet['selected'],[])
        self.assertNotIn('FAIL',packet['newsletter_markdown'])
        self.assertIn('FAIL - Six to ten roles',packet['review_notes'])
        self.assertEqual(packet['substack_notes'][0]['content_kind'],'story_edition')
    def test_unapproved_or_incomplete_story_cannot_bypass_hold(self):
        notes,story,held=self.packet();notes['approved']=False
        self.assertIs(build_story_edition(story,notes,held,datetime.now(timezone.utc),'url'),held)
        notes['approved']=True;story['body']='[CONFIRM: outcome]'
        self.assertIs(build_story_edition(story,notes,held,datetime.now(timezone.utc),'url'),held)
    def test_story_does_not_consume_job_issue_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);record_issue(root,[{'id':'story','content_kind':'story_edition'}])
            self.assertFalse((root/'issue_history.json').exists())

if __name__=='__main__':unittest.main()
