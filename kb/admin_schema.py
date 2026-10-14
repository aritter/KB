"""Administrative extraction schema; dates and exact values stay lossless strings."""
from copy import deepcopy
from .schema import obj, array
TEXT={'type':'string','maxLength':4000}
FIELD=obj({'name':{'type':'string','maxLength':80},'value':TEXT})
DATE=obj({'role':{'enum':['submission','deadline','follow_up','intervention','lead_days','promised_for']},
          'value':{'type':'string','maxLength':80},'basis':{'enum':['documented','user_preference','tentative']}})
# Keep the decoder shape simple; extracted_events validates calendar dates and
# the role/value pairing (lead_days must be an integer, other roles ISO dates).
DECODE_DATE=obj({'role':{'enum':['submission','deadline','follow_up','intervention','lead_days','promised_for']},
                 'value':{'type':'string','pattern':r'(\d{4}-\d{2}-\d{2}|\d{1,4})','minLength':1,'maxLength':10},
                 'basis':{'enum':['documented','user_preference','tentative']}})
EXTRACTION=obj({
 'status':{'enum':['ok','clarify','unsupported']},'explanation':TEXT,
 'request_id':{'type':'string','maxLength':100},
 'desired_outcome':TEXT,'responsible':TEXT,
 'expected':array(FIELD,0,16),'observed':array(FIELD,0,16),'dates':array(DATE,0,8),
 'documents':array({'type':'string','maxLength':80},0,16),
 'absent_documents':array({'type':'string','maxLength':80},0,16),
 'dependencies':array({'type':'string','maxLength':100},0,16)
})


def extraction_schema(template=None, *, kind='message'):
    """Constrain decoding to a selected template without mutating the base schema."""
    schema = deepcopy(EXTRACTION)
    schema['properties']['dates']['items'] = deepcopy(DECODE_DATE)
    if kind == 'confirmation':
        schema['properties']['expected']['maxItems'] = 0
        schema['properties']['desired_outcome'] = {'type': 'string', 'const': '', 'maxLength': 0}
    if template is None:
        return schema
    for section in ('expected', 'observed'):
        field_names = sorted(template['fields'])
        item = schema['properties'][section]
        if field_names:
            item['items']['properties']['name'] = {'enum': field_names}
        else:
            item['maxItems'] = 0
    for section in ('documents', 'absent_documents'):
        names = sorted(template['required_documents'])
        item = schema['properties'][section]
        if names:
            item['items'] = {'enum': names}
        else:
            item['maxItems'] = 0
    return schema


def empty(request_id='',**values):
    return dict(status='ok',explanation='',request_id=request_id,desired_outcome='',responsible='',
                expected=[],observed=[],dates=[],documents=[],absent_documents=[],dependencies=[],**values)
