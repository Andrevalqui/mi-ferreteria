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
    DetalleComprobante, Tienda, LoginLog, Perfil, CajaDiaria, MovimientoCaja,
    MovimientoStock, PagoCredito # Aseguramos importar estos también
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
# VISTAS DE VENTA Y POS (CORREGIDA PARA EVITAR ERROR 500)
# ==============================================================================

@login_required
def pos_view(request):
    try:
        # 1. Obtener tienda y validar
        tienda_actual = obtener_tienda_usuario(request.user)
        if not tienda_actual:
            messages.error(request, "No tienes una tienda asignada. Contacta al administrador.")
            return redirect('inventario:portal')

        # 2. Verificar si hay caja abierta de forma segura
        # Usamos filter().first() para evitar errores si no existe ninguna caja aún
        caja_abierta = CajaDiaria.objects.filter(tienda=tienda_actual, estado='ABIERTA').first()
        
        if not caja_abierta:
            messages.warning(request, "⚠️ CAJA CERRADA: Debes abrir caja para poder vender.")
            return redirect('inventario:apertura_caja')

        # 3. Cargar datos
        productos = Producto.objects.filter(tienda=tienda_actual)
        clientes = Cliente.objects.filter(tienda=tienda_actual)
        
        # 4. Preparar JSON para el Select2 (Buscador) con conversión segura de tipos
        productos_para_busqueda = []
        for p in productos:
            # Convertimos Decimal a float/str para que JSON no falle
            stock_val = float(p.stock) if p.stock is not None else 0.0
            precio_val = str(p.precio) if p.precio is not None else "0.00"
            codigo_val = p.codigo_barras if p.codigo_barras else ""

            productos_para_busqueda.append({
                'id': p.id,
                'text': f'{p.nombre} (Stock: {stock_val:.2f})',
                'codigo_barras': codigo_val,
                'precio': precio_val 
            })

        # 5. Obtener últimas ventas optimizando consultas
        ultimas_ventas_detalles = DetalleComprobante.objects.filter(
            comprobante__tienda=tienda_actual
        ).select_related(
            'comprobante__cliente', 'producto'
        ).order_by('-comprobante__fecha_emision')[:5]

        # Calcular totales para la vista rápida
        for detalle in ultimas_ventas_detalles:
            # Fallback si precio_unitario_con_igv es None
            precio_con_igv = detalle.precio_unitario_con_igv if detalle.precio_unitario_con_igv else (detalle.precio_unitario * Decimal('1.18'))
            detalle.total_item = precio_con_igv * detalle.cantidad

        contexto = {
            'productos_json': json.dumps(productos_para_busqueda),
            'clientes': clientes,
            'ultimas_ventas': ultimas_ventas_detalles,
            'tienda_actual': tienda_actual,
        }
        return render(request, 'inventario/pos.html', contexto)

    except Exception as e:
        # En caso de error crítico (ej. base de datos desconectada), mostramos el error en vez de pantalla blanca
        print(f"ERROR CRÍTICO EN POS: {str(e)}")
        return HttpResponse(f"<div style='padding:20px; color:red;'><h1>Error del Sistema</h1><p>Ocurrió un error inesperado al cargar el POS:</p><pre>{str(e)}</pre></div>", status=500)


@login_required
def emitir_comprobante_y_preparar_impresion_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    if not tienda_actual:
        messages.error(request, "No tienes una tienda asignada.")
        return redirect('inventario:dashboard')

    if request.method == 'POST':
        try:
            cliente_id = request.POST.get('cliente_id')
            observaciones_venta = request.POST.get('observaciones', '')
            tipo_comprobante = request.POST.get('tipo_comprobante')
            producto_id = request.POST.get('producto_id')
            cantidad_vendida = Decimal(request.POST.get('cantidad', 1)) 
            metodo_pago = request.POST.get('metodo_pago', 'EFECTIVO')

            producto = get_object_or_404(Producto, id=producto_id, tienda=tienda_actual)
            cliente_seleccionado = Cliente.objects.filter(id=cliente_id, tienda=tienda_actual).first() if cliente_id else None

            with transaction.atomic():
                if producto.stock < cantidad_vendida:
                    raise ValueError(f'Stock insuficiente para {producto.nombre}.')
                
                producto.stock -= cantidad_vendida
                producto.save()
                
                total_final_venta = producto.precio * cantidad_vendida
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
                    metodo_pago=metodo_pago,
                    observaciones=observaciones_venta,
                )

                if metodo_pago == 'CREDITO' and cliente_seleccionado:
                    cliente_seleccionado.saldo_deudora += total_final_venta
                    cliente_seleccionado.save()
                    comprobante.estado_pago = False
                    comprobante.save()

                DetalleComprobante.objects.create(
                    comprobante=comprobante,
                    producto=producto,
                    cantidad=cantidad_vendida,
                    precio_unitario=(producto.precio / tasa_igv).quantize(Decimal('0.01')),
                    costo_unitario=producto.costo,
                    subtotal=total_final_venta,
                    precio_unitario_con_igv=producto.precio
                )
                
                messages.success(request, 'Comprobante emitido con éxito.')
                return redirect('inventario:vista_ticket_comprobante', comprobante_id=comprobante.id)

        except Exception as e:
            messages.error(request, f'Ocurrió un error: {e}')
        
    return redirect('inventario:pos')


@login_required
def vista_para_impresion_basica(request, comprobante_id):
    tienda_actual = obtener_tienda_usuario(request.user)
    comprobante = get_object_or_404(Comprobante, id=comprobante_id, tienda=tienda_actual)
    return render(request, 'inventario/comprobante_ticket.html', {'comprobante': comprobante})


@login_required
def registrar_compra_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    form = CompraForm(tienda=tienda_actual) 
    if request.method == 'POST':
        form = CompraForm(request.POST, tienda=tienda_actual)
        if form.is_valid():
            try:
                compra = form.save(commit=False)
                compra.tienda = tienda_actual
                # El Kardex se registrará solo vía signals.py
                compra.producto.stock += compra.cantidad
                compra.producto.save()
                compra.save()
                messages.success(request, f'Compra registrada con éxito.')
                return redirect('inventario:registrar_compra')
            except Exception as e:
                messages.error(request, f'Error: {e}')
    
    return render(request, 'inventario/registrar_compra.html', {
        'form': form,
        'proveedores': Proveedor.objects.filter(tienda=tienda_actual),
        'productos': Producto.objects.filter(tienda=tienda_actual),
    })


def portal_view(request):
    if request.user.is_authenticated and not request.GET.get('force'):
        return redirect('inventario:dashboard')
    return render(request, 'inventario/portal.html')

def catalogo_view(request):
    """
    Vista corregida para usar el nuevo campo 'categoria' del modelo Producto
    y mejorar el filtrado.
    """
    query = request.GET.get('q', '')
    categoria_filtro = request.GET.get('categoria', '').upper() # Normalizamos a mayúsculas
    
    productos = Producto.objects.all().order_by('nombre')
    
    # Filtro por búsqueda de texto (Nombre o Código)
    if query:
        productos = productos.filter(Q(nombre__icontains=query) | Q(codigo_barras__icontains=query))
    
    # Filtro por Categoría (Usando el campo del modelo)
    if categoria_filtro:
        # Mapeo de URL params a las opciones del modelo
        if categoria_filtro == 'MATERIALES':
            productos = productos.filter(categoria='MATERIALES')
        elif categoria_filtro in ['HERRAMIENTA', 'HERRAMIENTAS']:
            productos = productos.filter(categoria='HERRAMIENTAS')
        elif categoria_filtro in ['PINTURA', 'PINTURAS']:
            productos = productos.filter(categoria='PINTURAS')
        elif categoria_filtro == 'SEGURIDAD':
            productos = productos.filter(categoria='SEGURIDAD')
        # Si la categoría no coincide, no filtra extra (muestra todo o solo búsqueda)

    context = {'productos': productos, 'busqueda': query, 'categoria_filtro': categoria_filtro}
    return render(request, 'inventario/catalogo.html', context)


# ==============================================================================
# REPORTES
# ==============================================================================

@login_required
def reporte_stock_bajo_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    productos = Producto.objects.filter(tienda=tienda_actual, stock__lte=5).order_by('stock')
    chart_labels = [p.nombre for p in productos]
    chart_data = [float(p.stock) for p in productos] 
    return render(request, 'inventario/reporte_stock_bajo.html', {
        'productos': productos, 'umbral': 5,
        'chart_labels': json.dumps(chart_labels), 'chart_data': json.dumps(chart_data)
    })

@login_required
def reporte_ventas_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    comprobantes = Comprobante.objects.filter(tienda=tienda_actual, estado='EMITIDO')
    total_ventas = comprobantes.aggregate(total=Sum('total_final'))['total'] or 0
    return render(request, 'inventario/reporte_ventas.html', {
        'total_ventas': total_ventas, 'fecha_inicio': timezone.now()
    })

@login_required
def reporte_stock_actual_view(request):
    tienda_actual = obtener_tienda_usuario(request.user)
    productos = Producto.objects.filter(tienda=tienda_actual).order_by('nombre')
    valor_total = 0
    for p in productos:
        p.valor_stock = p.stock * p.costo
        valor_total += p.valor_stock
    return render(request, 'inventario/reporte_stock_actual.html', {
        'productos': productos, 'valor_total_inventario': valor_total
    })


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
                messages.error(request, f"Error: {e}")
    return render(request, 'inventario/registro.html', {'form': RegistroTiendaForm()})

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
    contexto = {
        'tienda': tienda_actual,
        'show_splash': show_splash, 
        'ventas_hoy_monto': ventas_hoy.aggregate(total=Sum('total_final'))['total'] or 0,
        'total_ventas_hoy': ventas_hoy.count(),
        'productos_bajo_stock': Producto.objects.filter(tienda=tienda_actual, stock__lte=5).count(),
    }
    return render(request, 'inventario/dashboard.html', contexto)

@login_required
def gestion_lista_view(request, modelo):
    tienda = obtener_tienda_usuario(request.user)
    Modelos = {'productos': Producto, 'clientes': Cliente, 'proveedores': Proveedor, 'compras': Compra, 'comprobantes': Comprobante}
    queryset = Modelos[modelo].objects.filter(tienda=tienda).order_by('-id')
    return render(request, 'inventario/gestion_lista.html', {
        'objetos': queryset, 'modelo_nombre_plural': modelo, 'modelo_slug': modelo
    })

@login_required
def gestion_crear_view(request, modelo):
    tienda = obtener_tienda_usuario(request.user)
    Modelos = {'productos': (Producto, ProductoForm), 'clientes': (Cliente, ClienteForm), 'proveedores': (Proveedor, ProveedorForm), 'compras': (Compra, CompraForm)}
    M, F = Modelos[modelo]
    form = F(request.POST or None, tienda=tienda) if modelo == 'compras' else F(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        instancia = form.save(commit=False)
        instancia.tienda = tienda
        instancia.save()
        return redirect('inventario:gestion_lista', modelo=modelo)
    return render(request, 'inventario/gestion_form.html', {'form': form, 'modelo_nombre': modelo, 'modelo_slug': modelo, 'editando': False})

@login_required
def gestion_editar_view(request, modelo, pk):
    tienda = obtener_tienda_usuario(request.user)
    Modelos = {'productos': (Producto, ProductoForm), 'clientes': (Cliente, ClienteForm), 'proveedores': (Proveedor, ProveedorForm), 'compras': (Compra, CompraForm)}
    M, F = Modelos[modelo]
    instancia = get_object_or_404(M, pk=pk, tienda=tienda)
    form = F(request.POST or None, instance=instancia, tienda=tienda) if modelo == 'compras' else F(request.POST or None, instance=instancia)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('inventario:gestion_lista', modelo=modelo)
    return render(request, 'inventario/gestion_form.html', {'form': form, 'modelo_nombre': modelo, 'modelo_slug': modelo, 'editando': True})


# ==============================================================================
# IMPORTACIÓN / EXPORTACIÓN
# ==============================================================================

@login_required
def exportar_productos_view(request):
    tienda = obtener_tienda_usuario(request.user)
    dataset = ProductoResource().export(Producto.objects.filter(tienda=tienda))
    response = HttpResponse(dataset.xlsx, content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="productos.xlsx"'
    return response

@login_required
def descargar_plantilla_view(request, model_name):
    headers = IMPORT_TYPES[model_name]['template_headers']
    wb = openpyxl.Workbook()
    wb.active.append(headers)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="plantilla_{model_name}.xlsx"'
    wb.save(response)
    return response

@login_required
def importar_datos_view(request, data_type):
    tienda = obtener_tienda_usuario(request.user)
    if request.method == 'POST':
        dataset = Dataset()
        file = request.FILES.get('excel_file')
        if file:
            dataset.load(file.read(), format='xlsx' if file.name.endswith('.xlsx') else 'csv')
            resource = IMPORT_TYPES[data_type]['resource']()
            resource.tienda_actual = tienda
            resource.import_data(dataset, dry_run=False)
            return redirect('inventario:gestion_lista', modelo=data_type)
    return render(request, 'inventario/importar_datos.html', {'data_type_display': data_type, 'data_type': data_type})


# ==============================================================================
# AJAX Y PDF
# ==============================================================================

@login_required
@csrf_exempt
def emitir_comprobante_ajax_view(request):
    if request.method != 'POST': return JsonResponse({'error': 'Error'}, status=405)
    try:
        tienda_actual = obtener_tienda_usuario(request.user)
        data = json.loads(request.body)
        cart_items = data.get('cart')
        metodo = data.get('metodo_pago', 'EFECTIVO') # Nueva lógica Crédito
        
        if not cart_items: return JsonResponse({'error': 'Vacío'}, status=400)
        
        with transaction.atomic():
            total_final_venta = sum(Decimal(str(item['price'])) * Decimal(str(item['quantity'])) for item in cart_items)
            tasa_igv_decimal = Decimal('0.18')
            subtotal_venta = (total_final_venta / (1 + tasa_igv_decimal)).quantize(Decimal('0.01'), rounding='ROUND_HALF_UP')
            igv_monto = (total_final_venta - subtotal_venta)
            
            cliente_id = data.get('cliente_id')
            cliente_seleccionado = Cliente.objects.filter(id=cliente_id, tienda=tienda_actual).first() if cliente_id else None
            
            comprobante = Comprobante.objects.create(
                tienda=tienda_actual, 
                tipo_comprobante=data['tipo_comprobante'], 
                total_final=total_final_venta, 
                subtotal=subtotal_venta,
                igv=igv_monto,
                serie='B001' if data['tipo_comprobante'] == 'BOLETA' else 'F001',
                metodo_pago=metodo,
                cliente=cliente_seleccionado,
                observaciones=data.get('observaciones', '')
            )
            
            # SI ES CRÉDITO, ACTUALIZAMOS LA DEUDA DEL CLIENTE
            if metodo == 'CREDITO' and cliente_seleccionado:
                cliente_seleccionado.saldo_deudora += total_final_venta
                cliente_seleccionado.save()
                comprobante.estado_pago = False
                comprobante.save()

            stocks_actualizados = []
            for item in cart_items:
                producto = get_object_or_404(Producto, id=item['id'], tienda=tienda_actual)
                # Al restar stock aquí, el signal.py registrará el Kardex automáticamente
                producto.stock -= Decimal(str(item['quantity']))
                producto.save()
                
                DetalleComprobante.objects.create(
                    comprobante=comprobante, 
                    producto=producto, 
                    cantidad=item['quantity'], 
                    precio_unitario=Decimal(str(item['price']))/Decimal('1.18'), 
                    costo_unitario=producto.costo,
                    subtotal=Decimal(str(item['price']))*Decimal(str(item['quantity']))
                )
                stocks_actualizados.append({'id': producto.id, 'stock': float(producto.stock)})
            
            return JsonResponse({'comprobante_id': comprobante.id, 'stocks_actualizados': stocks_actualizados})
    except Exception as e: return JsonResponse({'error': str(e)}, status=500)

@login_required
def descargar_comprobante_pdf_view(request, comprobante_id):
    comprobante = get_object_or_404(Comprobante, id=comprobante_id, tienda=obtener_tienda_usuario(request.user))
    template = get_template('inventario/comprobante_ticket.html')
    html = template.render({'comprobante': comprobante, 'tienda': comprobante.tienda})
    result = BytesIO()
    pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)
    response = HttpResponse(result.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ticket_{comprobante.id}.pdf"'
    return response

@login_required
def eliminar_venta_view(request, comprobante_id):
    if request.method == 'POST':
        tienda = obtener_tienda_usuario(request.user)
        comprobante = get_object_or_404(Comprobante, id=comprobante_id, tienda=tienda)
        with transaction.atomic():
            # Si eliminamos una venta al crédito, restamos la deuda al cliente
            if comprobante.metodo_pago == 'CREDITO' and comprobante.cliente:
                comprobante.cliente.saldo_deudora -= comprobante.total_final
                comprobante.cliente.save()

            for d in comprobante.detalles.all():
                d.producto.stock += d.cantidad
                d.producto.save()
            comprobante.delete()
        return redirect('inventario:gestion_lista', modelo='comprobantes')
    return redirect('inventario:dashboard')

@login_required
def log_logueos_view(request):
    if not request.user.is_superuser: return redirect('inventario:dashboard')
    return render(request, 'inventario/log_logueos.html', {'logs': LoginLog.objects.all()})

@login_required
def lista_usuarios_tienda(request):
    tienda = obtener_tienda_usuario(request.user)
    return render(request, 'inventario/usuarios_lista.html', {
        'empleados': Perfil.objects.filter(tienda=tienda).exclude(user=request.user), 'tienda': tienda
    })

@login_required
def crear_usuario_tienda(request):
    tienda = obtener_tienda_usuario(request.user)
    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            d = form.cleaned_data
            u = User.objects.create_user(username=d['username'], password=d['password'], first_name=d['first_name'], last_name=d['last_name'])
            Perfil.objects.create(user=u, tienda=tienda, rol=d.get('rol', 'VENDEDOR'))
            return redirect('inventario:lista_usuarios_tienda')
    return render(request, 'inventario/usuarios_form.html', {'form': EmpleadoForm(), 'editando': False})

@login_required
def editar_usuario_tienda(request, usuario_id):
    tienda = obtener_tienda_usuario(request.user)
    perfil = get_object_or_404(Perfil, id=usuario_id, tienda=tienda)
    if request.method == 'POST':
        form = EmpleadoForm(request.POST)
        if form.is_valid():
            perfil.user.username = form.cleaned_data['username']
            if form.cleaned_data['password']: perfil.user.set_password(form.cleaned_data['password'])
            perfil.user.save()
            perfil.rol = form.cleaned_data['rol']
            perfil.save()
            return redirect('inventario:lista_usuarios_tienda')
    return render(request, 'inventario/usuarios_form.html', {'form': form, 'editando': True})

@login_required
def eliminar_usuario_tienda(request, usuario_id):
    get_object_or_404(Perfil, id=usuario_id, tienda=obtener_tienda_usuario(request.user)).user.delete()
    return redirect('inventario:lista_usuarios_tienda')

@login_required
def gestion_eliminar_view(request, modelo, pk):
    tienda = obtener_tienda_usuario(request.user)
    Modelos = {'productos': Producto, 'clientes': Cliente, 'proveedores': Proveedor, 'compras': Compra}
    obj = get_object_or_404(Modelos[modelo], pk=pk, tienda=tienda)
    if request.method == 'POST':
        if modelo == 'compras':
            obj.producto.stock -= obj.cantidad
            obj.producto.save()
        obj.delete()
    return redirect('inventario:gestion_lista', modelo=modelo)

@login_required
@csrf_exempt
def crear_cliente_ajax_view(request):
    if request.method == 'POST':
        tienda = obtener_tienda_usuario(request.user)
        data = json.loads(request.body)
        doc = data.get('ruc') or data.get('dni')
        c = Cliente.objects.create(tienda=tienda, nombre_completo=data.get('nombre'), dni=data.get('dni'), razon_social=data.get('razon'), ruc=data.get('ruc'), dni_ruc=doc)
        return JsonResponse({'id': c.id, 'text': str(c), 'ruc': c.ruc, 'razon': c.razon_social})
    return JsonResponse({'error': 'X'}, status=405)

def logout_view(request):
    nombre = "Usuario"
    if request.user.is_authenticated:
        nombre = request.user.first_name or request.user.username
    auth_logout(request)
    return redirect(reverse('inventario:portal') + f'?logout=true&nombre={nombre}')


# ==============================================================================
# GESTIÓN DE CAJA
# ==============================================================================

@login_required
def apertura_caja_view(request):
    tienda = obtener_tienda_usuario(request.user)
    if CajaDiaria.objects.filter(tienda=tienda, estado='ABIERTA').exists(): return redirect('inventario:pos')
    if request.method == 'POST':
        form = AperturaCajaForm(request.POST)
        if form.is_valid():
            c = form.save(commit=False)
            c.tienda, c.usuario_apertura, c.estado = tienda, request.user, 'ABIERTA'
            c.save()
            return redirect('inventario:pos')
    return render(request, 'inventario/caja_apertura.html', {'form': AperturaCajaForm()})

@login_required
def cierre_caja_view(request):
    tienda = obtener_tienda_usuario(request.user)
    caja = CajaDiaria.objects.filter(tienda=tienda, estado='ABIERTA').first()
    if not caja: return redirect('inventario:dashboard')
    ventas = Comprobante.objects.filter(tienda=tienda, fecha_emision__gte=caja.fecha_apertura, estado='EMITIDO').aggregate(t=Sum('total_final'))['t'] or 0
    movs = caja.movimientos.all()
    ingresos = movs.filter(tipo='INGRESO').aggregate(t=Sum('monto'))['t'] or 0
    egresos = movs.filter(tipo='EGRESO').aggregate(t=Sum('monto'))['t'] or 0
    total_sistema = caja.monto_inicial + ventas + ingresos - egresos
    if request.method == 'POST':
        form = CierreCajaForm(request.POST, instance=caja)
        if form.is_valid():
            c = form.save(commit=False)
            c.monto_final_sistema, c.usuario_cierre, c.fecha_cierre, c.estado = total_sistema, request.user, timezone.now(), 'CERRADA'
            c.diferencia = c.monto_final_real - total_sistema
            c.save()
            return redirect('inventario:dashboard')
    return render(request, 'inventario/caja_cierre.html', {'form': CierreCajaForm(), 'caja': caja, 'ventas': ventas, 'ingresos': ingresos, 'egresos': egresos, 'total_sistema': total_sistema})

@login_required
def movimiento_caja_view(request):
    tienda = obtener_tienda_usuario(request.user)
    caja = CajaDiaria.objects.filter(tienda=tienda, estado='ABIERTA').first()
    if not caja: return redirect('inventario:dashboard')
    if request.method == 'POST':
        form = MovimientoCajaForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.caja, m.usuario = caja, request.user
            m.save()
            return redirect('inventario:pos')
    return render(request, 'inventario/caja_movimiento.html', {'form': MovimientoCajaForm()})

@login_required
def exportar_modelo_generico_view(request, modelo):
    tienda = obtener_tienda_usuario(request.user)
    config = {
        'productos': (Producto, ProductoResource), 
        'clientes': (Cliente, ClienteResource), 
        'proveedores': (Proveedor, ProveedorResource), 
        'compras': (Compra, CompraResource), 
        'comprobantes': (Comprobante, ComprobanteResource), 
        'cajas': (CajaDiaria, CajaDiariaResource), 
        'movimientos': (MovimientoCaja, MovimientoCajaResource)
    }
    qs = config[modelo][0].objects.filter(caja__tienda=tienda) if modelo == 'movimientos' else config[modelo][0].objects.filter(tienda=tienda)
    dataset = config[modelo][1]().export(qs)
    response = HttpResponse(dataset.xlsx, content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = f'attachment; filename="{modelo}.xlsx"'
    return response

@login_required
def exportar_comprobantes_view(request): return redirect('inventario:dashboard')
@login_required
def exportar_reporte_ventas_excel_view(request): return redirect('inventario:dashboard')
@login_required
def exportar_stock_actual_excel_view(request): return redirect('inventario:dashboard')

# ==============================================================================
# MÓDULOS PROFESIONALES: DEUDORES Y KARDEX
# ==============================================================================

@login_required
def lista_deudores_view(request):
    """Muestra quién debe dinero a la ferretería"""
    tienda = obtener_tienda_usuario(request.user)
    deudores = Cliente.objects.filter(tienda=tienda, saldo_deudora__gt=0).order_by('-saldo_deudora')
    total_por_cobrar = deudores.aggregate(Sum('saldo_deudora'))['saldo_deudora__sum'] or 0
    return render(request, 'inventario/deudores_lista.html', {
        'deudores': deudores, 'total_por_cobrar': total_por_cobrar
    })

@login_required
def registrar_abono_view(request, cliente_id):
    """Registra cuando un cliente paga parte o toda su deuda"""
    tienda = obtener_tienda_usuario(request.user)
    cliente = get_object_or_404(Cliente, id=cliente_id, tienda=tienda)
    caja = CajaDiaria.objects.filter(tienda=tienda, estado='ABIERTA').first()

    if not caja:
        messages.error(request, "Debe abrir caja para recibir pagos de deudas.")
        return redirect('inventario:apertura_caja')

    if request.method == 'POST':
        monto = Decimal(request.POST.get('monto', 0))
        if monto > 0 and monto <= cliente.saldo_deudora:
            with transaction.atomic():
                PagoCredito.objects.create(cliente=cliente, monto=monto, usuario=request.user)
                cliente.saldo_deudora -= monto
                cliente.save()
                # El dinero entra a caja automáticamente
                MovimientoCaja.objects.create(
                    caja=caja, tipo='INGRESO', monto=monto, 
                    concepto=f"Abono de deuda: {cliente}", usuario=request.user
                )
                messages.success(request, f"Pago de S/ {monto} registrado con éxito.")
                return redirect('inventario:lista_deudores')
    return render(request, 'inventario/deudores_pago.html', {'cliente': cliente})

@login_required
def kardex_general_view(request):
    """Historial de movimientos de todos los productos"""
    tienda = obtener_tienda_usuario(request.user)
    movimientos = MovimientoStock.objects.filter(producto__tienda=tienda).select_related('producto', 'usuario')[:100]
    return render(request, 'inventario/kardex_lista.html', {'movimientos': movimientos})

@login_required
def kardex_producto_view(request, producto_id):
    """Kardex específico para ver la historia de UN solo producto"""
    tienda = obtener_tienda_usuario(request.user)
    producto = get_object_or_404(Producto, id=producto_id, tienda=tienda)
    movimientos = MovimientoStock.objects.filter(producto=producto).order_by('-fecha')
    return render(request, 'inventario/kardex_producto.html', {'producto': producto, 'movimientos': movimientos})

# --- TRUCO PARA CREAR SUPERUSUARIO DESDE VERCEL ---
def crear_admin_emergencia(request):
    try:
        # Verificamos si ya existe para no crearlo doble
        if not User.objects.filter(username='admin').exists():
            # CREA EL USUARIO: admin / admin123
            User.objects.create_superuser('admin', 'admin@ejemplo.com', 'admin123')
            return HttpResponse("<h1 style='color:green'>¡LISTO! Usuario creado.</h1><p>Usuario: <b>admin</b><br>Contraseña: <b>admin123</b></p>")
        else:
            return HttpResponse("<h1 style='color:orange'>El usuario 'admin' ya existe.</h1>")
    except Exception as e:
        return HttpResponse(f"<h1 style='color:red'>Error: {str(e)}</h1>")

