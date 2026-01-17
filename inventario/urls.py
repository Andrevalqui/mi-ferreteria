# inventario/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'inventario'

urlpatterns = [
    # --- RUTAS PÚBLICAS Y DE AUTENTICACIÓN ---
    path('', views.portal_view, name='portal'),
    path('catalogo/', views.catalogo_view, name='catalogo'),
    path('registro/', views.registro_view, name='registro'),
    path('login/', auth_views.LoginView.as_view(template_name='inventario/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),

    # --- RUTAS PARA CLIENTES LOGUEADOS ---
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('pos/', views.pos_view, name='pos'),
    path('registrar-compra/', views.registrar_compra_view, name='registrar_compra'),
    path('emitir-comprobante/', views.emitir_comprobante_y_preparar_impresion_view, name='emitir_comprobante'),

    # --- RUTAS DE REPORTES ---
    path('reportes/stock-bajo/', views.reporte_stock_bajo_view, name='reporte_stock_bajo'),
    path('reportes/ventas/', views.reporte_ventas_view, name='reporte_ventas'),
    path('reportes/stock-actual/', views.reporte_stock_actual_view, name='reporte_stock_actual'),
    path('reportes/ventas/exportar/', views.exportar_reporte_ventas_excel_view, name='exportar_reporte_ventas'),
    path('reportes/stock-actual/exportar/', views.exportar_stock_actual_excel_view, name='exportar_stock_actual'),
    path('reportes/logueos/', views.log_logueos_view, name='log_logueos'),

    # --- GESTIÓN (CRUD) ---
    path('gestion/comprobantes/exportar/', views.exportar_comprobantes_view, name='exportar_comprobantes'),
    path('comprobante/eliminar/<int:comprobante_id>/', views.eliminar_venta_view, name='eliminar_venta'),
    
    # Rutas dinámicas de gestión (Deben ir al final para no chocar con las específicas)
    path('gestion/<str:modelo>/', views.gestion_lista_view, name='gestion_lista'),
    path('gestion/<str:modelo>/nuevo/', views.gestion_crear_view, name='gestion_crear'),
    path('gestion/<str:modelo>/editar/<int:pk>/', views.gestion_editar_view, name='gestion_editar'),
    path('gestion/<str:modelo>/eliminar/<int:pk>/', views.gestion_eliminar_view, name='gestion_eliminar'),

    # --- IMPORTACIÓN/EXPORTACIÓN ---
    path('exportar/productos/', views.exportar_productos_view, name='exportar_productos'),
    path('exportar-global/<str:modelo>/', views.exportar_modelo_generico_view, name='exportar_global'),
    path('descargar-plantilla/<str:model_name>/', views.descargar_plantilla_view, name='descargar_plantilla'),
    path('importar/<str:data_type>/', views.importar_datos_view, name='importar_datos'),
    
    # --- AJAX Y PDF ---
    path('pos/emitir_comprobante_ajax/', views.emitir_comprobante_ajax_view, name='emitir_comprobante_ajax'),
    path('comprobante/<int:comprobante_id>/ticket/', views.vista_para_impresion_basica, name='vista_ticket_comprobante'),
    path('comprobante/<int:comprobante_id>/descargar-pdf/', views.descargar_comprobante_pdf_view, name='descargar_comprobante_pdf'),
    path('pos/crear-cliente-ajax/', views.crear_cliente_ajax_view, name='crear_cliente_ajax'),

    # --- USUARIOS ---
    path('mis-usuarios/', views.lista_usuarios_tienda, name='lista_usuarios_tienda'),
    path('mis-usuarios/nuevo/', views.crear_usuario_tienda, name='crear_usuario_tienda'),
    path('mis-usuarios/editar/<int:usuario_id>/', views.editar_usuario_tienda, name='editar_usuario_tienda'),
    path('mis-usuarios/eliminar/<int:usuario_id>/', views.eliminar_usuario_tienda, name='eliminar_usuario_tienda'),

    # --- CAJA ---
    path('caja/apertura/', views.apertura_caja_view, name='apertura_caja'),
    path('caja/cierre/', views.cierre_caja_view, name='cierre_caja'),
    path('caja/movimiento/', views.movimiento_caja_view, name='movimiento_caja'),

    # --- CRÉDITOS Y DEUDORES ---
    path('creditos/', views.lista_deudores_view, name='lista_deudores'),
    path('creditos/pagar/<int:cliente_id>/', views.registrar_abono_view, name='registrar_abono'),

    # --- AUDITORÍA (KARDEX) ---
    path('kardex/', views.kardex_general_view, name='kardex_general'),
    path('kardex/producto/<int:producto_id>/', views.kardex_producto_view, name='kardex_producto'),
]

