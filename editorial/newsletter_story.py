"""Newsletter openings grounded in recorded events, measured runs or worked examples."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def load_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def approved_story(row):
    return (row.get('approved') is True and row.get('kind') in {'builder','reader'}
            and bool(row.get('evidence_ref')) and 200<=len(row.get('body','').split())<=300
            and bool(row.get('lesson')) and bool(row.get('question'))
            and (row.get('kind')!='reader' or row.get('publish_consent') is True))


def worked_example(job, task):
    title,company=job.title,job.company
    lower=title.lower()
    if any(x in lower for x in ('qa','tester','testing')):
        after='I’ve attached [your genuine bug report]: reproduction steps, expected behaviour, actual behaviour and evidence. I also checked [what you really retested].'
    elif any(x in lower for x in ('data','annotat','moderator')):
        after='My attached [real annotation or review sample] includes the decisions, the rule used for each decision and [one genuine ambiguous case].'
    elif any(x in lower for x in ('support','customer')):
        after='My attached [real support reply] explains the next step in plain English, checks [the issue you actually checked], and shows when I would escalate.'
    elif any(x in lower for x in ('content','marketing','social','editor')):
        after='I’ve attached [a real content sample], with its intended audience, its purpose and [one change you made and why].'
    elif any(x in lower for x in ('engineer','developer','software')):
        after='I built [real project or feature] with [tools you actually used]. Here is [your repository or demo], and one bug I diagnosed and fixed: [real example].'
    else:
        after='I’ve attached [a genuine work sample] showing [how you carried out a relevant task], including [a verifiable result or decision].'
    body=(f'Here is a worked application example using a real vacancy in this issue: {title} at {company}. The useful starting point is a duty from the listing: “{task}”\n\n'
          'That line gives you something concrete to answer. A general introduction about motivation leaves the recruiter to guess whether you can do the work. A relevant sample makes the connection visible. You can use a personal project or a practice exercise if you describe it honestly; it does not have to be paid experience.\n\n'
          'Before — a generic template, not a quote from a reader:\n“I am passionate about this opportunity and would love to join your team.”\n\n'
          f'After — an example to complete with your own evidence:\n“{after}”\n\n'
          'Keep the brackets until you have something true to put in each one. If you have no suitable sample, create a small practice example around the advertised task and label it as practice. Do not claim a client, an employer, a result or a skill you cannot demonstrate.\n\n'
          'The next step is to check the employer’s application instructions and experience requirements. A better opening can show your fit, but it cannot remove a required qualification. Before sending, open your sample as a stranger would: does it work, is your contribution clear, and can someone see the relevant decision without searching through everything?')
    return {'id':'worked-'+hashlib.sha256((job.fingerprint+task).encode()).hexdigest()[:16], 'kind':'worked_example',
            'body':body,'lesson':'Lead with one relevant, genuine piece of evidence for the task the employer names.',
            'question':f'For the {title} role, what genuine sample could you show? Reply with the task and the sample you would use.'}


def data_story(audit, jobs, task):
    count,geo,verified=(audit['pool_unique'],audit['geography_pass_unique'],audit['verified_shortlist'])
    junior=audit['issue_juniors'];size=len(jobs)
    body=(f'This issue began with {count} distinct listings in the rolling vacancy pool. After the eligibility and suitability checks, {geo} remained. The scoring and application-link stage produced a verified shortlist of {verified}; the issue below contains {size} roles, including {junior} entry or junior roles. These are counts from this run, not an estimate of the whole remote-job market.\n\n'
          'The difference between those numbers matters. A listing can be real and useful to someone, yet still be wrong for this newsletter. A location restriction takes it out of our pool. An expired page, unclear eligibility or a duty line that only describes the company can also keep it out of the issue. Those are different checks, so the difference between the pool and the final list should not be read as a count of fake jobs.\n\n'
          'The smaller shortlist also changes how to use the newsletter. Instead of treating every role as another application to send, compare the experience requirement with something you can actually demonstrate. Start with the junior roles, then look at the work itself.\n\n'
          f'For example, one selected listing asks for this: “{task}” That is a better starting point for an application than the word “remote”. Pick a sample or a real example that addresses the task, then check working hours, country eligibility and the pay arrangement.\n\n'
          'There is a limit to what the count tells us. It measures this source pool and this set of filters. It does not tell us how many applicants will get interviews, and it does not turn an unknown experience requirement into a beginner-friendly role.')
    return {'id':'data-'+hashlib.sha256((json.dumps(audit,sort_keys=True)+jobs[0].fingerprint+task).encode()).hexdigest()[:16],'kind':'data',
            'body':body,'lesson':'Use the shortlist to choose a few suitable applications; the listing count is not a measure of your chances.',
            'question':'Which is stopping you most often: country restrictions, experience requirements, or finding a work sample? Reply with one real example.'}


def choose_story(jobs,task,history=None,audit=None,bank=None):
    history=history or {};used=set(history.get('used_ids',[]))
    bank=bank if bank is not None else load_json(ROOT/'editorial/story_bank.json',[])
    available=[row for row in bank if approved_story(row) and row['id'] not in used]
    readers=[r for r in available if r['kind']=='reader']
    builders=[r for r in available if r['kind']=='builder']
    last=history.get('last_kind')
    if readers:story=readers[0]
    elif builders and last not in {'builder','reader'}:story=builders[0]
    elif audit and last!='data' and data_story(audit,jobs,task)['id'] not in used:story=data_story(audit,jobs,task)
    else:story=worked_example(jobs[0],task)
    return dict(story)


def render_story(story):
    return story['body']+'\n\n**The lesson:** '+story['lesson']


def record_story(out,story,review=False):
    if review or not story:return
    path=out/'story_history.json';state=load_json(path,{})
    state['used_ids']=sorted(set(state.get('used_ids',[]))|{story['id']})
    state['last_kind']=story['kind']
    path.write_text(json.dumps(state,indent=2)+'\n')
