"""
Prosa del informe de cardiología pediátrica, con las mismas frases y el mismo orden que la Dra. Sierra usa en Word.
Funciones puras (datos → texto): las usan los campos calculados («Así sale en el informe») y el PDF.
Los números van con punto decimal, como en sus informes (0.78 m/s, 33.3 ml/m2SC).
"""
from apps.core.fechas import edad_partes

ROMANOS = [(10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]
GRADO = {'LEVE': 'leve', 'MODERADA': 'moderada', 'SEVERA': 'severa'}
CIA = {'OS': 'ostium secundum', 'OP': 'ostium primum', 'SV': 'seno venoso', 'SC': 'seno coronario'}
SHUNT = {'ID': 'I-D', 'DI': 'D-I', 'BI': 'bidireccional'}
DILATACION = {'NO': 'no dilatado', 'LEVE': 'levemente dilatado', 'MODERADO': 'moderadamente dilatado',
              'SEVERO': 'severamente dilatado'}


def num(valor, decimales=2):
    """10.40 → '10.4' · 7.0 → '7' · None → ''."""
    if valor in (None, ''):
        return ''
    try:
        texto = f'{float(valor):.{decimales}f}'
    except (TypeError, ValueError):
        return str(valor)
    return texto.rstrip('0').rstrip('.') if '.' in texto else texto


def romano(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ''
    salida = ''
    for valor, letra in ROMANOS:
        while n >= valor:
            salida, n = salida + letra, n - valor
    return salida


def gradiente(vmax, medido=None):
    """Gp medido por el equipo o, si no, Bernoulli simplificado 4·v²."""
    if medido not in (None, ''):
        return float(medido)
    if vmax in (None, ''):
        return None
    return round(4 * float(vmax) ** 2, 1)


def _frase(*partes, sep=', '):
    return sep.join(p for p in partes if p)


def _cerrar(texto):
    texto = (texto or '').strip()
    return texto if not texto or texto.endswith('.') else texto + '.'


# ── Antecedentes personales ─────────────────────────────────────────────────────────────────────────────────────
def antecedentes(d):
    d = {k: v for k, v in (d or {}).items() if k != 'texto_informe' and v not in (None, '', [])}
    if not d:
        return ''                     # sin datos no se afirma nada («Niega…» solo si se llenó la ficha)
    frases = []
    madre = f"Producto de madre de {num(d['edad_madre'], 0)} años" if d.get('edad_madre') else ''
    gestas = f"{romano(d['gestas'])}G" if d.get('gestas') else ''
    frases.append(_frase(madre, gestas, (d.get('gestas_detalle') or '').strip()))
    if d.get('semanas') or d.get('embarazo'):
        embarazo = {'SIMPLE': 'simple', 'GEMELAR': 'gemelar', 'MULTIPLE': 'múltiple'}.get(d.get('embarazo'), '')
        termino = {'TERMINO': 'a término', 'PRETERMINO': 'pretérmino', 'POSTERMINO': 'postérmino'}.get(
            d.get('termino'), '')
        semanas = ''
        if d.get('semanas'):
            semanas = f"{num(d['semanas'], 0)}" + (f" + {num(d['dias'], 0)}" if d.get('dias') else '') + ' semanas'
        frases.append(' '.join(p for p in ('Embarazo', embarazo, termino, semanas) if p))
    if d.get('complicaciones'):
        frases.append(f"Complicado con {d['complicaciones'].strip()}")
    elif d.get('semanas') or d.get('embarazo'):
        frases.append('No complicado')
    if d.get('via_parto'):
        via = {'EUTOCICO': 'parto eutócico', 'DISTOCICO': 'parto distócico', 'INSTRUMENTAL': 'parto instrumental',
               'CESAREA': 'cesárea segmentaria'}[d['via_parto']]
        frases.append(_frase(f'Nace a través de {via}', (d.get('via_detalle') or '').strip(), sep=' '))
    if d.get('respiro_lloro') is True:
        frases.append('Respiró y lloró espontáneamente al nacer')
    elif d.get('respiro_lloro') is False:
        frases.append('No respiró ni lloró espontáneamente al nacer')
    medidas = _frase(f"PAN: {_miles(d['pan'])} grs" if d.get('pan') else '',
                     f"TAN: {num(d['tan'], 1)} cms" if d.get('tan') else '')
    if medidas:
        frases.append(medidas)
    if d.get('egreso'):
        frases.append(d['egreso'].strip().rstrip('.'))
    niega, tiene = [], []
    for clave, negado, titulo in (('alergias', 'alergias', 'Alergias'), ('asma', 'asma bronquial', ''),
                                  ('eruptivas', 'eruptivas', 'Eruptivas'),
                                  ('hospitalizaciones', 'ingreso hospitalario', 'Ingreso hospitalario'),
                                  ('intervenciones', 'I/Qx', 'I/Q')):
        valor = d.get(clave)
        if clave == 'asma':
            if valor is True:
                tiene.append('Asma bronquial')
            else:
                niega.append(negado)
        elif valor:
            tiene.append(f'{titulo}: {str(valor).strip().rstrip(".")}')
        else:
            niega.append(negado)
    if niega:
        frases.append('Niega ' + (', '.join(niega[:-1]) + ' e ' + niega[-1] if len(niega) > 1 else niega[0]))
    frases += tiene
    if d.get('otros'):
        frases.append(d['otros'].strip().rstrip('.'))
    if d.get('inmunizaciones'):
        esquema = 'completo' if d['inmunizaciones'] == 'COMPLETO' else 'incompleto'
        documentado = {True: ', documentado', False: ', no documentado'}.get(d.get('inmunizaciones_documentado'), '')
        frases.append(f'Esquema de inmunizaciones {esquema}{documentado}')
    return ' '.join(_cerrar(f) for f in frases if f)


def _miles(gramos):
    """2740 → '2.740' (así lo escribe la doctora)."""
    try:
        return f'{int(round(float(gramos))):,}'.replace(',', '.')
    except (TypeError, ValueError):
        return str(gramos)


# ── Examen físico y EKG ────────────────────────────────────────────────────────────────────────────────────────
def examen_linea(signos, sc=None):
    s = signos or {}
    partes = []
    if s.get('fc'):
        partes.append(f"FC: {num(s['fc'], 0)} lpm")
    if s.get('spo2'):
        partes.append(f"Sat: {num(s['spo2'], 0)} %")
    if s.get('pa_sistolica') and s.get('pa_diastolica'):
        partes.append(f"TA: {num(s['pa_sistolica'], 0)}/{num(s['pa_diastolica'], 0)} mmHg")
    if s.get('peso_kg'):
        partes.append(f"Peso: {num(s['peso_kg'], 2)} Kgs")
    if s.get('talla_cm'):
        partes.append(f"Talla: {num(s['talla_cm'], 1)} cm")
    sc = sc or s.get('superficie_corporal')
    if sc:
        partes.append(f'SC: {num(sc, 2)} m2SC')
    return ', '.join(partes)


def qtc(d):
    try:
        qt, fc = float(d['qt']), float(d['fc'])
    except (KeyError, TypeError, ValueError):
        return None
    if fc <= 0:
        return None
    return round(qt / (60 / fc) ** 0.5, 2)


def ekg_linea(d):
    d = d or {}
    if not any(d.get(k) not in (None, '') for k in ('fc', 'pr', 'qrs', 'qt', 'eje_p', 'eje_qrs')):
        return ''
    valores = [d.get('ritmo') or '-', num(d.get('fc'), 0) or '-', num(d.get('pr'), 2) or '-',
               num(d.get('qrs'), 2) or '-', num(d.get('qt'), 2) or '-', num(qtc(d), 2) or '-',
               f"{num(d['eje_p'], 0)}°" if d.get('eje_p') not in (None, '') else '-',
               f"{num(d['eje_qrs'], 0)}°" if d.get('eje_qrs') not in (None, '') else '-']
    linea = '/'.join(valores)
    if d.get('trazo'):
        linea += f". Trazo: {_cerrar(d['trazo'])}"
    return linea


# ── Ecocardiograma ────────────────────────────────────────────────────────────────────────────────────────────
def _z(d, clave):
    return f"(Zscore: {num(d[clave], 2)})" if d.get(clave) not in (None, '') else ''


def _flujo(d, vmax, gp_medido=None, texto='captándose v máx'):
    if d.get(vmax) in (None, ''):
        return f"Gp: {num(d[gp_medido], 1)} mmHg" if gp_medido and d.get(gp_medido) not in (None, '') else ''
    gp = gradiente(d.get(vmax), d.get(gp_medido) if gp_medido else None)
    return f"{texto}: {num(d[vmax], 2)} m/s" + (f", Gp: {num(gp, 1)} mmHg" if gp is not None else '')


def _valvula_av(d, nombre, p):
    """Tricúspide / mitral: anillo, Z, ondas E y A, regurgitación, Vmáx y gradiente."""
    if not any(d.get(f'{p}_{k}') not in (None, '') for k in ('anillo', 'e', 'a', 'ir', 'vmax', 'jets', 'detalle')):
        return ''
    partes = [_frase(f"anillo {num(d[f'{p}_anillo'], 1)} mm" if d.get(f'{p}_anillo') else '', _z(d, f'{p}_z'),
                     sep=' ')]
    if d.get(f'{p}_e'):
        partes.append(f"Onda E: {num(d[f'{p}_e'], 2)} m/s")
    if d.get(f'{p}_a'):
        partes.append(f"Onda A: {num(d[f'{p}_a'], 2)} m/s")
    grado = d.get(f'{p}_ir')
    if grado in GRADO:
        jets = (d.get(f'{p}_jets') or 'jet').strip()
        partes.append(f'{jets} de regurgitación {GRADO[grado]}')
    elif grado == 'NO':
        partes.append('competente')
    partes.append(_flujo(d, f'{p}_vmax', f'{p}_gp_medido'))
    partes.append((d.get(f'{p}_detalle') or '').strip())
    return f'{nombre}: ' + _frase(*partes) + '.'


def _auricula(d, nombre, p):
    if not any(d.get(f'{p}_{k}') not in (None, '') for k in ('area', 'vol')) and d.get(f'{p}_estado') != 'DILATADA':
        return ''
    estado = 'dilatada' if d.get(f'{p}_estado') == 'DILATADA' else 'no dilatada'
    partes = [f"área: {num(d[f'{p}_area'], 2)} cm2" if d.get(f'{p}_area') else '',
              f"vol: {num(d[f'{p}_vol'], 1)} ml" if d.get(f'{p}_vol') else '']
    index = d.get(f'{p}_vol_index')
    if index:
        partes.append(f'vol índex: {num(index, 1)} ml/m2SC')
    return f'{nombre} {estado}: ' + _frase(*partes) + '.'


def eco(d, sc=None):
    """Prosa del ecocardiograma transtorácico (orden y frases del modelo de la doctora)."""
    d = dict(d or {})
    for p in ('ad', 'ai'):
        if d.get(f'{p}_vol') and sc and not d.get(f'{p}_vol_index'):
            d[f'{p}_vol_index'] = round(float(d[f'{p}_vol']) / float(sc), 1)
    o = []
    situs = {'SOLITUS': 'Situs solitus', 'INVERSUS': 'Situs inversus', 'AMBIGUO': 'Situs ambiguo'}.get(d.get('situs'))
    apex = {'LEVO': 'levocardia', 'DEXTRO': 'dextrocardia', 'MESO': 'mesocardia'}.get(d.get('apex'))
    if situs or apex:
        o.append(_frase(situs, f'ápex en {apex}' if apex else '') + '.')
    rvs = ''
    if d.get('rvs'):
        rvs = 'Retornos venosos sistémicos ' + ('normales' if d['rvs'] == 'NORMALES' else
                                                 _frase('anómalos', d.get('rvs_detalle'), sep=': '))
    vci = f"VCI: {num(d['vci'], 1)} mm" if d.get('vci') else ''
    colapso = {'MAYOR': 'con colapso inspiratorio > al 50%', 'MENOR': 'con colapso inspiratorio < al 50%'}.get(
        d.get('vci_colapso'), '')
    if rvs or vci:
        o.append(_frase(rvs, vci, colapso) + '.')
    if d.get('rvp'):
        o.append('Retornos venosos pulmonares ' + ('normales' if d['rvp'] == 'NORMALES' else
                                                   _frase('anómalos', d.get('rvp_detalle'), sep=': ')) + '.')
    tia = d.get('tia')
    if tia == 'INTACTO':
        o.append('Tabique interatrial: intacto.')
    elif tia == 'FOP':
        o.append(_frase('Tabique interatrial: foramen oval permeable',
                        f"shunt {SHUNT[d['cia_shunt']]}" if d.get('cia_shunt') in SHUNT else '') + '.')
    elif tia == 'DEFECTO':
        medidas = ' x '.join(f'{num(d[k], 1)} mm' for k in ('cia_mm1', 'cia_mm2') if d.get(k))
        defecto = _frase(f"defecto {CIA.get(d.get('cia_tipo'), '')}".strip(), medidas, sep=': ')
        bordes = [f"{n}: {num(d[k], 1)} mm" for k, n in (('borde_ps', 'borde posterosuperior'),
                                                          ('borde_pi', 'borde posteroinferior'),
                                                          ('borde_as', 'anterosuperior'), ('borde_ai', 'anteroinferior'))
                  if d.get(k)]
        texto = _frase('Tabique interatrial: ' + defecto, *bordes,
                       f"shunt {SHUNT[d['cia_shunt']]}" if d.get('cia_shunt') in SHUNT else '') + '.'
        if d.get('qpqs'):
            texto += f" QpQs: {num(d['qpqs'], 1)}:1."
        o.append(texto)
    o += [t for t in (_auricula(d, 'Aurícula derecha', 'ad'), _auricula(d, 'Aurícula izquierda', 'ai')) if t]
    if d.get('conexion_av'):
        o.append('Conexión AV ' + {'CONCORDANTE': 'concordante', 'DISCORDANTE': 'discordante',
                                   'UNIVENTRICULAR': 'univentricular', 'AUSENTE': 'ausente'}[d['conexion_av']] + '.')
    o += [t for t in (_valvula_av(d, 'Tricúspide', 'tric'), _valvula_av(d, 'Mitral', 'mit')) if t]
    tiv = d.get('tiv')
    if tiv:
        if tiv == 'INTACTO':
            base = 'intacto'
        elif tiv == 'CERRADO':
            base = 'cierre quirúrgico con parche'
        else:
            tipo = {'PERIMEMBRANOSA': 'perimembranosa', 'MUSCULAR': 'muscular', 'ENTRADA': 'de entrada',
                    'SUBARTERIAL': 'subarterial'}.get(d.get('civ_tipo'), '')
            base = _frase(f'CIV {tipo}'.strip() + (f" de {num(d['civ_mm'], 1)} mm" if d.get('civ_mm') else ''),
                          f"shunt {SHUNT[d['civ_shunt']]}" if d.get('civ_shunt') in SHUNT else '')
        detalle = (d.get('tiv_detalle') or '').strip().rstrip('.')
        o.append(_frase('Tabique interventricular: ' + base, detalle[:1].lower() + detalle[1:],
                        'movimiento septal paradójico' if d.get('tiv_movimiento') == 'PARADOJICO' else '') + '.')
    vd = [DILATACION.get(d.get('vd_estado'), '')]
    vd += [f"{n}: {num(d[k], 1)} mm" for k, n in (('vd_db', 'DB'), ('vd_dm', 'DM'), ('vd_dl', 'DL'),
                                                 ('tapse', 'TAPSE')) if d.get(k)]
    if d.get('vd_s'):
        vd.append(f"s’: {num(d['vd_s'], 2)} m/s")
    if any(vd):
        texto = 'Ventrículo derecho: ' + _frase(*vd) + '.'
        areas = _frase(f"Área en diástole {num(d['vd_area_d'], 2)} cm2" if d.get('vd_area_d') else '',
                       f"Área en sístole {num(d['vd_area_s'], 2)} cm2" if d.get('vd_area_s') else '',
                       f"CAF: {num(caf(d), 1)} %" if caf(d) is not None else '')
        o.append(texto + (f' {areas}.' if areas else ''))
    vi = [f"{n}: {num(d[k], 1)} mm" for k, n in (('sivd', 'SIVd'), ('ddvi', 'DdVI'), ('ppd', 'PPd'), ('sivs', 'SIVs'),
                                                 ('dsvi', 'DsVI'), ('pps', 'PPs')) if d.get(k)]
    fevi_txt = (d.get('fevi') or '').strip()
    if not fevi_txt and fevi(d) is not None:
        fevi_txt = f'{num(fevi(d), 0)} %'
    if fevi_txt:
        vi.append(f'FEVI: {fevi_txt}' + ('' if '%' in fevi_txt else ' %'))
    if vi:
        o.append('Ventrículo izquierdo: ' + _frase(*vi) + '.')
    tsvd = _frase(f"diámetro {num(d['tsvd_mm'], 1)} mm" if d.get('tsvd_mm') else '',
                  (d.get('tsvd_detalle') or '').strip().rstrip('.'), _flujo(d, 'tsvd_vmax'))
    if tsvd:
        o.append(f'TSVD: {tsvd}.')
    if d.get('conexion_va'):
        o.append('Conexión VA ' + {'CONCORDANTE': 'concordante', 'DISCORDANTE': 'discordante',
                                   'DSVD': 'doble salida del VD', 'UNICA': 'salida única'}[d['conexion_va']] + '.')
    pulm = _frase(_frase(f"anillo: {num(d['pulm_anillo'], 1)} mm" if d.get('pulm_anillo') else '', _z(d, 'pulm_z'),
                         sep=' '),
                  (d.get('pulm_detalle') or '').strip().rstrip('.'), _flujo(d, 'pulm_vmax'),
                  f"insuficiencia {GRADO[d['pulm_ip']]}" if d.get('pulm_ip') in GRADO else '')
    if pulm:
        o.append(f'Pulmonar: {pulm}.')
    ramas = []
    if d.get('tap_mm') or d.get('tap_detalle'):
        ramas.append('TAP: ' + _frase(_frase((d.get('tap_detalle') or '').strip(),
                                             f"{num(d['tap_mm'], 1)} mm" if d.get('tap_mm') else '', sep=': '),
                                      _z(d, 'tap_z'), _flujo(d, 'tap_vmax')))
    for p, n in (('rd', 'RD'), ('ri', 'RI')):
        if d.get(f'{p}_mm'):
            ramas.append(f'{n}: ' + _frase(_frase(f"{num(d[f'{p}_mm'], 1)} mm", _z(d, f'{p}_z'), sep=' '),
                                           _flujo(d, f'{p}_vmax', texto='vmáx')))
    if d.get('ramas'):
        ramas.append('ramas pulmonares ' + ('confluentes' if d['ramas'] == 'CONFLUENTES' else 'no confluentes'))
    ductus = {'NO': 'no se capta flujo de ductus', 'LIGADO': 'ductus ligado'}.get(d.get('ductus'), '')
    if d.get('ductus') == 'PERMEABLE':
        ductus = _frase('ductus permeable' + (f" de {num(d['ductus_mm'], 1)} mm" if d.get('ductus_mm') else ''),
                        f"shunt {SHUNT[d['ductus_shunt']]}" if d.get('ductus_shunt') in SHUNT else '')
    if ductus:
        ramas.append(ductus)
    if ramas:
        o.append(_cerrar('. '.join(r[0].upper() + r[1:] for r in ramas if r)))
    ao = []
    if d.get('ao_valva'):
        ao.append({'TRIVALVA': 'trivalva', 'BIVALVA': 'bivalva', 'UNIVALVA': 'univalva'}[d['ao_valva']])
    if d.get('ao_anillo'):
        ao.append(_frase(f"anillo: {num(d['ao_anillo'], 1)} mm", _z(d, 'ao_z'), sep=' '))
    if d.get('ao_ia') in GRADO:
        ao.append(f"insuficiencia {GRADO[d['ao_ia']]}")
    elif d.get('ao_ia') == 'NO' or d.get('ao_anillo'):
        ao.append('competente')
    if d.get('ao_vmax'):
        gp = gradiente(d['ao_vmax'])
        ao.append(f"vel: {num(d['ao_vmax'], 2)} m/s" + (f", Gp: {num(gp, 1)} mmHg" if gp and gp >= 10 else ''))
    texto_ao = 'Aorta: ' + _frase(*ao) + '.' if ao else ''
    medidas = _frase(*[f"{n}: {num(d[k], 1)} mm" for k, n in (('ao_sv', 'SV'), ('ao_ust', 'UST'),
                                                              ('ao_asc', 'Ao ascendente')) if d.get(k)])
    if medidas:
        texto_ao += f' {medidas}.'
    if d.get('arco'):
        obst = {'NO': 'sin obstrucción', 'COARTACION': 'con coartación', 'HIPOPLASIA': 'hipoplásico'}.get(
            d.get('arco_obstruccion'), '')
        texto_ao += f" Arco aórtico {'izquierdo' if d['arco'] == 'IZQUIERDO' else 'derecho'} {obst}".rstrip() + '.'
    if d.get('ao_desc_vmax'):
        texto_ao += f" Aorta descendente: vmáx: {num(d['ao_desc_vmax'], 2)} m/s."
    if texto_ao.strip():
        o.append(texto_ao.strip())
    o.append(_pericardio(d))
    if d.get('otros'):
        o.append(_cerrar(d['otros']))
    return ' '.join(t for t in o if t)


def _pericardio(d):
    no, si = [], []
    derrame = d.get('derrame')
    if derrame in (None, ''):
        pass
    elif derrame == 'NO':
        no.append('derrame pericárdico')
    else:
        si.append(f"derrame pericárdico {derrame.lower()}")
    for clave, nombre in (('trombos', 'trombos'), ('vegetaciones', 'vegetaciones')):
        if d.get(clave) is True:
            si.append(nombre)
        elif d.get(clave) is False:
            no.append(nombre)
    partes = []
    if no:
        partes.append('No se observa ' + (', '.join(no[:-1]) + ' ni ' + no[-1] if len(no) > 1 else no[0]) + '.')
    if si:
        partes.append('Se observa ' + ', '.join(si) + '.')
    return ' '.join(partes)


# ── Cálculos de cámaras ────────────────────────────────────────────────────────────────────────────────────────
def caf(d):
    try:
        ad, as_ = float(d['vd_area_d']), float(d['vd_area_s'])
    except (KeyError, TypeError, ValueError):
        return None
    return round((ad - as_) * 100 / ad, 1) if ad > 0 else None


def fa(d):
    try:
        dd, ds = float(d['ddvi']), float(d['dsvi'])
    except (KeyError, TypeError, ValueError):
        return None
    return round((dd - ds) * 100 / dd) if dd > 0 else None


def _teichholz(mm):
    cm = float(mm) / 10
    return 7 / (2.4 + cm) * cm ** 3


def fevi(d):
    try:
        vfd, vfs = _teichholz(d['ddvi']), _teichholz(d['dsvi'])
    except (KeyError, TypeError, ValueError):
        return None
    return round((vfd - vfs) * 100 / vfd) if vfd > 0 else None


def edad_informe(nacimiento, fecha):
    """'2 AÑOS + 11 MESES' · '9 AÑOS' · '7 MESES + 12 DÍAS' (como en el encabezado del informe)."""
    partes = edad_partes(nacimiento, fecha)
    if partes is None:
        return ''
    anios, meses, dias = partes
    if anios:
        texto = f"{anios} AÑO{'S' if anios != 1 else ''}"
        return texto + (f" + {meses} MES{'ES' if meses != 1 else ''}" if meses and anios < 6 else '')
    if meses:
        return f"{meses} MES{'ES' if meses != 1 else ''}" + (f" + {dias} DÍA{'S' if dias != 1 else ''}" if dias else '')
    return f"{dias} DÍA{'S' if dias != 1 else ''}"


def hallazgos(d):
    """Hallazgos del eco en etiquetas cortas (panel de la ficha y reporte). Solo lo anormal."""
    d = d or {}
    salida = []
    if d.get('situs') in ('INVERSUS', 'AMBIGUO'):
        salida.append('Situs ' + d['situs'].lower())
    if d.get('apex') in ('DEXTRO', 'MESO'):
        salida.append({'DEXTRO': 'Dextrocardia', 'MESO': 'Mesocardia'}[d['apex']])
    if d.get('tia') == 'DEFECTO':
        salida.append(_frase(f"CIA {CIA.get(d.get('cia_tipo'), '')}".strip(),
                             f"Qp:Qs {num(d['qpqs'], 1)}:1" if d.get('qpqs') else '', sep=' · '))
    elif d.get('tia') == 'FOP':
        salida.append('Foramen oval permeable')
    if d.get('tiv') == 'DEFECTO':
        salida.append('CIV' + (f" {d['civ_tipo'].lower()}" if d.get('civ_tipo') else ''))
    elif d.get('tiv') == 'CERRADO':
        salida.append('CIV con cierre quirúrgico')
    if d.get('ductus') == 'PERMEABLE':
        salida.append('Ductus permeable')
    for clave, nombre in (('tric_ir', 'Insuficiencia tricuspídea'), ('mit_ir', 'Insuficiencia mitral'),
                          ('pulm_ip', 'Insuficiencia pulmonar'), ('ao_ia', 'Insuficiencia aórtica')):
        if d.get(clave) in ('MODERADA', 'SEVERA'):
            salida.append(f'{nombre} {GRADO[d[clave]]}')
    if d.get('ao_valva') in ('BIVALVA', 'UNIVALVA'):
        salida.append(f"Aorta {d['ao_valva'].lower()}")
    if d.get('arco_obstruccion') in ('COARTACION', 'HIPOPLASIA'):
        salida.append('Coartación de aorta' if d['arco_obstruccion'] == 'COARTACION' else 'Arco aórtico hipoplásico')
    if d.get('vd_estado') in ('MODERADO', 'SEVERO'):
        salida.append(f"VD {DILATACION[d['vd_estado']]}")
    valor = fevi(d)
    if valor is not None and valor < 55 and not d.get('fevi'):
        salida.append(f'FEVI {valor} %')
    if d.get('derrame') in ('LEVE', 'MODERADO', 'SEVERO'):
        salida.append(f"Derrame pericárdico {d['derrame'].lower()}")
    for p, n in (('pulm', 'Anillo pulmonar'), ('tap', 'TAP'), ('ao', 'Anillo aórtico')):
        z = d.get(f'{p}_z')
        if z not in (None, '') and float(z) <= -2:
            salida.append(f'{n} hipoplásico (Z {num(z, 1)})')
    return salida
