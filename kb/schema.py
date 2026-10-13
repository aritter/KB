"""Closed JSON schema plus semantic validation; no executable model text."""
import re
from copy import deepcopy
from .domains.research import PREDICATES, DERIVED, EXPLICIT_ONLY, STATUS_VALUES
from .domains.admin import PREDICATES as ADMIN_PREDICATES

VOCAB = {
    "manages": ["person", "project"],
    "uses": ["project", "dataset"],
    "requires_renewal": ["dataset"],
    "needs_notification": ["person", "dataset"],
}
DESCRIPTIONS = {
    "manages": "person manages project (not necessarily its only manager)",
    "uses": "project uses dataset",
    "requires_renewal": "dataset requires renewed authorization",
    "needs_notification": "person needs to be notified about dataset",
}

VOCAB.update({p: spec[0] for p, spec in {**PREDICATES, **ADMIN_PREDICATES}.items()})
DESCRIPTIONS.update({p: spec[1] for p, spec in {**PREDICATES, **ADMIN_PREDICATES}.items()})
ENTITY_TYPES = sorted({t for roles in VOCAB.values() for role in roles for t in role.split("|")})

class Invalid(ValueError):
    pass


def obj(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def array(items, minimum=0, maximum=8):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


TERM = {"oneOf": [obj({"const": {"type": "string", "pattern": r"^(" + "|".join(ENTITY_TYPES) + r"):[a-z0-9][a-z0-9_-]{0,63}$"}}),
                  obj({"var": {"type": "string", "pattern": r"^[A-Z][A-Za-z0-9_]{0,31}$"}})]}
ATOM = {"oneOf": [obj({"predicate": {"const": p}, "args": array(TERM, len(types), len(types))})
                   for p, types in VOCAB.items()]}
ASSERTION = obj({"head": ATOM, "body": array(ATOM, 0, 6)})
SCHEMA = obj({
    "status": {"enum": ["ok", "clarify", "unsupported"]},
    "explanation": {"type": "string", "maxLength": 1000},
    "assertions": array(ASSERTION),
    "query": array(ATOM, 0, 6),
    "targets": array({"type": "string", "pattern": r"^a_[a-f0-9]{32}$"}, 0, 1),
})


def schema_for(operation, allowed_targets=()):
    """Constrain decoding to this operation, while retaining a no-action branch."""
    if operation not in {"teach", "ask", "correct", "retract"}:
        raise Invalid("Unknown operation")
    declined = deepcopy(SCHEMA)
    props = declined["properties"]
    props["status"] = {"enum": ["clarify", "unsupported"]}
    props["explanation"]["pattern"] = r"\s*\S[\s\S]*"
    for key in ("assertions", "query", "targets"):
        props[key]["maxItems"] = 0
    # With no known target, an update must ask for clarification, not invent an ID.
    if operation in {"correct", "retract"} and not allowed_targets:
        return declined
    accepted = deepcopy(SCHEMA)
    props = accepted["properties"]
    props["status"] = {"const": "ok"}
    required = {"teach": {"assertions"}, "ask": {"query"},
                "correct": {"assertions", "targets"}, "retract": {"targets"}}[operation]
    for key in ("assertions", "query", "targets"):
        if key in required:
            props[key]["minItems"] = 1
        else:
            props[key]["maxItems"] = 0
    if "targets" in required:
        props["targets"]["items"] = {"type": "string", "enum": list(allowed_targets)}
    return {"oneOf": [accepted, declined]}


def check_schema(value, schema, path="$"):
    """Validator for exactly the schema keywords used above (stdlib only)."""
    if "oneOf" in schema:
        matches = 0
        for branch in schema["oneOf"]:
            try:
                check_schema(value, branch, path)
                matches += 1
            except Invalid:
                pass
        if matches != 1:
            raise Invalid(f"{path}: expected exactly one schema alternative")
        return
    if "const" in schema and value != schema["const"]:
        raise Invalid(f"{path}: invalid constant")
    if "enum" in schema and value not in schema["enum"]:
        raise Invalid(f"{path}: invalid choice")
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise Invalid(f"{path}: missing or extra object fields")
        for key, child in schema["properties"].items():
            check_schema(value[key], child, f"{path}.{key}")
    elif kind == "array":
        if not isinstance(value, list) or not schema["minItems"] <= len(value) <= schema["maxItems"]:
            raise Invalid(f"{path}: invalid array size")
        for i, item in enumerate(value):
            check_schema(item, schema["items"], f"{path}[{i}]")
    elif kind == "string":
        if not isinstance(value, str) or len(value) > schema.get("maxLength", 10000):
            raise Invalid(f"{path}: invalid string")
        if "pattern" in schema and not re.fullmatch(schema["pattern"], value):
            raise Invalid(f"{path}: invalid identifier")


def variables(atoms):
    return {t["var"] for a in atoms for t in a["args"] if "var" in t}


def typed(atoms):
    seen = {}
    for atom in atoms:
        for term, expected in zip(atom["args"], VOCAB[atom["predicate"]]):
            if "const" in term:
                if term["const"].split(":")[0] not in expected.split("|"):
                    raise Invalid(f"{atom['predicate']}: expected {expected}")
            else:
                var = term["var"]
                allowed = set(expected.split("|"))
                seen[var] = seen.get(var, allowed) & allowed
                if not seen[var]:
                    raise Invalid(f"Variable {var} has incompatible entity types")


def validate_assertion(assertion):
    check_schema(assertion, ASSERTION)
    head, body = assertion["head"], assertion["body"]
    typed([head] + body)
    predicate = head["predicate"]
    if predicate in ADMIN_PREDICATES:
        raise Invalid("Administrative message assessments use the shared gateway; use admin override for human judgments")
    if predicate in DERIVED:
        raise Invalid("Coordination result predicates are read-only; inspect the domain rules")
    if body and predicate in EXPLICIT_ONLY:
        raise Invalid(f"{predicate} requires an explicit ground update, not a rule")
    if predicate in STATUS_VALUES and not body:
        status = head["args"][-1].get("const", "").split(":")[-1]
        if status not in STATUS_VALUES[predicate]:
            raise Invalid(f"Unsupported {predicate} status: {status}")
    if not variables([head]) <= variables(body):
        raise Invalid("Head variables must occur in the positive body; facts must be ground")
    if len(variables([head] + body)) > 12:
        raise Invalid("At most 12 variables per rule")


def validate(proposal, operation, allowed_targets=()):
    check_schema(proposal, SCHEMA)
    assertions, query, targets = (proposal[k] for k in ("assertions", "query", "targets"))
    if proposal["status"] != "ok":
        if assertions or query or targets or not proposal["explanation"].strip():
            raise Invalid("Clarification/unsupported responses need an explanation and no actions")
        return proposal
    if operation == "teach":
        valid = bool(assertions) and not query and not targets
    elif operation == "ask":
        valid = bool(query) and not assertions and not targets
    elif operation == "correct":
        valid = bool(assertions) and len(targets) == 1 and not query
    elif operation == "retract":
        valid = len(targets) == 1 and not assertions and not query
    else:
        raise Invalid("Unknown operation")
    if not valid:
        requirements = {
            "teach": "nonempty assertions; empty query and targets",
            "ask": "nonempty query; empty assertions and targets",
            "correct": "nonempty replacement assertions, exactly one target ID, and empty query",
            "retract": "exactly one target ID; empty assertions and query",
        }
        raise Invalid(f"Invalid fields for {operation}: expected {requirements[operation]}; "
                      f"got assertions={len(assertions)}, query={len(query)}, targets={len(targets)}")
    if not set(targets) <= set(allowed_targets):
        raise Invalid("Target must be an active assertion supplied as a candidate")
    for assertion in assertions:
        validate_assertion(assertion)
    typed(query)
    if len(variables(query)) > 12:
        raise Invalid("At most 12 query variables")
    return proposal


def atom(predicate, *terms):
    return {"predicate": predicate, "args": [{"var": t[1:]} if t.startswith("?") else {"const": t} for t in terms]}


def assertion(head, *body):
    return {"head": head, "body": list(body)}


def proposal(assertions=(), query=(), targets=(), status="ok", explanation=""):
    return dict(status=status, explanation=explanation, assertions=list(assertions), query=list(query), targets=list(targets))
