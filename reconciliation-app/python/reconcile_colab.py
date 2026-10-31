# Google Colab: paste into a cell and run. Uses sample data, or upload ledger.csv / bank.csv (date,description,amount).
import pandas as pd, numpy as np, re, io
from difflib import SequenceMatcher

STOP=set('trf transfer pos ref payment pmt purchase card debit credit ach eft atm online the and for to of inv invoice'.split())
def norm(s):
    s=re.sub(r'[^a-z0-9]+',' ',str(s).lower()); s=re.sub(r'(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])',' ',s)
    return ' '.join(w for w in s.split() if w not in STOP)

def to_num(v):
    if pd.isna(v): return np.nan
    t=str(v).strip(); neg=bool(re.match(r'^\(.*\)$',t)) or t.endswith('-') or t.startswith('-') or bool(re.search(r'\bDR\b',t,re.I))
    s=re.sub(r'[^\d.,]','',t)
    if not s: return np.nan
    if ',' in s and '.' in s: s=s.replace('.','').replace(',','.') if s.rfind(',')>s.rfind('.') else s.replace(',','')
    elif ',' in s: s=s.replace(',','.') if s.count(',')==1 and re.search(r',\d{1,2}$',s) else s.replace(',','')
    elif s.count('.')>1: s=s.replace('.','')
    n=float(s); return -n if neg and not re.search(r'\bCR\b',t,re.I) else n

SYN={'date':r'date|posted|posting|^dt','debit':r'debit|withdraw|paid out','credit':r'credit|deposit|paid in',
     'amount':r'amount|^amt|^value$|total','description':r'desc|detail|narr|memo|particular|payee|remark|reference|^ref|text|note|name'}

def clean_df(df, flip=False):
    """Normalise any bank/ledger CSV: column names, dates, amounts, debit/credit columns, text."""
    df.columns=[str(c).strip().lower() for c in df.columns]; m={}
    for k,p in SYN.items():
        c=next((c for c in df.columns if c not in m.values() and re.search(p,c)),None)
        if c: m[k]=c
    d=df[m['date']].astype(str)
    pr=d.str.extract(r'^(\d{1,2})[/.\-](\d{1,2})[/.\-]\d{2,4}').astype(float)
    mdy=(pr[1]>12).sum()>(pr[0]>12).sum()
    date=pd.to_datetime(d,dayfirst=not mdy,errors='coerce',format='mixed')
    if 'amount' in m: amt=df[m['amount']].map(to_num)
    else:
        z=lambda k: df[m[k]].map(to_num).abs().fillna(0) if k in m else 0
        amt=z('credit')-z('debit')
    desc=df[m.get('description',df.columns[1])].astype(str).str.replace(r'\s+',' ',regex=True).str.strip()
    out=pd.DataFrame({'date':date,'description':desc,'amount':(-amt if flip else amt).round(2)})
    bad=out.date.isna()|out.amount.isna()
    print(f'{len(out)} rows, {bad.sum()} dropped (bad date/amount), {out.duplicated().sum()} possible duplicates, dates read as {"MM/DD" if mdy else "DD/MM"}')
    return out[~bad].reset_index(drop=True)

def load(name, flip=False):
    """Upload a CSV in Colab; any delimiter. Use flip=True if the bank shows debits as positive."""
    from google.colab import files; up=files.upload()
    return clean_df(pd.read_csv(io.BytesIO(up[name]),sep=None,engine='python',encoding='utf-8-sig'),flip)

def sim(a,b): return SequenceMatcher(None, norm(a), norm(b)).ratio()

def reconcile_basic(L, B, auto=0.8, review=0.5, window=4, tol=0.0):
    pairs=[]
    for i,l in L.iterrows():
        for j,b in B.iterrows():
            dd=abs((l.date-b.date).days); ad=abs(l.amount-b.amount)
            if dd>window or ad>tol: continue
            pairs.append((.45*sim(l.description,b.description)+.3*(1-dd/(window+1))+.25*(ad==0 or .6), i, j))
    pairs.sort(reverse=True); ul,ub,out=set(),set(),[]
    for sc,i,j in pairs:
        if i in ul or j in ub or sc<review*.6: continue
        ul.add(i); ub.add(j)
        out.append(dict(ledger=L.loc[i,'description'], bank=B.loc[j,'description'], amount=L.loc[i,'amount'],
                        l_idx=i, b_idx=j, score=round(sc,2), status='Matched' if sc>=auto else 'Review' if sc>=review else 'Unmatched'))
    for i in set(L.index)-ul: out.append(dict(ledger=L.loc[i,'description'], bank=None, amount=L.loc[i,'amount'], l_idx=i, b_idx=None, score=0, status='Unmatched'))
    for j in set(B.index)-ub: out.append(dict(ledger=None, bank=B.loc[j,'description'], amount=B.loc[j,'amount'], l_idx=None, b_idx=j, score=0, status='Unmatched'))
    return pd.DataFrame(out)

from itertools import combinations
def toks(s): return set(norm(s).split())
def refs(t): return {w for w in t if w.isdigit() and len(w) >= 3}
def tsim(a, b):
    if not a or not b: return 0.0
    i = len(a & b); return 0.5*i/len(a | b) + 0.5*i/min(len(a), len(b))

def reconcile(L, B, auto=0.7, review=0.5, window=4, tol=0.0, tol_pct=0.05, split=True):
    """v2 engine: indexed candidates, token+reference-number similarity, uniqueness (margin) bonus,
    percentage amount tolerance (never auto-accepted), and many-to-one split matching (always reviewed)."""
    L = L.reset_index(drop=True); B = B.reset_index(drop=True)
    Lt = [toks(x) for x in L.description]; Bt = [toks(x) for x in B.description]
    La = L.amount.to_numpy(float); Ba = B.amount.to_numpy(float)
    Ld = L.date.values.astype('datetime64[D]').astype(int); Bd = B.date.values.astype('datetime64[D]').astype(int)
    order = np.argsort(Ba); Bs = Ba[order]; cand = []
    for i in range(len(L)):
        t = max(tol, tol_pct*abs(La[i]))
        lo, hi = np.searchsorted(Bs, [La[i]-t-1e-9, La[i]+t+1e-9])
        for j in order[lo:hi]:
            dd = abs(Ld[i]-Bd[j])
            if dd > window: continue
            ex = abs(La[i]-Ba[j]) < 0.005; s = tsim(Lt[i], Bt[j]); r = bool(refs(Lt[i]) & refs(Bt[j]))
            if not ex and s == 0 and not r: continue          # amount mismatch needs text evidence
            cand.append([.35*s + .25*(1-dd/(window+1)) + .2*(1 if ex else .5) + .2*r, i, j, ex])
    byl, byb = {}, {}
    for c in cand: byl.setdefault(c[1], []).append(c[0]); byb.setdefault(c[2], []).append(c[0])
    def other(d, k, sc):
        v = list(d[k]); v.remove(sc); return max(v, default=0.0)
    for c in cand:
        sc, i, j, ex = c; comp = max(other(byl, i, sc), other(byb, j, sc))
        bonus = .25*max(0, (sc-comp)/sc)*(.5 if abs(La[i]) % 10 < 1e-9 else 1)
        c[0] = min(1.0, sc+bonus) if ex else min(1.0, sc+bonus, auto-1e-6)
    cand.sort(reverse=True); ul, ub, out = set(), set(), []
    st = lambda sc: 'Matched' if sc >= auto else 'Review' if sc >= review else 'Unmatched'
    for sc, i, j, ex in cand:
        if i in ul or j in ub or sc < review*.6: continue
        ul.add(i); ub.add(j)
        out.append(dict(ledger=L.description[i], bank=B.description[j], amount=La[i], l_idx=i, b_idx=j, score=round(sc,2), status=st(sc), type='1:1'))
    if split:                                                   # one bank payment covering several ledger entries
        for j in [j for j in range(len(B)) if j not in ub]:
            near = [i for i in range(len(L)) if i not in ul and La[i]*Ba[j] > 0 and abs(La[i]) < abs(Ba[j])
                    and abs(Ld[i]-Bd[j]) <= window+3 and (tsim(Lt[i], Bt[j]) > 0 or refs(Lt[i]) & refs(Bt[j]))][:12]
            for k in (2, 3, 4):
                hit = next((c for c in combinations(near, k) if abs(sum(La[i] for i in c)-Ba[j]) < 0.005), None)
                if hit:
                    ub.add(j); sc = round(min(.95, .6+.3*np.mean([tsim(Lt[i], Bt[j]) for i in hit])), 2)
                    for i in hit: ul.add(i); out.append(dict(ledger=L.description[i], bank=B.description[j], amount=La[i], l_idx=i, b_idx=j, score=sc, status='Review', type=f'split 1:{k}')) 
                    break
    for i in set(range(len(L)))-ul: out.append(dict(ledger=L.description[i], bank=None, amount=La[i], l_idx=i, b_idx=None, score=0, status='Unmatched', type=''))
    for j in set(range(len(B)))-ub: out.append(dict(ledger=None, bank=B.description[j], amount=Ba[j], l_idx=None, b_idx=j, score=0, status='Unmatched', type=''))
    return pd.DataFrame(out)

# Demo on built-in sample data (skipped when another script sets DEMO=False first)
if globals().get('DEMO', True):
    rng = np.random.default_rng(7)
    names = ['Acme Supplies','Blue Nile Logistics','Habesha Foods','Addis Telecom','Office Rent']
    ledger = pd.DataFrame({'date': pd.Timestamp('2026-10-01')+pd.to_timedelta(rng.integers(0,28,30),'D'),
        'description': [f'INV-{1000+i} {names[i%5]}' for i in range(30)],
        'amount': -np.round(rng.uniform(200,9000,30),2)})
    bank = ledger.drop(ledger.sample(4, random_state=1).index).copy()
    bank['date'] += pd.to_timedelta(rng.integers(0,3,len(bank)),'D')
    bank['description'] = 'TRF ' + bank['description'].str.upper()
    bank.loc[bank.index[:2],'amount'] += 37.5          # amount differences to test review queue

    # Your own files: ledger = load('ledger.csv'); bank = load('bank.csv', flip=False)
    res = reconcile(ledger, bank)
    print(res.status.value_counts()); display(res.sort_values('status'))
    res.to_csv('reconciliation_result.csv', index=False)
    import base64
    from IPython.display import HTML
    b64 = base64.b64encode(res.to_csv(index=False).encode()).decode()
    display(HTML(f'<a download="reconciliation_result.csv" href="data:text/csv;base64,{b64}" style="display:inline-block;font-size:16px;padding:8px 14px;background:#1a9f5c;color:#fff;border-radius:6px;text-decoration:none">Download results CSV</a>'))
    print('Also saved as reconciliation_result.csv (open the folder icon on the left to find it).')
