# inventario/urls.py
from django.urls import path
from . import views
from django.contrib.auth import views as auth_views

app_name = 'inventario'

urlpatterns = [
    # --- RUTAS PÚBLICAS Y DE AUTENTICACIÓN ---
    path('', views.portal_view, name='portal'), # El nombre es 'portal'
    path('registro/', views.registro_view, name='registro'),
    path('login/', auth_views.LoginView.as_view(template_name='inventario/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),

    # --- RUTAS PARA CLIENTES LOGUEADOS ---
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('pos/', views.pos_view, name='pos'), # <-- Nombre simplificado
    path('registrar-compra/', views.registrar_compra_view, name='registrar_compra'),
    path('emitir-comprobante/', views.emitir_comprobante_y_preparar_impresion_view, name='emitir_comprobante'),
    # path('imprimir/<int:comprobante_id>/', views.vista_para_impresion_basica, name='vista_para_impresion_basica'), # Duplicado por 'vista_ticket_comprobante'

    # --- RUTAS DE REPORTES PARA CLIENTES ---
    path('reportes/stock-bajo/', views.reporte_stock_bajo_view, name='reporte_stock_bajo'),
    path('reportes/ventas/', views.reporte_ventas_view, name='reporte_ventas'),
    path('reportes/stock-actual/', views.reporte_stock_actual_view, name='reporte_stock_actual'),
    path('reportes/ventas/exportar/', views.exportar_reporte_ventas_excel_view, name='exportar_reporte_ventas'),
    path('reportes/stock-actual/exportar/', views.exportar_stock_actual_excel_view, name='exportar_stock_actual'),
    path('reportes/logueos/', views.log_logueos_view, name='log_logueos'),

    # --- RUTAS GENÉRICAS PARA GESTIÓN (CRUD) ---
    path('gestion/<str:modelo>/', views.gestion_lista_view, name='gestion_lista'),
    path('gestion/<str:modelo>/nuevo/', views.gestion_crear_view, name='gestion_crear'),
    path('gestion/<str:modelo>/editar/<int:pk>/', views.gestion_editar_view, name='gestion_editar'),
    path('gestion/comprobantes/exportar/', views.exportar_comprobantes_view, name='exportar_comprobantes'),
    path('comprobante/eliminar/<int:comprobante_id>/', views.eliminar_venta_view, name='eliminar_venta'), # Asegúrate que 'eliminar_item' sea 'eliminar_venta' si solo es para comprobantes

    # --- RUTAS PARA IMPORTACIÓN/EXPORTACIÓN DEL CLIENTE (GENÉRICAS Y MULTI-TENANT) ---
    # URLs para exportar (todas filtradas por tienda en la vista)
    path('exportar/productos/', views.exportar_productos_view, name='exportar_productos'),
    
    # URL para descargar plantillas de importación (nueva y genérica)
    # Ejemplo de uso: /descargar-plantilla/clientes/  o /descargar-plantilla/productos/
    path('descargar-plantilla/<str:model_name>/', views.descargar_plantilla_view, name='descargar_plantilla'),
    
    # URL para importar datos (nueva y genérica)
    # Ejemplo de uso: /importar/clientes/  o /importar/productos/
    path('importar/<str:data_type>/', views.importar_datos_view, name='importar_datos'),
    
    # --- RUTAS ESPECÍFICAS DE AJAX Y PDF (ya las tenías bien) ---
    path('pos/emitir_comprobante_ajax/', views.emitir_comprobante_ajax_view, name='emitir_comprobante_ajax'),
    path('comprobante/<int:comprobante_id>/ticket/', views.vista_para_impresion_basica, name='vista_ticket_comprobante'),
    path('comprobante/<int:comprobante_id>/descargar-pdf/', views.descargar_comprobante_pdf_view, name='descargar_comprobante_pdf'),

    path('mis-usuarios/', views.lista_usuarios_tienda, name='lista_usuarios_tienda'),
    path('mis-usuarios/nuevo/', views.crear_usuario_tienda, name='crear_usuario_tienda'),
    path('mis-usuarios/editar/<int:usuario_id>/', views.editar_usuario_tienda, name='editar_usuario_tienda'),
    path('mis-usuarios/eliminar/<int:usuario_id>/', views.eliminar_usuario_tienda, name='eliminar_usuario_tienda'),
    path('gestion/<str:modelo>/eliminar/<int:pk>/', views.gestion_eliminar_view, name='gestion_eliminar'),
    path('pos/crear-cliente-ajax/', views.crear_cliente_ajax_view, name='crear_cliente_ajax'),
]





