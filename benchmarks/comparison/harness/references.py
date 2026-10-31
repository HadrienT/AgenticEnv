"""Independent truth for the hidden checks: QuantLib where it covers the case, numpy /
mpmath otherwise, and both when they can be compared. Written before any agent ran."""
import json, math
import numpy as np
import QuantLib as ql
from scipy.stats import norm
from scipy.optimize import brentq

ql.Settings.instance().evaluationDate = ql.Date(1, 1, 2030)
today = ql.Date(1, 1, 2030)
dc = ql.Actual365Fixed()
def flat(r): return ql.YieldTermStructureHandle(ql.FlatForward(today, r, dc))
def mat(T): return today + ql.Period(int(round(T * 365)), ql.Days)
out = {}

# Discrete Asian: geometric closed form derived by hand, arithmetic by CV Monte Carlo.
def geo_asian(S, K, r, q, s, T, n):
    t = np.arange(1, n + 1) * T / n
    mu = math.log(S) + (r - q - .5 * s * s) * t.mean()
    cov = np.minimum.outer(t, t)
    var = s * s * cov.sum() / n**2
    d1 = (mu - math.log(K) + var) / math.sqrt(var); d2 = d1 - math.sqrt(var)
    return math.exp(-r * T) * (math.exp(mu + .5 * var) * norm.cdf(d1) - K * norm.cdf(d2))
def arith_asian(S, K, r, q, s, T, n, N=400_000_000, chunk=2_000_000, seed=11):
    rng = np.random.default_rng(seed); dt = T / n; g = geo_asian(S, K, r, q, s, T, n)
    sx = sy = sxx = sxy = syy = 0.0; m = 0
    drift = (r - q - .5 * s * s) * dt; vol = s * math.sqrt(dt)
    for _ in range(N // chunk):
        Z = rng.standard_normal((chunk, n))
        L = np.cumsum(drift + vol * Z, axis=1)
        P = S * np.exp(L)
        d = math.exp(-r * T)
        a = d * np.maximum(P.mean(1) - K, 0)
        b = d * np.maximum(S * np.exp(L.mean(1)) - K, 0)
        sx += a.sum(); sy += b.sum(); sxx += (a*a).sum(); sxy += (a*b).sum(); syy += (b*b).sum(); m += chunk
    beta = (sxy - sx*sy/m) / (syy - sy*sy/m)
    est = sx/m - beta*(sy/m - g)
    va = (sxx - sx*sx/m)/m; vb = (syy - sy*sy/m)/m; cab = (sxy - sx*sy/m)/m
    se = math.sqrt((va - 2*beta*cab + beta*beta*vb)/m)
    return est, se
def ql_geo(S, K, r, q, s, T, n):
    # QuantLib's discrete geometric engine, as the second opinion on the formula.
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)), flat(q), flat(r),
        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), s, dc)))
    fix = [today + ql.Period(int(round(i * T * 365 / n)), ql.Days) for i in range(1, n + 1)]
    opt = ql.DiscreteAveragingAsianOption(ql.Average.Geometric, 1.0, 0, fix,
        ql.PlainVanillaPayoff(ql.Option.Call, K), ql.EuropeanExercise(fix[-1]))
    opt.setPricingEngine(ql.AnalyticDiscreteGeometricAveragePriceAsianEngine(proc))
    return opt.NPV()
out["asian"] = []
for p in [(100, 105, .03, .01, .25, 1.0, 12), (100, 90, .05, 0.0, .4, 2.0, 24)]:
    e, se = arith_asian(*p, N=100_000_000)
    out["asian"].append({"p": p, "geo": geo_asian(*p), "geo_ql": ql_geo(*p), "arith": e, "arith_se": se})

# American put, S, r, q, vol, T: QuantLib binomial + FD agree.
def american(S, K, r, q, s, T, kind="put"):
    proc = ql.BlackScholesMertonProcess(ql.QuoteHandle(ql.SimpleQuote(S)), flat(q), flat(r),
        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.NullCalendar(), s, dc)))
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Put, K), ql.AmericanExercise(today, mat(T)))
    o.setPricingEngine(ql.BinomialVanillaEngine(proc, "crr", 20000)); b = o.NPV()
    o.setPricingEngine(ql.FdBlackScholesVanillaEngine(proc, 2000, 2000)); f = o.NPV()
    return b, f
out["american"] = []
for p in [(36,40,.06,0,.2,1.),(36,40,.06,0,.4,2.),(44,40,.06,0,.2,1.),(100,100,.05,.03,.3,1.),(80,100,.02,.04,.25,.5),(100,110,.08,0,.2,3.)]:
    out["american"].append({"p": p, "binom": american(*p)[0], "fd": american(*p)[1]})

# Heston: QuantLib analytic engine, and independently my Gil-Pelaez with mpmath-free quad.
from scipy.integrate import quad
def heston_gp(S, K, r, q, v0, ka, th, xi, rho, T):
    x = math.log(S/K) + (r-q)*T
    def cf(u):   # Albrecher "little trap" form, of log(S_T/F)
        d = np.sqrt((rho*xi*1j*u - ka)**2 + xi*xi*(1j*u + u*u))
        b = ka - rho*xi*1j*u; g = (b - d)/(b + d)
        C = ka*th/xi**2*((b-d)*T - 2*np.log((1-g*np.exp(-d*T))/(1-g)))
        D = (b-d)/xi**2*(1-np.exp(-d*T))/(1-g*np.exp(-d*T))
        return np.exp(C + D*v0)
    i1 = quad(lambda u: (np.exp(1j*u*x)*cf(u-.5j)/(u*u+.25)).real, 0, 2000, limit=4000, epsabs=1e-12, epsrel=1e-12)[0]
    return S*math.exp(-q*T) - math.sqrt(S*K*math.exp(-(r+q)*T))/math.pi*i1
def heston_ql(S, K, r, q, v0, ka, th, xi, rho, T):
    proc = ql.HestonProcess(flat(r), flat(q), ql.QuoteHandle(ql.SimpleQuote(S)), v0, ka, th, xi, rho)
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, K), ql.EuropeanExercise(mat(T)))
    o.setPricingEngine(ql.AnalyticHestonEngine(ql.HestonModel(proc), 1e-11, 200000)); return o.NPV()
out["heston"] = []
for p in [(100,100,.02,.01,.04,1.5,.04,.5,-.7,1.),(100,50,.02,.0,.04,1.5,.04,.5,-.7,.25),(100,200,.02,.0,.09,2.,.09,1.,-.8,.5),
          (100,100,0,0,.04,.5,.04,1.,-.9,10.),(100,70,0,0,.04,.5,.04,1.,-.9,10.),(100,140,0,0,.04,.5,.04,1.,-.9,10.),(100,100,0,0,.04,.3,.04,.9,-.5,15.),
          (100,100,0,0,.09,1.,.09,1.,-.3,5.),(100,130,.03,.01,.04,2.,.05,.3,-.5,30.),(100,100,.01,0,.04,1.5,.04,.5,-.7,1/365),(100,120,.01,0,.2,5.,.04,2.,.5,.08)]:
    out["heston"].append({"p": p, "ql": heston_ql(*p), "gp": heston_gp(*p)})

# Implied vol sanity, digital call.
def bs(S,K,r,q,s,T,c=True):
    d1=(math.log(S/K)+(r-q+.5*s*s)*T)/(s*math.sqrt(T)); d2=d1-s*math.sqrt(T)
    return (S*math.exp(-q*T)*norm.cdf(d1)-K*math.exp(-r*T)*norm.cdf(d2)) if c else (K*math.exp(-r*T)*norm.cdf(-d2)-S*math.exp(-q*T)*norm.cdf(-d1))

# Hull-White: bond option by QuantLib, Jamshidian by hand AND by exact MC in numpy.
a, sg, r0 = .05, .012, .03
hw = ql.HullWhite(flat(r0), a, sg)
def P(t, T, r=None):
    """Flat curve r0: bond formula."""
    B=(1-math.exp(-a*(T-t)))/a
    lnA=math.log(math.exp(-r0*T)/math.exp(-r0*t))+B*r0-sg*sg/(4*a)*(1-math.exp(-2*a*t))*B*B
    return math.exp(lnA-B*(r0 if r is None else r))
def zbo_call(K,T,S):
    sp=sg*math.sqrt((1-math.exp(-2*a*T))/(2*a))*(1-math.exp(-a*(S-T)))/a
    h=math.log(P(0,S)/(P(0,T)*K))/sp+sp/2
    return P(0,S)*norm.cdf(h)-K*P(0,T)*norm.cdf(h-sp)
def zbo_put(K,T,S):
    return zbo_call(K,T,S)-P(0,S)+K*P(0,T)
def jam_payer(T0,n,tau,K):
    dates=[T0+tau*i for i in range(1,n+1)]; c=[K*tau]*n; c[-1]+=1
    rstar=brentq(lambda r: sum(ci*P(T0,Ti,r) for ci,Ti in zip(c,dates))-1,-1,1,xtol=1e-14)
    return sum(ci*zbo_put(P(T0,Ti,rstar),T0,Ti) for ci,Ti in zip(c,dates))
def jam_mc(T0,n,tau,K,N=40_000_000):
    # Exact joint law of r(T0) and the integral of r under Q (Brigo-Mercurio 3.35-3.40).
    rng=np.random.default_rng(5)
    B=(1-math.exp(-a*T0))/a
    alpha=r0+sg*sg/(2*a*a)*(1-math.exp(-a*T0))**2
    vr=sg*sg/(2*a)*(1-math.exp(-2*a*T0))
    # x(t)=r(t)-alpha(t); I=int x ds
    x_mean=0.0
    Vi=sg*sg/(a*a)*(T0+2/a*math.exp(-a*T0)-1/(2*a)*math.exp(-2*a*T0)-3/(2*a))
    cov=sg*sg/(2*a*a)*(1-math.exp(-a*T0))**2
    z1=rng.standard_normal(N); z2=rng.standard_normal(N)
    x=math.sqrt(vr)*z1
    I=cov/math.sqrt(vr)*z1+math.sqrt(Vi-cov*cov/vr)*z2
    # int alpha = r0 T0 + 0.5*Vi(T0) on a flat curve: discount curve matched exactly.
    disc=math.exp(-r0*T0-.5*Vi)*np.exp(-I)
    r=alpha+x
    dates=[T0+tau*i for i in range(1,n+1)]
    pv=np.zeros(N)
    A=[]
    for Ti in dates:
        Bi=(1-math.exp(-a*(Ti-T0)))/a
        lnA=math.log(math.exp(-r0*Ti)/math.exp(-r0*T0))+Bi*r0-sg*sg/(4*a)*(1-math.exp(-2*a*T0))*Bi*Bi
        pv+=(K*tau+(Ti==dates[-1]))*np.exp(lnA-Bi*r)
    pay=disc*np.maximum(1-pv,0)
    return pay.mean(),pay.std()/math.sqrt(N)
out["hw"]={"a":a,"sigma":sg,"r0":r0,"zcb_5_10":P(5,10,.05),"zbc":zbo_call(.8,5,10),"zbc_ql":hw.discountBondOption(ql.Option.Call,.8,5,10),
 "zbp":zbo_put(.82,2,7),"zbp_ql":hw.discountBondOption(ql.Option.Put,.82,2,7),
 "jam_5x5":jam_payer(5,5,1.,.03),"jam_5x5_mc":jam_mc(5,5,1.,.03),"jam_2x10_semi_otm":jam_payer(2,20,.5,.045),"jam_2x10_mc":jam_mc(2,20,.5,.045)}

# Heston-free checks for the SABR hagan formula reference.
def hagan(F,K,T,al,be,rh,nu):
    if abs(F-K)<1e-12*F:
        return al/F**(1-be)*(1+((1-be)**2/24*al*al/F**(2-2*be)+rh*be*nu*al/(4*F**(1-be))+(2-3*rh*rh)/24*nu*nu)*T)
    lg=math.log(F/K); fk=(F*K)**((1-be)/2)
    z=nu/al*fk*lg
    x=math.log((math.sqrt(1-2*rh*z+z*z)+z-rh)/(1-rh)) if abs(z)>1e-14 else 1
    zx=z/x if abs(z)>1e-14 else 1
    den=fk*(1+(1-be)**2/24*lg*lg+(1-be)**4/1920*lg**4)
    return al/den*zx*(1+((1-be)**2/24*al*al/(fk*fk)+rh*be*nu*al/(4*fk)+(2-3*rh*rh)/24*nu*nu)*T)
out["sabr"]=[{"p":p,"vol":hagan(*p)} for p in [(.03,.03,2,.04,.5,-.3,.5),(.03,.02,2,.04,.5,-.3,.5),(.03,.05,2,.04,.5,-.3,.5),(100,80,1,.25,1.,-.4,.6),(100,130,1,.25,1.,-.4,.6),(.05,.04,5,.007,0.,.2,.3),(.05,.08,5,.007,0.,.2,.3),(.03,.025,1,.04,.5,.3,1e-6)]]

# PDE references: digital and american.
out["digital"]=[{"p":p,"v":math.exp(-p[2]*p[5])*norm.cdf((math.log(p[0]/p[1])+(p[2]-p[3]-.5*p[4]**2)*p[5])/(p[4]*math.sqrt(p[5])))} for p in [(100,100,.05,.02,.2,1.),(95,100,.03,0,.3,.5)]]
print(json.dumps(out,indent=1))
