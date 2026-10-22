"""Recibo de pago (Fase 09/10): lo que pagó el paciente, a qué cargos se aplicó y cómo queda su cuenta."""
from decimal import Decimal

from reportlab.lib.units import mm
from reportlab.platypus import Spacer, Table, TableStyle

from apps.core.pdf import ESTILO_CELDA, Paragraph
from apps.core.templatetags.ordo import bs, usd

from .base import ANCHO, CUERPO, FONDO, LINEA, construir, datos_paciente, lugar_y_fecha, seccion, titulo


def generar(doc, con_firma=True):
    from apps.cobros.models import Pago
    from apps.cobros.servicios import estado_cuenta
    pago = Pago.objects.select_related('paciente').get(pk=doc.datos['pago'])
    monto = bs(pago.monto) if pago.moneda == Pago.Moneda.BS else usd(pago.monto)
    texto = f'Recibimos de <b>{pago.paciente.nombre_completo}</b> la cantidad de <b>{monto}</b>'
    if pago.moneda == Pago.Moneda.BS and pago.tasa:
        texto += f' (equivalente a {usd(pago.monto_usd)} a la tasa de Bs {pago.tasa:.2f} por dólar)'
    texto += f' por medio de {pago.get_metodo_display().lower()}'
    texto += f', referencia {pago.referencia}.' if pago.referencia else '.'
    if pago.anulado:
        texto = f'<font color="#B91C1C"><b>PAGO ANULADO</b> ({pago.motivo_anulacion}).</font> ' + texto
    cuerpo = lugar_y_fecha(pago.fecha) + titulo('Recibo de pago', doc.tenant, doc.numero)
    cuerpo += datos_paciente(pago.paciente, completo=False) + [Spacer(1, 3 * mm), Paragraph(texto, CUERPO)]
    aplicaciones = list(pago.aplicaciones.select_related('cargo'))
    if aplicaciones:
        cuerpo += seccion('Aplicado a', doc.tenant)
        filas = [[Paragraph('<b>Fecha</b>', ESTILO_CELDA), Paragraph('<b>Concepto</b>', ESTILO_CELDA),
                  Paragraph('<b>Monto (USD)</b>', ESTILO_CELDA)]]
        for a in aplicaciones:
            filas.append([Paragraph(f'{a.cargo.fecha:%d/%m/%Y}', ESTILO_CELDA), Paragraph(a.cargo.descripcion, ESTILO_CELDA),
                          Paragraph(usd(a.monto_usd), ESTILO_CELDA)])
        sobrante = pago.sin_aplicar_usd
        if sobrante > Decimal('0'):
            filas.append(['', Paragraph('Saldo a favor del paciente', ESTILO_CELDA), Paragraph(usd(sobrante), ESTILO_CELDA)])
        t = Table(filas, colWidths=[28 * mm, ANCHO - 60 * mm, 32 * mm])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), FONDO), ('LINEBELOW', (0, 0), (-1, -1), 0.4, LINEA),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        cuerpo.append(t)
    cuenta = estado_cuenta(pago.paciente)
    if cuenta['saldo'] > 0:
        cuerpo += [Spacer(1, 3 * mm), Paragraph(f"Saldo pendiente de la cuenta: <b>{usd(cuenta['saldo'])}</b>", CUERPO)]
    elif cuenta['a_favor'] > 0:
        cuerpo += [Spacer(1, 3 * mm), Paragraph(f"Saldo a favor: <b>{usd(cuenta['a_favor'])}</b>", CUERPO)]
    return construir(doc, cuerpo, con_firma=False)
