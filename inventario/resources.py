from import_export import resources, fields
from import_export.widgets import ForeignKeyWidget
from .models import Producto, Venta, Proveedor, Compra, Cliente, Comprobante, DetalleComprobante
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

    def before_save_instance(self, instance, **kwargs):
        # Usamos getattr por seguridad. Si 'tienda_actual' no existe, devuelve None
        tienda = getattr(self, 'tienda_actual', None)
        if tienda:
            instance.tienda = tienda
        
        # IMPORTANTE: No olvides pasar los **kwargs al super
        super().before_save_instance(instance, **kwargs)


class ClienteResource(resources.ModelResource):
    class Meta:
        model = Cliente
        fields = ('id', 'nombre_completo', 'dni_ruc', 'telefono', 'email', 'pagina_web')
        export_order = fields
        skip_unchanged = True
        report_skipped = False
        import_id_fields = ('id',)

    # **ASEGÚRATE DE QUE ESTE MÉTODO ESTÉ AQUÍ Y ASÍ**
    def before_import_row(self, row, **kwargs):
        """
        Asigna la tienda a la fila antes de la importación si 'user' está en kwargs.
        """
        if 'user' in kwargs and hasattr(kwargs['user'], 'tienda'):
            row['tienda'] = kwargs['user'].tienda.id
        else:
            # Puedes manejar un error o establecer un valor por defecto si es necesario
            # para casos donde 'tienda' no puede ser determinada.
            # Este error será capturado por el bloque try-except en la vista.
            raise ValueError("No se pudo determinar la tienda para el cliente a importar. El usuario debe tener una tienda asignada.")


class ProveedorResource(resources.ModelResource):
    class Meta:
        model = Proveedor
        fields = ('id', 'razon_social', 'ruc', 'direccion', 'telefono', 'email', 'pagina_web', 'tienda')
        export_order = ('id', 'razon_social', 'ruc', 'direccion', 'telefono', 'email', 'pagina_web')
        
        skip_unchanged = True
        report_skipped = False

    def before_import_row(self, row, **kwargs):
        if 'user' in kwargs:
            row['tienda'] = kwargs['user'].tienda.id

class CompraResource(resources.ModelResource):
    producto_nuevo_nombre = fields.Field(column_name='producto_nuevo_nombre', attribute='producto_nuevo_nombre')
    producto_nuevo_costo = fields.Field(column_name='producto_nuevo_costo', attribute='producto_nuevo_costo')
    producto_nuevo_precio = fields.Field(column_name='producto_nuevo_precio', attribute='producto_nuevo_precio')

    producto = fields.Field(
        attribute='producto',
        column_name='producto_id',
        widget=ForeignKeyWidget(Producto, 'id')
    )
    proveedor = fields.Field(
        attribute='proveedor',
        column_name='proveedor',
        widget=CleanForeignKeyWidget(Proveedor, 'razon_social')
    )

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
            if nombre and hasattr(self, 'tienda_actual'): # Agregado 'hasattr(self, 'tienda_actual')'
                nuevo_producto, created = Producto.objects.get_or_create(
                    nombre=nombre,
                    tienda=self.tienda_actual,
                    defaults={'costo': costo or 0, 'precio': precio or 0, 'stock': 0}
                )
                row['producto_id'] = nuevo_producto.id

    # **CORRECCIÓN DE SANGRÍA AQUÍ**
    def before_save_instance(self, instance, **kwargs): # Solo instance y **kwargs
        if hasattr(self, 'tienda_actual'):
            instance.tienda = self.tienda_actual
        super().before_save_instance(instance, **kwargs) # Pasa **kwargs


class VentaResource(resources.ModelResource):
    producto = fields.Field(attribute='producto', widget=ForeignKeyWidget(Producto, 'nombre'))
    cliente = fields.Field(attribute='cliente', widget=ForeignKeyWidget(Cliente, 'nombre_completo'))
    class Meta:
        model = Venta
        fields = ('id', 'cliente', 'producto', 'cantidad', 'precio_unitario', 'costo_unitario', 'total', 'fecha_de_venta', 'observaciones')
        export_order = fields

    # **CORRECCIÓN DE SANGRÍA AQUÍ**
    # Este método no estaba correctamente indentado dentro de la clase VentaResource.
    # Además, la firma del método se ha estandarizado a `**kwargs`.
    def before_save_instance(self, instance, **kwargs):
        if hasattr(self, 'tienda_actual'): # Asegurarse de que tienda_actual esté configurada
            instance.tienda = self.tienda_actual
        super().before_save_instance(instance, **kwargs) # Pasa **kwargs

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

