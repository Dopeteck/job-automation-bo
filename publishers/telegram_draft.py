"""Deliver the newsletter file only to an explicitly configured private chat."""
import hashlib
import json
import os
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1] / 'data/editorial'

def call(token, method, **kwargs):
    try:
        response = requests.post(f'https://api.telegram.org/bot{token}/{method}', timeout=45, **kwargs)
        payload = response.json()
    except (requests.RequestException, ValueError):
        raise RuntimeError('Telegram draft request failed; check connectivity and configuration.') from None
    if not payload.get('ok'):
        raise RuntimeError('Telegram rejected draft delivery; check bot credentials and start its private chat.')
    return payload['result']

def deliver(token, chat_id, text, state):
    if not str(chat_id).isdigit() or int(chat_id) <= 0:
        raise ValueError('Draft destination must be a positive personal chat ID.')
    chat = call(token, 'getChat', json={'chat_id': chat_id})
    if chat.get('type') != 'private' or str(chat.get('id')) != str(chat_id):
        raise ValueError('Refusing draft delivery: destination is not the configured private chat.')
    digest = hashlib.sha256((str(chat_id)+'\n'+text).encode()).hexdigest()
    if state.get('digest') == digest:
        return state
    result = call(token, 'sendDocument', data={
        'chat_id': chat_id,
        'caption': (('Newsletter held: true STORY NOTES are missing or incomplete. The review file includes all holds and PASS/FAIL checks.' if 'STORY NEEDED' in text else 'Newsletter held by the editorial checks. Open the review file for missing inputs, held roles and PASS/FAIL results.') if 'Nothing queued.' in text else 'Your newsletter draft is ready. Open the text file, review the roles and paste into Substack → New post. This delivery does not publish the newsletter.'),
    }, files={'document': ('remote-jobs-editorial-review.txt' if 'Nothing queued.' in text else 'remote-jobs-newsletter.txt', text.encode(), 'text/plain; charset=utf-8')})
    return {'digest': digest, 'message_id': result['message_id']}

def main():
    token = os.getenv('TELEGRAM_DRAFT_BOT_TOKEN', '').strip()
    chat_id = os.getenv('TELEGRAM_DRAFT_CHAT_ID', '').strip()
    if not token or not chat_id:
        print('::notice::Private draft delivery not configured. Add TELEGRAM_DRAFT_BOT_TOKEN and TELEGRAM_DRAFT_CHAT_ID repository secrets.')
        return
    text = (ROOT/'latest_digest.md').read_text()
    path = ROOT/'telegram_draft_state.json'
    state = json.loads(path.read_text()) if path.exists() else {}
    updated = deliver(token, chat_id, text, state)
    path.write_text(json.dumps(updated, indent=2)+'\n')
    # A successful personal draft delivery reserves its roles; hold notices do not.
    if 'Nothing queued.' not in text:
        import sys
        sys.path.insert(0,str(ROOT.parents[1]))
        from editorial.digest_sources import record_featured
        notes=json.loads((ROOT/'substack_notes_queue.json').read_text())
        from editorial.newsletter_story import record_story,load_json
        record_story(ROOT,load_json(ROOT/'story_context.json',None),review=os.getenv('DIGEST_REVIEW_MODE')=='true')
        from editorial.strict_newsletter import record_issue
        record_issue(ROOT,notes,review=os.getenv('DIGEST_REVIEW_MODE')=='true')
    print('Newsletter draft delivered privately.' if updated != state else 'Identical draft already delivered.')

if __name__ == '__main__':
    main()
