"""Evaluation matrix for the reconciliation engine, using synthetic data with known ground truth.
Colab: run reconcile_colab.py's functions first (or keep both files together), then run this."""
import numpy as np, pandas as pd
if 'reconcile' not in globals():
    DEMO=False; exec(open('reconcile_colab.py').read())

def make_data(n=250, seed=42):
    rng = np.random.default_rng(seed)
    vend = ['Acme Supplies','Blue Nile Logistics','Habesha Foods','Addis Telecom','City Power Utility','Office Rent',
            'Zemen Consulting','Fuel Station','Print House','Abay Hardware','Selam Cleaning','Nile Insurance']
    common = [-1000.0,-2500.0,-500.0,-150.0]          # repeated amounts create ambiguity
    L, B = [], []
    for i in range(n):
        d = pd.Timestamp('2026-10-01') + pd.Timedelta(days=int(rng.integers(0,28)))
        v = vend[rng.integers(len(vend))]
        a = float(rng.choice(common)) if rng.random()<.2 else -round(float(rng.uniform(100,9000)),2)
        L.append(dict(date=d, description=f'INV-{1000+i} {v}', amount=a))
        r = rng.random()
        if   r<.60: B.append(dict(date=d, description=f'TRF {v.upper()} REF{1000+i}', amount=a, t=(i,)))
        elif r<.80: B.append(dict(date=d+pd.Timedelta(days=int(rng.integers(0,4))), description=f'{v.split()[0]} payment', amount=a, t=(i,)))
        elif r<.88: B.append(dict(date=d+pd.Timedelta(days=int(rng.integers(0,3))), description=f'POS {int(rng.integers(1000,9999))}', amount=a, t=(i,)))
        elif r<.93: B.append(dict(date=d, description=f'TRF {v.upper()} REF{1000+i}', amount=round(a*(1-rng.uniform(.005,.05)),2), t=(i,)))
        # else: missing from bank
    for k in range(int(n*.04)):                       # batch payments: one bank line pays two invoices
        v = vend[rng.integers(len(vend))]; ids = []
        for _ in range(2):
            d = pd.Timestamp('2026-10-01') + pd.Timedelta(days=int(rng.integers(0,28))); a = -round(float(rng.uniform(100,5000)),2)
            ids.append((len(L), d, a)); L.append(dict(date=d, description=f'INV-{1000+len(L)} {v}', amount=a))
        B.append(dict(date=max(x[1] for x in ids)+pd.Timedelta(days=1), description=f'TRF {v.upper()} REF{1000+ids[0][0]} REF{1000+ids[1][0]}',
                      amount=round(sum(x[2] for x in ids),2), t=(ids[0][0], ids[1][0])))
    for k in range(20):
        B.append(dict(date=pd.Timestamp('2026-10-01')+pd.Timedelta(days=int(rng.integers(0,28))),
                      description=str(rng.choice(['BANK CHARGE','INTEREST CREDIT','SMS FEE'])), amount=float(rng.choice([-45.0,-12.0,12.8])), t=()))
    B = pd.DataFrame(B).sample(frac=1, random_state=seed).reset_index(drop=True)
    truth = {(l, j) for j, r in B.iterrows() for l in r.t}
    return pd.DataFrame(L), B.drop(columns='t'), truth

def entry_matrix(pred, truth, nL, accept):
    """Ledger-entry confusion matrix for rows whose status is in `accept`."""
    has = {l for l,_ in truth}; tp=wrong=fp0=0
    acc = pred[pred.status.isin(accept) & pred.l_idx.notna() & pred.b_idx.notna()]
    for l,b in zip(acc.l_idx.astype(int), acc.b_idx.astype(int)):
        if (l,b) in truth: tp+=1
        elif l in has: wrong+=1
        else: fp0+=1
    fp=wrong+fp0; fn=len(truth)-tp; tn=nL-len(has)-fp0
    prec=tp/max(1,tp+fp); rec=tp/max(1,len(truth)); f1=2*prec*rec/max(1e-9,prec+rec)
    return dict(TP=tp, FP_wrong_partner=wrong, FP_no_counterpart=fp0, FN=fn, TN=tn,
                precision=round(prec,3), recall=round(rec,3), F1=round(f1,3))

def run(fn, L, B, truth, auto=0.7, review=0.5, **kw):
    import time; t0 = time.time(); res = fn(L, B, auto=auto, review=review, **kw); dt = time.time()-t0
    nL = len(L); m_a = entry_matrix(res, truth, nL, ['Matched']); m_r = entry_matrix(res, truth, nL, ['Matched','Review'])
    n_m = (res.status=='Matched').sum(); n_r = ((res.status=='Review')&res.l_idx.notna()).sum()
    return {'auto prec': m_a['precision'], 'auto recall': m_a['recall'], 'assisted prec': m_r['precision'], 'assisted recall': m_r['recall'],
            'F1 assisted': m_r['F1'], 'straight-through %': round(100*n_m/nL,1), 'review %': round(100*n_r/nL,1), 'seconds': round(dt,2)}

if True:
    L, B, truth = make_data(250)
    print(f'{len(L)} ledger, {len(B)} bank lines, {len(truth)} true pairs (incl. split payments)\n')
    rows = {'v1 basic': run(reconcile_basic, L, B, truth), 'v2 engine': run(reconcile, L, B, truth)}
    print(pd.DataFrame(rows).T.to_string(), '\n')
    print('v2 threshold sweep:')
    sw = {f'{a}/{r}': run(reconcile, L, B, truth, auto=a, review=r) for a, r in [(0.9,0.5),(0.8,0.5),(0.7,0.5),(0.6,0.4)]}
    print(pd.DataFrame(sw).T[['auto prec','auto recall','assisted recall','straight-through %','review %']].to_string(), '\n')
    L2, B2, t2 = make_data(5000, seed=1); print('Speed, 5000 ledger rows (v2 only):', run(reconcile, L2, B2, t2)['seconds'], 'seconds')
