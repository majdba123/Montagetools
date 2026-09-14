from pathlib import Path
import json
from ortools.sat.python import cp_model
from shapely.geometry import box
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'extension/resources/DEPENDENCY_MANIFEST_V20.json').read_text(encoding='utf-8'));imports={x['import']:x for x in manifest['python_packages']}
assert imports['ortools.sat.python.cp_model']['required'] and imports['ortools.sat.python.cp_model']['pip']=='ortools==9.15.6755';assert imports['shapely.geometry']['required'] and imports['shapely.geometry']['pip']=='shapely==2.1.2'
m=cp_model.CpModel();x=m.NewIntVar(0,3,'x');m.Add(x>=2);s=cp_model.CpSolver();s.parameters.num_search_workers=1;s.parameters.random_seed=0;assert s.Solve(m) in (cp_model.OPTIMAL,cp_model.FEASIBLE) and s.Value(x)>=2
assert abs(box(0,0,1,1).area-1.0)<1e-9
workflow=(ROOT/'.github/workflows/chatgpt-p0-branch-ci.yml').read_text(encoding='utf-8');assert 'ortools==9.15.6755' in workflow and 'shapely==2.1.2' in workflow
print('V31_PROBLEM2_DEPENDENCY_CONTRACT_PASS')
