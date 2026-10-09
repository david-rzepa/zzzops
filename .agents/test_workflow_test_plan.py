import json,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
import test_evidence_dag_journeys as journeys
m=journeys.z._test_plan
class TestPlanTests(unittest.TestCase):
 def plan(self):
  unit=lambda dep:{'purpose':'why','behavior':'observable','runner':'r','selection':'x','goals':['unknown'],'specifications':[],'dependencies':[dep],'completeness':'complete','fallback':'full','order_group':None}
  return {'schema_version':1,'graph_provider':{'name':'graft','version':'0.17.0','format':'v1','configuration':{}},'runners':{'r':{'adapter':'unittest'}},'tests':{'a':unit('a.py'),'b':unit('b.py'),'c':unit('c.py')},'latest_success':{}}
 def test_semantic_fingerprints_are_per_unit_and_results_exclude_themselves(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);[(root/f'{x}.py').write_text(x) for x in 'abc'];p=self.plan();kw={'inventory':p['tests'],'environment':{'py':'x'},'tooling':{'runner':'x'}};a=m.input_fingerprint(p,'a',root,**kw);b=m.input_fingerprint(p,'b',root,**kw);p['latest_success']['a']={'fingerprint':a};self.assertEqual(a,m.input_fingerprint(p,'a',root,**kw));p['tests']['a']['purpose']='changed';self.assertNotEqual(a,m.input_fingerprint(p,'a',root,**kw));self.assertEqual(b,m.input_fingerprint(p,'b',root,**kw))
 def test_edges_missing_graph_resume_and_newer_failure(self):
  p=self.plan();self.assertEqual(['a'],m.affected_units(p,['old.py'],previous_edges={'a':['old.py']},current_edges={'a':[]},graph_ok=True)['selected']);r=m.affected_units(p,['unmapped'],previous_edges=None,current_edges=None,graph_ok=False,fallback_reason='missing Graft');self.assertEqual(['a','b','c'],r['selected']);self.assertEqual({'missing Graft'},set(r['reasons'].values()));parts=m.partitions(['a','b','c'],{'a':2,'b':2,'c':8},5);self.assertEqual(['a','b','c'],[u for q in parts for u in q['units']]);self.assertIsNone(m.reusable_success([{'fingerprint':'f','outcome':'passed','sequence':1},{'fingerprint':'f','outcome':'assertion_failed','sequence':2}],'f'))
 def test_journal_modes_red_and_parallel_authority(self):
  with tempfile.TemporaryDirectory() as d:
   j=m.PartitionJournal(Path(d)/'j',{'inputs':'same'});j.append({'partition':'p1','fingerprint':'f1','outcome':'passed'});j.append({'partition':'p2','fingerprint':'f2','outcome':'timed_out'});self.assertEqual(2,len(j.facts()))
  p=self.plan();self.assertEqual(['a','b','c'],m.preview(p,mode='full')['selected']);self.assertEqual(['b'],m.preview(p,mode='explicit',explicit=['b'])['selected']);self.assertEqual('infrastructure_error',m.classify_outcome(exit_code=1,expected_red='wanted',output='wrong'));self.assertEqual('assertion_failed',m.classify_outcome(exit_code=1,expected_red='wanted',output='wanted'))
  for case in [dict(authority=None,capacity=2,isolation=True),dict(authority={'decision':'approved','maximum':2},capacity=1,isolation=True),dict(authority={'decision':'approved','maximum':2},capacity=2,isolation=False)]:
   with self.assertRaises(ValueError):m.parallel_contract(requested=2,**case)
  self.assertEqual(2,m.parallel_contract(requested=2,authority={'decision':'approved','maximum':2},capacity=2,isolation=True))
 def test_validated_graft_adapter_follows_transitive_and_deleted_edges(self):
  p=self.plan();graph={'meta':{'version':1},'nodes':[],'edges':[{'source':'a.py','target':'shared.py','relation':'imports','confidence':'extracted'},{'source':'shared.py','target':'old.py','relation':'imports','confidence':'extracted'}]}
  class R:
   def __init__(self,out='',code=0):self.stdout=out;self.stderr='';self.returncode=code
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);path=root/'graph.json';path.write_text(json.dumps(graph));calls=[]
   def run(command,**kwargs):calls.append(command);return R('graft 0.17.0' if '--version' in command else '{}')
   observed=m.graft_snapshot(root,p['graph_provider'],graph_path=path,run=run)
   pin=m.pin_graph(root,observed);self.assertEqual(observed,json.loads(Path(pin['path']).read_text())['graph'])
  edges=m.graph_unit_edges(p,observed);self.assertIn('old.py',edges['a']);self.assertEqual([['graft','--version'],['graft','check','--json']],calls)
 def test_public_workflow_plan_adapter_emits_exact_units_and_fingerprints(self):
  p=self.plan()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'zzzops-test-plan.json').write_text(json.dumps(p));[(root/f'{x}.py').write_text(x) for x in 'abc']
   owner=SimpleNamespace(repo=root)
   with mock.patch.object(m,'graft_snapshot',side_effect=ValueError('stale graph')):
    commands,evidence=journeys.z._workflow.Workflow.node_test_plan_commands(owner,{'verification_plan':{'mode':'explicit','selected':['b']}})
   self.assertEqual(['b'],evidence['preview']['selected']);self.assertEqual(['b'],list(evidence['fingerprints']));self.assertEqual([['.agents','b']],json.loads(commands[0][-1]));self.assertEqual(['b'],evidence['partitions'][0]['units'])
 def test_readonly_public_workflow_rejects_plan_execution(self):
  owner=SimpleNamespace()
  with self.assertRaisesRegex(ValueError,'resource authority'):
   journeys.z._workflow.Workflow.node_workspace_proof(owner,{}, {'workspace':{'readonly':True}}, {}, {'verification_plan':{'mode':'full'}})
 def test_current_graph_requires_clean_detached_head_identity_and_widens(self):
  graph={'meta':{'version':1},'nodes':[],'edges':[]};p=self.plan()
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(['git','init','-q'],cwd=root,check=True);[(root/f'{x}.py').write_text(x) for x in 'abc'];(root/'transitive.py').write_text('old');(root/'zzzops-test-plan.json').write_text(json.dumps(p));subprocess.run(['git','add','.'],cwd=root,check=True);subprocess.run(['git','-c','user.name=t','-c','user.email=t@t','commit','-qm','x'],cwd=root,check=True);owner=SimpleNamespace(repo=root);(root/'transitive.py').write_text('changed');(root/'untracked-reachable.py').write_text('new')
   with mock.patch.object(m,'graft_snapshot',return_value=graph),mock.patch.object(m,'authenticate_revision_graph',side_effect=ValueError('Graft graph does not match pinned revision')):
    _,evidence=journeys.z._workflow.Workflow.node_test_plan_commands(owner,{'verification_plan':{'mode':'changed','changed':['untracked-reachable.py']}})
   self.assertFalse(evidence['graph']['validated']);self.assertIn('does not match pinned revision',evidence['graph']['fallback_reason']);self.assertNotIn('current',evidence['graph'])
   with mock.patch.object(m,'graft_snapshot',return_value=graph),mock.patch.object(m,'authenticate_revision_graph',side_effect=OSError('graft missing')):
    _,missing=journeys.z._workflow.Workflow.node_test_plan_commands(owner,{'verification_plan':{'mode':'changed','changed':['a.py']}})
   self.assertEqual('graft missing',missing['graph']['fallback_reason'])
   (root/'transitive.py').write_text('old');(root/'untracked-reachable.py').unlink();before=set(Path(tempfile.gettempdir()).glob('zzzops-graft-revision-*'))
   with mock.patch.object(m,'graft_snapshot',return_value=graph),mock.patch.object(m,'authenticate_revision_graph',return_value=None):
    _,clean=journeys.z._workflow.Workflow.node_test_plan_commands(owner,{'verification_plan':{'mode':'full'}})
   self.assertIn('current',clean['graph']);self.assertEqual(before,set(Path(tempfile.gettempdir()).glob('zzzops-graft-revision-*')))
 def test_revision_build_cache_seed_is_untrusted_and_safe(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)/'source';checkout=Path(d)/'checkout';(root/'graft/.cache').mkdir(parents=True);checkout.mkdir();(root/'graft/.cache/extract.json').write_text('poisoned-stale-seed')
   self.assertTrue(m.seed_graft_cache(root,checkout));self.assertEqual('poisoned-stale-seed',(checkout/'graft/.cache/extract.json').read_text())
   shutil.rmtree(checkout/'graft/.cache');(root/'graft/.cache/link').symlink_to('/etc/passwd')
   self.assertFalse(m.seed_graft_cache(root,checkout));self.assertFalse((checkout/'graft/.cache').exists())
 def test_seeded_authentication_still_rebuilds_and_matches_clean_identity(self):
  graph={'meta':{'version':1},'nodes':[],'edges':[]}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(['git','init','-q'],cwd=root,check=True);subprocess.run(['git','-c','user.name=t','-c','user.email=t@t','commit','--allow-empty','-qm','x'],cwd=root,check=True);(root/'graft/.cache').mkdir(parents=True);(root/'graft/.cache/poison').write_text('stale');revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();builds=[]
   def run(command,**kwargs):
    if command[:2]==['graft','--version']:return SimpleNamespace(returncode=0,stdout='0.17.0',stderr='')
    if command[:2]==['graft','build']:
     builds.append((kwargs['cwd']/'graft/.cache/poison').exists());path=kwargs['cwd']/'graft/.graph/wiring.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(graph));return SimpleNamespace(returncode=0,stdout='',stderr='')
    return subprocess.run(command,**kwargs)
   m.authenticate_revision_graph(root,graph,revision,self.plan()['graph_provider'],run=run);self.assertEqual([True],builds)
   shutil.rmtree(root/'graft/.cache');m.authenticate_revision_graph(root,graph,revision,self.plan()['graph_provider'],run=run);self.assertEqual([True,False],builds);self.assertEqual(m.digest(graph),m.digest(graph))
 def test_successful_partition_fact_reuses_across_lease_without_rerun(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(['git','init','-q'],cwd=root,check=True);count=root/'count'
   owner=SimpleNamespace(repo=root,repository='owner/repo');command=[sys.executable,'-c',f"from pathlib import Path;p=Path({str(count)!r});p.write_text((p.read_text() if p.exists() else '')+'x')"]
   identity={'semantic_plan':'p','fingerprints':{'u':'f'}};before={'x':'same'};request={'request_id':'one'}
   first=journeys.z._workflow.Workflow.node_verification_commands(owner,{'number':1},{'token':'a','worker':'one','acquisition':{}},request,[command],before,identity)
   second=journeys.z._workflow.Workflow.node_verification_commands(owner,{'number':1},{'token':'b','worker':'two','acquisition':{}},{'request_id':'two'},[command],before,identity)
   self.assertEqual(first,second);self.assertEqual('x',count.read_text())
 def test_parallel_public_runner_preserves_inventory_order_and_cleans_up(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(['git','init','-q'],cwd=root,check=True);owner=SimpleNamespace(repo=root,repository='owner/repo')
   commands=[[sys.executable,'-c',"from pathlib import Path;import time;time.sleep(.05);Path('partition-marker').write_text('x');print(Path.cwd())"] for i in range(3)]
   before=set(Path(tempfile.gettempdir()).glob('zzzops-test-partitions-*'));results=journeys.z._workflow.Workflow.node_verification_commands(owner,{'number':1},{'token':'p','worker':'w','acquisition':{}},{'request_id':'p'},commands,{}, {'inventory':'three'},3,True)
   self.assertEqual(commands,[r['command'] for r in results]);self.assertEqual(3,len(results));self.assertTrue(all(r['exit_code']==0 and r['isolated'] for r in results));self.assertEqual(3,len({Path(r['log']).read_text().strip().splitlines()[-1] for r in results}))
   self.assertFalse((root/'partition-marker').exists());self.assertEqual(before,set(Path(tempfile.gettempdir()).glob('zzzops-test-partitions-*')))
 def test_graph_promotion_is_atomic_and_requires_exact_pin(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(['git','init','-q'],cwd=root,check=True);subprocess.run(['git','-c','user.name=t','-c','user.email=t@t','commit','--allow-empty','-qm','x'],cwd=root,check=True);graph={'meta':{'version':1},'nodes':[],'edges':[]};provider=self.plan()['graph_provider'];pin=m.pin_graph(root,graph,provider);target=m.promote_graph(root,pin)
   with self.assertRaisesRegex(ValueError,'rebuild failed|does not match pinned revision'):m.historical_graph(root,target,provider)
   Path(pin['path']).write_text('{}')
   with self.assertRaisesRegex(ValueError,'changed before promotion'):m.promote_graph(root,pin)
   self.assertEqual(pin['hash'],m.digest(json.loads(target.read_text())))
 def test_parallel_failure_cleans_isolated_filesystems(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);subprocess.run(['git','init','-q'],cwd=root,check=True);owner=SimpleNamespace(repo=root,repository='owner/repo');before=set(Path(tempfile.gettempdir()).glob('zzzops-test-partitions-*'))
   commands=[[sys.executable,'-c',"from pathlib import Path;Path('failed-marker').write_text('x');raise SystemExit(1)"],[sys.executable,'-c','pass']]
   results=journeys.z._workflow.Workflow.node_verification_commands(owner,{'number':2},{'token':'f','worker':'w','acquisition':{}},{'request_id':'f'},commands,{}, {'inventory':'failure'},2,True)
   self.assertEqual([1,0],[r['exit_code'] for r in results]);self.assertFalse((root/'failed-marker').exists());self.assertEqual(before,set(Path(tempfile.gettempdir()).glob('zzzops-test-partitions-*')))
