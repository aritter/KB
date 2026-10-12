:- use_module(library(http/json)).
:- use_module(library(time)).
:- use_module(library(solution_sequences)).
:- dynamic known/2.
:- dynamic rule/3.

% Model terms are DATA, never callable goals. No predicate dispatch via call/1.
solve([], []).
solve([H|T], Proof) :-
    known(H, P), solve(T, Q), append(P, Q, Both), sort(Both, Proof).

% Finite positive Datalog closure. First proof per ground atom, no table cache.
saturate(Max) :-
    ( once((rule(H, Body, ID), solve(Body, P), \+ known(H, _))) ->
        aggregate_all(count, known(_, _), N),
        ( N >= Max -> throw(closure_limit_exceeded) ; true ),
        ( ground(H) -> true ; throw(non_ground_head) ),
        sort([ID|P], Proof), assertz(known(H, Proof)), saturate(Max)
    ; true ).

run(Query, Bindings, Limit, Seconds, Max) :-
    call_with_time_limit(Seconds,
        (saturate(Max),
         once(findnsols(Limit, _{bindings:Bindings,support:Proof},
             distinct(Bindings, solve(Query, Proof)), Rows)))),
    json_write_dict(current_output, _{rows:Rows}, [width(0)]), nl.
