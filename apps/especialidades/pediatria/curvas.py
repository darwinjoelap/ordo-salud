"""
Curvas de crecimiento OMS (P3–P97) con los puntos del paciente. Un solo cálculo de geometría, dos salidas:
SVG para la pantalla (sin librerías ni CDN: funciona sin conexión) y dibujo ReportLab para el PDF.
"""
import math
from html import escape

from . import oms

INDICADORES = {
    'peso': {'titulo': 'Peso para la edad', 'unidad': 'kg', 'campo': 'peso_kg'},
    'talla': {'titulo': 'Talla para la edad', 'unidad': 'cm', 'campo': 'talla_cm'},
    'pc': {'titulo': 'Perímetro cefálico para la edad', 'unidad': 'cm', 'campo': 'pc_cm'},
    'imc': {'titulo': 'IMC para la edad', 'unidad': 'kg/m²', 'campo': 'imc'},
}
ESTILO = {3: ('#9FB4C4', 1.2, '4 3'), 15: ('#1C8577', 1.2, ''), 50: ('#145F8F', 2.2, ''),
          85: ('#1C8577', 1.2, ''), 97: ('#9FB4C4', 1.2, '4 3')}
ANCHO, ALTO = 760, 400
M_IZQ, M_DER, M_SUP, M_INF = 52, 44, 18, 40


def puntos_del_paciente(paciente, indicador, mediciones, nacimiento=None):
    """[(edad_meses, valor, url, etiqueta)] ordenados. `nacimiento` = datos de la ficha perinatal."""
    campo = INDICADORES[indicador]['campo']
    puntos = []
    if nacimiento:
        valor = {'peso': nacimiento.get('peso_nacer_g') and nacimiento['peso_nacer_g'] / 1000,
                 'talla': nacimiento.get('talla_nacer_cm'), 'pc': nacimiento.get('pc_nacer_cm')}.get(indicador)
        if valor:
            puntos.append((0.0, float(valor), None, 'Nacimiento'))
    for m in mediciones:
        v = getattr(m, campo)
        if v is None or m.edad_meses is None:
            continue
        url = f'/consultas/{m.consulta_id}/' if m.consulta_id else None
        puntos.append((float(m.edad_meses), float(v), url, m.fecha.strftime('%d/%m/%Y')))
    return sorted(puntos, key=lambda p: p[0])


def geometria(indicador, sexo, puntos):
    """Escalas, curvas y puntos en coordenadas de dibujo (origen arriba a la izquierda). None sin sexo."""
    try:
        primero, ultimo = oms.rango(indicador, sexo)
    except ValueError:
        return None
    edad_max = max([p[0] for p in puntos] or [0])
    hasta = min(ultimo, max(24, math.ceil(edad_max) + 6))
    if hasta > 60:
        hasta = min(ultimo, int(math.ceil(hasta / 12) * 12))
    desde = primero
    if edad_max > 72:                           # escolares: no hace falta ver desde el nacimiento
        desde = max(primero, int(math.floor((min(p[0] for p in puntos if p[0] > 0) - 24) / 12) * 12))
    paso = 1 if hasta - desde <= 72 else 3
    curvas = oms.curvas(indicador, sexo, hasta, desde_meses=desde, paso=paso)
    visibles = [p for p in puntos if desde <= p[0] <= hasta]
    valores = [v for serie in curvas.values() for _, v in serie] + [p[1] for p in visibles]
    y_min, y_max = min(valores), max(valores)
    margen = (y_max - y_min) * 0.05 or 1
    y_min, y_max = max(0, y_min - margen), y_max + margen
    ancho_util, alto_util = ANCHO - M_IZQ - M_DER, ALTO - M_SUP - M_INF

    def x(mes):
        return M_IZQ + (mes - desde) / (hasta - desde) * ancho_util

    def y(valor):
        return M_SUP + (1 - (valor - y_min) / (y_max - y_min)) * alto_util

    lineas = {p: [(x(m), y(v)) for m, v in serie] for p, serie in curvas.items()}
    años = hasta > 36
    marcas_x = []
    salto = 12 if años and hasta - desde > 60 else (6 if años else 3)
    mes = desde
    while mes <= hasta:
        texto = (f'{mes // 12}a' if mes % 12 == 0 else f'{mes // 12}a{mes % 12}m') if años else f'{mes}m'
        marcas_x.append((x(mes), texto))
        mes += salto
    paso_y = _paso_lindo((y_max - y_min) / 6)
    marcas_y = []
    v = math.ceil(y_min / paso_y) * paso_y
    while v <= y_max:
        marcas_y.append((y(v), f'{v:g}'))
        v += paso_y
    return {
        'indicador': indicador, 'titulo': INDICADORES[indicador]['titulo'], 'unidad': INDICADORES[indicador]['unidad'],
        'lineas': lineas, 'marcas_x': marcas_x, 'marcas_y': marcas_y, 'ancho': ANCHO, 'alto': ALTO,
        'area': (M_IZQ, M_SUP, ancho_util, alto_util),
        'puntos': [(x(m), y(v), url, f'{etq}: {v:g} {INDICADORES[indicador]["unidad"]}') for m, v, url, etq in visibles],
        'etiquetas_p': {p: lineas[p][-1] for p in lineas if lineas[p]},
    }


def _paso_lindo(bruto):
    if bruto <= 0:
        return 1
    exp = 10 ** math.floor(math.log10(bruto))
    for f in (1, 2, 2.5, 5, 10):
        if bruto <= f * exp:
            return f * exp
    return 10 * exp


def svg(g):
    """SVG accesible y liviano para la ficha del paciente."""
    if g is None:
        return ''
    x0, y0, w, h = g['area']
    partes = [f'<svg viewBox="0 0 {g["ancho"]} {g["alto"]}" class="os-curva" role="img" '
              f'aria-label="{escape(g["titulo"])}" xmlns="http://www.w3.org/2000/svg">',
              f'<rect x="{x0}" y="{y0}" width="{w}" height="{h}" fill="#FFFFFF" stroke="#DCE4EB"/>']
    for yy, texto in g['marcas_y']:
        partes.append(f'<line x1="{x0}" y1="{yy:.1f}" x2="{x0 + w}" y2="{yy:.1f}" stroke="#E8EEF3"/>'
                      f'<text x="{x0 - 6}" y="{yy + 4:.1f}" text-anchor="end" class="os-curva-eje">{texto}</text>')
    for xx, texto in g['marcas_x']:
        partes.append(f'<line x1="{xx:.1f}" y1="{y0}" x2="{xx:.1f}" y2="{y0 + h}" stroke="#F3F0EA"/>'
                      f'<text x="{xx:.1f}" y="{y0 + h + 16}" text-anchor="middle" class="os-curva-eje">{texto}</text>')
    for p, pts in g['lineas'].items():
        color, grosor, raya = ESTILO[p]
        camino = ' '.join(f'{a:.1f},{b:.1f}' for a, b in pts)
        partes.append(f'<polyline points="{camino}" fill="none" stroke="{color}" stroke-width="{grosor}"'
                      + (f' stroke-dasharray="{raya}"' if raya else '') + '/>')
        ex, ey = g['etiquetas_p'][p]
        partes.append(f'<text x="{ex + 4:.1f}" y="{ey + 4:.1f}" class="os-curva-p" fill="{color}">P{p}</text>')
    if len(g['puntos']) > 1:
        camino = ' '.join(f'{a:.1f},{b:.1f}' for a, b, _, _ in g['puntos'])
        partes.append(f'<polyline points="{camino}" fill="none" stroke="#0C385B" stroke-width="1.5"/>')
    for a, b, url, titulo in g['puntos']:
        punto = (f'<circle cx="{a:.1f}" cy="{b:.1f}" r="5" fill="#0C385B" stroke="#FFFFFF" stroke-width="1.5">'
                 f'<title>{escape(titulo)}</title></circle>')
        partes.append(f'<a href="{escape(url)}">{punto}</a>' if url else punto)
    partes.append(f'<text x="{x0}" y="{g["alto"] - 4}" class="os-curva-eje">Edad</text>'
                  f'<text x="12" y="{y0 + 4}" class="os-curva-eje">{escape(g["unidad"])}</text></svg>')
    return ''.join(partes)


def dibujo_pdf(g, escala=0.7):
    """reportlab Drawing con la misma geometría (Y invertida)."""
    from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Rect, String
    from reportlab.lib import colors
    alto = g['alto']
    d = Drawing(g['ancho'] * escala, alto * escala)
    d.scale(escala, escala)

    def inv(yy):
        return alto - yy

    x0, y0, w, h = g['area']
    d.add(Rect(x0, inv(y0 + h), w, h, fillColor=colors.white, strokeColor=colors.HexColor('#DCE4EB')))
    for yy, texto in g['marcas_y']:
        d.add(Line(x0, inv(yy), x0 + w, inv(yy), strokeColor=colors.HexColor('#E8EEF3')))
        d.add(String(x0 - 6, inv(yy) - 3, texto, fontSize=8, textAnchor='end', fillColor=colors.HexColor('#4B5E6D')))
    for xx, texto in g['marcas_x']:
        d.add(String(xx, inv(y0 + h) - 14, texto, fontSize=8, textAnchor='middle',
                     fillColor=colors.HexColor('#4B5E6D')))
    for p, pts in g['lineas'].items():
        color, grosor, raya = ESTILO[p]
        linea = PolyLine([c for a, b in pts for c in (a, inv(b))], strokeColor=colors.HexColor(color),
                         strokeWidth=grosor)
        if raya:
            linea.strokeDashArray = [4, 3]
        d.add(linea)
        ex, ey = g['etiquetas_p'][p]
        d.add(String(ex + 4, inv(ey) - 3, f'P{p}', fontSize=8, fillColor=colors.HexColor(color)))
    if len(g['puntos']) > 1:
        d.add(PolyLine([c for a, b, _, _ in g['puntos'] for c in (a, inv(b))],
                       strokeColor=colors.HexColor('#0C385B'), strokeWidth=1.5))
    for a, b, _, _ in g['puntos']:
        d.add(Circle(a, inv(b), 4.5, fillColor=colors.HexColor('#0C385B'), strokeColor=colors.white))
    d.add(String(12, inv(y0) - 4, g['unidad'], fontSize=8, fillColor=colors.HexColor('#4B5E6D')))
    return d
