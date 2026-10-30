from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('', views.painel, name='index'),
    path('login/', auth_views.LoginView.as_view(template_name='dashboard/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('racks/<str:codigo>/', views.rack_detalhe, name='rack_detalhe'),
    path('alarmes/', views.alarmes, name='alarmes'),
    path('alarmes/<int:pk>/reconhecer/', views.reconhecer_alarme, name='reconhecer_alarme'),
    path('historico/', views.historico, name='historico'),
    path('exportar-csv/', views.exportar_csv, name='exportar_csv'),
]
