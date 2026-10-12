"""Only print import/function names from prior harness; never credential values."""
import ast
from pathlib import Path
root=Path(__file__).resolve().parents[2]/'html 파일 모음/결과/f4_socket_261010_assets/raw'
for relative in ['system_limits.py','original_controller_reference.py','scripts/run_sweep.py']:
 p=root/relative
 if not p.exists():continue
 tree=ast.parse(p.read_text(encoding='utf-8'))
 print(relative)
 for n in tree.body:
  if isinstance(n,(ast.Import,ast.ImportFrom)):print(ast.unparse(n))
 for n in ast.walk(tree):
  if isinstance(n,ast.FunctionDef) and any(s in n.name for s in ['ssh','remote','connect']):print('function',n.name,'line',n.lineno)
 names=[n.id for n in ast.walk(tree) if isinstance(n,ast.Name) and any(s in n.id.lower() for s in ['password','passwd','ssh','host','key'])]
 print('Variable names:',sorted(set(names)))
 for n in tree.body:
  if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('SSH','HOST') for t in n.targets):
   try:
    value=ast.literal_eval(n.value)
    if isinstance(value,(list,tuple)) and not any('pass' in str(v).lower() or str(v)=='-p' for v in value):print('SSH arguments:',value)
    elif isinstance(value,str) and '@' in value:print('Remote account:',value)
   except Exception:pass
