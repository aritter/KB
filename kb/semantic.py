"""Central semantic gateway. Raw model scores and acceptance decisions are separate."""
import hashlib
import json
import math
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from .schema import Invalid, atom, check_schema, ATOM

CHOICES = {'supported', 'contradicted', 'insufficient_evidence'}


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def install(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS semantic_definitions (
      id TEXT PRIMARY KEY, name TEXT NOT NULL, document TEXT NOT NULL,
      active INTEGER NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS raw_judgments (
      cache_key TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL, request TEXT NOT NULL,
      raw TEXT NOT NULL, latency REAL NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS judgment_decisions (
      id TEXT PRIMARY KEY, raw_id TEXT, status TEXT NOT NULL,
      document TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS semantic_overrides (
      id TEXT PRIMARY KEY, predicate TEXT NOT NULL, arguments TEXT NOT NULL, status TEXT NOT NULL,
      source TEXT NOT NULL, created_at TEXT NOT NULL, retracted_at TEXT);
    CREATE TABLE IF NOT EXISTS source_notes (
      id TEXT PRIMARY KEY, source TEXT NOT NULL, explanation TEXT NOT NULL, created_at TEXT NOT NULL);
    ''')


def register(store, definition):
    required = {'name','arity','grounded_inputs','version','evidence','question','choices',
                'deterministic_evaluator','max_evidence_bytes','policy','backend'}
    from .domains.admin import SEMANTICS
    if set(definition) - {'input_format'} != required or definition['name'] not in {'has_skill', *SEMANTICS} or definition['arity'] != 2 or definition['grounded_inputs'] != [0,1]:
        raise Invalid('Only explicitly registered research/admin semantic predicates are supported')
    if definition.get('input_format', 'evidence-records-v1') not in {'evidence-records-v1', 'admin-message-v2'}:
        raise Invalid('Unregistered semantic input format')
    if definition.get('input_format') == 'admin-message-v2' and definition['name'] not in SEMANTICS:
        raise Invalid('Administrative input format requires an administrative predicate')
    if set(definition['choices']) != CHOICES or definition['deterministic_evaluator'] not in {None,'empty-evidence-v1'}:
        raise Invalid('Invalid choices or unregistered deterministic evaluator')
    if not isinstance(definition['max_evidence_bytes'], int) or not 1 <= definition['max_evidence_bytes'] <= 12000:
        raise Invalid('Evidence byte limit must be between 1 and 12000')
    policy = definition['policy']
    if set(policy) != {'version','threshold','margin'} or not 0.5 <= policy['threshold'] <= 1 or not 0 <= policy['margin'] <= 1:
        raise Invalid('Invalid acceptance policy')
    if not definition['version'] or not policy['version']:
        raise Invalid('Definition and policy need versions')
    if not isinstance(definition['question'], str) or len(definition['question']) > 2000 or any(not isinstance(v,str) or len(v)>1000 for v in definition['choices'].values()):
        raise Invalid('Question/choice descriptions exceed supported limits')
    try:
        definition['question'].format(person='person:example', skill='skill:example')
    except (KeyError, ValueError) as exc:
        raise Invalid('Question supports only {person} and {skill} placeholders') from exc
    from .kev import make_backend
    make_backend(definition['backend'])  # Validate configuration without connecting.
    ident = 'd_' + digest(definition)
    with store.db:
        store.db.execute('UPDATE semantic_definitions SET active=0 WHERE name=?', (definition['name'],))
        store.db.execute('INSERT INTO semantic_definitions VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET active=1',
                         (ident, definition['name'], encoded(definition), 1, now()))
        store.db.execute('UPDATE meta SET revision=revision+1 WHERE id=1')
    return ident


def definition(store, name="has_skill"):
    row = store.db.execute('SELECT id,document FROM semantic_definitions WHERE name=? AND active=1', (name,)).fetchone()
    if not row:
        raise Invalid('Register a semantic definition first: python3 -m kb register config/has_skill.json')
    return row['id'], json.loads(row['document'])


@dataclass
class Budget:
    judgments: int = 12
    requests: int = 12
    seconds: float = 30
    steps: int = 200000
    depth: int = 32
    results: int = 100
    plans: int = 500
    batch: int = 8

    def __post_init__(self):
        if any(not isinstance(getattr(self, k), int) or getattr(self, k) < 0 for k in ('judgments','requests','steps','depth','results','plans','batch')):
            raise Invalid('Budgets must be nonnegative integers')
        if not math.isfinite(self.seconds) or self.seconds <= 0 or min(self.steps,self.depth,self.results,self.plans,self.batch) < 1:
            raise Invalid('Time and symbolic/result/batch budgets must be positive')
        self.started = time.monotonic()
        self.metrics = {'cache_hits':0, 'memo_hits':0, 'new_judgments':0, 'backend_calls':0,
                        'backend_requests':0, 'model_latency_ms':0, 'backend_wall_seconds':0}
        self.stopping = set()

    def remaining(self):
        return max(0, self.seconds - (time.monotonic() - self.started))

    def permit(self, count, requests):
        if self.remaining() <= 0: self.stopping.add('wall_clock_budget')
        if self.metrics['new_judgments'] + count > self.judgments: self.stopping.add('judgment_budget')
        if self.metrics['backend_requests'] + requests > self.requests: self.stopping.add('backend_request_budget')
        return self.remaining() > 0 and self.metrics['new_judgments'] + count <= self.judgments and self.metrics['backend_requests'] + requests <= self.requests


class Gateway:
    def __init__(self, store, records, budget, backend=None, predicate="has_skill", resolver=None, as_of=None, force_models=False):
        self.store, self.records, self.budget = store, records, budget
        self.predicate, self.resolver, self.as_of = predicate, resolver, as_of
        self.definition_id, self.definition = definition(store,predicate)
        from .kev import make_backend
        self.backend = backend or make_backend(self.definition['backend'])
        if self.backend.config != self.definition['backend']:
            raise Invalid('Backend must match the registered model configuration')
        self.memo = {}
        self.force_models = force_models

    def prepare(self, person, skill):
        check_schema(atom(self.predicate,person,skill), ATOM)
        if self.resolver:
            evidence, explicit = self.resolver(person,skill)
            for row in self.store.db.execute('SELECT * FROM semantic_overrides WHERE predicate=? AND arguments=?', (self.predicate,encoded([person,skill]))):
                cutoff=self.as_of or now()
                if row['created_at'] <= cutoff and (not row['retracted_at'] or row['retracted_at'] > cutoff):
                    explicit.append({'id':row['id'],'status':row['status'],'source':row['source']})
            spec={k:v for k,v in self.definition.items() if k not in {'policy','backend'}}
            return {'predicate':self.predicate,'arguments':[person,skill], 'definition':spec,
                    'evidence':evidence, 'model_configuration':self.backend.config}, explicit
        if not person.startswith('person:') or not skill.startswith('skill:'):
            raise Invalid('Semantic inputs must be grounded person and skill constants')
        evidence, explicit = [], []
        for record in self.records:
            item = record['assertion']
            if item['body']: continue
            head = item['head']; args = [t.get('const') for t in head['args']]
            if head['predicate'] == 'person_profile' and args[0] == person:
                evidence.append({'id':record['id'], 'profile':args[1], 'source':record['source'],
                                 'hash':digest({'assertion':item,'source':record['source']})})
            if head['predicate'] in {'has_skill','lacks_skill'} and args == [person,skill]:
                explicit.append({'id':record['id'], 'status':'supported' if head['predicate']=='has_skill' else 'contradicted', 'source':record['source']})
        evidence.sort(key=lambda x:x['id'])
        spec = {k:v for k,v in self.definition.items() if k not in {'policy','backend'}}
        request = {'predicate':'has_skill','arguments':[person,skill], 'definition':spec,
                   'evidence':evidence, 'model_configuration':self.backend.config}
        return request, explicit

    def record(self, request, status, origin, raw_id=None, **extra):
        result = {'status':status, 'origin':origin, 'raw_id':raw_id, 'predicate':self.predicate,
                  'definition_id':self.definition_id, 'arguments':request['arguments'],
                  'evidence':request['evidence'], 'policy':self.definition['policy'], **extra}
        result['id']='j_'+digest(result)
        with self.store.db:
            self.store.db.execute('INSERT OR IGNORE INTO judgment_decisions VALUES(?,?,?,?,?)',
                (result['id'], raw_id, status, encoded(result), now()))
        self.memo[tuple(request['arguments'])] = result
        return result

    def interpret(self, request, raw_id, raw):
        answer = raw['answer']; probs = answer['probabilities']; winner = answer['choice']
        ordered = sorted(probs.values(), reverse=True)
        policy = self.definition['policy']
        accepted = probs[winner] >= policy['threshold'] and ordered[0] - ordered[1] >= policy['margin']
        status = winner if accepted else 'insufficient_evidence'
        return self.record(request, status, 'model_assessment', raw_id, raw=raw,
                           acceptance='threshold_met' if accepted else 'policy_abstention')

    def lookup(self, pair):
        pair = tuple(pair)
        if pair in self.memo:
            self.budget.metrics['memo_hits'] += 1
            return self.memo[pair]
        request, explicit = self.prepare(*pair)
        if explicit:
            states = {x['status'] for x in explicit}
            return self.record(request, next(iter(states)) if len(states)==1 else 'conflict', 'explicit', explicit=explicit)
        row = self.store.db.execute('SELECT * FROM raw_judgments WHERE cache_key=?', (digest(request),)).fetchone()
        if row and not self.force_models:
            self.budget.metrics['cache_hits'] += 1
            return self.interpret(request, row['id'], json.loads(row['raw']))
        if not request['evidence'] and self.definition['deterministic_evaluator']=='empty-evidence-v1':
            return self.record(request, 'insufficient_evidence', 'deterministic', reason='No active profile evidence')
        if len(encoded(request['evidence']).encode()) > self.definition['max_evidence_bytes']:
            return self.record(request, 'insufficient_evidence', 'evidence_limit', reason='Evidence exceeds configured limit; nothing truncated')
        return None

    def resolve(self, pairs):
        """One bounded batch, with one person's exact evidence shared across questions."""
        pairs = list(dict.fromkeys(tuple(x) for x in pairs))
        result = {pair:self.lookup(pair) for pair in pairs}
        missing = [pair for pair in pairs if result[pair] is None]
        while missing:
            first = missing[0]
            group = [x for x in missing if x[0] == first[0]][:self.budget.batch]
            # Shrink a batch to remaining individual-judgment budget.
            remaining = self.budget.judgments - self.budget.metrics['new_judgments']
            if remaining > 0: group = group[:remaining]
            requests_needed = self.backend.requests_needed()
            if not self.budget.permit(len(group), requests_needed):
                for pair in missing:
                    req,_ = self.prepare(*pair)
                    result[pair] = self.record(req, 'not_evaluated_budget', 'budget')
                break
            requests = [self.prepare(*pair)[0] for pair in group]
            self.budget.metrics['new_judgments'] += len(group)
            self.budget.metrics['backend_calls'] += 1
            before_requests = self.backend.http_requests
            started = time.monotonic()
            try:
                raw_answers = self.backend.evaluate(requests, self.budget.remaining())
                if len(raw_answers) != len(group): raise Invalid('Backend returned wrong number of judgments')
                if self.budget.remaining() <= 0:
                    raise TimeoutError('Semantic response arrived after query deadline')
                for pair, req, raw in zip(group, requests, raw_answers):
                    validate_raw(raw)
                    raw_id = 'raw_'+uuid.uuid4().hex
                    cache_key = digest(req) if not self.force_models else digest(req)+':full:'+raw_id
                    with self.store.db:
                        self.store.db.execute('INSERT OR IGNORE INTO raw_judgments VALUES(?,?,?,?,?,?)',
                            (cache_key,raw_id,encoded(req),encoded(raw),time.monotonic()-started,now()))
                        stored = self.store.db.execute('SELECT id,raw FROM raw_judgments WHERE cache_key=?',(cache_key,)).fetchone()
                    result[pair] = self.interpret(req,stored['id'],json.loads(stored['raw']))
                # Shared batch latency counted once, never summed across its questions.
                self.budget.metrics['model_latency_ms'] += raw_answers[0].get('latency_ms',0)
            except Exception as exc:
                for pair, req in zip(group, requests):
                    result[pair] = self.record(req, 'backend_error', 'backend_error', error=str(exc))
                self.budget.stopping.add('backend_error')
            self.budget.metrics['backend_requests'] += self.backend.http_requests - before_requests
            self.budget.metrics['backend_wall_seconds'] += time.monotonic()-started
            missing = [x for x in missing if x not in group]
        return result


def validate_raw(raw):
    try:
        answer = raw['answer']; probs = answer['probabilities']; choice = answer['choice']
        if raw.get('truncated') or answer['type'] != 'choice' or set(probs) != CHOICES or choice not in CHOICES:
            raise ValueError('wrong fields or truncated evidence')
        if any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in probs.values()):
            raise ValueError('invalid probabilities')
        if abs(sum(probs.values())-1) > 0.01 or probs[choice] != max(probs.values()):
            raise ValueError('invalid probability distribution or choice')
    except (KeyError, TypeError, ValueError) as exc:
        raise Invalid(f'Invalid Kev decision output: {exc}') from exc
