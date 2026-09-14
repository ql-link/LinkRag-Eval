import collections,json,re,subprocess,unicodedata
from pathlib import Path
from urllib.parse import unquote
root=Path('/Users/kawauso/Documents/Projects/LinkRag-Eval-issue22-completion')
original=Path('/Users/kawauso/Documents/Projects/LinkRag-Eval')
tracked=set(subprocess.check_output(['git','ls-files'],cwd=root,text=True).splitlines())
files=sorted(p for p in tracked if p.endswith('.md') and not p.startswith(('.ai/','.agents/')))
missing=[];anchors=[];external=0;local=0;only_original=[];local_present_ignored=[]
for f in files:
 p=root/f;text=p.read_text();masked=re.sub(r'```[^\n]*\n.*?```',lambda m:'\n'*m.group(0).count('\n'),text,flags=re.S)
 for m in re.finditer(r'\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)',masked):
  raw=m.group(1).strip('<>');line=masked.count('\n',0,m.start())+1
  if re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:',raw):external+=1;continue
  parts=raw.split('#',1);rel=unquote(parts[0]);path=(p.parent/rel).resolve() if rel else p
  local+=1
  if not path.exists():
   try:other=original/path.relative_to(root)
   except ValueError:other=None
   obj={'source':f,'line':line,'link':raw,'target':str(path)}
   if other and other.exists():only_original.append(obj)
   else:missing.append(obj)
   continue
  try:tr=str(path.relative_to(root))
  except ValueError:tr=None
  if tr not in tracked and path.is_file():local_present_ignored.append({'source':f,'line':line,'link':raw})
  if len(parts)<2 or not parts[1] or path.suffix!='.md':continue
  target=path.read_text();valid=set(re.findall(r'<a\s+(?:id|name)=[\"\']([^\"\']+)',target))
  count=collections.Counter()
  for heading in re.findall(r'^#{1,6}\s+(.+?)\s*#*\s*$',target,re.M):
   heading=re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',heading)
   heading=re.sub(r'<[^>]*>','',heading).replace('`','').lower()
   slug=''.join(ch for ch in heading if ch in (' ','-','_') or unicodedata.category(ch)[0] in 'LN').replace(' ','-')
   n=count[slug];count[slug]+=1;valid.add(slug+(f'-{n}' if n else ''))
  anchor=unquote(parts[1])
  if anchor not in valid:anchors.append({'source':f,'line':line,'link':raw,'note':'heuristic GFM check; manually verify'})
r={'scope_files':len(files),'local_links':local,'external_links_not_validated':external,'missing_in_both_workspaces':missing,'present_only_original_workspace':only_original,'local_ignored_targets_count':len(local_present_ignored),'anchor_candidates':anchors}
Path('/tmp/linkrag-master-audit-20260913/links.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
print({k:v if not isinstance(v,list) else len(v) for k,v in r.items()})
for x in missing: print('MISSING',x['source'],x['line'],x['link'])
for x in anchors: print('ANCHOR?',x['source'],x['line'],x['link'])
