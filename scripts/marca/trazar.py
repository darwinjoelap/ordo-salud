"""Vectoriza el logo Ordo Salud: segmenta formas por los separadores blancos, traza con potrace y arma SVG."""
import math, json
import numpy as np
from PIL import Image
from scipy import ndimage
import potrace

ESC = 4
im = Image.open('logo-original.png').convert('RGB')
W, H = im.size
big = np.array(im.resize((W * ESC, H * ESC), Image.LANCZOS)).astype(int)
lum = big.sum(axis=2) / 3
sat = big.max(axis=2) - big.min(axis=2)
tinta = (lum < 205) | (sat > 35)


def trazar(mask, ox=0, oy=0):
    bm = potrace.Bitmap(~mask)
    plist = bm.trace(turdsize=20, alphamax=1.0, opticurve=True, opttolerance=0.3)
    d = []
    for curve in plist:
        s = curve.start_point
        d.append(f'M{(s.x)/ESC + ox:.2f},{(s.y)/ESC + oy:.2f}')
        for seg in curve.segments:
            if seg.is_corner:
                d.append(f'L{seg.c.x/ESC + ox:.2f},{seg.c.y/ESC + oy:.2f}L{seg.end_point.x/ESC + ox:.2f},{seg.end_point.y/ESC + oy:.2f}')
            else:
                d.append(f'C{seg.c1.x/ESC + ox:.2f},{seg.c1.y/ESC + oy:.2f} {seg.c2.x/ESC + ox:.2f},{seg.c2.y/ESC + oy:.2f} {seg.end_point.x/ESC + ox:.2f},{seg.end_point.y/ESC + oy:.2f}')
        d.append('Z')
    return ''.join(d)


# ---- ícono ----
x0, y0, x1, y1 = 200 * ESC, 230 * ESC, 660 * ESC, 670 * ESC
sub = tinta[y0:y1, x0:x1]
lab, n = ndimage.label(sub)
comps = sorted([(int((lab == i).sum()), i) for i in range(1, n + 1)], reverse=True)
comps = [i for s, i in comps if s > 500]
info = {}
for i in comps:
    ys, xs = np.where(lab == i)
    info[i] = (xs.min() / ESC + 200, xs.max() / ESC + 200, ys.min() / ESC + 230, ys.max() / ESC + 230)
print(info)
anillo = comps[0]
cruz = [i for i in comps if 330 < info[i][0] < 345][0]
cabezaA = [i for i in comps if 520 < info[i][0] < 530][0]
cabezaB = [i for i in comps if info[i][0] < 230 and info[i][3] < 545][0]
brazo = [i for i in comps if 570 < info[i][0] < 585][0]

CX, CY = 430, 447
m_anillo = lab == anillo
# cola interior: primer tramo de tinta desde adentro, en ángulos 180–258
yy, xx = np.mgrid[0:m_anillo.shape[0], 0:m_anillo.shape[1]]
px = xx / ESC + 200; py = yy / ESC + 230
ang = (np.degrees(np.arctan2(-(py - CY), px - CX)) + 360) % 360
rad = np.hypot(px - CX, py - CY)
cola = np.zeros_like(m_anillo)
for a10 in range(1780, 2600, 2):
    a = a10 / 10
    rs = np.arange(100, 215, 0.25)
    xs_ = ((CX + rs * math.cos(math.radians(a))) - 200) * ESC
    ys_ = ((CY - rs * math.sin(math.radians(a))) - 230) * ESC
    vals = m_anillo[ys_.astype(int), xs_.astype(int)]
    dentro = False; corte = None
    for r, v in zip(rs, vals):
        if v and not dentro: dentro = True
        elif dentro and not v: corte = r; break
    if corte is None: continue
    sel = (ang >= a - 0.25) & (ang < a + 0.25) & (rad < corte) & m_anillo
    cola |= sel
cola = ndimage.binary_closing(cola, iterations=3) & m_anillo
cola = ndimage.binary_opening(cola, iterations=2)

paths = {
    'anillo': trazar(m_anillo, 200, 230), 'cola': trazar(cola, 200, 230), 'cruz': trazar(lab == cruz, 200, 230),
    'cabezaA': trazar(lab == cabezaA, 200, 230), 'cabezaB': trazar(lab == cabezaB, 200, 230),
    'brazo': trazar(lab == brazo, 200, 230),
}

# ---- palabra ----
x0, y0, x1, y1 = 680 * ESC, 290 * ESC, 1460 * ESC, 650 * ESC
sub = tinta[y0:y1, x0:x1]
lab2, n2 = ndimage.label(sub)
letras = []
for i in range(1, n2 + 1):
    m = lab2 == i
    if m.sum() < 400: continue
    ys, xs = np.where(m)
    letras.append((xs.min(), ys.min(), i))
letras.sort()
ordo = [l for l in letras if l[1] < 200 * ESC / ESC * 1 + 0 or True]
ordo = [l for l in letras if (l[1] / ESC + 290) < 420]
salud = [l for l in letras if (l[1] / ESC + 290) >= 540]
print('ordo', len(ordo), 'salud', len(salud))
paths['ord'] = trazar(np.isin(lab2, [l[2] for l in ordo[:3]]), 680, 290)
paths['o_final'] = trazar(lab2 == ordo[3][2], 680, 290)
paths['salud'] = trazar(np.isin(lab2, [l[2] for l in salud]), 680, 290)
json.dump(paths, open('paths.json', 'w'))
print({k: len(v) for k, v in paths.items()})
