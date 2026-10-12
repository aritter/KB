"""Deterministic compiler to a non-executable term language and isolated SWI runner."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from .schema import Invalid, ATOM, array, check_schema, typed, variables, validate_assertion


class RuntimeUnavailable(RuntimeError):
    pass


class InferenceError(RuntimeError):
    pass


def quote(value):
    # Only validated canonical identifiers reach here. Quoting remains defensive.
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def compile_atom(atom):
    check_schema(atom, ATOM)
    terms = ["V_" + t["var"] if "var" in t else quote(t["const"]) for t in atom["args"]]
    return atom["predicate"] + "(" + ",".join(terms) + ")"


def compile_list(atoms):
    return "[" + ",".join(map(compile_atom, atoms)) + "]"


def program(records, query, limit=100, seconds=3.0, max_facts=5000):
    if not 1 <= limit <= 1000 or not 0 < seconds <= 30 or not 1 <= max_facts <= 50000:
        raise Invalid("Invalid inference resource limits")
    check_schema(query, array(ATOM, 1, 6))
    typed(query)
    lines = [Path(__file__).with_name("engine.pl").read_text()]
    for record in records:
        item = record["assertion"]
        validate_assertion(item)
        ident = record["id"]
        check_schema(ident, {"type": "string", "pattern": r"^a_[a-f0-9]{32}$"})
        # Facts are zero-body rules too, so every assertion follows the same proof path.
        lines.append(f"rule({compile_atom(item['head'])},{compile_list(item['body'])},{quote(ident)}).")
    bindings = "bindings{" + ",".join(quote(v) + ":V_" + v for v in sorted(variables(query))) + "}"
    goal = f"run({compile_list(query)},{bindings},{limit + 1},{seconds},{max_facts})"
    lines.append(f":- initialization((catch(({goal}), E, (print_message(error,E),halt(2))),halt),main).")
    return "\n".join(lines)


class Prolog:
    def __init__(self, executable="swipl", seconds=3.0, limit=100):
        self.executable, self.seconds, self.limit = executable, seconds, limit

    def ask(self, records, query):
        executable = shutil.which(self.executable)
        if not executable:
            raise RuntimeUnavailable("SWI-Prolog not found. Install with: brew install swi-prolog")
        code = program(records, query, self.limit, self.seconds)
        with tempfile.TemporaryDirectory(prefix="research-kb-") as tmp:
            path = Path(tmp) / "query.pl"
            path.write_text(code)
            try:
                proc = subprocess.run([executable, "--stack-limit=256m", "-q", "-f", "none", "-s", str(path)],
                                      capture_output=True, text=True, timeout=self.seconds + 3)
            except subprocess.TimeoutExpired as exc:
                raise InferenceError("Prolog wall-clock limit exceeded; no answer established") from exc
            if proc.returncode:
                raise InferenceError("Prolog failed (no partial answer): " + proc.stderr[-2000:])
            try:
                rows = json.loads(proc.stdout)["rows"]
            except (ValueError, KeyError) as exc:
                raise InferenceError("Invalid Prolog response") from exc
        truncated = len(rows) > self.limit
        rows = rows[:self.limit]
        if not rows:
            answer = "No answer could be established from the active knowledge. This does not establish falsity."
        elif not variables(query):
            answer = "The proposition is supported by the active knowledge."
        else:
            answer = "; ".join(", ".join(f"{key} = {value}" for key, value in row["bindings"].items()) for row in rows)
        return {"rows": rows, "answer": answer, "truncated": truncated}
