from __future__ import annotations
import asyncio, hmac, ipaddress, json, logging, os, subprocess, uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal
import httpx, uvicorn, websockets
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from xml.etree import ElementTree as ET

VERSION='0.1.0'
OPT=json.loads(Path('/data/options.json').read_text())
TOKEN=str(OPT.get('mcp_token','')).strip()
if not TOKEN or TOKEN=='CHANGE_ME_BEFORE_STARTING':
    raise RuntimeError('Configure mcp_token first')
PORT=int(OPT.get('port',8765))
BIND=str(OPT.get('bind_host','0.0.0.0'))
MAX_HOSTS=min(max(int(OPT.get('max_scan_hosts',1024)),1),4096)
TIMEOUT=min(max(int(OPT.get('scan_timeout_seconds',900)),30),3600)
ALLOWED=[str(x) for x in OPT.get('allowed_cidrs',[])]
HA_TOKEN=os.environ.get('SUPERVISOR_TOKEN','')
HEAD={'Authorization':f'Bearer {HA_TOKEN}','Content-Type':'application/json'}
HTTP=httpx.AsyncClient(headers=HEAD,timeout=httpx.Timeout(30,read=120))
JOBS:dict[str,dict[str,Any]]={}
logging.basicConfig(level=getattr(logging,str(OPT.get('log_level','INFO')).upper(),logging.INFO))

async def ha_get(path:str):
    r=await HTTP.get('http://supervisor/core/api'+path)
    r.raise_for_status()
    return r.json()

async def ha_ws(kind:str):
    async with websockets.connect('ws://supervisor/core/websocket',max_size=32*1024*1024) as ws:
        hello=json.loads(await ws.recv())
        if hello.get('type')=='auth_required':
            await ws.send(json.dumps({'type':'auth','access_token':HA_TOKEN}))
            auth=json.loads(await ws.recv())
            if auth.get('type')!='auth_ok':
                raise RuntimeError('HA websocket auth failed')
        await ws.send(json.dumps({'id':1,'type':kind}))
        while True:
            m=json.loads(await ws.recv())
            if m.get('id')==1:
                if not m.get('success'):
                    raise RuntimeError(str(m.get('error')))
                return m.get('result',[])

def auto_cidrs()->list[str]:
    try:
        out=subprocess.check_output(['ip','-j','-4','route','show','scope','link'],text=True,timeout=10)
        nets=[]
        for r in json.loads(out):
            dst=r.get('dst')
            if dst and dst!='default':
                try:
                    n=ipaddress.ip_network(dst,strict=False)
                    if n.is_private:
                        nets.append(str(n))
                except ValueError:
                    pass
        return sorted(set(nets))
    except Exception:
        return []

def validate_targets(raw:list[str]|None)->list[str]:
    vals=raw or ALLOWED or auto_cidrs()
    if not vals:
        raise ValueError('No private scan networks detected/configured')
    total=0
    out=[]
    for x in vals:
        n=ipaddress.ip_network(x,strict=False)
        if n.version!=4 or not n.is_private:
            raise ValueError(f'Only private IPv4 networks are allowed: {x}')
        count=n.num_addresses-(2 if n.prefixlen<=30 else 0)
        total+=max(count,0)
        if total>MAX_HOSTS:
            raise ValueError(f'{total} hosts exceed max_scan_hosts={MAX_HOSTS}')
        out.append(str(n))
    return out

def parse_xml(text:str)->list[dict[str,Any]]:
    root=ET.fromstring(text)
    hosts=[]
    for h in root.findall('host'):
        status=h.find('status')
        if status is not None and status.get('state')=='down':
            continue
        item={'ip':None,'mac':None,'vendor':None,'hostnames':[],'ports':[],'os':[]}
        for a in h.findall('address'):
            if a.get('addrtype')=='ipv4':
                item['ip']=a.get('addr')
            elif a.get('addrtype')=='mac':
                item['mac']=a.get('addr')
                item['vendor']=a.get('vendor')
        for hn in h.findall('./hostnames/hostname'):
            if hn.get('name'):
                item['hostnames'].append(hn.get('name'))
        for p in h.findall('./ports/port'):
            st=p.find('state')
            svc=p.find('service')
            if st is None or st.get('state')!='open':
                continue
            item['ports'].append({'port':int(p.get('portid','0')),'protocol':p.get('protocol'),'service':svc.get('name') if svc is not None else None,'product':svc.get('product') if svc is not None else None,'version':svc.get('version') if svc is not None else None,'extra':svc.get('extrainfo') if svc is not None else None})
        for m in h.findall('./os/osmatch')[:5]:
            item['os'].append({'name':m.get('name'),'accuracy':m.get('accuracy')})
        if item['ip']:
            hosts.append(item)
    return hosts

async def run_nmap(targets:list[str],profile:str)->list[dict[str,Any]]:
    args=['nmap','-oX','-','-n','--reason']
    if profile=='quick':
        args += ['-T4','--top-ports','100','-sT']
    elif profile=='standard':
        args += ['-T4','--top-ports','300','-sV','--version-light']
    elif profile=='deep':
        args += ['-T4','--top-ports','1500','-sV','-O','--osscan-limit','--script','banner,http-title,ssl-cert,upnp-info']
    else:
        count=sum(ipaddress.ip_network(t).num_addresses for t in targets)
        if count>32:
            raise ValueError('exhaustive scan is limited to <=32 addresses')
        args += ['-T4','-p-','-sV','-O','--osscan-limit']
    args += targets
    proc=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    out,err=await asyncio.wait_for(proc.communicate(),timeout=TIMEOUT)
    if proc.returncode not in (0,1):
        raise RuntimeError(err.decode(errors='replace')[-2000:])
    return parse_xml(out.decode(errors='replace'))

async def registries():
    kinds={'areas':'config/area_registry/list','devices':'config/device_registry/list','entities':'config/entity_registry/list','floors':'config/floor_registry/list'}
    out={}
    for k,v in kinds.items():
        try:
            out[k]=await ha_ws(v)
        except Exception:
            out[k]=[]
    return out

async def correlate(hosts:list[dict[str,Any]])->list[dict[str,Any]]:
    regs=await registries()
    devices=regs['devices']
    ents=regs['entities']
    by_dev=defaultdict(list)
    for e in ents:
        by_dev[e.get('device_id')].append(e)
    text_index=[]
    for d in devices:
        blob=json.dumps(d,ensure_ascii=False).lower()
        text_index.append((d,blob))
    for h in hosts:
        matches=[]
        ip=(h.get('ip') or '').lower()
        mac=(h.get('mac') or '').lower().replace(':','')
        for d,blob in text_index:
            if (ip and ip in blob) or (mac and mac in blob.replace(':','').replace('-','')):
                matches.append({'device_id':d.get('id'),'name':d.get('name_by_user') or d.get('name'),'manufacturer':d.get('manufacturer'),'model':d.get('model'),'entities':[e.get('entity_id') for e in by_dev.get(d.get('id'),[])][:50]})
        h['home_assistant_matches']=matches
    return hosts

async def job_runner(job_id:str,targets:list[str],profile:str):
    j=JOBS[job_id]
    try:
        j.update(status='running',phase='nmap',progress=10)
        j['events'].append('Nmap discovery/service scan started')
        hosts=await run_nmap(targets,profile)
        j.update(phase='correlation',progress=85)
        j['events'].append(f'{len(hosts)} hosts discovered; correlating with Home Assistant')
        hosts=await correlate(hosts)
        j.update(status='completed',phase='done',progress=100,hosts=hosts)
        j['events'].append('Scan completed')
    except Exception as e:
        j.update(status='failed',phase='failed',error=str(e))
        j['events'].append(f'ERROR: {e}')

mcp=MCPServer('HA Intelligence Bridge',version=VERSION,instructions='Read-only Home Assistant inventory and private LAN/VLAN discovery. Use existing chatgpt_ha_admin MCP for dashboard/config writes.')

@mcp.tool()
async def bridge_status()->dict[str,Any]:
    return {'version':VERSION,'auto_private_cidrs':auto_cidrs(),'configured_allowed_cidrs':ALLOWED,'max_scan_hosts':MAX_HOSTS,'profiles':['quick','standard','deep','exhaustive'],'existing_admin_mcp':'/api/mcp/chatgpt_ha_admin'}

@mcp.tool()
async def ha_summary()->dict[str,Any]:
    states=await ha_get('/states')
    regs=await registries()
    domains=Counter(x.get('entity_id','').split('.',1)[0] for x in states)
    bad=[x['entity_id'] for x in states if x.get('state') in ('unknown','unavailable')]
    return {'entity_count':len(states),'domain_counts':dict(domains),'unavailable_or_unknown_count':len(bad),'unavailable_or_unknown':bad[:500],'area_count':len(regs['areas']),'device_count':len(regs['devices']),'registry_entity_count':len(regs['entities'])}

@mcp.tool()
async def ha_states(query:str='',domain:str|None=None,state:str|None=None,limit:int=500)->dict[str,Any]:
    q=query.casefold()
    out=[]
    for s in await ha_get('/states'):
        eid=s.get('entity_id','')
        if domain and not eid.startswith(domain+'.'):
            continue
        if state and s.get('state')!=state:
            continue
        if q and q not in (eid+' '+str(s.get('attributes',{}).get('friendly_name',''))+' '+str(s.get('state',''))).casefold():
            continue
        out.append(s)
        if len(out)>=min(max(limit,1),1000):
            break
    return {'count':len(out),'entities':out}

@mcp.tool()
async def ha_registry(kind:Literal['areas','devices','entities','floors']='devices',limit:int=1000)->dict[str,Any]:
    r=await registries()
    vals=r.get(kind,[])
    return {'kind':kind,'count':len(vals),'items':vals[:min(max(limit,1),2000)]}

@mcp.tool()
async def ha_house_model()->dict[str,Any]:
    r=await registries()
    areas={x.get('area_id') or x.get('id'):x for x in r['areas']}
    devs={x.get('id'):x for x in r['devices']}
    rooms=defaultdict(lambda:{'devices':[],'entities':[]})
    for d in r['devices']:
        aid=d.get('area_id')
        rooms[aid]['devices'].append({'id':d.get('id'),'name':d.get('name_by_user') or d.get('name'),'manufacturer':d.get('manufacturer'),'model':d.get('model')})
    for e in r['entities']:
        aid=e.get('area_id') or (devs.get(e.get('device_id')) or {}).get('area_id')
        rooms[aid]['entities'].append(e.get('entity_id'))
    result=[]
    for aid,v in rooms.items():
        a=areas.get(aid,{}) if aid else {}
        result.append({'area_id':aid,'area_name':a.get('name') if a else 'Unassigned','device_count':len(v['devices']),'entity_count':len(v['entities']),'devices':v['devices'],'entities':v['entities']})
    return {'rooms':result}

@mcp.tool()
async def network_scan_start(ctx:Context,profile:Literal['quick','standard','deep','exhaustive']='standard',targets:list[str]|None=None)->dict[str,Any]:
    t=validate_targets(targets)
    jid=uuid.uuid4().hex[:12]
    JOBS[jid]={'id':jid,'status':'queued','phase':'queued','progress':0,'profile':profile,'targets':t,'events':['Scan queued'],'hosts':[],'error':None}
    asyncio.create_task(job_runner(jid,t,profile))
    await ctx.info(f'Started private network scan {jid}')
    return {'job_id':jid,'profile':profile,'targets':t}

@mcp.tool()
async def network_scan_status(job_id:str,since_event:int=0)->dict[str,Any]:
    j=JOBS.get(job_id)
    if not j:
        raise ValueError('Unknown job_id')
    ev=j['events']
    return {'job_id':job_id,'status':j['status'],'phase':j['phase'],'progress':j['progress'],'events_total':len(ev),'events':ev[max(0,since_event):],'host_count':len(j.get('hosts',[])),'error':j.get('error')}

@mcp.tool()
async def network_scan_result(job_id:str,offset:int=0,limit:int=100)->dict[str,Any]:
    j=JOBS.get(job_id)
    if not j:
        raise ValueError('Unknown job_id')
    hosts=j.get('hosts',[])
    o=max(offset,0)
    l=min(max(limit,1),500)
    return {'status':j['status'],'total':len(hosts),'offset':o,'returned':len(hosts[o:o+l]),'hosts':hosts[o:o+l]}

@mcp.tool()
async def network_scan_unmanaged(job_id:str)->dict[str,Any]:
    j=JOBS.get(job_id)
    if not j:
        raise ValueError('Unknown job_id')
    hosts=[h for h in j.get('hosts',[]) if not h.get('home_assistant_matches')]
    return {'count':len(hosts),'hosts':hosts}

async def health(_:Request):
    return JSONResponse({'status':'ok','version':VERSION})

class Auth:
    def __init__(self,app):
        self.app=app
    async def __call__(self,scope,receive,send):
        if scope.get('type')!='http' or scope.get('path')=='/health':
            return await self.app(scope,receive,send)
        headers={k.decode().lower():v.decode() for k,v in scope.get('headers',[])}
        a=headers.get('authorization','')
        presented=a[7:] if a.lower().startswith('bearer ') else headers.get('x-bridge-token','')
        if not presented or not hmac.compare_digest(presented,TOKEN):
            body=b'{"error":"Unauthorized"}'
            await send({'type':'http.response.start','status':401,'headers':[(b'content-type',b'application/json'),(b'content-length',str(len(body)).encode())]})
            return await send({'type':'http.response.body','body':body})
        return await self.app(scope,receive,send)

def app():
    sec=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    a=mcp.streamable_http_app(streamable_http_path='/mcp',stateless_http=False,json_response=False,host=BIND,transport_security=sec)
    a.add_route('/health',health,methods=['GET'])
    return Auth(a)

if __name__=='__main__':
    uvicorn.run(app(),host=BIND,port=PORT,log_level=str(OPT.get('log_level','INFO')).lower())
