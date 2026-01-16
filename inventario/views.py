from django.shortcuts import render, redirect, get_object_or_404
from .models import Producto, Venta, Proveedor, Compra, Cliente, Comprobante, DetalleComprobante, Tienda, LoginLog, Perfil, CajaDiaria, MovimientoCaja
import json
from django.utils import timezone
from django.db.models import Sum, Count, Q
from datetime import datetime, timedelta, time
from django.db.models.functions import TruncDay
from django.utils.timezone import make_aware 
from django.db.models import F 
import openpyxl
from django.http import HttpResponse, JsonResponse 
from django.db import transaction 
from decimal import Decimal 
from django.urls import reverse
from django.contrib.auth import views as auth_views
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from .forms import (
    RegistroTiendaForm, ProductoForm, ClienteForm, ProveedorForm, CompraForm, EmpleadoForm
)
from .resources import (
    ProductoResource, ClienteResource, ProveedorResource, CompraResource, 
    ComprobanteResource, CajaDiariaResource, MovimientoCajaResource # <--- AGREGADOS
)
from tablib import Dataset
from django.views.decorators.csrf import csrf_exempt
from django.template.loader import get_template
from io import BytesIO
from xhtml2pdf import pisa
from django.contrib import messages


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
# VISTAS
# ==============================================================================

@login_required
def pos_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada. Contacta al administrador.")
        return redirect('inventario:portal')

    from .models import CajaDiaria # Importación local para evitar ciclos
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

# === NUEVA LÓGICA DE CATÁLOGO (ACTUALIZADA POR REQUERIMIENTO) ===
def catalogo_view(request):
    """
    Vista pública del catálogo.
    Filtra por 'categoria' usando el inicio del código de barras (MAT, HER, PIN, SEG).
    """
    query = request.GET.get('q', '')
    categoria = request.GET.get('categoria', '')

    # Mostramos todos los productos ordenados
    productos = Producto.objects.all().order_by('nombre')

    # Búsqueda general
    if query:
        productos = productos.filter(
            Q(nombre__icontains=query) | Q(codigo_barras__icontains=query)
        )
    
    # Filtro por Categoría basado en Código de Barras (ej: MAT-001)
    if categoria:
        if categoria == 'materiales':
            productos = productos.filter(codigo_barras__istartswith='MAT')
        elif categoria == 'herramienta':
            productos = productos.filter(codigo_barras__istartswith='HER')
        elif categoria == 'pintura':
            productos = productos.filter(codigo_barras__istartswith='PIN')
        elif categoria == 'seguridad':
            productos = productos.filter(codigo_barras__istartswith='SEG')

    context = {
        'productos': productos,
        'busqueda': query,
        'categoria_filtro': categoria
    }
    return render(request, 'inventario/catalogo.html', context)


@login_required
def reporte_stock_bajo_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    umbral_stock_bajo = 5 
    productos_bajos_stock = Producto.objects.filter(tienda=tienda_actual, stock__lte=umbral_stock_bajo).order_by('stock')
    
    # --- CORRECCIÓN: Convertir Decimal a float para JSON ---
    chart_labels = [p.nombre for p in productos_bajos_stock]
    chart_data = [float(p.stock) for p in productos_bajos_stock] 

    contexto = {
        'productos': productos_bajos_stock,
        'umbral': umbral_stock_bajo,
        # Usamos json.dumps para crear el string JSON aquí
        'chart_labels': json.dumps(chart_labels),
        'chart_data': json.dumps(chart_data),
    }
    return render(request, 'inventario/reporte_stock_bajo.html', contexto)

@login_required
def reporte_ventas_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    fecha_inicio_str = request.GET.get('fecha_inicio')
    fecha_fin_str = request.GET.get('fecha_fin')

    fecha_fin_default = timezone.localdate()
    fecha_inicio_default = fecha_fin_default - timedelta(days=6)
    
    try:
        fecha_inicio_obj = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date() if fecha_inicio_str else fecha_inicio_default
        fecha_fin_obj = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date() if fecha_fin_str else fecha_fin_default
    except ValueError:
        messages.error(request, "Formato de fecha inválido. Usa YYYY-MM-DD.")
        fecha_inicio_obj = fecha_inicio_default
        fecha_fin_obj = fecha_fin_default

    fecha_inicio_dt = make_aware(datetime.combine(fecha_inicio_obj, time.min))
    fecha_fin_dt = make_aware(datetime.combine(fecha_fin_obj, time.max))

    comprobantes_periodo = Comprobante.objects.filter(
        tienda=tienda_actual, 
        fecha_emision__range=(fecha_inicio_dt, fecha_fin_dt),
        estado='EMITIDO'
    ).prefetch_related('detalles')

    detalles_periodo = DetalleComprobante.objects.filter(
        comprobante__in=comprobantes_periodo
    ).select_related('producto')

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

    contexto = {
        'detalles_ventas': detalles_periodo,
        'total_ventas': total_ventas,
        'total_costos': total_costos,
        'ganancia_bruta': ganancia_bruta,
        'fecha_inicio': fecha_inicio_obj,
        'fecha_fin': fecha_fin_obj,
        'chart_labels': json.dumps(chart_labels),
        'sales_data': json.dumps(sales_data),
        'costs_data': json.dumps(costs_data),
        'profits_data': json.dumps(profits_data),
    }
    return render(request, 'inventario/reporte_ventas.html', contexto)

@login_required
def reporte_stock_actual_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    productos = Producto.objects.filter(tienda=tienda_actual).order_by('nombre')
    
    valor_total_inventario = 0
    for p in productos:
        p.valor_stock = p.stock * p.costo
        valor_total_inventario += p.valor_stock

    contexto = {
        'productos': productos,
        'valor_total_inventario': valor_total_inventario,
    }
    return render(request, 'inventario/reporte_stock_actual.html', contexto)


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
                form.add_error(None, f"Ocurrió un error al registrar: {e}")
                messages.error(request, f"Ocurrió un error al registrar: {e}")
    else:
        form = RegistroTiendaForm()
    return render(request, 'inventario/registro.html', {'form': form})

@login_required
def dashboard_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    
    if not tienda_actual:
        auth_logout(request)
        messages.error(request, "Tu usuario no tiene una tienda asignada. Contacta al administrador.")
        return redirect('inventario:portal')

    # Lógica para el Splash Screen:
    # Solo mostramos el splash si el usuario viene de la página de login.
    referer = request.META.get('HTTP_REFERER', '')
    show_splash = 'login' in referer

    hoy = timezone.localdate()

    ventas_hoy = Comprobante.objects.filter(
        tienda=tienda_actual, 
        fecha_emision__date=hoy,
        estado='EMITIDO'
    )
    ventas_hoy_monto = ventas_hoy.aggregate(total=Sum('total_final'))['total'] or Decimal('0.00')
    total_ventas_hoy = ventas_hoy.count()

    productos_bajo_stock = Producto.objects.filter(tienda=tienda_actual, stock__lte=5).count()

    contexto = {
        'tienda': tienda_actual,
        'ventas_hoy_monto': ventas_hoy_monto,
        'total_ventas_hoy': total_ventas_hoy,
        'productos_bajo_stock': productos_bajo_stock,
        'show_splash': show_splash, 
    }
    return render(request, 'inventario/dashboard.html', contexto)

@login_required
def gestion_lista_view(request, modelo):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    Modelos = {
        'productos': Producto, 
        'clientes': Cliente, 
        'proveedores': Proveedor, 
        'compras': Compra,
        'comprobantes': Comprobante,
    }
    
    Modelo = Modelos.get(modelo)
    if not Modelo: 
        messages.error(request, "Módulo no encontrado.")
        return redirect('inventario:dashboard')

    queryset = Modelo.objects.filter(tienda=tienda_actual).order_by('-id')
    
    contexto = {
        'objetos': queryset, 
        'modelo_nombre_plural': Modelo._meta.verbose_name_plural, 
        'modelo_slug': modelo
    }
    return render(request, 'inventario/gestion_lista.html', contexto)


@login_required
def gestion_crear_view(request, modelo):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    Modelos = {'productos': (Producto, ProductoForm), 'clientes': (Cliente, ClienteForm), 'proveedores': (Proveedor, ProveedorForm), 'compras': (Compra, CompraForm)}
    if modelo not in Modelos: 
        messages.error(request, "Módulo no encontrado.")
        return redirect('inventario:dashboard')

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
            messages.error(request, "Por favor, corrige los errores en el formulario.")
    else:
        form = Formulario(**form_kwargs)
    
    contexto = {
        'form': form, 
        'modelo_nombre': Modelo._meta.verbose_name, 
        'modelo_slug': modelo, 
        'editando': False
    }
    return render(request, 'inventario/gestion_form.html', contexto)


@login_required
def gestion_editar_view(request, modelo, pk):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    Modelos = {'productos': (Producto, ProductoForm), 'clientes': (Cliente, ClienteForm), 'proveedores': (Proveedor, ProveedorForm), 'compras': (Compra, CompraForm)}
    if modelo not in Modelos: 
        messages.error(request, "Módulo no encontrado.")
        return redirect('inventario:dashboard')

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
            messages.error(request, "Por favor, corrige los errores en el formulario.")
    else:
        form = Formulario(**form_kwargs)
    
    contexto = {
        'form': form, 
        'modelo_nombre': Modelo._meta.verbose_name, 
        'modelo_slug': modelo, 
        'editando': True
    }
    return render(request, 'inventario/gestion_form.html', contexto)

@login_required
def exportar_productos_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    producto_resource = ProductoResource()
    queryset = Producto.objects.filter(tienda=tienda_actual)
    dataset = producto_resource.export(queryset)
    
    response = HttpResponse(dataset.xlsx, content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="mis_productos.xlsx"'
    return response

@login_required
def descargar_plantilla_view(request, model_name):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    config = IMPORT_TYPES.get(model_name)
    if not config:
        messages.error(request, f"No hay una plantilla definida para el modelo '{model_name}'.")
        return redirect('inventario:dashboard')

    headers = config['template_headers']
    
    workbook = openpyxl.Workbook()
    ws = workbook.active
    ws.title = f"Plantilla de {config['singular_name']}"
    ws.append(headers)

    if model_name == 'clientes':
        ws.append(['Piera Juarez (Ejemplo)', '12345678', '999999999', 'piera@ejemplo.com', 'https://ejemplo.com'])
    elif model_name == 'productos':
        ws.append(['Producto Ejemplo A', 'ABC-001', '100', '10.50', '5.00'])
    elif model_name == 'proveedores':
        ws.append(['Proveedor XYZ S.A.C. (Ejemplo)', '20100113610', 'AV. NICOLAS AYLLON 398', '987654321', 'contacto@proveedor.com', 'https://proveedor.com'])
    elif model_name == 'compras':
        ws.append(['20100113610', 'ABC-001', '50', '250.00', '2025-07-21', 'FACT-001'])
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="plantilla_{model_name}.xlsx"'
    workbook.save(response)
    
    return response

@login_required
def importar_datos_view(request, data_type):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    if data_type not in IMPORT_TYPES:
        messages.error(request, 'Tipo de importación inválido.')
        return redirect('inventario:dashboard')

    config = IMPORT_TYPES[data_type]
    ResourceClass = config['resource']
    singular_name = config['singular_name']
    plural_name = config['plural_name']
    template_headers = config['template_headers']

    if request.method == 'POST':
        file = request.FILES.get('excel_file')
        if not file:
            messages.error(request, f'Selecciona un archivo para importar.')
            return redirect('inventario:importar_datos', data_type=data_type)

        dataset = Dataset()
        try:
            if file.name.endswith('.csv'):
                dataset.load(file.read().decode('utf-8'), format='csv')
            elif file.name.endswith(('.xls', '.xlsx')):
                dataset.load(file.read(), format='xlsx')
            
            data_resource = ResourceClass()
            data_resource.tienda_actual = tienda_actual 

            result = data_resource.import_data(dataset, dry_run=True, raise_errors=False)

            if result.has_errors():
                for error in result.row_errors():
                    row_number = error[0] + 1
                    for field_error in error[1]:
                        error_msg = str(field_error.error)
                        field = getattr(field_error, 'field', None)
                        
                        if field:
                            messages.error(request, f"Fila {row_number}: {error_msg} (Columna: {field.column_name})")
                        else:
                            messages.error(request, f"Fila {row_number}: {error_msg}")
                
                return render(request, 'inventario/importar_datos.html', {
                    'data_type_display': plural_name,
                    'template_headers': template_headers,
                    'dry_run_result': result,
                    'data_type': data_type
                })
            else:
                data_resource.tienda_actual = tienda_actual 
                data_resource.import_data(dataset, dry_run=False, raise_errors=False)
                
                messages.success(request, f'¡Importación de {plural_name} completada!')
                return redirect('inventario:gestion_lista', modelo=data_type)

        except Exception as e:
            messages.error(request, f'Error al procesar el archivo: {e}')
            return redirect('inventario:importar_datos', data_type=data_type)

    return render(request, 'inventario/importar_datos.html', {
        'data_type_display': plural_name,
        'template_headers': template_headers,
        'data_type': data_type
    })

@login_required
@csrf_exempt
def emitir_comprobante_ajax_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        tienda_actual = obtener_tienda_usuario(request.user)
        if not tienda_actual:
             return JsonResponse({'error': 'No tienes tienda asignada'}, status=403)

        data = json.loads(request.body)
        
        cliente_id = data.get('cliente_id')
        observaciones_venta = data.get('observaciones', '')
        tipo_comprobante = data.get('tipo_comprobante')
        cart_items = data.get('cart')

        if not cart_items:
            return JsonResponse({'error': 'El carrito está vacío.'}, status=400)

        with transaction.atomic():
            total_final_venta = sum(Decimal(item['price']) * int(item['quantity']) for item in cart_items)
            
            tasa_igv_decimal = Decimal('0.18')
            subtotal_venta = (total_final_venta / (1 + tasa_igv_decimal)).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
            igv_monto = (subtotal_venta * tasa_igv_decimal).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')

            cliente_seleccionado = None
            if cliente_id:
                cliente_seleccionado = get_object_or_404(Cliente, id=cliente_id, tienda=tienda_actual)

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

            stocks_actualizados = []
            for item in cart_items:
                producto = get_object_or_404(Producto, id=item['id'], tienda=tienda_actual)
                cantidad_vendida = int(item['quantity'])
                
                if producto.stock < cantidad_vendida:
                    raise ValueError(f"Stock insuficiente para {producto.nombre}.")

                producto.stock -= cantidad_vendida
                producto.save()

                precio_unitario_con_igv = Decimal(item['price'])
                precio_unitario_sin_igv = (precio_unitario_con_igv / (1 + tasa_igv_decimal)).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')

                DetalleComprobante.objects.create(
                    comprobante=comprobante,
                    producto=producto,
                    cantidad=cantidad_vendida,
                    precio_unitario=precio_unitario_sin_igv,
                    precio_unitario_con_igv=precio_unitario_con_igv,
                    costo_unitario=producto.costo,
                    subtotal=precio_unitario_sin_igv * cantidad_vendida,
                )
                stocks_actualizados.append({'id': producto.id, 'stock': float(producto.stock)})

            nueva_venta_data = {
                'cliente': cliente_seleccionado.nombre_completo if cliente_seleccionado else "General",
                'producto': f"{cart_items[0]['name']} y más..." if len(cart_items) > 1 else cart_items[0]['name'],
                'cantidad': sum(int(item['quantity']) for item in cart_items),
                'total': f'{total_final_venta:.2f}',
                'fecha': timezone.localtime(comprobante.fecha_emision).strftime("%d/%m/%Y %H:%M"),
                'observaciones': observaciones_venta or "--"
            }

            return JsonResponse({
                'comprobante_id': comprobante.id,
                'nueva_venta': nueva_venta_data,
                'stocks_actualizados': stocks_actualizados
            })
        
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': f'Ocurrió un error inesperado: {e}'}, status=500)


@login_required
def exportar_comprobantes_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    messages.error(request, "Funcionalidad de exportación de comprobantes no implementada completamente.")
    return redirect('inventario:dashboard')


@login_required
def descargar_comprobante_pdf_view(request, comprobante_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    comprobante = get_object_or_404(Comprobante, id=comprobante_id, tienda=tienda_actual)

    template_path = 'inventario/comprobante_ticket.html'
    template = get_template(template_path)
    context = {'comprobante': comprobante, 'tienda': tienda_actual}
    html = template.render(context)
    
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        filename = f"{comprobante.get_tipo_comprobante_display()}_{comprobante.serie}-{comprobante.numero}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    messages.error(request, "Error al generar el PDF.")
    return redirect('inventario:gestion_lista', modelo='comprobantes')


@login_required
def eliminar_venta_view(request, comprobante_id):
    if request.method == 'POST':
        try:
            tienda_actual = obtener_tienda_usuario(request.user)
            if not tienda_actual:
                raise Tienda.DoesNotExist
            
            comprobante_a_eliminar = get_object_or_404(Comprobante, id=comprobante_id, tienda=tienda_actual)

            with transaction.atomic():
                for detalle in comprobante_a_eliminar.detalles.all():
                    producto = detalle.producto
                    if producto.tienda != tienda_actual:
                        raise ValueError(f"Intento de eliminar venta con producto ajeno ({producto.nombre}).")
                    
                    producto.stock += detalle.cantidad
                    producto.save()

                comprobante_a_eliminar.delete()
                messages.success(request, f"Venta {comprobante_a_eliminar.serie}-{comprobante_a_eliminar.numero} eliminada y stock restaurado.")

        except Tienda.DoesNotExist:
            messages.error(request, "No tienes una tienda asignada.")
        except Exception as e:
            messages.error(request, f"Error al eliminar venta: {e}")
            
        return redirect('inventario:gestion_lista', modelo='comprobantes')
    else:
        messages.warning(request, "Acceso no permitido.")
        return redirect('inventario:gestion_lista', modelo='comprobantes')

@login_required
def exportar_reporte_ventas_excel_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')
    
    messages.error(request, "Funcionalidad de exportación de reporte de ventas no implementada completamente.")
    return redirect('inventario:dashboard')


@login_required
def exportar_stock_actual_excel_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    messages.error(request, "Funcionalidad de exportación de stock actual no implementada completamente.")
    return redirect('inventario:dashboard')

@login_required
def log_logueos_view(request):
    if not request.user.is_superuser:
        messages.error(request, "Acceso solo para administrador.")
        return redirect('inventario:dashboard')

    logs = LoginLog.objects.all()

    username_filter = request.GET.get('username', '')
    start_date_str = request.GET.get('start_date', '')
    end_date_str = request.GET.get('end_date', '')
    status_filter = request.GET.get('status', '')

    if username_filter:
        logs = logs.filter(username_tried__icontains=username_filter)

    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            logs = logs.filter(timestamp__date__gte=start_date)
        except ValueError:
            messages.error(request, "Fecha inicio inválida.")

    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            logs = logs.filter(timestamp__date__lte=end_date)
        except ValueError:
            messages.error(request, "Fecha fin inválida.")
    
    if status_filter == 'success':
        logs = logs.filter(is_successful=True)
    elif status_filter == 'failed':
        logs = logs.filter(is_successful=False)

    total_logins = logs.count()
    successful_logins = logs.filter(is_successful=True).count()
    failed_logins = logs.filter(is_successful=False).count()
    
    context = {
        'logs': logs,
        'username_filter': username_filter,
        'start_date_filter': start_date_str,
        'end_date_filter': end_date_str,
        'status_filter': status_filter,
        'total_logins': total_logins,
        'successful_logins': successful_logins,
        'failed_logins': failed_logins,
    }
    return render(request, 'inventario/log_logueos.html', context)

@login_required
def lista_usuarios_tienda(request):
    tienda = obtener_tienda_usuario(request.user)
    if not tienda:
        return redirect('inventario:dashboard')
    empleados = Perfil.objects.filter(tienda=tienda).exclude(user=request.user)
    return render(request, 'inventario/usuarios_lista.html', {
        'empleados': empleados,
        'tienda': tienda 
    })

@login_required
def crear_usuario_tienda(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        return redirect('inventario:dashboard')

    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            try:
                with transaction.atomic():
                    nuevo_user = User.objects.create_user(
                        username=data['username'],
                        password=data['password'],
                        first_name=data['first_name'],
                        last_name=data['last_name'],
                        is_staff=False
                    )
                    Perfil.objects.create(
                        user=nuevo_user,
                        tienda=tienda_actual,
                        rol=data.get('rol', 'VENDEDOR')
                    )
                messages.success(request, f"¡Empleado {nuevo_user.username} creado con éxito!")
                return redirect('inventario:lista_usuarios_tienda')
            except Exception as e:
                messages.error(request, f"Error al crear el usuario: {e}")
    else:
        form = EmpleadoForm()
    
    return render(request, 'inventario/usuarios_form.html', {'form': form, 'editando': False})

@login_required
def editar_usuario_tienda(request, usuario_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        return redirect('inventario:dashboard')
        
    perfil = get_object_or_404(Perfil, id=usuario_id, tienda=tienda_actual)
    usuario = perfil.user

    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            usuario.username = data['username']
            usuario.first_name = data['first_name']
            usuario.last_name = data['last_name']
            if data['password']:
                usuario.set_password(data['password'])
            usuario.save()

            perfil.rol = data.get('rol', 'VENDEDOR')
            perfil.save()

            messages.success(request, f"Empleado {usuario.username} actualizado.")
            return redirect('inventario:lista_usuarios_tienda')
    else:
        form = EmpleadoForm(initial={
            'username': usuario.username,
            'first_name': usuario.first_name,
            'last_name': usuario.last_name,
            'rol': perfil.rol,
        })
    
    return render(request, 'inventario/usuarios_form.html', {'form': form, 'editando': True})

@login_required
def eliminar_usuario_tienda(request, usuario_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        return redirect('inventario:dashboard')

    perfil = get_object_or_404(Perfil, id=usuario_id, tienda=tienda_actual)
    
    if request.method == 'POST':
        usuario = perfil.user
        usuario.delete() 
        messages.success(request, f"El empleado ha sido eliminado de la tienda.")
    
    return redirect('inventario:lista_usuarios_tienda')

@login_required
def gestion_eliminar_view(request, modelo, pk):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')
    
    Modelos = {
        'productos': Producto, 'clientes': Cliente, 
        'proveedores': Proveedor, 'compras': Compra
    }
    
    Modelo = Modelos.get(modelo)
    if not Modelo:
        messages.error(request, "Módulo no encontrado.")
        return redirect('inventario:dashboard')

    objeto = get_object_or_404(Modelo, pk=pk, tienda=tienda_actual)

    if request.method == 'POST':
        try:
            with transaction.atomic():
                if modelo == 'compras':
                    producto = objeto.producto
                    producto.stock -= objeto.cantidad
                    producto.save()
                
                objeto.delete()
                messages.success(request, "El registro ha sido eliminado correctamente.")
        except Exception as e:
            messages.error(request, f"Error al eliminar: {e}")
        
        return redirect('inventario:gestion_lista', modelo=modelo)

    return redirect('inventario:gestion_lista', modelo=modelo)

@login_required
@csrf_exempt
def crear_cliente_ajax_view(request):
    if request.method == 'POST':
        try:
            tienda_actual = obtener_tienda_usuario(request.user)
            if not tienda_actual:
                 return JsonResponse({'error': 'No tienes tienda asignada'}, status=403)
            
            data = json.loads(request.body)
            nombre_persona = data.get('nombre')
            dni_persona = data.get('dni')
            razon_social_empresa = data.get('razon')
            ruc_empresa = data.get('ruc')
            telefono_contacto = data.get('tel', '')

            if not nombre_persona and not razon_social_empresa:
                return JsonResponse({'error': 'Debe ingresar un Nombre o una Razón Social'}, status=400)

            documento_principal = ruc_empresa if ruc_empresa else dni_persona

            cliente = Cliente.objects.create(
                tienda=tienda_actual,
                nombre_completo=nombre_persona,
                dni=dni_persona,
                razon_social=razon_social_empresa,
                ruc=ruc_empresa,
                dni_ruc=documento_principal,
                telefono=telefono_contacto
            )

            return JsonResponse({
                'id': cliente.id,
                'text': str(cliente),
                'nombre': cliente.nombre_completo,
                'dni': cliente.dni,
                'razon': cliente.razon_social,
                'ruc': cliente.ruc
            })
            
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
            
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def logout_view(request):
    nombre_completo = ""
    if request.user.is_authenticated:
        nombre_completo = request.user.get_full_name() or request.user.username
    
    auth_logout(request)
    
    # Limpia URL params al hacer logout para seguridad
    response = redirect('inventario:portal')
    response['Location'] += f'?logout=true&nombre={nombre_completo}'
    return response

# === GESTIÓN DE CAJA (NUEVO MÓDULO) ===
from .forms import AperturaCajaForm, CierreCajaForm, MovimientoCajaForm
from .models import CajaDiaria, MovimientoCaja

@login_required
def apertura_caja_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual: return redirect('inventario:dashboard')

    # Verificar si ya hay una abierta
    if CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').exists():
        messages.info(request, "Ya tienes una caja abierta. Ciérrala antes de abrir otra.")
        return redirect('inventario:pos')

    if request.method == 'POST':
        form = AperturaCajaForm(request.POST)
        if form.is_valid():
            caja = form.save(commit=False)
            caja.tienda = tienda_actual
            caja.usuario_apertura = request.user
            caja.estado = 'ABIERTA'
            caja.save()
            messages.success(request, f"Caja abierta con S/ {caja.monto_inicial}")
            return redirect('inventario:pos')
    else:
        form = AperturaCajaForm()
    
    return render(request, 'inventario/caja_apertura.html', {'form': form})

@login_required
def cierre_caja_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    # Buscamos la caja abierta
    caja = CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').first()
    
    if not caja:
        messages.error(request, "No hay ninguna caja abierta para cerrar.")
        return redirect('inventario:dashboard')

    # Calcular totales
    ventas_del_dia = Comprobante.objects.filter(
        tienda=tienda_actual, 
        fecha_emision__gte=caja.fecha_apertura,
        estado='EMITIDO'
    ).aggregate(total=Sum('total_final'))['total'] or Decimal('0.00')

    ingresos_extras = caja.movimientos.filter(tipo='INGRESO').aggregate(t=Sum('monto'))['t'] or Decimal('0.00')
    egresos_varios = caja.movimientos.filter(tipo='EGRESO').aggregate(t=Sum('monto'))['t'] or Decimal('0.00')

    # Fórmula: Inicial + Ventas + IngresosExtras - Gastos
    total_sistema = caja.monto_inicial + ventas_del_dia + ingresos_extras - egresos_varios

    if request.method == 'POST':
        form = CierreCajaForm(request.POST, instance=caja)
        if form.is_valid():
            cierre = form.save(commit=False)
            cierre.monto_final_sistema = total_sistema
            cierre.diferencia = cierre.monto_final_real - total_sistema
            cierre.usuario_cierre = request.user
            cierre.fecha_cierre = timezone.now()
            cierre.estado = 'CERRADA'
            cierre.save()
            
            estado_cierre = "CUADRÓ PERFECTO"
            if cierre.diferencia > 0: estado_cierre = f"SOBRÓ S/ {cierre.diferencia}"
            elif cierre.diferencia < 0: estado_cierre = f"FALTÓ S/ {abs(cierre.diferencia)}"
            
            messages.success(request, f"Caja cerrada exitosamente. Resultado: {estado_cierre}")
            return redirect('inventario:dashboard')
    else:
        form = CierreCajaForm()

    contexto = {
        'form': form,
        'caja': caja,
        'ventas': ventas_del_dia,
        'ingresos': ingresos_extras,
        'egresos': egresos_varios,
        'total_sistema': total_sistema
    }
    return render(request, 'inventario/caja_cierre.html', contexto)

@login_required
def movimiento_caja_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    caja = CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').first()
    
    if not caja:
        messages.error(request, "Abre caja primero para registrar gastos o ingresos.")
        return redirect('inventario:dashboard')

    if request.method == 'POST':
        form = MovimientoCajaForm(request.POST)
        if form.is_valid():
            mov = form.save(commit=False)
            mov.caja = caja
            mov.usuario = request.user
            mov.save()
            messages.success(request, "Movimiento registrado.")
            return redirect('inventario:pos')
    else:
        form = MovimientoCajaForm()
    
    return render(request, 'inventario/caja_movimiento.html', {'form': form})

@login_required
def exportar_modelo_generico_view(request, modelo):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    # Diccionario maestro de recursos y modelos
    config = {
        'productos': (Producto, ProductoResource),
        'clientes': (Cliente, ClienteResource),
        'proveedores': (Proveedor, ProveedorResource),
        'compras': (Compra, CompraResource),
        'comprobantes': (Comprobante, ComprobanteResource),
        'cajas': (CajaDiaria, CajaDiariaResource),
        'movimientos': (MovimientoCaja, MovimientoCajaResource),
    }

    if modelo not in config:
        messages.error(request, "Módulo de exportación no válido.")
        return redirect('inventario:dashboard')

    Modelo, Recurso = config[modelo]
    resource = Recurso()
    
    # Filtramos por tienda (seguridad para que no descarguen data de otros)
    if modelo == 'movimientos':
        queryset = Modelo.objects.filter(caja__tienda=tienda_actual)
    else:
        queryset = Modelo.objects.filter(tienda=tienda_actual)

    dataset = resource.export(queryset)
    
    # Preparamos la descarga
    fecha_hoy = timezone.now().strftime('%Y-%m-%d')
    response = HttpResponse(dataset.xlsx, content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{modelo}_{fecha_hoy}.xlsx"'
    return response





