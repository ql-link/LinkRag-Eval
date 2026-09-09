"""Small DOM simulation for actual standalone HTML; not a browser/rendering acceptance."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser


class Controls(HTMLParser):
    def __init__(self):
        super().__init__()
        self.nodes = {}
        self.form = None
        self.select = None
        self.option = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "form":
            self.form = values.get("id")
        if values.get("id"):
            self.nodes[values["id"]] = {"tag": tag, "form": self.form, "required": "required" in values,
                                        "hidden": "hidden" in values, "disabled": "disabled" in values,
                                        "type": values.get("type", ""), "checked": "checked" in values,
                                        "value": values.get("value", ""), "options": []}
        if tag == "select":
            self.select = values["id"]
        if tag == "option":
            self.option = [values.get("value"), ""]

    def handle_data(self, data):
        if self.option is not None:
            self.option[1] += data

    def handle_endtag(self, tag):
        if tag == "option" and self.option is not None:
            value, text = self.option
            self.nodes[self.select]["options"].append(text if value is None else value)
            self.option = None
        if tag == "select":
            self.select = None
        if tag == "form":
            self.form = None


def describe(html):
    parser = Controls()
    parser.feed(html)
    scripts = re.findall(r'<script([^>]*)>(.*?)</script>', html, re.DOTALL)
    payload = next((json.loads(body) for attrs, body in scripts if 'id="review-data"' in attrs), None)
    code = '\n'.join(body for attrs, body in scripts if 'application/json' not in attrs)
    return {"nodes": parser.nodes, "payload": payload, "script": code}


HARNESS = r"""
const fs=require('fs'),vm=require('vm'),i=JSON.parse(fs.readFileSync(0,'utf8'));
const nodes={},storage={...(i.storage||{})},events={},downloads=[],blobs={};let sequence=0,selection=null;
function make(id,description={}){
 const n={...description,id,options:[...(description.options||[])],handlers:{},textContent:'',
 appendChild(child){if(this.tag==='select')this.options.push(child.value);},
 addEventListener(k,f){(this.handlers[k]||=[]).push(f);},remove(){},focus(){},
 contains(v){return v===this;},querySelectorAll(){return Object.values(nodes).filter(x=>x.form===id&&['input','select','textarea'].includes(x.tag));},
 click(){if(this.href){downloads.push({filename:this.download,value:JSON.parse(blobs[this.href])});}}};
 let value=description.value||'';
 Object.defineProperty(n,'value',{get(){return value;},set(v){v=String(v);value=this.tag==='select'&&!this.options.includes(v)?'':v;}});
 return n;
}
for(const [id,d] of Object.entries(i.nodes))nodes[id]=make(id,d);
if(i.payload)nodes['review-data'].textContent=JSON.stringify(i.payload);
const node=id=>{if(!nodes[id])throw Error('Missing actual HTML node: '+id);return nodes[id];};
const c={document:{getElementById:node,createElement:tag=>make('',{tag}),body:{appendChild(){}}},
 localStorage:{getItem:k=>{if(i.denyRead)throw Error('SecurityError');return storage[k]??null;},
 setItem:(k,v)=>{if(i.denyWrite)throw Error('QuotaExceededError');storage[k]=v;}},
 Blob:class{constructor(parts){this.text=parts.join('');}},URL:{createObjectURL:b=>{const k='blob:'+(++sequence);blobs[k]=b.text;return k;},revokeObjectURL(){}},
 setTimeout(){},window:{confirm:()=>i.confirm!==false,addEventListener:(k,f)=>events[k]=f,
 getSelection(){return {rangeCount:selection?1:0,getRangeAt:()=>selection};}}};
vm.runInNewContext(i.script,c,{timeout:2000});
async function event(n,k){const e={target:n,preventDefault(){}};for(const f of n.handlers[k]||[])await f(e);
 if(n.form&&n.form!==n.id)for(const f of node(n.form).handlers[k]||[])await f(e);}
(async()=>{
 for(const a of i.actions||[]){
  if(a.kind==='input'){
   const n=node(a.id);if(n.disabled)throw Error('Cannot fill disabled '+a.id);
   n.value=a.value;await event(n,'input');
  }else if(a.kind==='check'){
   const n=node(a.id);n.checked=!!a.checked;await event(n,'change');
  }else if(a.kind==='click'){
   const n=node(a.id);if(n.disabled)continue;if(n.onclick)await n.onclick();await event(n,'click');
  }else if(a.kind==='import')await node('import-file').onchange({target:{files:[{text:async()=>JSON.stringify(a.value)}],value:'file'}});
  else if(a.kind==='capture'){
   const n=node(a.side+'-text'),prefix=Array.from(n.textContent).slice(0,a.start).join(''),quote=Array.from(n.textContent).slice(a.start,a.end).join('');
   selection={startContainer:n,endContainer:n,startOffset:prefix.length,toString:()=>quote,
    cloneRange:()=>({selectNodeContents(){},setEnd(){},toString:()=>prefix})};
   await node(a.side+'-capture').onclick();selection=null;
  }
 }
 process.stdout.write(JSON.stringify({storage,downloads,nodes:Object.fromEntries(Object.entries(nodes).map(([k,n])=>[k,{value:n.value,checked:n.checked,hidden:n.hidden,disabled:n.disabled,text:n.textContent}]))}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
"""


def run(html, **kwargs):
    executable = shutil.which("node")
    if not executable:
        raise RuntimeError("Node is required for the explicit HTML script check")
    result = subprocess.run([executable, "-e", HARNESS],
                            input=json.dumps({**describe(html), **kwargs}),
                            capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)
