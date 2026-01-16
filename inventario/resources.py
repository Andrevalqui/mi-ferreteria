from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from .models import Producto, Venta, Proveedor, Compra, Cliente, Comprobante, DetalleComprobante, CajaDiaria, MovimientoCaja
from decimal import Decimal

class CleanForeignKeyWidget(ForeignKeyWidget):
    def clean(self, value, row=None, **kwargs):
        if not value:
            return None
        return self.get_queryset(value, row, **kwargs).get(**{f"{self.field}__iexact": value.strip()})

class ProductoResource(resources.ModelResource):
    class Meta:
        model = Producto
        fields = ('id', 'nombre', 'codigo_barras', 'stock', 'precio', 'costo')
        export_order = fields
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('id',)

    # FIRMA UNIVERSAL: acepta cualquier cantidad de argumentos (*args)
    def before_save_instance(self, instance, row, *args, **kwargs):
        tienda = getattr(self, 'tienda_actual', None)
        if tienda:
            instance.tienda = tienda
        super().before_save_instance(instance, row, *args, **kwargs)

class ClienteResource(resources.ModelResource):
    class Meta:
        model = Cliente
        fields = ('id', 'nombre_completo', 'dni_ruc', 'telefono', 'email', 'pagina_web')
        import_id_fields = ('id',)

    def before_save_instance(self, instance, row, *args, **kwargs):
        tienda = getattr(self, 'tienda_actual', None)
        if tienda:
            instance.tienda = tienda
        super().before_save_instance(instance, row, *args, **kwargs)

class ProveedorResource(resources.ModelResource):
    class Meta:
        model = Proveedor
        fields = ('id', 'razon_social', 'ruc', 'direccion', 'telefono', 'email', 'pagina_web')
        import_id_fields = ('id',)

    def before_save_instance(self, instance, row, *args, **kwargs):
        tienda = getattr(self, 'tienda_actual', None)
        if tienda:
            instance.tienda = tienda
        super().before_save_instance(instance, row, *args, **kwargs)

class CompraResource(resources.ModelResource):
    producto_nuevo_nombre = fields.Field(column_name='producto_nuevo_nombre', attribute='producto_nuevo_nombre')
    producto_nuevo_costo = fields.Field(column_name='producto_nuevo_costo', attribute='producto_nuevo_costo')
    producto_nuevo_precio = fields.Field(column_name='producto_nuevo_precio', attribute='producto_nuevo_precio')

    producto = fields.Field(attribute='producto', column_name='producto_id', widget=ForeignKeyWidget(Producto, 'id'))
    proveedor = fields.Field(attribute='proveedor', column_name='proveedor', widget=CleanForeignKeyWidget(Proveedor, 'razon_social'))

    class Meta:
        model = Compra
        fields = ('id', 'producto_id', 'proveedor', 'cantidad', 'costo_total','producto_nuevo_nombre', 'producto_nuevo_costo', 'producto_nuevo_precio')
        skip_unchanged = True
        report_skipped = False

    def before_import_row(self, row, **kwargs):
        if not row.get('producto_id'):
            nombre = row.get('producto_nuevo_nombre')
            costo = row.get('producto_nuevo_costo')
            precio = row.get('producto_nuevo_precio')
            tienda = getattr(self, 'tienda_actual', None)
            if nombre and tienda:
                nuevo_producto, created = Producto.objects.get_or_create(
                    nombre=nombre,
                    tienda=tienda,
                    defaults={'costo': costo or 0, 'precio': precio or 0, 'stock': 0}
                )
                row['producto_id'] = nuevo_producto.id

    def before_save_instance(self, instance, row, *args, **kwargs):
        tienda = getattr(self, 'tienda_actual', None)
        if tienda:
            instance.tienda = tienda
        super().before_save_instance(instance, row, *args, **kwargs)

class VentaResource(resources.ModelResource):
    producto = fields.Field(attribute='producto', widget=ForeignKeyWidget(Producto, 'nombre'))
    cliente = fields.Field(attribute='cliente', widget=ForeignKeyWidget(Cliente, 'nombre_completo'))
    class Meta:
        model = Venta
        fields = ('id', 'cliente', 'producto', 'cantidad', 'precio_unitario', 'costo_unitario', 'total', 'fecha_de_venta', 'observaciones')

    def before_save_instance(self, instance, row, *args, **kwargs):
        tienda = getattr(self, 'tienda_actual', None)
        if tienda:
            instance.tienda = tienda
        super().before_save_instance(instance, row, *args, **kwargs)

class ComprobanteResource(resources.ModelResource):
    cliente = fields.Field(attribute='cliente', widget=ForeignKeyWidget(Cliente, 'nombre_completo'))
    class Meta:
        model = Comprobante
        fields = ('id', 'tipo_comprobante', 'serie', 'numero', 'fecha_emision', 'cliente', 'cliente__dni_ruc', 'subtotal', 'igv', 'total_final', 'estado', 'observaciones')
        export_order = fields

class DetalleComprobanteResource(resources.ModelResource):
    # Campos personalizados para que el reporte sea más claro
    fecha_emision = fields.Field(attribute='comprobante__fecha_emision', column_name='Fecha de Emisión')
    comprobante_nro = fields.Field(column_name='Comprobante')
    cliente = fields.Field(attribute='comprobante__cliente__nombre_completo', column_name='Cliente')
    producto = fields.Field(attribute='producto__nombre', column_name='Producto')
    precio_unitario_con_igv = fields.Field(column_name='Precio Unit. (inc. IGV)')
    total_venta_item = fields.Field(column_name='Total Venta (inc. IGV)')
    ganancia_item = fields.Field(column_name='Ganancia')

    class Meta:
        model = DetalleComprobante
        # Lista de campos que se incluirán en el Excel y su orden
        fields = ('fecha_emision', 'comprobante_nro', 'cliente', 'producto', 'cantidad', 'precio_unitario_con_igv', 'costo_unitario', 'total_venta_item', 'ganancia_item')
        export_order = fields

    # Método para componer el número de comprobante (ej. B001-5)
    def dehydrate_comprobante_nro(self, detalle):
        return f"{detalle.comprobante.serie}-{detalle.comprobante.numero}"

    # Método para calcular el precio unitario incluyendo el IGV
    def dehydrate_precio_unitario_con_igv(self, detalle):
        precio_con_igv = detalle.precio_unitario * Decimal('1.18')
        return precio_con_igv

    # Método para calcular el total de la línea de venta
    def dehydrate_total_venta_item(self, detalle):
        precio_con_igv = self.dehydrate_precio_unitario_con_igv(detalle)
        return precio_con_igv * detalle.cantidad

    # Método para calcular la ganancia por línea de venta
    def dehydrate_ganancia_item(self, detalle):
        precio_con_igv = self.dehydrate_precio_unitario_con_igv(detalle)
        costo = detalle.costo_unitario
        return (precio_con_igv - costo) * detalle.cantidad

class StockActualResource(resources.ModelResource):
    # Añadimos un campo calculado para el valor total del stock
    valor_total_stock = fields.Field(column_name='Valor Total del Stock')

    class Meta:
        model = Producto
        # Definimos las columnas exactas que queremos en este reporte
        fields = ('nombre', 'stock', 'costo', 'valor_total_stock')
        export_order = fields

    # Este método calcula el valor para nuestra nueva columna
    def dehydrate_valor_total_stock(self, producto):
        return producto.stock * producto.costo

class CajaDiariaResource(resources.ModelResource):
    usuario_apertura = fields.Field(attribute='usuario_apertura__username', column_name='Usuario Apertura')
    usuario_cierre = fields.Field(attribute='usuario_cierre__username', column_name='Usuario Cierre')
    
    class Meta:
        model = CajaDiaria
        fields = ('id', 'fecha_apertura', 'fecha_cierre', 'monto_inicial', 'monto_final_sistema', 'monto_final_real', 'diferencia', 'estado', 'observaciones', 'usuario_apertura', 'usuario_cierre')
        export_order = fields

class MovimientoCajaResource(resources.ModelResource):
    caja_id = fields.Field(attribute='caja__id', column_name='ID Caja')
    usuario = fields.Field(attribute='usuario__username', column_name='Usuario')

    class Meta:
        model = MovimientoCaja
        fields = ('id', 'caja_id', 'tipo', 'monto', 'concepto', 'fecha', 'usuario')
        export_order = fields




