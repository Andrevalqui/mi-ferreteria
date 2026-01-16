# inventario/admin.py

from django.contrib import admin
from django.urls import path
from django.http import HttpResponse
from django.template.loader import get_template
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from io import BytesIO
from xhtml2pdf import pisa
from import_export.admin import ImportExportModelAdmin
from .models import CajaDiaria, MovimientoCaja

# --- IMPORTACIONES LOCALES ORGANIZADAS ---
from .models import (
    Tienda, Producto, Venta, Proveedor, Compra, Cliente, Comprobante, DetalleComprobante
)
from .resources import (
    ProductoResource, ClienteResource, ProveedorResource, CompraResource, VentaResource, ComprobanteResource
)
from .views import descargar_plantilla_view


# === ACCIÓN PERSONALIZADA PARA GENERAR PDF MASIVO ===
def generar_pdf_seleccionados(modeladmin, request, queryset):
    template = get_template('inventario/reporte_comprobantes_pdf.html')
    context = {'comprobantes': queryset}
    html = template.render(context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="comprobantes_seleccionados.pdf"'
        return response
        
    modeladmin.message_user(request, "Error al generar el PDF.", level='error')
    return None

generar_pdf_seleccionados.short_description = "Generar PDF de Comprobantes Seleccionados"


# === CLASE BASE DE ADMIN CON FUNCIONALIDAD PERSONALIZADA ===
class CustomImportExportAdmin(ImportExportModelAdmin):
    change_list_template = "admin/inventario/change_list.html"
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'descargar-plantilla/',
                self.admin_site.admin_view(descargar_plantilla_view),
                name='descargar_plantilla_para_modelo'
            )
        ]
        return custom_urls + urls

# === REGISTRO DE MODELOS EN EL ADMIN ===

@admin.register(Producto)
class ProductoAdmin(CustomImportExportAdmin):
    resource_class = ProductoResource
    list_display = ('nombre', 'codigo_barras', 'stock', 'precio', 'costo')
    search_fields = ('nombre', 'codigo_barras')

@admin.register(Cliente)
class ClienteAdmin(CustomImportExportAdmin):
    resource_class = ClienteResource
    list_display = ('nombre_completo', 'dni_ruc', 'telefono', 'email')
    search_fields = ('nombre_completo', 'dni_ruc')

@admin.register(Proveedor)
class ProveedorAdmin(CustomImportExportAdmin):
    resource_class = ProveedorResource
    list_display = ('razon_social', 'ruc', 'telefono', 'email')
    search_fields = ('razon_social', 'ruc')

@admin.register(Compra)
class CompraAdmin(CustomImportExportAdmin):
    resource_class = CompraResource
    list_display = ('id', 'proveedor', 'producto', 'cantidad', 'costo_total', 'fecha_de_compra')
    list_filter = ('fecha_de_compra', 'proveedor')
    search_fields = ('producto__nombre', 'proveedor__razon_social')

@admin.register(Venta)
class VentaAdmin(CustomImportExportAdmin):
    resource_class = VentaResource
    list_display = ('id', 'cliente', 'producto', 'cantidad', 'total', 'fecha_de_venta')
    list_filter = ('fecha_de_venta', 'cliente')
    search_fields = ('producto__nombre', 'cliente__nombre_completo', 'observaciones')

@admin.register(Comprobante)
class ComprobanteAdmin(CustomImportExportAdmin):
    resource_class = ComprobanteResource
    list_display = ('tipo_comprobante', 'serie', 'numero', 'fecha_emision', 'cliente', 'total_final', 'estado')
    list_filter = ('tipo_comprobante', 'estado', 'fecha_emision')
    search_fields = ('serie', 'numero', 'cliente__nombre_completo', 'cliente__dni_ruc')
    actions = ['delete_selected', generar_pdf_seleccionados]

@admin.register(DetalleComprobante)
class DetalleComprobanteAdmin(admin.ModelAdmin):
    list_display = ('comprobante', 'producto', 'cantidad', 'precio_unitario', 'subtotal')
    list_filter = ('comprobante__tipo_comprobante', 'producto')
    search_fields = ('comprobante__serie', 'comprobante__numero', 'producto__nombre')

@admin.register(Tienda)
class TiendaAdmin(CustomImportExportAdmin): # <-- ¡CAMBIO AQUÍ!
    resource_class = None # Tienda no necesita import/export, lo desactivamos
    list_display = ('id', 'nombre', 'propietario', 'creada_en')
    search_fields = ('nombre', 'propietario__username')
    list_filter = ('creada_en',)
    readonly_fields = ('creada_en',)

    
class CustomUserAdmin(BaseUserAdmin):
    pass

try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass

admin.site.register(User, CustomUserAdmin)

@admin.register(CajaDiaria)
class CajaDiariaAdmin(admin.ModelAdmin):
    list_display = ('id', 'tienda', 'fecha_apertura', 'monto_inicial', 'estado', 'usuario_apertura')
    list_filter = ('estado', 'fecha_apertura', 'tienda')

@admin.register(MovimientoCaja)
class MovimientoCajaAdmin(admin.ModelAdmin):
    list_display = ('tipo', 'monto', 'concepto', 'caja', 'fecha')
    list_filter = ('tipo', 'caja__tienda')

