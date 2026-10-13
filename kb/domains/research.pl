:- discontiguous coord/5.
% Trusted coordination rules v1. User/model terms remain data in rule/3.
% f/2 holds the positive symbolic closure, never semantic assessments.
f(T,Ids) :- known(T,Ids).
flat(Xs, Ys) :- append(Xs, Z), sort(Z,Ys).
people(P) :- distinct(P,(f(person_profile(P,_),_);f(available(P,_),_);f(unavailable(P,_),_);f(assigned_to(_,P),_);f(has_skill(P,_),_);f(lacks_skill(P,_),_))).
periods(P) :- distinct(P,(f(available(_,P),_);f(unavailable(_,P),_))).
skills(S) :- distinct(S,(f(requires_skill(_,S),_);f(has_skill(_,S),_);f(lacks_skill(_,S),_))).
state(task,T,State,Proof) :- findall(S-I,f(task_status(T,S),I),Pairs), state_pairs(Pairs,State,Proof).
state(resource,T,State,Proof) :- findall(S-I,f(resource_status(T,S),I),Pairs), state_pairs(Pairs,State,Proof).
state_pairs(Pairs,State,Proof) :- findall(S,member(S-_,Pairs),Ss),sort(Ss,Unique),
    findall(I,member(_-I,Pairs),Is),flat(Is,Proof),
    (Unique=[] -> State=unknown ; Unique=[One] -> State=One ; State=conflict).
availability(P,Period,State,Proof) :-
    findall(yes-I,f(available(P,Period),I),A), findall(no-I,f(unavailable(P,Period),I),B),
    append(A,B,C),state_pairs(C,State,Proof).

% Ground guarded graph traversal; visited nodes stop cycles, depth is global input.
reach(T,T,_,_,[]).
reach(T,D,Seen,Depth,Proof) :-
    (Depth=<0 -> throw(symbolic_depth_limit) ; true),
    f(depends_on(T,N),P), \+memberchk(N,Seen), D1 is Depth-1,
    reach(N,D,[N|Seen],D1,Q), append(P,Q,Proof).
cycle(T,Seen,Depth,Proof) :-
    (Depth=<0 -> throw(symbolic_depth_limit) ; true), f(depends_on(T,N),P),
    (memberchk(N,Seen) -> Proof=P ; D1 is Depth-1,cycle(N,[N|Seen],D1,Q),append(P,Q,Proof)).

% Explicit completeness guards the closed-world check. Missing status is a reason.
block(T,T,'reason:incomplete_spec',[]) :- \+f(task_spec_complete(T),_).
block(T,D,Reason,Proof) :- f(depends_on(T,D),P),state(task,D,S,Q),S\='status:completed',
    (S=unknown -> Reason='reason:unknown_status';S=conflict -> Reason='reason:conflict';Reason='reason:unmet_task'),append(P,Q,Proof).
block(T,R,Reason,Proof) :- f(requires_resource(T,R),P),state(resource,R,S,Q),S\='status:available',
    (S=unknown -> Reason='reason:unknown_status';S=conflict -> Reason='reason:conflict';Reason='reason:unavailable_resource'),append(P,Q,Proof).
block(T,T,'reason:cycle',Proof) :- depth_bound(D),once(cycle(T,[T],D,Proof)).

coord(candidate(P,T,Period),Needs,Proof,State,Reasons) :-
    f(task(T),TaskProof), people(P), (var(Period)->periods(Period);true),
    availability(P,Period,A,AP),
    (A=no -> State=contradicted,Reasons=[unavailable],Needs=[],More=[]
    ; A\=yes -> State=insufficient_evidence,Reasons=[availability_unknown_or_conflicting],Needs=[],More=[]
    ; \+f(task_spec_complete(T),_) -> State=insufficient_evidence,Reasons=[incomplete_spec],Needs=[],More=[]
    ; State=supported,Reasons=[],f(task_spec_complete(T),CP),
      findall(S-I,f(requires_skill(T,S),I),Pairs), findall([P,S],member(S-_,Pairs),Ns),sort(Ns,Needs),
      findall(I,member(_-I,Pairs),Is),flat([CP|Is],More)),
    flat([TaskProof,AP,More, ['coord:candidate_all_skills_v1']],Proof).

coord(ready(T),[],Proof,State,Reasons) :-
    f(task(T),TP),state(task,T,S,SP), findall(R-I,block(T,_,R,I),Blocks),
    findall(R,member(R-_,Blocks),Rs), findall(I,member(_-I,Blocks),Is),
    (S='status:pending',Rs=[] -> State=supported,Reasons=[]
    ; (memberchk(S,['status:in_progress','status:completed']);member('reason:unmet_task',Rs);member('reason:unavailable_resource',Rs);member('reason:cycle',Rs))
      -> State=contradicted,Reasons=[S|Rs]
    ; State=insufficient_evidence,Reasons=[S|Rs]),
    findall(I,(f(depends_on(T,D),I);f(task_status(D,'status:completed'),I),f(depends_on(T,D),_);
               f(requires_resource(T,R),I);f(resource_status(R,'status:available'),I),f(requires_resource(T,R),_);
               f(task_spec_complete(T),I)),Satisfied),
    append(Is,Satisfied,All),flat([TP,SP,['coord:ready_v1']|All],Proof).

coord(blocked_by(T,D,R),[],Proof,supported,[]) :- f(task(T),TP),block(T,D,R,BP),flat([TP,BP,['coord:block_v1']],Proof).
coord(milestone_blocker(M,D,R),[],Proof,supported,[]) :-
    f(milestone_requires(M,T),MP),depth_bound(Depth),reach(T,N,[T],Depth,Path),block(N,D,R,BP),
    flat([MP,Path,BP,['coord:milestone_blocker_v1']],Proof).
coord(affected_milestone(M,R),[],Proof,supported,[]) :-
    f(milestone_requires(M,T),MP),depth_bound(Depth),reach(T,N,[T],Depth,Path),f(requires_resource(N,R),RP),
    flat([MP,Path,RP,['coord:affected_v1']],Proof).

% Missing edges cannot be discovered. Surface incomplete reachable specifications.
coverage_warning(Query, _{task:N,reason:incomplete_dependency_spec}) :-
    member(Goal,Query),
    (Goal=affected_milestone(M,_);Goal=milestone_blocker(M,_,_)),
    f(milestone_requires(M,T),_),depth_bound(Depth),reach(T,N,[T],Depth,_),
    \+f(task_spec_complete(N),_).

coord(milestone_blocker(M,T,R),[],Proof,supported,[]) :-
    f(milestone_requires(M,Root),MP),depth_bound(Depth),reach(Root,T,[Root],Depth,Path),
    state(task,T,S,SP), S\='status:completed',
    (S=unknown -> R='reason:unknown_status';S=conflict -> R='reason:conflict';R='reason:unfinished_task'),
    flat([MP,Path,SP,['coord:milestone_completion_v1']],Proof).
coord(ready(T),[],['coord:unknown_task_v1'],insufficient_evidence,[unknown_task]) :-
    ground(T),\+f(task(T),_).
coord(candidate(P,T,Period),[],['coord:unknown_task_v1'],insufficient_evidence,[unknown_task]) :-
    ground(T),\+f(task(T),_),people(P),(var(Period)->periods(Period);true).
