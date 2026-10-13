% Restricted proof discovery. No semantic backend is called inside Prolog.
reserved(candidate(_,_,_)). reserved(ready(_)). reserved(blocked_by(_,_,_)).
reserved(milestone_blocker(_,_,_)). reserved(affected_milestone(_,_)). reserved(has_skill(_,_)).
semantic_goal(has_skill(_,_)).
order_goals(Goals,Ordered) :- partition(semantic_goal,Goals,Sem,Symbolic),append(Symbolic,Sem,Ordered).
merge_state(contradicted,_,contradicted) :- !.
merge_state(_,contradicted,contradicted) :- !.
merge_state(supported,supported,supported) :- !.
merge_state(_,_,insufficient_evidence).
plans([],_,_,[],[],supported,[]).
plans([H|T],Seen,Depth,Needs,Proof,State,Reasons) :-
    discover(H,Seen,Depth,N,P,S,R),plans(T,Seen,Depth,N2,P2,S2,R2),
    append(N,N2,NN),sort(NN,Needs),append(P,P2,PP),sort(PP,Proof),
    merge_state(S,S2,State),append(R,R2,Reasons).
discover(has_skill(P,S),_,_,[[P,S]],[],supported,[]) :-
    (var(P)->people(P);true),(var(S)->skills(S);true),ground([P,S]).
discover(H,_,_,N,P,S,R) :- H\=has_skill(_,_),reserved(H),coord(H,N,P,S,R).
discover(H,_,_,[],P,supported,[]) :- \+reserved(H),f(H,P).
discover(H,Seen,Depth,Needs,[ID|Proof],State,Reasons) :-
    \+reserved(H),
    (Depth=<0 -> throw(symbolic_depth_limit) ; true),
    \+ (member(Old,Seen),H =@= Old),(rule(H,Body,ID);deferred_rule(H,Body,ID)),Body\=[],
    order_goals(Body,Ordered),D1 is Depth-1,plans(Ordered,[H|Seen],D1,Needs,Proof,State,Reasons).

plan_query(Query,Bindings,Limit,Seconds,Steps,Depth) :-
    statistics(inferences,Before),
    call_with_time_limit(Seconds,
      call_with_inference_limit(
        (saturate(5000),order_goals(Query,Ordered),
         once(findnsols(Limit,_{bindings:Bindings,needs:N,support:P,status:S,reasons:R},
              plans(Ordered,[],Depth,N,P,S,R),Rows)),
         findall(W,coverage_warning(Query,W),Warnings)),Steps,Outcome)),
    (Outcome=inference_limit_exceeded -> throw(symbolic_step_limit);true),
    statistics(inferences,After),Used is After-Before,
    json_write_dict(current_output,_{plans:Rows,symbolic_steps:Used,coverage_warnings:Warnings},[width(0)]),nl.
