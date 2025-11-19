"""
Unit tests for receipt_service model methods and properties
Tests Receipt, Category, UserCategoryPreference, and LedgerEntry models
Uses Django's database for model validation
"""
import pytest
import uuid
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from receipt_service.models.receipt import Receipt, receipt_file_path
from receipt_service.models.category import Category, UserCategoryPreference
from receipt_service.models.ledger import LedgerEntry

User = get_user_model()


@pytest.fixture
def sample_user(db):
    """Create sample user"""
    return User.objects.create_user(
        email='user@example.com',
        first_name='Test',
        last_name='User'
    )


@pytest.fixture
def sample_category(db):
    """Create sample category"""
    return Category.objects.create(
        name='Food & Dining',
        icon='🍔',
        color='#FF5722'
    )


@pytest.fixture
def sample_receipt(db, sample_user):
    """Create sample receipt"""
    return Receipt.objects.create(
        user=sample_user,
        original_filename='test_receipt.jpg',
        file_size=1024 * 100,  # 100 KB
        mime_type='image/jpeg',
        file_hash='abc123def456',
        status='uploaded'
    )


# =====================================================
# Receipt Model Tests
# =====================================================

@pytest.mark.django_db
class TestReceiptModel:
    """Test Receipt model methods and properties"""
    
    def test_receipt_creation(self, sample_receipt, sample_user):
        """Test receipt creation with required fields"""
        assert sample_receipt.user == sample_user
        assert sample_receipt.original_filename == 'test_receipt.jpg'
        assert sample_receipt.status == 'uploaded'
        assert sample_receipt.file_size == 102400
    
    def test_receipt_id_is_uuid(self, sample_receipt):
        """Test receipt ID is UUID"""
        assert isinstance(sample_receipt.id, uuid.UUID)
    
    def test_receipt_str_representation(self, sample_receipt):
        """Test receipt string representation"""
        expected = f"Receipt test_receipt.jpg - user@example.com [uploaded]"
        assert str(sample_receipt) == expected
    
    def test_receipt_meta_table_name(self):
        """Test correct database table name"""
        assert Receipt._meta.db_table == 'receipts'
    
    def test_receipt_meta_ordering(self):
        """Test default ordering"""
        assert Receipt._meta.ordering == ['-created_at']
    
    def test_receipt_file_hash_indexed(self):
        """Test file_hash is indexed"""
        indexes = [idx.fields for idx in Receipt._meta.indexes]
        assert ['file_hash'] in indexes
    
    def test_processing_duration_seconds_no_start(self, sample_receipt):
        """Test processing duration when not started"""
        assert sample_receipt.processing_duration_seconds == 0
    
    def test_processing_duration_seconds_in_progress(self, sample_receipt):
        """Test processing duration when in progress"""
        sample_receipt.processing_started_at = timezone.now() - timedelta(seconds=30)
        sample_receipt.save()
        
        duration = sample_receipt.processing_duration_seconds
        assert duration >= 30
        assert duration <= 35  # Allow some time variance
    
    def test_processing_duration_seconds_completed(self, sample_receipt):
        """Test processing duration when completed"""
        started = timezone.now() - timedelta(seconds=45)
        completed = started + timedelta(seconds=30)
        
        sample_receipt.processing_started_at = started
        sample_receipt.processing_completed_at = completed
        sample_receipt.save()
        
        assert sample_receipt.processing_duration_seconds == 30
    
    def test_can_be_confirmed_true(self, sample_receipt):
        """Test can_be_confirmed returns True for processed receipt"""
        sample_receipt.status = 'processed'
        sample_receipt.save()
        
        assert sample_receipt.can_be_confirmed() is True
    
    def test_can_be_confirmed_false_wrong_status(self, sample_receipt):
        """Test can_be_confirmed returns False for non-processed"""
        sample_receipt.status = 'uploaded'
        sample_receipt.save()
        
        assert sample_receipt.can_be_confirmed() is False
    
    def test_can_be_confirmed_false_already_confirmed(self, sample_receipt, sample_user, sample_category):
        """Test can_be_confirmed returns False if already confirmed"""
        sample_receipt.status = 'processed'
        sample_receipt.save()
        
        # Create ledger entry (confirms receipt)
        LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        sample_receipt.refresh_from_db()
        assert sample_receipt.can_be_confirmed() is False
    
    def test_get_file_url_no_file(self, sample_receipt):
        """Test get_file_url with no file"""
        assert sample_receipt.get_file_url() is None
    
    def test_receipt_file_path_generation(self, sample_user):
        """Test receipt_file_path utility function"""
        class MockReceipt:
            def __init__(self, user):
                self.user = user
        
        mock_receipt = MockReceipt(sample_user)
        path = receipt_file_path(mock_receipt, 'test.jpg')
        
        assert str(sample_user.id) in path
        assert '.jpg' in path
        assert path.count('/') >= 2  # Should have date path
    
    def test_created_at_auto_set(self, sample_receipt):
        """Test created_at is automatically set"""
        assert sample_receipt.created_at is not None
        assert sample_receipt.created_at <= timezone.now()
    
    def test_updated_at_auto_updates(self, sample_receipt):
        """Test updated_at updates automatically"""
        old_updated = sample_receipt.updated_at
        
        sample_receipt.status = 'processing'
        sample_receipt.save()
        
        assert sample_receipt.updated_at > old_updated


# =====================================================
# Category Model Tests
# =====================================================

@pytest.mark.django_db
class TestCategoryModel:
    """Test Category model methods"""
    
    def test_category_creation(self, sample_category):
        """Test category creation"""
        assert sample_category.name == 'Food & Dining'
        assert sample_category.icon == '🍔'
        assert sample_category.color == '#FF5722'
        assert sample_category.is_active is True
    
    def test_category_slug_auto_generated(self, db):
        """Test slug is auto-generated from name"""
        category = Category.objects.create(
            name='Travel & Transportation',
            icon='✈️',
            color='#2196F3'
        )
        
        assert category.slug == 'travel-transportation'
    
    def test_category_slug_manual(self, db):
        """Test manually setting slug"""
        category = Category.objects.create(
            name='Custom Category',
            slug='custom-slug',
            icon='🏷️',
            color='#9C27B0'
        )
        
        assert category.slug == 'custom-slug'
    
    def test_category_str_representation(self, sample_category):
        """Test category string representation"""
        assert str(sample_category) == "🍔 Food & Dining"
    
    def test_category_id_is_uuid(self, sample_category):
        """Test category ID is UUID"""
        assert isinstance(sample_category.id, uuid.UUID)
    
    def test_category_name_unique(self, sample_category, db):
        """Test category name unique constraint"""
        with pytest.raises(IntegrityError):
            Category.objects.create(
                name='Food & Dining',  # Same name
                icon='🍕',
                color='#FFC107'
            )
    
    def test_category_slug_unique(self, db):
        """Test category slug unique constraint"""
        Category.objects.create(
            name='Food',
            slug='food',
            icon='🍔',
            color='#FF5722'
        )
        
        with pytest.raises(IntegrityError):
            Category.objects.create(
                name='Food Items',
                slug='food',  # Same slug
                icon='🍕',
                color='#FFC107'
            )
    
    def test_category_meta_table_name(self):
        """Test correct database table name"""
        assert Category._meta.db_table == 'receipt_categories'
    
    def test_category_meta_ordering(self):
        """Test default ordering"""
        assert Category._meta.ordering == ['display_order', 'name']
    
    def test_category_display_order_default(self, sample_category):
        """Test display_order defaults to 0"""
        assert sample_category.display_order == 0
    
    def test_created_at_auto_set(self, sample_category):
        """Test created_at is automatically set"""
        assert sample_category.created_at is not None


# =====================================================
# UserCategoryPreference Model Tests
# =====================================================

@pytest.mark.django_db
class TestUserCategoryPreferenceModel:
    """Test UserCategoryPreference model methods"""
    
    def test_preference_creation(self, sample_user, sample_category):
        """Test preference creation"""
        pref = UserCategoryPreference.objects.create(
            user=sample_user,
            category=sample_category,
            usage_count=5
        )
        
        assert pref.user == sample_user
        assert pref.category == sample_category
        assert pref.usage_count == 5
    
    def test_preference_id_is_uuid(self, sample_user, sample_category):
        """Test preference ID is UUID"""
        pref = UserCategoryPreference.objects.create(
            user=sample_user,
            category=sample_category
        )
        
        assert isinstance(pref.id, uuid.UUID)
    
    def test_preference_usage_count_default(self, sample_user, sample_category):
        """Test usage_count defaults to 0"""
        pref = UserCategoryPreference.objects.create(
            user=sample_user,
            category=sample_category
        )
        
        assert pref.usage_count == 0
    
    def test_increment_usage(self, sample_user, sample_category):
        """Test increment_usage method"""
        pref = UserCategoryPreference.objects.create(
            user=sample_user,
            category=sample_category,
            usage_count=5
        )
        
        old_last_used = pref.last_used
        pref.increment_usage()
        
        pref.refresh_from_db()
        assert pref.usage_count == 6
        assert pref.last_used > old_last_used
    
    def test_preference_str_representation(self, sample_user, sample_category):
        """Test preference string representation"""
        pref = UserCategoryPreference.objects.create(
            user=sample_user,
            category=sample_category,
            usage_count=10
        )
        
        expected = f"user@example.com -> Food & Dining (10x)"
        assert str(pref) == expected
    
    def test_preference_unique_together(self, sample_user, sample_category, db):
        """Test unique_together constraint"""
        UserCategoryPreference.objects.create(
            user=sample_user,
            category=sample_category
        )
        
        with pytest.raises(IntegrityError):
            UserCategoryPreference.objects.create(
                user=sample_user,
                category=sample_category  # Same user + category
            )
    
    def test_preference_meta_table_name(self):
        """Test correct database table name"""
        assert UserCategoryPreference._meta.db_table == 'receipt_user_category_preferences'
    
    def test_last_used_auto_set(self, sample_user, sample_category):
        """Test last_used is automatically set"""
        pref = UserCategoryPreference.objects.create(
            user=sample_user,
            category=sample_category
        )
        
        assert pref.last_used is not None


# =====================================================
# LedgerEntry Model Tests
# =====================================================

@pytest.mark.django_db
class TestLedgerEntryModel:
    """Test LedgerEntry model methods and properties"""
    
    def test_ledger_entry_creation(self, sample_user, sample_receipt, sample_category):
        """Test ledger entry creation"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            vendor='Test Vendor',
            amount=Decimal('99.99'),
            currency='USD'
        )
        
        assert entry.user == sample_user
        assert entry.receipt == sample_receipt
        assert entry.category == sample_category
        assert entry.amount == Decimal('99.99')
    
    def test_ledger_entry_id_is_uuid(self, sample_user, sample_receipt, sample_category):
        """Test ledger entry ID is UUID"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        assert isinstance(entry.id, uuid.UUID)
    
    def test_ledger_entry_str_representation(self, sample_user, sample_receipt, sample_category):
        """Test ledger entry string representation"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            vendor='Amazon',
            amount=Decimal('149.99')
        )
        
        expected = "Amazon - $149.99 (Food & Dining)"
        assert str(entry) == expected
    
    def test_was_ai_accurate_true(self, sample_user, sample_receipt, sample_category):
        """Test was_ai_accurate returns True when no corrections"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00'),
            user_corrected_amount=False,
            user_corrected_category=False,
            user_corrected_vendor=False,
            user_corrected_date=False
        )
        
        assert entry.was_ai_accurate is True
    
    def test_was_ai_accurate_false(self, sample_user, sample_receipt, sample_category):
        """Test was_ai_accurate returns False when corrections made"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00'),
            user_corrected_amount=True
        )
        
        assert entry.was_ai_accurate is False
    
    def test_accuracy_score_perfect(self, sample_user, sample_receipt, sample_category):
        """Test accuracy_score with no corrections"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        assert entry.accuracy_score == 1.0
    
    def test_accuracy_score_one_correction(self, sample_user, sample_receipt, sample_category):
        """Test accuracy_score with one correction"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00'),
            user_corrected_amount=True
        )
        
        assert entry.accuracy_score == 0.75
    
    def test_accuracy_score_multiple_corrections(self, sample_user, sample_receipt, sample_category):
        """Test accuracy_score with multiple corrections"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00'),
            user_corrected_amount=True,
            user_corrected_category=True,
            user_corrected_vendor=True
        )
        
        assert entry.accuracy_score == 0.25
    
    def test_accuracy_score_all_corrections(self, sample_user, sample_receipt, sample_category):
        """Test accuracy_score with all corrections"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00'),
            user_corrected_amount=True,
            user_corrected_category=True,
            user_corrected_vendor=True,
            user_corrected_date=True
        )
        
        assert entry.accuracy_score == 0.0
    
    def test_tags_default_empty_list(self, sample_user, sample_receipt, sample_category):
        """Test tags defaults to empty list"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        assert entry.tags == []
    
    def test_ledger_entry_meta_table_name(self):
        """Test correct database table name"""
        assert LedgerEntry._meta.db_table == 'receipt_ledger_entries'
    
    def test_ledger_entry_meta_ordering(self):
        """Test default ordering"""
        assert LedgerEntry._meta.ordering == ['-date', '-created_at']
    
    def test_created_at_auto_set(self, sample_user, sample_receipt, sample_category):
        """Test created_at is automatically set"""
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        assert entry.created_at is not None


# =====================================================
# LedgerEntry QuerySet Tests
# =====================================================

@pytest.mark.django_db
class TestLedgerEntryQuerySet:
    """Test LedgerEntry custom queryset methods"""
    
    def test_for_user(self, sample_user, sample_receipt, sample_category, db):
        """Test for_user queryset method"""
        # Create entries for different users
        other_user = User.objects.create_user(email='other@example.com')
        
        entry1 = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        other_receipt = Receipt.objects.create(
            user=other_user,
            original_filename='other.jpg',
            file_size=1024,
            mime_type='image/jpeg',
            file_hash='other123'
        )
        
        LedgerEntry.objects.create(
            user=other_user,
            receipt=other_receipt,
            category=sample_category,
            date=date.today(),
            amount=Decimal('75.00')
        )
        
        user_entries = LedgerEntry.objects.for_user(sample_user)
        assert user_entries.count() == 1
        assert entry1 in user_entries
    
    def test_for_category(self, sample_user, sample_receipt, db):
        """Test for_category queryset method"""
        cat1 = Category.objects.create(name='Food', icon='🍔', color='#FF0000')
        cat2 = Category.objects.create(name='Travel', icon='✈️', color='#0000FF')
        
        entry1 = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=cat1,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        entries = LedgerEntry.objects.for_category(cat1)
        assert entries.count() == 1
        assert entry1 in entries
    
    def test_for_date_range(self, sample_user, sample_receipt, sample_category, db):
        """Test for_date_range queryset method"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        
        entry_today = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=today,
            amount=Decimal('50.00')
        )
        
        entries = LedgerEntry.objects.for_date_range(yesterday, tomorrow)
        assert entries.count() == 1
        assert entry_today in entries
    
    def test_for_month(self, sample_user, sample_receipt, sample_category, db):
        """Test for_month queryset method"""
        today = date.today()
        
        entry = LedgerEntry.objects.create(
            user=sample_user,
            receipt=sample_receipt,
            category=sample_category,
            date=today,
            amount=Decimal('50.00')
        )
        
        entries = LedgerEntry.objects.for_month(today.year, today.month)
        assert entries.count() == 1
        assert entry in entries
    
    def test_total_amount(self, sample_user, sample_category, db):
        """Test total_amount queryset method"""
        # Create multiple entries
        receipt1 = Receipt.objects.create(
            user=sample_user,
            original_filename='r1.jpg',
            file_size=1024,
            mime_type='image/jpeg',
            file_hash='hash1'
        )
        
        receipt2 = Receipt.objects.create(
            user=sample_user,
            original_filename='r2.jpg',
            file_size=1024,
            mime_type='image/jpeg',
            file_hash='hash2'
        )
        
        LedgerEntry.objects.create(
            user=sample_user,
            receipt=receipt1,
            category=sample_category,
            date=date.today(),
            amount=Decimal('50.00')
        )
        
        LedgerEntry.objects.create(
            user=sample_user,
            receipt=receipt2,
            category=sample_category,
            date=date.today(),
            amount=Decimal('75.50')
        )
        
        total = LedgerEntry.objects.for_user(sample_user).total_amount()
        assert total == Decimal('125.50')
    
    def test_total_amount_empty_queryset(self):
        """Test total_amount with empty queryset"""
        total = LedgerEntry.objects.none().total_amount()
        assert total == Decimal('0.00')
