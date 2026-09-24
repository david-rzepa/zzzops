"""Local evaluator timing and explicit modeled gateway budgets, not live latency."""
import json
import statistics
import time
from probe import Fixture as Model, Node


def timed(expanded):
    nodes = {f'work/{i}': Node(inputs=(f'work/{i}',)) for i in range(100)}
    inputs = {f'work/{i}': {'item': i} for i in range(100)}
    m = Model({} if expanded else nodes, {} if expanded else inputs)
    if expanded:
        m.expand('work', {str(i): {'item': i} for i in range(100)}, {})
    started = time.perf_counter()
    for _ in range(100):
        assert len(m.ready()) == 100
    return time.perf_counter() - started


class GatewayBudget:
    def __init__(self):
        self.cache = {'goal/498': 'v1', 'pr/538': 'p1'}
        self.calls = []

    def preview(self, goal_revision='v1', selected=True):
        self.calls.extend(['open_goal_index', 'open_pr_index'])
        if selected and self.cache['goal/498'] != goal_revision:
            self.calls.append('exact_goal/498')
            self.cache['goal/498'] = goal_revision
        # Releases explicitly assumed fresh in cache; no release or graph I/O.


if __name__ == '__main__':
    fixed = statistics.median(timed(False) for _ in range(5))
    expanded = statistics.median(timed(True) for _ in range(5))
    warm = GatewayBudget(); warm.preview()
    changed = GatewayBudget(); changed.preview('v2')
    unrelated = GatewayBudget(); unrelated.preview('v2', selected=False)
    report = {'fixed_median_seconds': fixed, 'expanded_median_seconds': expanded,
              'expanded_over_fixed': expanded / fixed,
              'local_threshold_pass': expanded < 1.0 and expanded / fixed < 2.0,
              'modeled_warm_preview_calls': warm.calls,
              'modeled_changed_selected_calls': changed.calls,
              'modeled_changed_unselected_calls': unrelated.calls,
              'live_provider_calls': 0,
              'limitations': 'Synthetic 100 ready tasks x 100 evaluations, 5 trials. Gateway budgets are assumptions tested as a counter model, not observed GitHub request counts; no agent runtime/context overhead measured.'}
    assert len(warm.calls) == 2 and len(changed.calls) == 3 and len(unrelated.calls) == 2
    assert report['local_threshold_pass'], report
    print(json.dumps(report, indent=2))
