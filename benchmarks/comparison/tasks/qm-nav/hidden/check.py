import re,sys
qs=[('macro_file', 'include/quantModeling/core/platform\\.hpp'), ('visit_count', '\\b28\\b'), ('tape_sizes', '16384.*32768.*65536'), ('gpu_rng', '(?i)philox\\s*-?\\s*4x32\\s*-?\\s*10|philox4x32_10'), ('digital_adapter', 'price_equity_digital_bs_analytic'), ('unsupported', 'UnsupportedInstrument'), ('sobol_dims', '21\\s?201'), ('host_compiler', '(?is)g\\+\\+-13.*(gcc\\s*14|14)'), ('sobol_direct', 'sobol_point_bits'), ('pde_file', 'src/engines/pde/european_vanilla\\.cpp')]
p=sys.argv[1]+'/ANSWERS.md'
try: lines=open(p).read().splitlines()
except OSError: lines=[]
ans={}
for l in lines:
    m=re.match(r'\s*\**(\d+)\**[:.)]\s*(.*)',l)
    if m: ans[int(m.group(1))]=m.group(2)
for i,(n,r) in enumerate(qs):
    print(('PASS ' if re.search(r,ans.get(i+1,'')) else 'FAIL ')+n)
