import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Tuple
import logging
from ..utils.exceptions import (
    DataExtractionException,
    DateParsingException,
    AmountParsingException,
    VendorExtractionException
)


logger = logging.getLogger(__name__)


class TextParser:
    """
    Parse structured data from OCR text with comprehensive error handling
    """
    
    def __init__(self):
        # Regex patterns for data extraction
        self.patterns = {
            'amounts': [
                re.compile(r'total[\s:]*\$?([\d,]+\.?\d*)', re.IGNORECASE),
                re.compile(r'\$\s*([\d,]+\.\d{2})'),
                re.compile(r'([\d,]+\.\d{2})\s*(?:usd|dollar)', re.IGNORECASE),
                re.compile(r'amount[\s:]*\$?([\d,]+\.?\d*)', re.IGNORECASE)
            ],
            'dates': [
                re.compile(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})'),
                re.compile(r'(\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{2,4})', re.IGNORECASE),
                re.compile(r'((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{2,4})', re.IGNORECASE),
                re.compile(r'date[\s:]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', re.IGNORECASE)
            ],
            'vendors': [
                re.compile(r'^([A-Z][A-Z\s&\.\-]+)(?=\n|\s{3,})', re.MULTILINE),
                re.compile(r'store[\s:]*(.+?)(?=\n|$)', re.IGNORECASE),
                re.compile(r'merchant[\s:]*(.+?)(?=\n|$)', re.IGNORECASE),
                re.compile(r'^(.+?)(?=\n.*(?:address|phone|receipt))', re.IGNORECASE | re.MULTILINE)
            ],
            'tax': [
                re.compile(r'tax[\s:]*\$?([\d,]+\.?\d*)', re.IGNORECASE),
                re.compile(r'gst[\s:]*\$?([\d,]+\.?\d*)', re.IGNORECASE),
                re.compile(r'vat[\s:]*\$?([\d,]+\.?\d*)', re.IGNORECASE)
            ],
            'subtotal': [
                re.compile(r'subtotal[\s:]*\$?([\d,]+\.?\d*)', re.IGNORECASE),
                re.compile(r'sub[\s-]?total[\s:]*\$?([\d,]+\.?\d*)', re.IGNORECASE)
            ]
        }
        
        # Month name mappings
        self.month_mappings = {
            'jan': 1, 'january': 1,
            'feb': 2, 'february': 2,
            'mar': 3, 'march': 3,
            'apr': 4, 'april': 4,
            'may': 5,
            'jun': 6, 'june': 6,
            'jul': 7, 'july': 7,
            'aug': 8, 'august': 8,
            'sep': 9, 'september': 9,
            'oct': 10, 'october': 10,
            'nov': 11, 'november': 11,
            'dec': 12, 'december': 12
        }
    
    def extract_structured_data(self, text: str, receipt_id: str) -> Dict[str, Any]:
        """
        Extract all structured data from receipt text
        
        Args:
            text: Cleaned OCR text
            receipt_id: Receipt ID for logging context
            
        Returns:
            Dictionary containing extracted data and confidence scores
            
        Raises:
            DataExtractionException: If extraction completely fails
        """
        try:
            if not text or len(text.strip()) < 5:
                raise DataExtractionException(
                    detail="Insufficient text for data extraction",
                    context={'text_length': len(text) if text else 0, 'receipt_id': receipt_id}
                )
            
            extracted_data = {}
            confidence_scores = {}
            
            # Extract vendor name
            try:
                vendor_result = self._extract_vendor_name(text)
                extracted_data['vendor_name'] = vendor_result['value'] or 'Unknown'
                confidence_scores['vendor_name'] = vendor_result['confidence']
            except VendorExtractionException as e:
                logger.warning(f"Vendor extraction failed for receipt {receipt_id}: {e.detail}")
                extracted_data['vendor_name'] = None
                confidence_scores['vendor_name'] = 0.0
            
            # Extract receipt date
            try:
                date_result = self._extract_receipt_date(text)
                extracted_data['receipt_date'] = date_result['value']
                confidence_scores['receipt_date'] = date_result['confidence']
            except DateParsingException as e:
                logger.warning(f"Date extraction failed for receipt {receipt_id}: {e.detail}")
                extracted_data['receipt_date'] = None
                confidence_scores['receipt_date'] = 0.0
            
            # Extract total amount
            try:
                amount_result = self._extract_total_amount(text)
                extracted_data['total_amount'] = amount_result['value']
                confidence_scores['total_amount'] = amount_result['confidence']
            except AmountParsingException as e:
                logger.warning(f"Amount extraction failed for receipt {receipt_id}: {e.detail}")
                extracted_data['total_amount'] = None
                confidence_scores['total_amount'] = 0.0
            
            # Extract additional amounts (best effort - no exceptions)
            tax_result = self._extract_tax_amount(text)
            extracted_data['tax_amount'] = tax_result['value']
            confidence_scores['tax_amount'] = tax_result['confidence']
            
            subtotal_result = self._extract_subtotal(text)
            extracted_data['subtotal'] = subtotal_result['value']
            confidence_scores['subtotal'] = subtotal_result['confidence']
            
            # Extract line items (best effort)
            line_items = self._extract_line_items(text)
            extracted_data['line_items'] = line_items
            
            # Default currency
            extracted_data['currency'] = 'USD'  # TODO: Add currency detection
            
            # Calculate overall extraction confidence
            valid_extractions = sum(1 for score in confidence_scores.values() if score > 0.5)
            total_extractions = len(confidence_scores)
            overall_confidence = valid_extractions / total_extractions if total_extractions > 0 else 0.0
            
            result = {
                'extracted_data': extracted_data,
                'confidence_scores': confidence_scores,
                'overall_confidence': overall_confidence,
                'extraction_method': 'regex_parsing',
                'receipt_id': receipt_id
            }
            
            logger.info(f"Data extraction completed for receipt {receipt_id} with {valid_extractions}/{total_extractions} successful extractions")
            
            return result
            
        except DataExtractionException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in data extraction for receipt {receipt_id}: {str(e)}")
            raise DataExtractionException(
                detail="Unexpected error during data extraction",
                context={'receipt_id': receipt_id, 'error': str(e)}
            )
    
    def _extract_vendor_name(self, text: str) -> Dict[str, Any]:
        """
        Extract vendor name from text
        
        Raises:
            VendorExtractionException: If no vendor name found
        """
        try:
            lines = text.split('\n')
            candidates = []
            
            # Try pattern matching
            for pattern in self.patterns['vendors']:
                matches = pattern.findall(text)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    
                    cleaned_match = match.strip()
                    if self._is_valid_vendor_name(cleaned_match):
                        confidence = self._calculate_vendor_confidence(cleaned_match, text)
                        candidates.append((cleaned_match, confidence))
            
            # Try first line heuristic (often vendor name)
            if lines:
                first_line = lines[0].strip()
                if self._is_valid_vendor_name(first_line):
                    confidence = self._calculate_vendor_confidence(first_line, text)
                    candidates.append((first_line, confidence + 0.2))  # Bonus for first line
            
            # Select best candidate
            if candidates:
                best_candidate = max(candidates, key=lambda x: x[1])
                if best_candidate[1] >= 0.3:  # Minimum confidence threshold
                    return {
                        'value': best_candidate[0],
                        'confidence': min(1.0, best_candidate[1])
                    }
            
            raise VendorExtractionException(
                detail="No valid vendor name found in receipt text",
                context={'candidates_count': len(candidates)}
            )
            
        except VendorExtractionException:
            raise
        except Exception as e:
            raise VendorExtractionException(
                detail="Vendor name extraction failed",
                context={'error': str(e)}
            )
    
    def _extract_receipt_date(self, text: str) -> Dict[str, Any]:
        """
        Extract receipt date from text
        
        Raises:
            DateParsingException: If no valid date found
        """
        try:
            candidates = []
            
            for pattern in self.patterns['dates']:
                matches = pattern.findall(text)
                for match in matches:
                    try:
                        parsed_date = self._parse_date_string(match)
                        if parsed_date:
                            confidence = self._calculate_date_confidence(match, text)
                            candidates.append((parsed_date, confidence))
                    except Exception:
                        continue
            
            # Select most recent reasonable date
            if candidates:
                # Filter dates within reasonable range (not future, not too old)
                today = date.today()
                valid_candidates = []
                
                for date_obj, confidence in candidates:
                    if date_obj <= today and (today - date_obj).days <= 365:  # Within 1 year
                        valid_candidates.append((date_obj, confidence))
                
                if valid_candidates:
                    # Prefer higher confidence, then more recent dates
                    best_candidate = max(valid_candidates, key=lambda x: (x[1], x[0]))
                    return {
                        'value': best_candidate[0],
                        'confidence': best_candidate[1]
                    }
            
            raise DateParsingException(
                detail="No valid receipt date found in text",
                context={'candidates_found': len(candidates)}
            )
            
        except DateParsingException:
            raise
        except Exception as e:
            raise DateParsingException(
                detail="Receipt date extraction failed",
                context={'error': str(e)}
            )
    
    def _extract_total_amount(self, text: str) -> Dict[str, Any]:
        """
        Extract total amount from text
        
        Raises:
            AmountParsingException: If no valid amount found
        """
        try:
            candidates = []
            
            for pattern in self.patterns['amounts']:
                matches = pattern.findall(text)
                for match in matches:
                    try:
                        # Clean and parse amount
                        amount_str = match.replace(',', '').strip()
                        amount = Decimal(amount_str)
                        
                        if self._is_reasonable_amount(amount):
                            confidence = self._calculate_amount_confidence(match, text, pattern)
                            candidates.append((amount, confidence))
                    except (InvalidOperation, ValueError):
                        continue
            
            if candidates:
                # Prefer higher confidence amounts
                best_candidate = max(candidates, key=lambda x: x[1])
                if best_candidate[1] >= 0.3:  # Minimum confidence threshold
                    return {
                        'value': best_candidate[0],
                        'confidence': best_candidate[1]
                    }
            
            raise AmountParsingException(
                detail="No valid total amount found in receipt text",
                context={'candidates_found': len(candidates)}
            )
            
        except AmountParsingException:
            raise
        except Exception as e:
            raise AmountParsingException(
                detail="Total amount extraction failed",
                context={'error': str(e)}
            )
    
    def _extract_tax_amount(self, text: str) -> Dict[str, Any]:
        """Extract tax amount - does not raise exceptions"""
        try:
            for pattern in self.patterns['tax']:
                matches = pattern.findall(text)
                for match in matches:
                    try:
                        amount_str = match.replace(',', '').strip()
                        amount = Decimal(amount_str)
                        if 0 < amount < 1000:  # Reasonable tax range
                            return {'value': amount, 'confidence': 0.8}
                    except (InvalidOperation, ValueError):
                        continue
        except Exception:
            pass
        
        return {'value': None, 'confidence': 0.0}
    
    def _extract_subtotal(self, text: str) -> Dict[str, Any]:
        """Extract subtotal - does not raise exceptions"""
        try:
            for pattern in self.patterns['subtotal']:
                matches = pattern.findall(text)
                for match in matches:
                    try:
                        amount_str = match.replace(',', '').strip()
                        amount = Decimal(amount_str)
                        if self._is_reasonable_amount(amount):
                            return {'value': amount, 'confidence': 0.7}
                    except (InvalidOperation, ValueError):
                        continue
        except Exception:
            pass
        
        return {'value': None, 'confidence': 0.0}
    
    def _extract_line_items(self, text: str) -> List[Dict]:
        """Extract line items - best effort, no exceptions"""
        line_items = []
        
        try:
            lines = text.split('\n')
            
            for line in lines:
                # Look for patterns like "Item Name $X.XX" or "Item $X.XX"
                item_pattern = re.compile(r'(.+?)\s+\$?([\d,]+\.\d{2})')
                match = item_pattern.search(line.strip())
                
                if match:
                    item_name = match.group(1).strip()
                    price_str = match.group(2).replace(',', '')
                    
                    try:
                        price = Decimal(price_str)
                        if 0.01 <= price <= 500:  # Reasonable item price range
                            line_items.append({
                                'name': item_name[:100],  # Limit name length
                                'price': float(price)
                            })
                    except (InvalidOperation, ValueError):
                        continue
        except Exception:
            pass
        
        return line_items[:20]  # Limit number of items
    
    # Helper methods for validation and confidence scoring
    
    def _is_valid_vendor_name(self, name: str) -> bool:
        """Check if a string looks like a valid vendor name"""
        if not name or len(name) < 2 or len(name) > 100:
            return False
        
        # Exclude common receipt text that's not vendor names
        exclude_patterns = [
            r'^\d+$',  # Just numbers
            r'^[\W\s]+$',  # Just punctuation
            r'receipt|invoice|tax|total|subtotal|amount|date|time',  # Common receipt words
        ]
        
        name_lower = name.lower()
        for pattern in exclude_patterns:
            if re.search(pattern, name_lower):
                return False
        
        return True
    
    def _is_reasonable_amount(self, amount: Decimal) -> bool:
        """Check if amount is in reasonable range"""
        return Decimal('0.01') <= amount <= Decimal('10000.00')
    
    def _parse_date_string(self, date_str: str) -> Optional[date]:
        """Parse date string into date object"""
        date_str = date_str.strip()
        
        # Try different date formats
        formats = [
            '%m/%d/%Y', '%m-%d-%Y', '%m/%d/%y', '%m-%d-%y',
            '%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        # Try parsing month names
        try:
            parts = re.split(r'[\s,]+', date_str)
            if len(parts) >= 3:
                month_str = parts[0].lower()
                if month_str in self.month_mappings:
                    month = self.month_mappings[month_str]
                    day = int(parts[1])
                    year = int(parts[2])
                    
                    # Handle 2-digit years
                    if year < 50:
                        year += 2000
                    elif year < 100:
                        year += 1900
                    
                    return date(year, month, day)
        except (ValueError, IndexError):
            pass
        
        return None
    
    def _calculate_vendor_confidence(self, vendor: str, text: str) -> float:
        """Calculate confidence score for vendor extraction"""
        confidence = 0.5
        
        # Bonus if at beginning of text
        if text.strip().startswith(vendor):
            confidence += 0.3
        
        # Bonus if proper case
        if vendor.istitle() or vendor.isupper():
            confidence += 0.2
        
        # Bonus for reasonable length
        if 3 <= len(vendor) <= 30:
            confidence += 0.1
        
        return min(1.0, confidence)
    
    def _calculate_date_confidence(self, date_str: str, text: str) -> float:
        """Calculate confidence score for date extraction"""
        confidence = 0.5
        
        # Bonus if near "date" keyword
        if re.search(r'date[\s:]*' + re.escape(date_str), text, re.IGNORECASE):
            confidence += 0.4
        
        # Bonus for standard formats
        if re.match(r'\d{1,2}[/-]\d{1,2}[/-]\d{4}', date_str):
            confidence += 0.2
        
        return min(1.0, confidence)
    
    def _calculate_amount_confidence(self, amount_str: str, text: str, pattern) -> float:
        """Calculate confidence score for amount extraction"""
        confidence = 0.5
        
        # Higher confidence for "total" matches
        if 'total' in pattern.pattern.lower():
            confidence += 0.3
        
        # Bonus for currency symbols
        if '$' in amount_str:
            confidence += 0.2
        
        # Bonus for standard format (X.XX)
        if re.match(r'[\d,]+\.\d{2}$', amount_str.replace(',', '')):
            confidence += 0.2
        
        return min(1.0, confidence)
