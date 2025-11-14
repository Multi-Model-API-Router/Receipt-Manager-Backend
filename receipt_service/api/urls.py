from django.urls import path, include

urlpatterns = [
    path('v1/', include('receipt_service.api.v1.urls')),
    # Future versions would go here:
    # path('v2/', include('receipt_service.api.v2.urls')),
]