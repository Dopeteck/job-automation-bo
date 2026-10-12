"""A story edition remains available when the separate jobs digest is held."""
import hashlib
import unicodedata

def build_story_edition(story,notes,jobs_packet,now,telegram_url):
    title=notes.get('title') or 'What building something taught me about finding paid work'
    body=story['body']
    newsletter='# '+title+'\n\n'+body+'\n\n**The lesson: '+story['lesson']+'**\n\n'+story['question']+'\n\nDaily remote roles: '+telegram_url
    checks={'Story approved by author':notes.get('approved') is True,
            'Opening is 250–350 words':250<=len(body.split())<=350,
            'Title under 70 characters':len(title)<70,
            'No unresolved confirmations':'[CONFIRM:' not in newsletter,
            'No emojis':not any(unicodedata.category(c)=='So' for c in newsletter),
            'No held jobs included':'\nApply: ' not in newsletter}
    if not all(checks.values()):return jobs_packet
    identifier=hashlib.sha256(newsletter.encode()).hexdigest()[:20]
    review=('REVIEW NOTES\n\nStandalone story edition. The jobs digest remains held; none of its listings are included.\n\n'
            +'\n'.join('PASS - '+name for name in checks)+'\n\nJOBS DIGEST REVIEW\n'+jobs_packet['review_notes'])
    return {'held':False,'jobs_held':True,'edition_type':'story','newsletter_markdown':newsletter,
        'review_notes':review,'checks':checks,'selected':[],'held_roles':jobs_packet['held_roles'],
        'story_context':{'id':story['id'],'kind':story['kind']},'x_posts':[],
        'substack_notes':[{'id':'story-note-'+identifier,'source_id':identifier,'content_kind':'story_edition',
            'text':newsletter,'source_published_at':now.isoformat(),'job_fingerprints':[],'job_urls':[]}]}
