"""Fictional reviewed domain data; no model assessments embedded in facts."""
from kb.schema import atom, assertion


def records():
    rows=[]
    def add(predicate,*args,source=None):
        rows.append({'source':source or f'Reviewed demo declaration: {predicate}({", ".join(args)})',
                     'assertion':assertion(atom(predicate,*args))})
    add('person_profile','person:alice','profile:alice',source='Alice built Python pipelines for cleaning, joining, and validating research datasets.')
    add('person_profile','person:bob','profile:bob',source='Bob implemented Python data-processing pipelines and automated dataset quality checks.')
    add('person_profile','person:carol','profile:carol',source='Carol is interested in research and enjoys helping teams.')
    add('available','person:alice','period:october')
    add('unavailable','person:bob','period:october')
    add('available','person:carol','period:october')
    for t in ('preprocess','baseline','validate'):
        add('task','task:'+t)
        add('task_status','task:'+t,'status:pending')
        add('task_spec_complete','task:'+t)
    add('requires_skill','task:preprocess','skill:python')
    add('requires_resource','task:preprocess','dataset:d')
    add('requires_skill','task:baseline','skill:python')
    add('depends_on','task:baseline','task:preprocess')
    add('requires_resource','task:baseline','resource:compute')
    add('requires_skill','task:validate','skill:statistical_validation')
    add('depends_on','task:validate','task:baseline')
    add('milestone_requires','milestone:evaluation_complete','task:validate')
    add('resource_status','dataset:d','status:unavailable')
    add('resource_status','resource:compute','status:available')
    add('assigned_to','task:preprocess','person:bob')
    # An independent task shows work that can proceed while access is blocked.
    add('task','task:document_protocol')
    add('task_status','task:document_protocol','status:pending')
    add('requires_skill','task:document_protocol','skill:python')
    add('task_spec_complete','task:document_protocol',source='Document protocol has a complete specification: Python is its only required skill, and it has no prerequisite tasks or resources.')
    return rows


def mock_definition():
    import json
    from pathlib import Path
    definition=json.loads((Path(__file__).parents[1]/'config/has_skill.json').read_text())
    definition['backend']={'kind':'counting_mock','version':'research-demo-v1','answers':{
        'person:alice|skill:python':'supported',
        'person:bob|skill:python':'supported',
        'person:carol|skill:python':'insufficient_evidence',
        'person:alice|skill:statistical_validation':'insufficient_evidence'}}
    return definition
