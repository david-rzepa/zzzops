"""Deterministic repository test plans and resumable partition facts."""
from __future__ import annotations
import hashlib, json, os
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
RESULT_FIELDS = frozenset({'latest_success'})
OUTCOMES = frozenset({'passed','assertion_failed','timed_out','cancelled','infrastructure_error'})

def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()

def digest(value: Any) -> str:
    return 'sha256:' + hashlib.sha256(canonical(value)).hexdigest()

def semantic_plan(plan: dict) -> dict:
    value = dict(plan); value.pop('latest_success', None)
    return value

def validate_plan(plan: Any) -> dict:
    if not isinstance(plan, dict) or plan.get('schema_version') != SCHEMA_VERSION:
        raise ValueError('Unsupported test-plan schema')
    required={'schema_version','graph_provider','runners','tests','latest_success'}
    if set(plan)!=required: raise ValueError('Test plan fields are incomplete or unknown')
    provider=plan['graph_provider']
    if not isinstance(provider,dict) or set(provider)!= {'name','version','format','configuration'} or any(not isinstance(provider[k],str) or not provider[k] for k in ('name','version','format')) or not isinstance(provider['configuration'],dict):
        raise ValueError('Graph provider identity/configuration is invalid')
    if not isinstance(plan['runners'],dict) or not plan['runners']: raise ValueError('Test plan requires runners')
    tests=plan['tests']
    if not isinstance(tests,dict) or not tests: raise ValueError('Test plan requires stable test units')
    for identity,unit in tests.items():
        if not isinstance(identity,str) or not identity or not isinstance(unit,dict): raise ValueError('Test unit identity is invalid')
        fields={'purpose','behavior','runner','selection','goals','specifications','dependencies','completeness','fallback','order_group'}
        if set(unit)!=fields: raise ValueError('Test unit definition is incomplete or unknown')
        if any(not isinstance(unit[k],str) or not unit[k] for k in ('purpose','behavior','runner','selection','completeness','fallback')): raise ValueError('Test unit text is invalid')
        for k in ('goals','specifications','dependencies'):
            if not isinstance(unit[k],list) or len(unit[k])!=len(set(unit[k])) or any(not isinstance(x,str) or not x for x in unit[k]): raise ValueError('Test unit list is invalid')
        if unit['order_group'] is not None and (not isinstance(unit['order_group'],str) or not unit['order_group']): raise ValueError('Order group is invalid')
    if not isinstance(plan['latest_success'],dict) or any(k not in tests for k in plan['latest_success']): raise ValueError('Latest success references unknown test')
    return plan

def file_identity(root: Path, relative: str) -> str:
    path=root/relative
    if not path.exists(): return 'missing'
    if path.is_symlink(): data=os.fsencode(os.readlink(path))
    elif path.is_file(): data=path.read_bytes()
    else: raise ValueError('Test input must be a file, symlink, or missing')
    return 'sha256:'+hashlib.sha256(data).hexdigest()

def input_fingerprint(plan: dict, unit_id: str, root: Path, *, inventory: Iterable[str], environment: dict[str,str], tooling: dict[str,str]) -> str:
    validate_plan(plan); unit=plan['tests'][unit_id]
    inputs={p:file_identity(root,p) for p in sorted(unit['dependencies'])}
    return digest({'plan':semantic_plan(plan),'unit':unit_id,'inventory':sorted(inventory),'inputs':inputs,'environment':environment,'tooling':tooling})

def affected_units(plan: dict, changed: Iterable[str], *, previous_edges: dict[str,list[str]]|None, current_edges: dict[str,list[str]]|None, graph_ok: bool, fallback_reason: str|None=None) -> dict:
    validate_plan(plan); changed=set(changed); selected=set(); reasons={}
    if not graph_ok or previous_edges is None or current_edges is None:
        reason=fallback_reason or 'dependency graph unavailable or stale'
        for unit in plan['tests']: selected.add(unit); reasons[unit]=reason
    else:
        for unit,spec in plan['tests'].items():
            structural=set(previous_edges.get(unit,()))|set(current_edges.get(unit,()))
            declared=set(spec['dependencies'])
            if spec['completeness']!='complete':
                selected.add(unit); reasons[unit]='dependency mapping incomplete: '+spec['fallback']
            elif changed & (structural|declared):
                selected.add(unit); reasons[unit]='relevant input changed'
    return {'selected':sorted(selected),'reasons':reasons}

def partitions(unit_ids: Iterable[str], durations: dict[str,float], maximum_seconds: float) -> list[dict]:
    if maximum_seconds<=0: raise ValueError('Partition duration must be positive')
    result=[]; current=[]; total=0.0
    for identity in unit_ids:
        duration=max(0.0,float(durations.get(identity,0.0)))
        if current and total+duration>maximum_seconds:
            result.append({'id':digest(current),'units':current}); current=[]; total=0.0
        current.append(identity); total+=duration
    if current: result.append({'id':digest(current),'units':current})
    if [u for p in result for u in p['units']] != list(unit_ids): raise ValueError('Partition inventory changed')
    return result

def reusable_success(facts: Iterable[dict], fingerprint: str) -> dict|None:
    matching=[f for f in facts if f.get('fingerprint')==fingerprint]
    if not matching: return None
    newest=max(matching,key=lambda f:f.get('sequence',-1))
    return newest if newest.get('outcome')=='passed' else None

def parallel_contract(*,requested:int,authority:dict|None,capacity:int,isolation:bool)->int:
    if requested<1: raise ValueError('Parallelism must be positive')
    if requested==1:return 1
    if not authority or authority.get('decision')!='approved' or authority.get('maximum',0)<requested: raise ValueError('Current reviewed parallel resource authority is absent')
    if capacity<requested: raise ValueError('Parallel execution capacity is insufficient')
    if not isolation: raise ValueError('Safe parallel test isolation is absent')
    return requested

def write_plan(path:Path,plan:dict)->None:
    validate_plan(plan); data=canonical(plan)+b'\n'; temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(data); os.replace(temporary,path)

class PartitionJournal:
    """Compact crash-safe local recovery; tracked plan remains the authority."""
    def __init__(self,path:Path,identity:dict): self.path=path; self.identity=identity
    def _read(self):
        if not self.path.exists(): return {'schema_version':1,'identity':self.identity,'facts':[]}
        envelope=json.loads(self.path.read_text(encoding='utf-8'))
        if set(envelope)!= {'hash','record'} or digest(envelope['record'])!=envelope['hash']: raise ValueError('Partition journal integrity changed')
        if envelope['record'].get('identity')!=self.identity: raise ValueError('Partition journal identity changed')
        return envelope['record']
    def facts(self): return list(self._read()['facts'])
    def append(self,fact:dict):
        if not isinstance(fact,dict) or fact.get('outcome') not in OUTCOMES or not isinstance(fact.get('partition'),str) or not isinstance(fact.get('fingerprint'),str): raise ValueError('Partition fact is invalid')
        record=self._read(); existing=[f for f in record['facts'] if f['partition']==fact['partition'] and f['fingerprint']==fact['fingerprint']]
        if existing and existing[-1]==fact:return
        fact=dict(fact); fact['sequence']=1+max((f.get('sequence',0) for f in record['facts']),default=0); record['facts'].append(fact)
        self.path.parent.mkdir(parents=True,exist_ok=True); temporary=self.path.with_name(self.path.name+'.tmp')
        with temporary.open('w',encoding='utf-8') as h: json.dump({'hash':digest(record),'record':record},h,sort_keys=True,separators=(',',':'));h.flush();os.fsync(h.fileno())
        os.replace(temporary,self.path)

def classify_outcome(*,exit_code:int|None,timed_out=False,cancelled=False,execution_error:str|None=None,expected_red:str|None=None,output:str='')->str:
    if timed_out:return 'timed_out'
    if cancelled:return 'cancelled'
    if execution_error or exit_code is None:return 'infrastructure_error'
    if exit_code==0:return 'passed'
    if expected_red is not None and expected_red not in output:return 'infrastructure_error'
    return 'assertion_failed'
