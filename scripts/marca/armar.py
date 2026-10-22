"""Arma los SVG de la marca Ordo Salud a partir de paths.json (trazado) + geometría limpia (cruz, cabezas)."""
import json, math
P = json.load(open('paths.json'))
CX, CY = 430, 447

def hx(c): return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))
def mezcla(a, b, t): return '#%02X%02X%02X' % tuple(round(x + (y - x) * t) for x, y in zip(hx(a), hx(b)))
def escala(stops):
    s = sorted(stops.items())
    def f(a):
        for (a0, c0), (a1, c1) in zip(s, s[1:]):
            if a0 <= a <= a1: return mezcla(c0, c1, (a - a0) / (a1 - a0) if a1 > a0 else 0)
        return s[-1][1] if a > s[-1][0] else s[0][1]
    return f

EXTERIOR = escala({0: '#218AB8', 20: '#2991C0', 45: '#3A99C8', 65: '#3497C7', 80: '#2D8DC0', 100: '#1874A6',
                   120: '#105A89', 140: '#0C4066', 160: '#0C385C', 180: '#0C385C', 185.9: '#0C385C', 186: '#68CAAF',
                   220: '#61C4AB', 240: '#49B099', 250: '#3BA390', 260: '#2E9689', 280: '#1F837F', 300: '#187582',
                   320: '#187694', 340: '#1B82AD', 360: '#218AB8'})
COLA = escala({170: '#0C385C', 190: '#0D3F61', 200: '#0F4966', 210: '#186677', 220: '#288083', 230: '#39968E',
               240: '#4DAE9C', 250: '#5EBEA9', 265: '#66C6AF'})

def cuñas(f, desde, hasta, paso=1.5, r=300):
    out = []
    a = desde
    while a < hasta:
        a1, a2 = math.radians(a - 0.4), math.radians(a + paso + 0.4)
        p1 = (CX + r * math.cos(a1), CY - r * math.sin(a1)); p2 = (CX + r * math.cos(a2), CY - r * math.sin(a2))
        out.append(f'<path d="M{CX},{CY}L{p1[0]:.1f},{p1[1]:.1f}L{p2[0]:.1f},{p2[1]:.1f}Z" fill="{f(a + paso / 2)}"/>')
        a += paso
    return ''.join(out)

CRUZ = ('<rect x="396.5" y="357" width="61" height="181" rx="10"/>'
        '<rect x="337" y="417" width="180" height="61" rx="10"/>')

def defs(pref):
    return f'''<defs>
<clipPath id="{pref}a"><path d="{P['anillo']}"/></clipPath>
<clipPath id="{pref}c"><path d="{P['cola']}"/></clipPath>
<linearGradient id="{pref}x" x1="350" y1="530" x2="505" y2="365" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#1E8075"/><stop offset=".55" stop-color="#3AA28F"/><stop offset="1" stop-color="#52B79F"/></linearGradient>
<linearGradient id="{pref}b" x1="590" y1="320" x2="625" y2="485" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#22897D"/><stop offset=".5" stop-color="#4FB49E"/><stop offset="1" stop-color="#6ACDB4"/></linearGradient>
<radialGradient id="{pref}h" cx=".38" cy=".35" r=".75"><stop offset="0" stop-color="#5CC1A8"/><stop offset="1" stop-color="#46AC95"/></radialGradient>
</defs>'''

def icono(pref='os', color=True):
    if not color:            # monocromo: usa currentColor
        return (f'<path d="{P["anillo"]}"/><path d="{P["brazo"]}"/>{CRUZ}'
                f'<circle cx="553.75" cy="305.4" r="29"/><circle cx="252.25" cy="513.75" r="28.5"/>')
    return (defs(pref)
            + f'<g clip-path="url(#{pref}a)">{cuñas(EXTERIOR, 0, 360)}</g>'
            + f'<g clip-path="url(#{pref}c)">{cuñas(COLA, 170, 265)}</g>'
            + f'<path d="{P["brazo"]}" fill="url(#{pref}b)"/>'
            + f'<g fill="url(#{pref}x)">{CRUZ}</g>'
            + f'<circle cx="553.75" cy="305.4" r="29" fill="#1E7E72"/>'
            + f'<circle cx="252.25" cy="513.75" r="28.5" fill="url(#{pref}h)"/>')

VB_ICONO = '214 231.5 431 431'
def svg(vb, cuerpo, extra=''):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}"{extra}>{cuerpo}</svg>\n'

# palabra: coordenadas del original (paths de letras con offset 680,290 → se reubican)
def palabra(navy='#0C385B', salud='#9DB3AF', o_final=True, pref='os'):
    g = (f'<linearGradient id="{pref}o" x1="1260" y1="560" x2="1450" y2="360" gradientUnits="userSpaceOnUse">'
         '<stop offset="0" stop-color="#1A7A70"/><stop offset=".6" stop-color="#2E9886"/><stop offset="1" stop-color="#66C9B0"/></linearGradient>')
    fill_o = f'url(#{pref}o)' if o_final else navy
    return (f'<defs>{g}</defs><g>'
            f'<path d="{P["ord"]}" fill="{navy}"/><path d="{P["o_final"]}" fill="{fill_o}"/>'
            f'<path d="{P["salud"]}" fill="{salud}"/></g>')

archivos = {
    'ordo-salud-icono.svg': svg(VB_ICONO, icono()),
    'ordo-salud-icono-mono.svg': svg(VB_ICONO, f'<g fill="currentColor">{icono(color=False)}</g>', ' color="#0C385B"'),
    'ordo-salud-icono-blanco.svg': svg(VB_ICONO, f'<g fill="#FFFFFF">{icono(color=False)}</g>'),
    'ordo-salud-logo.svg': svg('205 230 1265 430', icono() + palabra()),
    'ordo-salud-logo-blanco.svg': svg('205 230 1265 430', f'<g fill="#FFFFFF">{icono(color=False)}</g>'
                                      + palabra(navy='#FFFFFF', salud='#BFD6DC', o_final=False)),
    'ordo-salud-palabra.svg': svg('680 290 785 365', palabra()),
}
for nombre, contenido in archivos.items():
    open(nombre, 'w').write(contenido)
    print(nombre, len(contenido) // 1024, 'KB')
