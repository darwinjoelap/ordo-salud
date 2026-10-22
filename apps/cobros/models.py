"""
Cobros (ADR-011): USD es la moneda base; cada cargo y cada pago CONGELAN la tasa del momento.
- Servicio: catálogo con precio en USD.
- Cargo: lo que se le cobra al paciente (de una consulta, una cita o suelto).
- Pago: lo que el paciente paga (USD o Bs, cualquier método). Se aplica a los cargos pendientes, del más
  viejo al más nuevo; lo que sobra queda como saldo a favor y se aplica al próximo cargo.
"""
from decimal import Decimal

from django.db import models
from django.db.models import Q, Sum

from apps.core.tenancy import Auditable, TenantModel


class Servicio(TenantModel, Auditable):
    nombre = models.CharField('Nombre', max_length=150)
    descripcion = models.CharField('Descripción', max_length=250, blank=True)
    especialidad = models.ForeignKey('plataforma.Especialidad', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='+', verbose_name='Especialidad',
                                     help_text='Vacío = sirve para cualquier especialidad.')
    precio_usd = models.DecimalField('Precio (USD)', max_digits=9, decimal_places=2)
    costo_usd = models.DecimalField('Costo (USD)', max_digits=9, decimal_places=2, null=True, blank=True,
                                    help_text='Opcional (p. ej. vacunas o insumos). Para calcular el ingreso real.')
    activo = models.BooleanField('Activo', default=True)

    class Meta:
        verbose_name = 'Servicio'
        verbose_name_plural = 'Servicios'
        ordering = ['nombre']
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'nombre'], name='servicio_unico'),
            models.CheckConstraint(condition=models.Q(precio_usd__gte=0), name='servicio_precio_no_negativo'),
        ]

    def __str__(self):
        return self.nombre


CERO = Decimal('0.00')


class Cargo(TenantModel, Auditable):
    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PARCIAL = 'PARCIAL', 'Abonado'
        PAGADO = 'PAGADO', 'Pagado'
        ANULADO = 'ANULADO', 'Anulado'

    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='cargos')
    consulta = models.ForeignKey('clinica.Consulta', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='cargos')
    cita = models.ForeignKey('agenda.Cita', on_delete=models.SET_NULL, null=True, blank=True, related_name='cargos')
    procedimiento = models.ForeignKey('clinica.Procedimiento', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='cargos')
    profesional = models.ForeignKey('equipo.PerfilProfesional', on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='cargos')
    servicio = models.ForeignKey(Servicio, on_delete=models.SET_NULL, null=True, blank=True, related_name='cargos')
    fecha = models.DateField('Fecha', db_index=True)
    descripcion = models.CharField('Concepto', max_length=200)
    precio_usd = models.DecimalField('Precio (USD)', max_digits=10, decimal_places=2)
    descuento_usd = models.DecimalField('Descuento (USD)', max_digits=10, decimal_places=2, default=0)
    exonerado = models.BooleanField('Exonerado', default=False)
    costo_usd = models.DecimalField('Costo (USD)', max_digits=10, decimal_places=2, null=True, blank=True)
    tasa = models.DecimalField('Tasa del día (Bs/USD)', max_digits=14, decimal_places=4, null=True, blank=True)
    estado = models.CharField('Estado', max_length=10, choices=Estado.choices, default=Estado.PENDIENTE,
                              db_index=True)
    motivo_anulacion = models.CharField('Motivo de anulación', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Cargo'
        verbose_name_plural = 'Cargos'
        ordering = ['-fecha', '-id']
        constraints = [
            models.CheckConstraint(condition=Q(precio_usd__gte=0), name='cargo_precio_no_negativo'),
            models.CheckConstraint(condition=Q(descuento_usd__gte=0) & Q(descuento_usd__lte=models.F('precio_usd')),
                                   name='cargo_descuento_valido'),
        ]

    def __str__(self):
        return self.descripcion

    @property
    def monto_usd(self):
        if self.exonerado or self.estado == self.Estado.ANULADO:
            return CERO
        return (self.precio_usd - self.descuento_usd).quantize(Decimal('0.01'))

    @property
    def pagado_usd(self):
        total = self.aplicaciones.filter(pago__anulado=False).aggregate(t=Sum('monto_usd'))['t']
        return total or CERO

    @property
    def saldo_usd(self):
        return max(self.monto_usd - self.pagado_usd, CERO)

    @property
    def monto_bs(self):
        return (self.monto_usd * self.tasa).quantize(Decimal('0.01')) if self.tasa else None


class Pago(TenantModel, Auditable):
    class Moneda(models.TextChoices):
        USD = 'USD', 'Dólares'
        BS = 'BS', 'Bolívares'

    class Metodo(models.TextChoices):
        EFECTIVO = 'EFECTIVO', 'Efectivo'
        PAGO_MOVIL = 'PAGO_MOVIL', 'Pago móvil'
        TRANSFERENCIA = 'TRANSFER', 'Transferencia'
        ZELLE = 'ZELLE', 'Zelle'
        PUNTO = 'PUNTO', 'Punto de venta'
        OTRO = 'OTRO', 'Otro'

    paciente = models.ForeignKey('pacientes.Paciente', on_delete=models.PROTECT, related_name='pagos')
    fecha = models.DateField('Fecha', db_index=True)
    moneda = models.CharField('Moneda', max_length=3, choices=Moneda.choices, default=Moneda.USD)
    monto = models.DecimalField('Monto', max_digits=14, decimal_places=2)
    tasa = models.DecimalField('Tasa (Bs/USD)', max_digits=14, decimal_places=4, null=True, blank=True)
    monto_usd = models.DecimalField('Equivalente (USD)', max_digits=12, decimal_places=2)
    metodo = models.CharField('Método', max_length=10, choices=Metodo.choices, default=Metodo.EFECTIVO)
    referencia = models.CharField('Referencia', max_length=60, blank=True)
    notas = models.CharField('Notas', max_length=200, blank=True)
    anulado = models.BooleanField('Anulado', default=False)
    motivo_anulacion = models.CharField('Motivo de anulación', max_length=200, blank=True)

    class Meta:
        verbose_name = 'Pago'
        verbose_name_plural = 'Pagos'
        ordering = ['-fecha', '-id']
        constraints = [models.CheckConstraint(condition=Q(monto__gt=0), name='pago_monto_positivo')]

    def __str__(self):
        return f'{self.get_moneda_display()} {self.monto} · {self.fecha:%d/%m/%Y}'

    @property
    def aplicado_usd(self):
        return self.aplicaciones.aggregate(t=Sum('monto_usd'))['t'] or CERO

    @property
    def sin_aplicar_usd(self):
        return CERO if self.anulado else max(self.monto_usd - self.aplicado_usd, CERO)


class PagoAplicado(TenantModel):
    pago = models.ForeignKey(Pago, on_delete=models.CASCADE, related_name='aplicaciones')
    cargo = models.ForeignKey(Cargo, on_delete=models.CASCADE, related_name='aplicaciones')
    monto_usd = models.DecimalField('Monto aplicado (USD)', max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = 'Aplicación de pago'
        verbose_name_plural = 'Aplicaciones de pagos'
        constraints = [models.CheckConstraint(condition=Q(monto_usd__gt=0), name='aplicado_positivo')]
