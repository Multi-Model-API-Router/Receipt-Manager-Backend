from django.urls import path
from .views.receipt_views import (
    ReceiptUploadView,
    ReceiptUploadStatusView,  # NEW
    ReceiptExtractedDataView,  # NEW
    ReceiptDetailView, 
    ReceiptConfirmView,
    ReceiptListView,
    UserQuotaStatusView,
    UserUploadHistoryView  # NEW
)
from .views.category_views import (
    CategoryListView,
    CategoryDetailView,
    CategoryUsageStatsView,
    UserCategoryPreferencesView,
    CategorySuggestView,
    CategoryValidateView
)
from .views.ledger_views import (
    LedgerEntryListView,
    LedgerEntryDetailView,
    LedgerSummaryView,
    LedgerExportView,
    LedgerExportStatusView,
    LedgerExportDownloadView
)

urlpatterns = [
    # Receipt management (matches API flow exactly)
    path('receipts/upload/', ReceiptUploadView.as_view(), name='receipt_upload'),
    path('receipts/upload-status/<uuid:upload_id>/', ReceiptUploadStatusView.as_view(), name='receipt_upload_status'),
    path('receipts/<uuid:receipt_id>/extracted-data/', ReceiptExtractedDataView.as_view(), name='receipt_extracted_data'),
    path('receipts/<uuid:receipt_id>/', ReceiptDetailView.as_view(), name='receipt_detail'),
    path('receipts/<uuid:receipt_id>/confirm/', ReceiptConfirmView.as_view(), name='receipt_confirm'),
    path('receipts/', ReceiptListView.as_view(), name='receipt_list'),
    
    # Category management (matches API flow)
    path('categories/', CategoryListView.as_view(), name='category_list'),
    path('categories/<uuid:category_id>/', CategoryDetailView.as_view(), name='category_detail'),
    path('categories/usage-stats/', CategoryUsageStatsView.as_view(), name='category_usage_stats'),
    path('categories/preferences/', UserCategoryPreferencesView.as_view(), name='category_preferences'),
    path('categories/suggest/', CategorySuggestView.as_view(), name='category_suggestion'),
    path('categories/<uuid:category_id>/validate/', CategoryValidateView.as_view(), name='category_validate'),
    
    # User quota & history (matches API flow)
    path('user/quota-status/', UserQuotaStatusView.as_view(), name='user_quota_status'),
    path('user/upload-history/', UserUploadHistoryView.as_view(), name='user_upload_history'),
    
    # Ledger management (matches API flow)
    path('ledger/entries/', LedgerEntryListView.as_view(), name='ledger_entries'),
    path('ledger/entries/<uuid:entry_id>/', LedgerEntryDetailView.as_view(), name='ledger_entry_detail'),
    path('ledger/summary/', LedgerSummaryView.as_view(), name='ledger_summary'),
    path('ledger/export/', LedgerExportView.as_view(), name='ledger_export'),
    path('ledger/exports/<uuid:task_id>/status/', LedgerExportStatusView.as_view(), name='export_status'),
    path('ledger/exports/<uuid:task_id>/download/', LedgerExportDownloadView.as_view(), name='export_download'),
]
