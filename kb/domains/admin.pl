% Trusted administrative attention policy v1, calendar dates supplied as ordinals.
% wf(Request,AsOf,Deadline,Intervention,FollowUp,Snooze,Stale,Done,Discrepancies,Missing).
flag(R,0,overdue,'admin:overdue_v1') :- wf(R,A,D,_,_,_,_,false,_,_),D>0,A>D.
flag(R,1,intervention_reached,'admin:intervention_v1') :- wf(R,A,_,I,_,_,_,false,_,_),I>0,A>=I.
flag(R,2,discrepancy,'admin:discrepancy_v1') :- wf(R,_,_,_,_,_,_,_,N,_),N>0.
flag(R,3,known_missing_prerequisite,'admin:missing_v1') :- wf(R,_,_,_,_,_,_,_,_,N),N>0.
flag(R,4,follow_up_due,'admin:followup_v1') :- wf(R,A,_,_,F,S,_,false,_,_),F>0,A>=F,(S=0->true;A>=S).
flag(R,5,stale,'admin:stale_v1') :- wf(R,A,_,_,_,S,T,false,_,_),T>0,A>=T,(S=0->true;A>=S).
flag(R,6,verification_outstanding,'admin:claim_unverified_v1') :- claim(R),wf(R,_,_,_,_,S,_,false,0,_),wf(R,A,_,_,_,_,_,_,_,_),(S=0->true;A>=S).
flag(R,2,unresolved_dependency,'admin:dependency_v1') :- unresolved_dependency(R).

flag(R,3,information_requested,'admin:information_requested_v1') :- info_requested(R),wf(R,_,_,_,_,_,_,false,_,_).

flag(R,2,promise_overdue,'admin:promise_overdue_v1') :- promised_for(R,D), wf(R,A,_,_,_,_,_,false,_,_), A>D.
