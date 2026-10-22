"""
Formulario Django construido desde el esquema de una sección (mismo contrato que validación, PDF y dictado).

    form = FormularioSeccion(campos, data=request.POST, initial=datos_guardados, prefix='s12')
    if form.is_valid(): datos = form.datos_limpios   # listo para JSON

Las tablas se dibujan como filas con columnas (`<prefijo>-<clave>__<fila>__<columna>`).
"""
from django import forms

from apps.core.forms import aplicar_bootstrap, decimales_tolerantes

from . import esquemas

FILAS_TABLA_EXTRA = 1


def _campo_django(c):
    etiqueta = c.get('etiqueta') or c['clave']
    comunes = {'label': etiqueta, 'required': False, 'help_text': c.get('ayuda', '')}
    tipo = c['tipo']
    if tipo == 'texto':
        return forms.CharField(max_length=300, **comunes)
    if tipo == 'texto_largo':
        return forms.CharField(widget=forms.Textarea(attrs={'rows': c.get('filas', 3)}), **comunes)
    if tipo == 'numero':
        dec = int(c.get('decimales', 2))
        attrs = {'inputmode': 'decimal' if dec else 'numeric'}
        if c.get('unidad'):
            attrs['data-unidad'] = c['unidad']
        return forms.DecimalField(decimal_places=dec, max_digits=12, widget=forms.TextInput(attrs=attrs), **comunes)
    if tipo == 'fecha':
        return forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'), **comunes)
    if tipo == 'hora':
        return forms.TimeField(widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'), **comunes)
    if tipo == 'si_no':
        return forms.ChoiceField(choices=[('si', 'Sí'), ('no', 'No')], widget=forms.RadioSelect, **comunes)
    if tipo == 'opcion':
        opciones = esquemas.opciones_de(c)
        if len(opciones) <= 4 and c.get('estilo') != 'lista':
            return forms.ChoiceField(choices=opciones, widget=forms.RadioSelect, **comunes)
        return forms.ChoiceField(choices=[('', '—')] + opciones, **comunes)
    if tipo == 'opciones':
        return forms.MultipleChoiceField(choices=esquemas.opciones_de(c), widget=forms.CheckboxSelectMultiple,
                                         **comunes)
    if tipo == 'escala':
        minimo, maximo = int(c.get('min', 0)), int(c.get('max', 10))
        return forms.ChoiceField(choices=[(str(n), str(n)) for n in range(minimo, maximo + 1)],
                                 widget=forms.RadioSelect, **comunes)
    return None


def _inicial(c, valor):
    if valor is None:
        valor = c.get('por_defecto')
    if valor is None:
        return None
    if c['tipo'] == 'si_no':
        return 'si' if valor in (True, 'si', 'sí') else 'no'
    if c['tipo'] == 'escala':
        return str(valor)
    return valor


class FormularioSeccion(forms.Form):
    def __init__(self, campos, *args, initial=None, contexto=None, exigir_requeridos=True, **kwargs):
        self.campos_def = campos
        self.exigir_requeridos = exigir_requeridos
        self.contexto = contexto or {}
        guardados = initial or {}
        super().__init__(*args, **kwargs)
        self.guardados = guardados
        self.tablas = {}
        for c in campos:
            if c['tipo'] == 'tabla':
                filas = guardados.get(c['clave']) or []
                total = max(len(filas) + FILAS_TABLA_EXTRA, int(c.get('filas', 2)))
                if self.is_bound:
                    total = max(total, self._filas_enviadas(c))
                self.tablas[c['clave']] = []
                for i in range(total):
                    fila = []
                    for sub in c.get('subcampos', []):
                        nombre = f'{c["clave"]}__{i}__{sub["clave"]}'
                        campo = _campo_django({**sub, 'tipo': sub.get('tipo', 'texto'),
                                               'etiqueta': sub.get('etiqueta', sub['clave'])})
                        if sub.get('tipo') == 'opcion':
                            campo = forms.ChoiceField(choices=[('', '—')] + esquemas.opciones_de(sub),
                                                      required=False, label=sub.get('etiqueta'))
                        campo.widget.attrs['placeholder'] = sub.get('etiqueta', sub['clave'])
                        self.fields[nombre] = campo
                        valor = filas[i].get(sub['clave']) if i < len(filas) else None
                        if valor is not None:
                            self.initial[nombre] = valor
                        fila.append((sub, nombre))
                    self.tablas[c['clave']].append(fila)
                continue
            campo = _campo_django(c)
            if campo is None:
                continue
            self.fields[c['clave']] = campo
            inicial = _inicial(c, guardados.get(c['clave']))
            if inicial is not None:
                self.initial[c['clave']] = inicial
        decimales_tolerantes(self)
        aplicar_bootstrap(self)
        for c in campos:              # atributos para el JS de visible_si y la vista previa de calculados
            if c['clave'] in self.fields and c.get('visible_si'):
                self.fields[c['clave']].widget.attrs['data-visible-si'] = _json(c['visible_si'])
            if c['clave'] in self.fields and c.get('no_aplica_si'):
                # «No aplica» (p. ej. ciclo menstrual con histerectomía): se atenúa, pero el dato NO se borra.
                self.fields[c['clave']].widget.attrs['data-no-aplica-si'] = _json(c['no_aplica_si'])

    @property
    def tiene_calculados(self):
        return any(c['tipo'] == 'calculado' for c in self.campos_def)

    @property
    def calculados(self):
        """Valores de los campos calculados: lo recién validado o, si no, lo que ya estaba guardado."""
        fuente = getattr(self, 'datos_limpios', None) or self.guardados
        return {c['clave']: fuente.get(c['clave']) for c in self.campos_def if c['tipo'] == 'calculado'}

    def _filas_enviadas(self, c):
        prefijo = self.add_prefix(f'{c["clave"]}__')
        indices = {int(k[len(prefijo):].split('__')[0]) for k in self.data
                   if k.startswith(prefijo) and k[len(prefijo):].split('__')[0].isdigit()}
        return max(indices) + 1 if indices else 0

    def clean(self):
        datos = super().clean()
        crudo = {}
        for c in self.campos_def:
            if c['tipo'] == 'tabla':
                filas = []
                for fila in self.tablas.get(c['clave'], []):
                    filas.append({sub['clave']: datos.get(nombre) for sub, nombre in fila})
                crudo[c['clave']] = filas
            elif c['clave'] in datos:
                crudo[c['clave']] = datos[c['clave']]
        limpios, errores = esquemas.validar_datos(self.campos_def, crudo, self.contexto, self.exigir_requeridos)
        for clave, mensaje in errores.items():
            if clave in self.fields:
                self.add_error(clave, mensaje.split(': ', 1)[-1])
            else:
                self.add_error(None, mensaje)
        self.datos_limpios = limpios
        return datos

    def items(self):
        """Para la plantilla: [(definición, bound_field | None, filas_tabla | None)] en el orden del esquema."""
        salida = []
        for c in self.campos_def:
            if c['tipo'] == 'tabla':
                filas = [[(sub, self[nombre]) for sub, nombre in fila] for fila in self.tablas.get(c['clave'], [])]
                salida.append({'def': c, 'campo': None, 'filas': filas, 'ancho': esquemas.ancho(c)})
            else:
                salida.append({'def': c, 'campo': self[c['clave']] if c['clave'] in self.fields else None,
                               'filas': None, 'ancho': esquemas.ancho(c)})
        return salida


def _json(valor):
    import json
    return json.dumps(valor, ensure_ascii=False)
