"""Kev's real local TypeSafe-compatible decision API, not Ollama generation."""
import json
import math
import time
import urllib.request
from urllib.parse import urlparse
from .schema import Invalid


class KevBackend:
    def __init__(self, config):
        self.config = config
        parsed = urlparse(config['url'])
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1','localhost','::1'} or parsed.username:
            raise Invalid('Kev must use a local HTTP endpoint')
        if '@' not in config['checkpoint'] or not config.get('runtime_version'):
            raise Invalid('Pin a checkpoint revision and runtime version for cache identity')
        self.verified = False
        self.http_requests = 0
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def requests_needed(self): return 1 if self.verified else 2

    def request(self, path, data, timeout):
        self.http_requests += 1
        request = urllib.request.Request(self.config['url'].rstrip('/')+path,
            data=None if data is None else json.dumps(data).encode(), headers={'Content-Type':'application/json'})
        with self.opener.open(request, timeout=max(0.001,timeout)) as response:
            raw = response.read(1_000_001)
        if len(raw)>1_000_000: raise Invalid('Kev response exceeds limit')
        return json.loads(raw)

    def evaluate(self, requests, timeout):
        started = time.monotonic()
        if not self.verified:
            models = self.request('/v1/models',None,timeout)['models']
            model = next(x for x in models if x['name']=='kev-latest')
            if model['run'] != self.config['checkpoint'] or model['truncate_states']:
                raise Invalid('Kev server checkpoint mismatch or truncation enabled')
            for key in ('backend','dtype','temperature'):
                equal = math.isclose(float(model[key]),float(self.config[key]),abs_tol=1e-6) if key=='temperature' else str(model[key])==str(self.config[key])
                if not equal:
                    raise Invalid(f'Kev server {key} differs from registered configuration: {model[key]}')
            self.model_metadata = {k:model[k] for k in ('run','base','backend','dtype','temperature') if k in model}
            self.verified = True
        evidence = requests[0]['evidence']
        if any(x['evidence'] != evidence for x in requests):
            raise Invalid('Batch cannot mix evidence from different people')
        input_format = requests[0]['definition'].get('input_format', 'evidence-records-v1')
        if any(x['definition'].get('input_format', 'evidence-records-v1') != input_format for x in requests):
            raise Invalid('Batch cannot mix semantic input formats')
        state = evidence
        if input_format == 'admin-message-v2':
            if not evidence:
                raise Invalid('Administrative judgment requires message evidence')
            # Preserve full sources in the gateway audit/cache, but give the model
            # named text fields rather than opaque IDs and provenance metadata.
            state = {'message': evidence[0]['source'],
                     'request_context': [item['source'] for item in evidence[1:]]}
        questions = {}
        for i, req in enumerate(requests):
            person, skill = req['arguments']; spec = req['definition']
            questions[f'q{i}'] = {'type':'choice','instructions':spec['question'].format(person=person,skill=skill), 'criteria':spec['choices']}
        # Each question sees only this one person's original source documents.
        remaining = timeout-(time.monotonic()-started)
        if remaining <= 0: raise TimeoutError('Kev preflight exhausted the deadline')
        response = self.request('/v1/systemone', {'model':'kev-latest', 'state':state, 'questions':questions},remaining)
        usage = response.get('usage',{})
        if response.get('truncated') or usage.get('state_tokens',0)>usage.get('state_tokens_used',float('inf')):
            raise Invalid('Kev truncated evidence; refusing judgment')
        return [{'answer':response['answers'][f'q{i}'], 'latency_ms':response.get('latency_ms',0),
                 'usage':usage, 'server_model':response.get('model'), 'server_configuration':self.model_metadata} for i in range(len(requests))]


class CountingMock:
    """Fixture lookup ONLY. No learned inference or keyword heuristic is disguised as Kev."""
    def __init__(self, config):
        self.config = config
        self.calls = self.judgments = self.http_requests = 0
        self.seen = []
    def requests_needed(self): return 1
    def evaluate(self, requests, timeout):
        self.calls += 1; self.http_requests += 1; self.judgments += len(requests); self.seen.extend(requests)
        output=[]
        for req in requests:
            key = '|'.join(req['arguments'])
            status = self.config.get('answers',{}).get(req['predicate']+'|'+key, self.config.get('answers',{}).get(key))
            if status is None:
                source=req['evidence'][0]['source'] if req['evidence'] else ''
                status=self.config.get('fixtures',{}).get(req['predicate']+'|'+source,'insufficient_evidence')
            if status=='backend_error': raise RuntimeError('Mock backend error')
            output.append({'answer':{'type':'choice','choice':status,'confidence':1.0,
                'probabilities':{k:float(k==status) for k in ('supported','contradicted','insufficient_evidence')}},
                'latency_ms':0,'mock':True})
        return output


def make_backend(config):
    if not isinstance(config,dict) or config.get('kind') not in {'kev','counting_mock'}:
        raise Invalid('Backend must be kev or explicitly counting_mock')
    if config['kind']=='kev':
        required={'kind','url','checkpoint','runtime_version','backend','dtype','temperature'}
        if set(config)!=required: raise Invalid('Incomplete Kev model configuration')
        return KevBackend(config)
    if not set(config)<= {'kind','version','answers','fixtures'} or not config.get('version'):
        raise Invalid('Counting mock requires a version and optional fixture answers')
    if any(v not in {'supported','contradicted','insufficient_evidence','backend_error'} for v in list(config.get('answers',{}).values())+list(config.get('fixtures',{}).values())):
        raise Invalid('Invalid counting mock fixture outcome')
    return CountingMock(config)
