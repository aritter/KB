"""Research coordination vocabulary. Skill eligibility is not access or capacity."""
PREDICATES = {
 'person_profile': (['person','profile'], 'Documented profile; evidence is the original source text of this assertion.'),
 'available': (['person','period'], 'Explicitly available in this named planning period; not unlimited capacity.'),
 'unavailable': (['person','period'], 'Explicitly unavailable in this planning period.'),
 'task': (['task'], 'A declared research task.'),
 'requires_skill': (['task','skill'], 'One mandatory skill; all listed skills must be supported.'),
 'assigned_to': (['task','person'], 'Explicit responsibility/ownership; does not imply skill or availability.'),
 'task_status': (['task','status'], 'Explicit pending, in_progress, or completed status.'),
 'depends_on': (['task','task'], 'Task requires completion of this prerequisite task.'),
 'requires_resource': (['task','resource|dataset'], 'Task requires this resource/access permission to be available.'),
 'resource_status': (['resource|dataset','status'], 'Explicit available or unavailable status; permissions must be stated.'),
 'milestone_requires': (['milestone','task'], 'Milestone requires completion of this task.'),
 'task_spec_complete': (['task'], 'Explicit declaration that ALL prerequisite tasks, resources and required skills are listed, including empty lists.'),
 'has_skill': (['person','skill'], 'Documented support for skill, resolved by the semantic gateway; positive explicit facts are human evidence.'),
 'lacks_skill': (['person','skill'], 'Explicit human contradiction of has_skill; omission is never contradiction.'),
 'candidate': (['person','task','period'], 'Derived eligibility: explicit availability and ALL mandatory skills for a complete task specification. Not authorization or readiness.'),
 'ready': (['task'], 'Derived ready: complete specification, pending status, all prerequisites completed and all resources explicitly available; no dependency cycle.'),
 'blocked_by': (['task','task|resource|dataset','reason'], 'Derived unmet or unknown prerequisite/resource; reason says which.'),
 'milestone_blocker': (['milestone','task|resource|dataset','reason'], 'Blockers of any required task, including transitive dependencies.'),
 'affected_milestone': (['milestone','resource|dataset'], 'Milestone depends directly or transitively on a task requiring resource; hypothetical loss consequence, not prediction.'),
}
DERIVED = {'candidate','ready','blocked_by','milestone_blocker','affected_milestone'}
# These are accepted updates, never inferred by a model judgment or taught rule.
EXPLICIT_ONLY = set(PREDICATES) - DERIVED
STATUS_VALUES = {'task_status': {'pending','in_progress','completed'},
                 'resource_status': {'available','unavailable'}}
