# inventario/forms.py

from django import forms
from .models import Producto, Cliente, Proveedor, Compra
from django.contrib.auth.models import User

# --- FORMULARIO PARA EL REGISTRO DE NUEVAS TIENDAS ---
class RegistroTiendaForm(forms.Form):
    username = forms.CharField(max_length=100, required=True, label="Nombre de Usuario")
    email = forms.EmailField(required=True, label="Correo Electrónico")
    password = forms.CharField(widget=forms.PasswordInput, required=True, label="Contraseña")
    password_confirm = forms.CharField(widget=forms.PasswordInput, required=True, label="Confirmar Contraseña")
    nombre_tienda = forms.CharField(max_length=100, required=True, label="Nombre de tu Tienda")
    ruc_tienda = forms.CharField(max_length=11, required=False, label="RUC de tu Tienda (Opcional)")

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return cleaned_data

# --- FORMULARIO PARA LA IMPORTACIÓN DE ARCHIVOS EXCEL ---
class ImportForm(forms.Form):
    archivo_excel = forms.FileField(label="Selecciona tu archivo Excel (.xlsx)")

# --- FORMULARIOS DE MODELOS PARA EL PANEL DE CLIENTE ---
# Usamos ModelForm para crear/editar objetos fácilmente.

class ProductoForm(forms.ModelForm):
    class Meta:
        model = Producto
        fields = ['nombre', 'codigo_barras', 'stock', 'precio', 'costo']

class ClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nombre_completo', 'dni_ruc', 'telefono', 'email', 'pagina_web']

class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ['razon_social', 'ruc', 'direccion', 'telefono', 'email', 'pagina_web']

class CompraForm(forms.ModelForm):
    class Meta:
        model = Compra
        fields = ['proveedor', 'producto', 'cantidad', 'costo_total']

    # Hacemos que los desplegables solo muestren productos/proveedores de la tienda actual
    def __init__(self, *args, **kwargs):
        tienda = kwargs.pop('tienda', None)
        super(CompraForm, self).__init__(*args, **kwargs)
        if tienda:
            self.fields['proveedor'].queryset = Proveedor.objects.filter(tienda=tienda)
            self.fields['producto'].queryset = Producto.objects.filter(tienda=tienda)

class EmpleadoForm(forms.Form):
    username = forms.CharField(max_length=150, label="Usuario de acceso")
    first_name = forms.CharField(max_length=150, label="Nombre")
    last_name = forms.CharField(max_length=150, label="Apellido")
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    rol = forms.ChoiceField(choices=[('ADMIN', 'Admin Local'), ('VENDEDOR', 'Vendedor')], label="Rol en la tienda")

class EmpleadoForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label="Contraseña")
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']
        labels = {
            'username': 'Nombre de Usuario (para el login)',
            'first_name': 'Nombres',
            'last_name': 'Apellidos',
            'email': 'Correo electrónico',
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"]) # Encripta la contraseña
        if commit:
            user.save()
        return user



