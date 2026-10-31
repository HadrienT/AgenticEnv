"""Second pass: maturities that are a whole number of days, so QuantLib and the hand
formulas price the same contract, and the Bermudan target of a 50-date LSM."""
import json, math
from pathlib import Path
import numpy as np
REFS = Path(__file__).with_name('references.py').read_text()
exec(REFS.split('out["asian"] = []')[0])
from scipy.integrate import quad
from scipy.optimize import brentq
exec("def american" + REFS.split("def american")[1].split('out["american"]')[0])
exec("def heston_gp" + REFS.split("def heston_gp")[1].split('out["heston"]')[0])
r = {}
# The geometric formula against QuantLib, on fixings 73 days apart.
r["geo_check"] = [{"p": p, "mine": geo_asian(*p), "ql": ql_geo(*p)} for p in [(100,105,.03,.01,.25,1.0,5),(100,90,.05,0.,.4,2.0,10)]]
r["heston"] = []
days = [(100,100,.02,.01,.04,1.5,.04,.5,-.7,365),(100,50,.02,0.,.04,1.5,.04,.5,-.7,73),(100,200,.02,0.,.09,2.,.09,1.,-.8,146),
        (100,100,0,0,.04,.5,.04,1.,-.9,3650),(100,70,0,0,.04,.5,.04,1.,-.9,3650),(100,140,0,0,.04,.5,.04,1.,-.9,3650),(100,100,0,0,.04,.3,.04,.9,-.5,5475),
        (100,100,0,0,.09,1.,.09,1.,-.3,1825),(100,130,.03,.01,.04,2.,.05,.3,-.5,10950),(100,100,.01,0,.04,1.5,.04,.5,-.7,1),(100,120,.01,0,.2,5.,.04,2.,.5,29)]
for d in days:
    p = list(d[:-1]) + [d[-1]/365]
    r["heston"].append({"p": p, "ql": heston_ql(*p), "gp": heston_gp(*p)})
# Bermudan put with n equally spaced exercise dates, on a CRR tree refined within each date.
def bermudan(S,K,rf,s,T,ex,sub=400):
    N=ex*sub; dt=T/N; u=math.exp(s*math.sqrt(dt)); d=1/u; p=(math.exp(rf*dt)-d)/(u-d); df=math.exp(-rf*dt)
    x=S*u**(N-2*np.arange(N+1.)); v=np.maximum(K-x,0)
    for i in range(N-1,-1,-1):
        v=df*(p*v[:-1]+(1-p)*v[1:])
        if i%sub==0 and i>0:
            x=S*u**(i-2*np.arange(i+1.)); v=np.maximum(v,K-x)
    return float(v[0])
r["bermudan"]=[{"p":p,"v50":bermudan(*p,50)} for p in [(36,40,.06,.2,1.),(36,40,.06,.4,2.),(44,40,.06,.2,1.)]]
r["american"]=[]
for p in [(100,100,.05,.03,.3,1.),(80,100,.02,.04,.25,.6),(100,110,.08,0.,.2,3.),(36,40,.06,0.,.2,1.)]:
    b,f=american(*p); r["american"].append({"p":p,"binom":b,"fd":f})
# Asian for the CUDA bug hunt, fixings at i*T/n, n=12.
e,se=arith_asian(100,100,.05,0.,.2,1.,12,N=80_000_000)
r["cuda_asian"]={"v":e,"se":se}
e,se=arith_asian(100,95,.02,0.,.3,1.,64,N=20_000_000)
r["cuda_multi"]={"v":e,"se":se}
print(json.dumps(r,indent=1))
