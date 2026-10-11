import unittest
from unittest.mock import patch
from publishers.telegram_draft import deliver

class PrivateDraftTests(unittest.TestCase):
    def test_channel_and_group_cannot_receive_draft(self):
        for chat_type in ('channel','group','supergroup'):
            with patch('publishers.telegram_draft.call', return_value={'id':123,'type':chat_type}) as call:
                with self.assertRaises(ValueError): deliver('token','123','draft',{})
                self.assertEqual(call.call_count,1)
        with self.assertRaises(ValueError): deliver('token','-100123','draft',{})

    def test_successful_delivery_is_deduplicated(self):
        with patch('publishers.telegram_draft.call', side_effect=[{'id':123,'type':'private'}, {'message_id':5}]) as call:
            state=deliver('token','123','draft',{})
            self.assertEqual(call.call_args.args[1],'sendDocument')
        with patch('publishers.telegram_draft.call', return_value={'id':123,'type':'private'}) as call:
            self.assertEqual(deliver('token','123','draft',state),state)
            self.assertEqual(call.call_count,1)

    def test_wrong_person_cannot_receive_draft(self):
        with patch('publishers.telegram_draft.call',return_value={'id':999,'type':'private'}):
            with self.assertRaises(ValueError): deliver('token','123','draft',{})
