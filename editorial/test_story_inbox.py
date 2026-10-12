import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from editorial.story_inbox import (WorkshopError, read_state, save_state, seed_history,
    validate_draft, sentences, handle, poll, selected_notes, next_history, seal_review, restore_review, inventory, send_reply)

class StoryInboxTests(unittest.TestCase):
    def state(self):
        return {'offset':0,'drafts':{},'history':[],'used_history':[],'selected':None}
    def packet(self):
        from editorial.test_strict_newsletter import StrictTests
        # Synthetic fixture, not an author's actual experience.
        n=StrictTests().notes();body=n['draft']
        return {'title':'A synthetic test story','draft':body,'lesson':n['lesson'],
            'reply_prompt':n['reply_prompt'],'suggestions':['Check your actual outcome.'],
            'opinions':[],'confirmations':[],
            'provenance':[{'sentence':s,'kind':'fact','basis':s} for s in sentences(body)]}
    def test_encrypted_roundtrip_and_wrong_key(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'state.enc';s=self.state();s['history']=[{'notes':'PRIVATE test text'}]
            save_state(p,'test-token',s)
            self.assertNotIn(b'PRIVATE',p.read_bytes());self.assertEqual(s,read_state(p,'test-token'))
            with self.assertRaises(WorkshopError):read_state(p,'other-token')
    def test_seed_only_once(self):
        s=self.state();seed=json.dumps({'history':[{'id':'h1','notes':'A supplied past event.'}]})
        seed_history(s,seed);seed_history(s,seed);self.assertEqual(len(s['history']),1)
    def test_approved_seed_replaces_unreviewed_history_version(self):
        from editorial.test_strict_newsletter import StrictTests
        n=StrictTests().notes();n['history_id']='h1';s=self.state()
        s['drafts']['old']={'id':'old','approved':False,'history_id':'h1','packet':{},'errors':[]}
        seed_history(s,json.dumps({'history':[{'id':'h1','notes':'True historical notes.'}],'approved_drafts':[n]}))
        self.assertTrue(s['drafts']['old']['archived'])
        self.assertEqual(inventory(s)['approved_ready_drafts'],1)
        seed_history(s,json.dumps({'history':[{'id':'h1','notes':'True historical notes.'}],'approved_drafts':[n]}))
        self.assertEqual(inventory(s)['approved_ready_drafts'],1)
    def test_unsupported_number_quote_and_missing_provenance(self):
        p=self.packet();notes=p['draft'];self.assertEqual(validate_draft(p,notes),[])
        p['draft']+='\n\nI earned 9999 dollars.'
        self.assertTrue(any('number' in e for e in validate_draft(p,notes)))
        p=self.packet();p['draft']+='\n\n“An invented quotation.”'
        self.assertTrue(any('quotation' in e for e in validate_draft(p,notes)))
        p=self.packet();p['provenance']=[]
        self.assertTrue(any('sentence' in e for e in validate_draft(p,p['draft'])))
    def test_action_cannot_be_classified_as_opinion(self):
        p=self.packet();p['provenance'].append({'sentence':'I earned money.','kind':'opinion'})
        self.assertTrue(any('first-person' in e for e in validate_draft(p,p['draft'])))
    def test_approval_and_revision(self):
        s=self.state();p=self.packet();notes=p['draft']
        handle(s,'/story '+notes,lambda *a,**k:p);identifier=next(iter(s['drafts']))
        self.assertIn('not been published',handle(s,'/approve '+identifier))
        self.assertEqual(s['selected'],identifier)
        handle(s,'/revise '+identifier+' A true correction.',lambda *a,**k:p)
        self.assertFalse(s['drafts'][identifier]['approved']);self.assertIsNone(s['selected'])
    def test_missing_facts_cannot_be_approved(self):
        s=self.state();p=self.packet();p['confirmations']=['What happened next?']
        handle(s,'/story '+p['draft'],lambda *a,**k:p)
        identifier=next(iter(s['drafts']));self.assertIn('needs context',handle(s,'/approve '+identifier))
    def test_quota_saves_notes_and_retry(self):
        s=self.state();p=self.packet()
        def quota(*a,**k):raise WorkshopError('Quota exhausted.')
        handle(s,'/story '+p['draft'],quota);identifier=next(iter(s['drafts']))
        self.assertEqual(s['drafts'][identifier]['notes'],p['draft'])
        handle(s,'/revise '+identifier,lambda *a,**k:p)
        self.assertFalse(s['drafts'][identifier]['errors'])
    def test_history_does_not_repeat(self):
        s=self.state();p=self.packet();s['history']=[{'id':'h1','notes':p['draft']}]
        self.assertIn('EDITORIAL REVIEW',next_history(s,lambda *a,**k:p))
        self.assertIn('No unused history',next_history(s,lambda *a,**k:p))
    def test_selected_notes_exclude_consumed_story(self):
        s=self.state();p=self.packet();handle(s,'/story '+p['draft'],lambda *a,**k:p)
        identifier=next(iter(s['drafts']));handle(s,'/approve '+identifier)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'state.enc';save_state(path,'token',s)
            with patch('editorial.story_inbox.STATE_PATH',path):
                n=selected_notes('token',[]);self.assertTrue(n['approved'])
                self.assertIsNone(selected_notes('token',[n['id']]))
    def test_poll_accepts_only_owner_private_messages(self):
        s=self.state();updates=[{'update_id':1,'message':{'chat':{'type':'group','id':-1},'from':{'id':123},'text':'private input'}},
            {'update_id':2,'message':{'chat':{'type':'private','id':456},'from':{'id':456},'text':'private input'}},
            {'update_id':3,'message':{'chat':{'type':'private','id':123},'from':{'id':123},'text':'/help'}}]
        def api(token,method,**kwargs):
            return {'type':'private','id':123} if method=='getChat' else {} if method=='getWebhookInfo' else updates
        replies=[]
        with patch('editorial.story_inbox.call',api):self.assertEqual(poll('token','123',s,replies.append),1)
        self.assertEqual(s['offset'],4);self.assertEqual(len(replies),1)
    def test_existing_webhook_is_left_untouched(self):
        def api(token,method,**kwargs):return {'type':'private','id':123} if method=='getChat' else {'url':'https://existing.example'}
        with patch('editorial.story_inbox.call',api):
            with self.assertRaises(WorkshopError):poll('token','123',self.state(),lambda t:None)
    def test_multiline_command_and_skip(self):
        s=self.state();p=self.packet();handle(s,'/story\n'+p['draft'],lambda *a,**k:p)
        identifier=next(iter(s['drafts']))
        handle(s,'/skip '+identifier);self.assertTrue(s['drafts'][identifier]['archived'])
        self.assertFalse(s['drafts'][identifier]['approved'])
    def test_editorial_archive_has_only_ciphertext(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=root/'data/editorial';data.mkdir(parents=True)
            (data/'latest_digest.md').write_text('PRIVATE AUTHOR STORY')
            review=root/'data/review.enc'
            with patch('editorial.story_inbox.ROOT',root),patch('editorial.story_inbox.REVIEW_PATH',review):
                seal_review('test-token');self.assertNotIn(b'PRIVATE AUTHOR STORY',review.read_bytes())
                (data/'latest_digest.md').write_text('old')
                restore_review('test-token');self.assertEqual((data/'latest_digest.md').read_text(),'PRIVATE AUTHOR STORY')
    def test_status_is_a_chat_message_but_story_is_a_document(self):
        s=self.state();reply=handle(s,'/status')
        self.assertIn('Approved stories ready: 0',reply)
        self.assertIn('Unused experiences to turn into stories: 0',reply)
        with patch('editorial.story_inbox.call',return_value={'message_id':1}) as api:
            send_reply('test-token','123',reply)
            self.assertEqual(api.call_args.args[1],'sendMessage')
            self.assertEqual(api.call_args.kwargs['json']['text'],reply)
            send_reply('test-token','123','Story text\nEDITORIAL REVIEW\nID: test')
            self.assertEqual(api.call_args.args[1],'sendDocument')

if __name__=='__main__':unittest.main()
