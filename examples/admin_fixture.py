"""Fictional manually reviewed extraction and decision fixtures, not model evaluation."""
from kb.admin_schema import empty
from kb.domains.admin import SEMANTICS
REQUEST='request:alex_appointment'
TEXTS={
 'original':'Please appoint Alex Example from November 1 through December 31, 2026, funded by FUND-A. Submitted October 12, 2026 to the fictional Appointments Office. My follow-up date is October 20, 2026 and my intervention date is October 25, 2026.',
 'ack':'Received, we’ll take care of it.',
 'claim':'All set.',
 'wrong':'Appointment confirmation: Alex Example, 2026-11-01 through 2026-12-31, funding account FUND-B.',
 'correct':'Corrected appointment confirmation: Alex Example, 2026-11-01 through 2026-12-31, funding account FUND-A.',
 'ambiguous':'All set for that request.',
 'date':'Please follow up on 11/12.'}


def extraction(which):
    result=empty(REQUEST)
    if which=='original':
        result['desired_outcome']='Appoint Alex Example for November–December 2026 using FUND-A.'
        result['responsible']='Fictional Appointments Office'
        result['expected']=[{'name':k,'value':v} for k,v in {'person':'Alex Example','start_date':'2026-11-01','end_date':'2026-12-31','funding_account':'FUND-A'}.items()]
        result['dates']=[{'role':k,'value':v,'basis':b} for k,v,b in [('submission','2026-10-12','documented'),('follow_up','2026-10-20','user_preference'),('intervention','2026-10-25','user_preference')]]
    if which in {'wrong','correct'}:
        result['observed']=[{'name':k,'value':v} for k,v in {'person':'Alex Example','start_date':'2026-11-01','end_date':'2026-12-31','funding_account':'FUND-B' if which=='wrong' else 'FUND-A'}.items()]
        result['documents']=['appointment_confirmation']
    if which=='ambiguous':result.update(status='clarify',request_id='',explanation='Which request does this refer to?')
    if which=='date':result.update(status='clarify',explanation='Does 11/12 mean November 12 or December 11, and which year?')
    return result


def backend():
    fixtures={}
    for label,text in TEXTS.items():
        for name in SEMANTICS:
            supported=(name=='message_acknowledges' and label=='ack' or
                       name=='message_promises' and label=='ack' or
                       name=='message_claims_completion' and label in {'claim','wrong','correct'} or
                       name=='evidence_addresses' and label in {'wrong','correct'})
            fixtures[name+'|'+text]='supported' if supported else 'contradicted'
    return {'kind':'counting_mock','version':'fictional-admin-v1','fixtures':fixtures}
