"""Documentos comunes a todas las especialidades (Fase 10)."""
from . import forms
from .generadores import clinicos, historia, recibo, recipe
from .registro import DocumentoDef, registrar

RECIPE = registrar(DocumentoDef('recipe', 'Récipe e indicaciones', prefijo='RCP', generar=recipe.generar,
                                requiere_consulta=True, icono='bi-capsule', orden=10,
                                descripcion='Rp. e indicaciones en media carta cada uno, desde la prescripción.'))
INFORME = registrar(DocumentoDef('informe', 'Informe médico', prefijo='INF', generar=clinicos.informe,
                                 formulario=forms.InformeForm, requiere_consulta=True, icono='bi-file-medical',
                                 orden=20, descripcion='La consulta completa, con introducción y conclusión opcionales.'))
REFERENCIA = registrar(DocumentoDef('referencia', 'Referencia', prefijo='REF', generar=clinicos.referencia,
                                    formulario=forms.ReferenciaForm, inicial=clinicos.inicial_referencia,
                                    icono='bi-send', orden=30))
REPOSO = registrar(DocumentoDef('reposo', 'Reposo médico', prefijo='REP', generar=clinicos.reposo,
                                formulario=forms.ReposoForm, inicial=clinicos.inicial_reposo,
                                icono='bi-hospital', orden=40))
CONSTANCIA = registrar(DocumentoDef('constancia', 'Constancia de asistencia', prefijo='CON', generar=clinicos.constancia,
                                    formulario=forms.ConstanciaForm, inicial=clinicos.inicial_constancia,
                                    icono='bi-patch-check', orden=50))
HISTORIA = registrar(DocumentoDef('historia', 'Historia clínica completa', prefijo='HCL', generar=historia.generar,
                                  formulario=forms.HistoriaForm, icono='bi-journal-medical', orden=60,
                                  descripcion='Datos, antecedentes, fichas y consultas, para entregar o archivar.'))
RECIBO = registrar(DocumentoDef('recibo', 'Recibo de pago', prefijo='RCB', generar=recibo.generar,
                                icono='bi-receipt', orden=90, extra={'interno': True}))
