# inventario/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse 
from django.db import transaction
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncDay
from django.utils.timezone import make_aware 
from django.db.models import F 
from django.urls import reverse
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.template.loader import get_template
from decimal import Decimal 
import json
import openpyxl
from io import BytesIO
from xhtml2pdf import pisa
from tablib import Dataset

# Importaciones locales de tu App (Consolidadas aquí arriba)
from .models import (
    Producto, Venta, Proveedor, Compra, Cliente, Comprobante, 
    DetalleComprobante, Tienda, LoginLog, Perfil, CajaDiaria, MovimientoCaja
)
from .forms import (
    RegistroTiendaForm, ProductoForm, ClienteForm, ProveedorForm, 
    CompraForm, EmpleadoForm, AperturaCajaForm, CierreCajaForm, MovimientoCajaForm
)
from .resources import (
    ProductoResource, ClienteResource, ProveedorResource, CompraResource, 
    ComprobanteResource, CajaDiariaResource, MovimientoCajaResource
)

IMPORT_TYPES = {
    'clientes': {
        'resource': ClienteResource,
        'template_headers': ['nombre_completo', 'dni_ruc', 'telefono', 'email', 'pagina_web'],
        'singular_name': 'Cliente',
        'plural_name': 'Clientes'
    },
    'productos': {
        'resource': ProductoResource,
        'template_headers': ['nombre', 'codigo_barras', 'stock', 'costo', 'precio'],
        'singular_name': 'Producto',
        'plural_name': 'Productos'
    },
    'proveedores': {
        'resource': ProveedorResource,
        'template_headers': ['razon_social', 'ruc', 'direccion', 'telefono', 'email', 'pagina_web'],
        'singular_name': 'Proveedor',
        'plural_name': 'Proveedores'
    },
    'compras': {
        'resource': CompraResource,
        'template_headers': ['ruc_proveedor', 'codigo_barras_producto', 'cantidad', 'costo_total', 'fecha_de_compra', 'numero_factura'],
        'singular_name': 'Compra',
        'plural_name': 'Compras'
    }
}

# ==============================================================================
# HELPER PARA VALIDAR DUEÑO O EMPLEADO
# ==============================================================================
def obtener_tienda_usuario(user):
    if hasattr(user, 'tienda'):
        return user.tienda
    if hasattr(user, 'perfil'):
        return user.perfil.tienda
    return None


# ==============================================================================
# VISTAS DE VENTA Y POS
# ==============================================================================

@login_required
def pos_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada. Contacta al administrador.")
        return redirect('inventario:portal')

    # Importación local de CajaDiaria removida porque ya está arriba
    caja_abierta = CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').first()
    
    if not caja_abierta:
        messages.warning(request, "⚠️ DEBES ABRIR CAJA PARA PODER VENDER.")
        return redirect('inventario:apertura_caja')

    productos = Producto.objects.filter(tienda=tienda_actual)
    clientes = Cliente.objects.filter(tienda=tienda_actual)
    
    productos_para_busqueda = []
    for p in productos:
        productos_para_busqueda.append({
            'id': p.id,
            'text': f'{p.nombre} (Stock: {p.stock})',
            'codigo_barras': p.codigo_barras,
            'precio': str(p.precio) 
        })

    ultimas_ventas_detalles = DetalleComprobante.objects.filter(
        comprobante__tienda=tienda_actual
    ).select_related(
        'comprobante__cliente', 'producto'
    ).order_by('-comprobante__fecha_emision')[:5]

    for detalle in ultimas_ventas_detalles:
        precio_a_usar = detalle.precio_unitario_con_igv or (detalle.precio_unitario * Decimal('1.18'))
        detalle.total_item = precio_a_usar * detalle.cantidad

    contexto = {
        'productos_json': json.dumps(productos_para_busqueda),
        'clientes': clientes,
        'ultimas_ventas': ultimas_ventas_detalles,
        'tienda_actual': tienda_actual,
    }
    return render(request, 'inventario/pos.html', contexto)


@login_required
def emitir_comprobante_y_preparar_impresion_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    productos = Producto.objects.filter(tienda=tienda_actual)
    clientes = Cliente.objects.filter(tienda=tienda_actual)

    productos_para_busqueda = []
    for p in productos:
        productos_para_busqueda.append({
            'id': p.id,
            'text': f'{p.nombre} (Stock: {p.stock})',
            'codigo_barras': p.codigo_barras,
            'stock': p.stock,
            'precio': float(p.precio)
        })

    if request.method == 'POST':
        try:
            cliente_id = request.POST.get('cliente_id')
            observaciones_venta = request.POST.get('observaciones', '')
            tipo_comprobante = request.POST.get('tipo_comprobante')
            producto_id = request.POST.get('producto_id')
            cantidad_vendida = int(request.POST.get('cantidad', 1))

            producto = get_object_or_404(Producto, id=producto_id, tienda=tienda_actual)
            cliente_seleccionado = None
            if cliente_id:
                cliente_seleccionado = get_object_or_404(Cliente, id=cliente_id, tienda=tienda_actual)

            with transaction.atomic():
                if producto.stock < cantidad_vendida:
                    raise ValueError(f'Stock insuficiente para {producto.nombre}.')
                
                producto.stock -= cantidad_vendida
                producto.save()
                
                precio_final_unitario = producto.precio
                total_final_venta = precio_final_unitario * Decimal(cantidad_vendida)
                tasa_igv = Decimal('1.18')
                subtotal_venta = (total_final_venta / tasa_igv).quantize(Decimal('0.01'))
                igv_monto = total_final_venta - subtotal_venta
                
                comprobante = Comprobante.objects.create(
                    tienda=tienda_actual,
                    tipo_comprobante=tipo_comprobante,
                    serie='B001' if tipo_comprobante == 'BOLETA' else 'F001',
                    cliente=cliente_seleccionado,
                    subtotal=subtotal_venta,
                    igv=igv_monto,
                    total_final=total_final_venta,
                    observaciones=observaciones_venta,
                )

                precio_unitario_sin_igv = (precio_final_unitario / tasa_igv).quantize(Decimal('0.01'))
                
                DetalleComprobante.objects.create(
                    comprobante=comprobante,
                    producto=producto,
                    cantidad=cantidad_vendida,
                    precio_unitario=precio_unitario_sin_igv,
                    costo_unitario=producto.costo,
                    subtotal=subtotal_venta,
                    precio_unitario_con_igv=precio_final_unitario
                )
                
                messages.success(request, 'Comprobante emitido con éxito y stock actualizado.')
                return redirect('inventario:vista_ticket_comprobante', comprobante_id=comprobante.id)

        except (Producto.DoesNotExist, Cliente.DoesNotExist):
            messages.error(request, "Error: El producto o cliente no pertenece a tu tienda.")
        except ValueError as e:
            messages.error(request, f'Error de stock o cantidad: {e}')
        except Exception as e:
            messages.error(request, f'Ocurrió un error al procesar la emisión: {e}')
        
    contexto = {
        'productos_json': json.dumps(productos_para_busqueda),
        'clientes': clientes,
    }
    return render(request, 'inventario/pos.html', contexto)


@login_required
def vista_para_impresion_basica(request, comprobante_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    comprobante = get_object_or_404(Comprobante, id=comprobante_id, tienda=tienda_actual)
    return render(request, 'inventario/comprobante_ticket.html', {'comprobante': comprobante})


@login_required
def registrar_compra_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    form = CompraForm(tienda=tienda_actual) 

    if request.method == 'POST':
        form = CompraForm(request.POST, tienda=tienda_actual)
        if form.is_valid():
            try:
                compra = form.save(commit=False)
                compra.tienda = tienda_actual
                
                producto = compra.producto
                if producto.tienda != tienda_actual:
                    raise ValueError(f"El producto '{producto.nombre}' no pertenece a tu tienda.")
                
                producto.stock += compra.cantidad
                producto.save()
                
                compra.save()
                messages.success(request, f'Compra de {compra.cantidad} x {producto.nombre} registrada.')
                return redirect('inventario:registrar_compra')
            except Exception as e:
                messages.error(request, f'Error al registrar la compra: {e}')
    
    proveedores = Proveedor.objects.filter(tienda=tienda_actual)
    productos = Producto.objects.filter(tienda=tienda_actual)
    
    contexto = {
        'form': form,
        'proveedores': proveedores,
        'productos': productos,
    }
    return render(request, 'inventario/registrar_compra.html', contexto)


def portal_view(request):
    if request.user.is_authenticated and not request.GET.get('force'):
        return redirect('inventario:dashboard')
    
    return render(request, 'inventario/portal.html')

# === LÓGICA DE CATÁLOGO ===
def catalogo_view(request):
    query = request.GET.get('q', '')
    categoria = request.GET.get('categoria', '')
    productos = Producto.objects.all().order_by('nombre')
    if query:
        productos = productos.filter(Q(nombre__icontains=query) | Q(codigo_barras__icontains=query))
    if categoria:
        if categoria == 'materiales': productos = productos.filter(codigo_barras__istartswith='MAT')
        elif categoria == 'herramienta': productos = productos.filter(codigo_barras__istartswith='HER')
        elif categoria == 'pintura': productos = productos.filter(codigo_barras__istartswith='PIN')
        elif categoria == 'seguridad': productos = productos.filter(codigo_barras__istartswith='SEG')
    context = {'productos': productos, 'busqueda': query, 'categoria_filtro': categoria}
    return render(request, 'inventario/catalogo.html', context)


# ==============================================================================
# REPORTES
# ==============================================================================

@login_required
def reporte_stock_bajo_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')
    umbral_stock_bajo = 5 
    productos_bajos_stock = Producto.objects.filter(tienda=tienda_actual, stock__lte=umbral_stock_bajo).order_by('stock')
    chart_labels = [p.nombre for p in productos_bajos_stock]
    chart_data = [float(p.stock) for p in productos_bajos_stock] 
    contexto = {'productos': productos_bajos_stock, 'umbral': umbral_stock_bajo, 'chart_labels': json.dumps(chart_labels), 'chart_data': json.dumps(chart_data)}
    return render(request, 'inventario/reporte_stock_bajo.html', contexto)

@login_required
def reporte_ventas_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual: return redirect('inventario:dashboard')
    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin')
    fecha_fin_default = timezone.localdate()
    fecha_inicio_default = fecha_fin_default - timedelta(days=6)
    try:
        fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date() if fecha_inicio_str else fecha_inicio_default
        fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date() if fecha_fin_str else fecha_fin_default
    except ValueError:
        fecha_inicio_obj = fecha_inicio_default
        fecha_fin_obj = fecha_fin_default
    fecha_inicio_dt = make_aware(datetime.combine(fecha_inicio_obj, time.min))
    fecha_fin_dt = make_aware(datetime.combine(fecha_fin_obj, time.max))
    comprobantes_periodo = Comprobante.objects.filter(tienda=tienda_actual, fecha_emision__range=(fecha_inicio_dt, fecha_fin_dt), estado='EMITIDO').prefetch_related('detalles')
    detalles_periodo = DetalleComprobante.objects.filter(comprobante__in=comprobantes_periodo).select_related('producto')
    total_ventas = comprobantes_periodo.aggregate(total=Sum('total_final'))['total'] or 0
    total_costos = sum(d.costo_unitario * d.cantidad for d in detalles_periodo)
    ganancia_bruta = total_ventas - total_costos
    daily_summary = {}
    current_date = fecha_inicio_obj
    while current_date <= fecha_fin_obj:
        daily_summary[current_date.strftime('%Y-%m-%d')] = {'ventas': 0.0, 'costos': 0.0, 'ganancias': 0.0}
        current_date += timedelta(days=1)
    for comp in comprobantes_periodo:
        dia_str = timezone.localtime(comp.fecha_emision).date().strftime('%Y-%m-%d')
        costo_comprobante = sum(d.costo_unitario * d.cantidad for d in comp.detalles.all())
        if dia_str in daily_summary:
            daily_summary[dia_str]['ventas'] += float(comp.total_final)
            daily_summary[dia_str]['costos'] += float(costo_comprobante)
            daily_summary[dia_str]['ganancias'] += float(comp.total_final - costo_comprobante)
    for detalle in detalles_periodo:
        detalle.precio_unitario_display = detalle.precio_unitario * Decimal('1.18')
        detalle.costo_unitario_display = detalle.costo_unitario
        detalle.total_venta = detalle.precio_unitario_display * detalle.cantidad
        detalle.ganancia = (detalle.precio_unitario_display - detalle.costo_unitario_display) * detalle.cantidad
    sorted_date_strings = sorted(daily_summary.keys())
    chart_labels = [datetime.strptime(d, '%Y-%m-%d').strftime('%d/%m') for d in sorted_date_strings]
    sales_data = [daily_summary[d]['ventas'] for d in sorted_date_strings]
    costs_data = [daily_summary[d]['costos'] for d in sorted_date_strings]
    profits_data = [daily_summary[d]['ganancias'] for d in sorted_date_strings]
    contexto = {'detalles_ventas': detalles_periodo, 'total_ventas': total_ventas, 'total_costos': total_costos, 'ganancia_bruta': ganancia_bruta, 'fecha_inicio': fecha_inicio_obj, 'fecha_fin': fecha_fin_obj, 'chart_labels': json.dumps(chart_labels), 'sales_data': json.dumps(sales_data), 'costs_data': json.dumps(costs_data), 'profits_data': json.dumps(profits_data)}
    return render(request, 'inventario/reporte_ventas.html', contexto)

@login_required
def reporte_stock_actual_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual: return redirect('inventario:dashboard')
    productos = Producto.objects.filter(tienda=tienda_actual).order_by('nombre')
    valor_total_inventario = 0
    for p in productos:
        p.valor_stock = p.stock * p.costo
        valor_total_inventario += p.valor_stock
    contexto = {'productos': productos, 'valor_total_inventario': valor_total_inventario}
    return render(request, 'inventario/reporte_stock_actual.html', contexto)


# ==============================================================================
# GESTIÓN Y DASHBOARD
# ==============================================================================

def registro_view(request):
    if request.method == 'POST':
        form = RegistroTiendaForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    nuevo_usuario = User.objects.create_user(username=data['username'], email=data['email'], password=data['password'])
                    Tienda.objects.create(propietario=nuevo_usuario, nombre=data['nombre_tienda'], ruc=data['ruc_tienda'])
                messages.success(request, "¡Registro exitoso! Ya puedes iniciar sesión.")
                return redirect('inventario:login')
            except Exception as e:
                messages.error(request, f"Ocurrió un error al registrar: {e}")
    else:
        form = RegistroTiendaForm()
    return render(request, 'inventario/registro.html', {'form': form})

@login_required
def dashboard_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        auth_logout(request)
        return redirect('inventario:portal')
    referer = request.META.get('HTTP_REFERER', '')
    show_splash = 'login' in referer
    hoy = timezone.localdate()
    ventas_hoy = Comprobante.objects.filter(tienda=tienda_actual, fecha_emision__date=hoy, estado='EMITIDO')
    ventas_hoy_monto = ventas_hoy.aggregate(total=Sum('total_final'))['total'] or Decimal('0.00')
    total_ventas_hoy = ventas_hoy.count()
    productos_bajo_stock = Producto.objects.filter(tienda=tienda_actual, stock__lte=5).count()
    contexto = {'tienda': tienda_actual, 'ventas_hoy_monto': ventas_hoy_monto, 'total_ventas_hoy': total_ventas_hoy, 'productos_bajo_stock': productos_bajo_stock, 'show_splash': show_splash}
    return render(request, 'inventario/dashboard.html', contexto)

@login_required
def gestion_lista_view(request, modelo):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual: return redirect('inventario:dashboard')
    Modelos = {'productos': Producto, 'clientes': Cliente, 'proveedores': Proveedor, 'compras': Compra, 'comprobantes': Comprobante}
    Modelo = Modelos.get(modelo)
    if not Modelo: return redirect('inventario:dashboard')
    queryset = Modelo.objects.filter(tienda=tienda_actual).order_by('-id')
    contexto = {'objetos': queryset, 'modelo_nombre_plural': Modelo._meta.verbose_name_plural, 'modelo_slug': modelo}
    return render(request, 'inventario/gestion_lista.html', contexto)

@login_required
def gestion_crear_view(request, modelo):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual: return redirect('inventario:dashboard')
    Modelos = {'productos': (Producto, ProductoForm), 'clientes': (Cliente, ClienteForm), 'proveedores': (Proveedor, ProveedorForm), 'compras': (Compra, CompraForm)}
    if modelo not in Modelos: return redirect('inventario:dashboard')
    Modelo, Formulario = Modelos[modelo]
    form_kwargs = {}
    if modelo == 'compras': form_kwargs['tienda'] = tienda_actual
    if request.method == 'POST':
        form = Formulario(request.POST, **form_kwargs)
        if form.is_valid():
            instancia = form.save(commit=False)
            instancia.tienda = tienda_actual
            instancia.save()
            messages.success(request, f"{Modelo._meta.verbose_name} creado exitosamente.")
            return redirect('inventario:gestion_lista', modelo=modelo)
    else:
        form = Formulario(**form_kwargs)
    return render(request, 'inventario/gestion_form.html', {'form': form, 'modelo_nombre': Modelo._meta.verbose_name, 'modelo_slug': modelo, 'editando': False})

@login_required
def gestion_editar_view(request, modelo, pk):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual: return redirect('inventario:dashboard')
    Modelos = {'productos': (Producto, ProductoForm), 'clientes': (Cliente, ClienteForm), 'proveedores': (Proveedor, ProveedorForm), 'compras': (Compra, CompraForm)}
    if modelo not in Modelos: return redirect('inventario:dashboard')
    Modelo, Formulario = Modelos[modelo]
    instancia = get_object_or_404(Modelo, pk=pk, tienda=tienda_actual)
    form_kwargs = {'instance': instancia}
    if modelo == 'compras': form_kwargs['tienda'] = tienda_actual
    if request.method == 'POST':
        form = Formulario(request.POST, **form_kwargs)
        if form.is_valid():
            form.save()
            messages.success(request, f"{Modelo._meta.verbose_name} actualizado exitosamente.")
            return redirect('inventario:gestion_lista', modelo=modelo)
    else:
        form = Formulario(**form_kwargs)
    return render(request, 'inventario/gestion_form.html', {'form': form, 'modelo_nombre': Modelo._meta.verbose_name, 'modelo_slug': modelo, 'editando': True})


# ==============================================================================
# IMPORTACIÓN / EXPORTACIÓN
# ==============================================================================

@login_required
def exportar_productos_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual: return redirect('inventario:dashboard')
    producto_resource = ProductoResource()
    queryset = Producto.objects.filter(tienda=tienda_actual)
    dataset = producto_resource.export(queryset)
    response = HttpResponse(dataset.xlsx, content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="mis_productos.xlsx"'
    return response

@login_required
def descargar_plantilla_view(request, model_name):
    tienda_actual = obtener_tienda_usuario(request.user)
    config = IMPORT_TYPES.get(model_name)
    if not config: return redirect('inventario:dashboard')
    headers = config['template_headers']
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.append(headers)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="plantilla_{model_name}.xlsx"'
    workbook.save(response)
    return response

@login_required
def importar_datos_view(request, data_type):
    tienda_actual = obtener_tienda_usuario(request.user)
    if data_type not in IMPORT_TYPES: return redirect('inventario:dashboard')
    config = IMPORT_TYPES[data_type]
    ResourceClass = config['resource']
    if request.method == 'POST':
        file = request.FILES.get('excel_file')
        if not file: return redirect('inventario:importar_datos', data_type=data_type)
        dataset = Dataset()
        try:
            if file.name.endswith('.csv'): dataset.load(file.read().decode('utf-8'), format='csv')
            elif file.name.endswith(('.xls', '.xlsx')): dataset.load(file.read(), format='xlsx')
            data_resource = ResourceClass()
            data_resource.tienda_actual = tienda_actual 
            result = data_resource.import_data(dataset, dry_run=True, raise_errors=False)
            if not result.has_errors():
                data_resource.import_data(dataset, dry_run=False, raise_errors=False)
                messages.success(request, f'¡Importación completada!')
                return redirect('inventario:gestion_lista', modelo=data_type)
        except Exception as e: messages.error(request, f'Error: {e}')
    return render(request, 'inventario/importar_datos.html', {'data_type_display': config['plural_name'], 'template_headers': config['template_headers'], 'data_type': data_type})


# ==============================================================================
# AJAX Y FUNCIONES ESPECÍFICAS
# ==============================================================================

@login_required
@csrf_exempt
def emitir_comprobante_ajax_view(request):
    if request.method != 'POST': return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        tienda_actual = obtener_tienda_usuario(request.user)
        data = json.loads(request.body)
        cart_items = data.get('cart')
        if not cart_items: return JsonResponse({'error': 'Vacío'}, status=400)
        with transaction.atomic():
            total_final_venta = sum(Decimal(str(item['price'])) * Decimal(str(item['quantity'])) for item in cart_items)
            tasa_igv_decimal = Decimal('0.18')
            subtotal_venta = (total_final_venta / (1 + tasa_igv_decimal)).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
            igv_monto = (subtotal_venta * tasa_igv_decimal).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
            cliente_id = data.get('cliente_id')
            cliente_seleccionado = Cliente.objects.filter(id=cliente_id, tienda=tienda_actual).first() if cliente_id else None
            comprobante = Comprobante.objects.create(tienda=tienda_actual, tipo_comprobante=data.get('tipo_comprobante'), serie='B001' if data.get('tipo_comprobante') == 'BOLETA' else 'F001', cliente=cliente_seleccionado, subtotal=subtotal_venta, igv=igv_monto, total_final=total_final_venta, observaciones=data.get('observaciones', ''))
            
            stocks_actualizados = []
            for item in cart_items:
                producto = get_object_or_404(Producto, id=item['id'], tienda=tienda_actual)
                producto.stock -= Decimal(str(item['quantity']))
                producto.save()
                DetalleComprobante.objects.create(comprobante=comprobante, producto=producto, cantidad=item['quantity'], precio_unitario=Decimal(str(item['price']))/Decimal('1.18'), costo_unitario=producto.costo, subtotal=Decimal(str(item['price']))*Decimal(str(item['quantity'])))
                stocks_actualizados.append({'id': producto.id, 'stock': float(producto.stock)})
            return JsonResponse({'comprobante_id': comprobante.id, 'stocks_actualizados': stocks_actualizados})
    except Exception as e: return JsonResponse({'error': str(e)}, status=500)

@login_required
def descargar_comprobante_pdf_view(request, comprobante_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    comprobante = get_object_or_404(Comprobante, id=comprobante_id, tienda=tienda_actual)
    template = get_template('inventario/comprobante_ticket.html')
    html = template.render({'comprobante': comprobante, 'tienda': tienda_actual})
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="comprobante_{comprobante.numero}.pdf"'
        return response
    return redirect('inventario:dashboard')

@login_required
def eliminar_venta_view(request, comprobante_id):
    if request.method == 'POST':
        tienda_actual = obtener_tienda_usuario(request.user)
        comprobante = get_object_or_404(Comprobante, id=comprobante_id, tienda=tienda_actual)
        with transaction.atomic():
            for detalle in comprobante.detalles.all():
                detalle.producto.stock += detalle.cantidad
                detalle.producto.save()
            comprobante.delete()
        return redirect('inventario:gestion_lista', modelo='comprobantes')
    return redirect('inventario:dashboard')

@login_required
def exportar_comprobantes_view(request):
    return redirect('inventario:dashboard')

@login_required
def exportar_reporte_ventas_excel_view(request):
    return redirect('inventario:dashboard')

@login_required
def exportar_stock_actual_excel_view(request):
    return redirect('inventario:dashboard')

@login_required
def log_logueos_view(request):
    if not request.user.is_superuser: return redirect('inventario:dashboard')
    logs = LoginLog.objects.all()
    return render(request, 'inventario/log_logueos.html', {'logs': logs})

# ==============================================================================
# USUARIOS Y PERSONAL
# ==============================================================================

@login_required
def lista_usuarios_tienda(request):
    tienda = obtener_tienda_usuario(request.user)
    empleados = Perfil.objects.filter(tienda=tienda).exclude(user=request.user)
    return render(request, 'inventario/usuarios_lista.html', {'empleados': empleados, 'tienda': tienda})

@login_required
def crear_usuario_tienda(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            nuevo_user = User.objects.create_user(username=data['username'], password=data['password'], first_name=data['first_name'], last_name=data['last_name'])
            Perfil.objects.create(user=nuevo_user, tienda=tienda_actual, rol=data.get('rol', 'VENDEDOR'))
            return redirect('inventario:lista_usuarios_tienda')
    else: form = EmpleadoForm()
    return render(request, 'inventario/usuarios_form.html', {'form': form, 'editando': False})

@login_required
def editar_usuario_tienda(request, usuario_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    perfil = get_object_or_404(Perfil, id=usuario_id, tienda=tienda_actual)
    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            perfil.user.username = form.cleaned_data['username']
            if form.cleaned_data['password']: perfil.user.set_password(form.cleaned_data['password'])
            perfil.user.save()
            perfil.rol = form.cleaned_data.get('rol', 'VENDEDOR')
            perfil.save()
            return redirect('inventario:lista_usuarios_tienda')
    else: form = EmpleadoForm(initial={'username': perfil.user.username, 'rol': perfil.rol})
    return render(request, 'inventario/usuarios_form.html', {'form': form, 'editando': True})

@login_required
def eliminar_usuario_tienda(request, usuario_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    perfil = get_object_or_404(Perfil, id=usuario_id, tienda=tienda_actual)
    perfil.user.delete()
    return redirect('inventario:lista_usuarios_tienda')

@login_required
def gestion_eliminar_view(request, modelo, pk):
    tienda_actual = obtener_tienda_usuario(request.user)
    Modelos = {'productos': Producto, 'clientes': Cliente, 'proveedores': Proveedor, 'compras': Compra}
    Modelo = Modelos.get(modelo)
    objeto = get_object_or_404(Modelo, pk=pk, tienda=tienda_actual)
    if request.method == 'POST':
        if modelo == 'compras':
            objeto.producto.stock -= objeto.cantidad
            objeto.producto.save()
        objeto.delete()
    return redirect('inventario:gestion_lista', modelo=modelo)

@login_required
@csrf_exempt
def crear_cliente_ajax_view(request):
    if request.method == 'POST':
        tienda_actual = obtener_tienda_usuario(request.user)
        data = json.loads(request.body)
        cliente = Cliente.objects.create(tienda=tienda_actual, nombre_completo=data.get('nombre'), dni=data.get('dni'), razon_social=data.get('razon'), ruc=data.get('ruc'), dni_ruc=data.get('ruc') or data.get('dni'), telefono=data.get('tel', ''))
        return JsonResponse({'id': cliente.id, 'text': str(cliente), 'ruc': cliente.ruc, 'razon': cliente.razon_social})
    return JsonResponse({'error': 'Error'}, status=405)

def logout_view(request):
    auth_logout(request)
    return redirect('inventario:portal')


# ==============================================================================
# GESTIÓN DE CAJA
# ==============================================================================

@login_required
def apertura_caja_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').exists(): return redirect('inventario:pos')
    if request.method == 'POST':
        form = AperturaCajaForm(request.POST)
        if form.is_valid():
            caja = form.save(commit=False)
            caja.tienda, caja.usuario_apertura, caja.estado = tienda_actual, request.user, 'ABIERTA'
            caja.save()
            return redirect('inventario:pos')
    else: form = AperturaCajaForm()
    return render(request, 'inventario/caja_apertura.html', {'form': form})

@login_required
def cierre_caja_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    caja = CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').first()
    if not caja: return redirect('inventario:dashboard')
    ventas = Comprobante.objects.filter(tienda=tienda_actual, fecha_emision__gte=caja.fecha_apertura, estado='EMITIDO').aggregate(t=Sum('total_final'))['t'] or Decimal('0.00')
    ingresos = caja.movimientos.filter(tipo='INGRESO').aggregate(t=Sum('monto'))['t'] or Decimal('0.00')
    egresos = caja.movimientos.filter(tipo='EGRESO').aggregate(t=Sum('monto'))['t'] or Decimal('0.00')
    total_sistema = caja.monto_inicial + ventas + ingresos - egresos
    if request.method == 'POST':
        form = CierreCajaForm(request.POST, instance=caja)
        if form.is_valid():
            cierre = form.save(commit=False)
            cierre.monto_final_sistema, cierre.usuario_cierre, cierre.fecha_cierre, cierre.estado = total_sistema, request.user, timezone.now(), 'CERRADA'
            cierre.diferencia = cierre.monto_final_real - total_sistema
            cierre.save()
            return redirect('inventario:dashboard')
    else: form = CierreCajaForm()
    return render(request, 'inventario/caja_cierre.html', {'form': form, 'caja': caja, 'ventas': ventas, 'ingresos': ingresos, 'egresos': egresos, 'total_sistema': total_sistema})

@login_required
def movimiento_caja_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    caja = CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').first()
    if not caja: return redirect('inventario:dashboard')
    if request.method == 'POST':
        form = MovimientoCajaForm(request.POST)
        if form.is_valid():
            mov = form.save(commit=False)
            mov.caja, mov.usuario = caja, request.user
            mov.save()
            return redirect('inventario:pos')
    else: form = MovimientoCajaForm()
    return render(request, 'inventario/caja_movimiento.html', {'form': form})

@login_required
def exportar_modelo_generico_view(request, modelo):
    tienda_actual = obtener_tienda_usuario(request.user)
    config = {'productos': (Producto, ProductoResource), 'clientes': (Cliente, ClienteResource), 'proveedores': (Proveedor, ProveedorResource), 'compras': (Compra, CompraResource), 'comprobantes': (Comprobante, ComprobanteResource), 'cajas': (CajaDiaria, CajaDiariaResource), 'movimientos': (MovimientoCaja, MovimientoCajaResource)}
    if modelo not in config: return redirect('inventario:dashboard')
    Modelo, Recurso = config[modelo]
    queryset = Modelo.objects.filter(caja__tienda=tienda_actual) if modelo == 'movimientos' else Modelo.objects.filter(tienda=tienda_actual)
    dataset = Recurso().export(queryset)
    response = HttpResponse(dataset.xlsx, content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{modelo}.xlsx"'
    return response
