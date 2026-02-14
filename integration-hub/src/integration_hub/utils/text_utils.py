"""
Text normalization utilities for vendor items and invoice data.
"""
import re


def to_title_case(text: str) -> str:
    """
    Convert text to title case with smart handling for food/restaurant items.

    Handles edge cases:
    - Preserves common abbreviations (LB, OZ, CS, EA, IPA, etc.)
    - Handles number+unit combos (16OZ, 750ML, 12pk)
    - Handles slash-separated words (Mozzarella/Provolone)
    - Handles hyphenated words (Extra-Virgin)
    - Preserves numeric fractions (80/20)

    Examples:
    - "CHICKEN BREAST BNLS SKNLS" -> "Chicken Breast Bnls Sknls"
    - "BEEF, GROUND 80/20" -> "Beef, Ground 80/20"
    - "OIL OLIVE EXTRA-VIRGIN" -> "Oil Olive Extra-Virgin"
    - "Cigar City Jai Alai IPA C24 16OZ" -> "Cigar City Jai Alai IPA C24 16oz"
    - "JOSH CELLARS CHARDONNAY 750ML" -> "Josh Cellars Chardonnay 750ml"
    """
    if not text:
        return text

    # Standalone abbreviations to preserve in uppercase
    preserve_upper = {
        'LB', 'OZ', 'CS', 'EA', 'CT', 'PK', 'BX', 'BG', 'GL', 'QT', 'PT',
        'GAL', 'PKG', 'DOZ', 'PC', 'SL', 'BTL', 'JAR', 'TUB', 'ML', 'DZ',
        'USDA', 'IQF', 'RTU', 'RTE', 'NAE', 'ABF', 'LSRW',
        'IPA', 'IPL', 'ABV', 'PET', 'AA',
    }

    # Unit suffixes that stay lowercase when attached to numbers (e.g., 16oz, 750ml, 12pk)
    unit_suffixes = {'oz', 'ml', 'pk', 'ct', 'lb', 'gal', 'l', 'bbl', 'sl', 'p', 'ps', 'psl'}

    # Common words to keep lowercase (unless first word or single letter)
    lowercase_words = {'and', 'or', 'with', 'w/', 'in', 'for', 'of', 'the', 'an', 'to', 'di', 'x'}

    # Regex for number+unit combos like "16OZ", "750ML", "12pk", "1/2bbl"
    num_unit_re = re.compile(r'^(\d[\d/]*)((?:' + '|'.join(sorted(unit_suffixes, key=len, reverse=True)) + r')\w*)$', re.IGNORECASE)

    # Ordinal suffixes (1st, 2nd, 3rd, 4th, 25th, etc.)
    ordinal_re = re.compile(r'^(\d+)(st|nd|rd|th)$', re.IGNORECASE)

    def process_word(word: str, is_first: bool) -> str:
        """Process a single word for title casing."""
        if not word:
            return word

        # Check if it's a preserved abbreviation (standalone)
        word_upper = word.upper()
        if word_upper in preserve_upper:
            return word_upper

        # Check for number+unit combos (e.g., "16OZ" -> "16oz", "750ML" -> "750ml")
        m = num_unit_re.match(word)
        if m:
            return m.group(1) + m.group(2).lower()

        # Ordinal numbers (25TH -> 25th, 1ST -> 1st)
        m = ordinal_re.match(word)
        if m:
            return m.group(1) + m.group(2).lower()

        # Handle apostrophe-separated words (e.g., "D'ASTI" -> "D'Asti")
        if "'" in word and len(word) > 2:
            parts = word.split("'")
            return "'".join(process_word(p, True) for p in parts)

        # Check for pure numbers/fractions (e.g., "80/20", "6x5", "0.75")
        if any(c.isdigit() for c in word):
            alpha_count = sum(1 for c in word if c.isalpha())
            if alpha_count <= 1:
                return word
            # Mixed alphanumeric — capitalize first alpha, lowercase rest
            result = []
            capitalize_next = True
            for c in word:
                if c.isalpha():
                    if capitalize_next:
                        result.append(c.upper())
                        capitalize_next = False
                    else:
                        result.append(c.lower())
                else:
                    result.append(c)
            return ''.join(result)

        # Handle hyphenated words (e.g., "Extra-Virgin", "Bag-in-Box")
        if '-' in word:
            parts = word.split('-')
            return '-'.join(process_word(p, i == 0) for i, p in enumerate(parts))

        # Handle slash-separated words (e.g., "Mozzarella/Provolone/Muenster")
        if '/' in word:
            # Only process if parts are alphabetic (not numeric fractions like 80/20)
            parts = word.split('/')
            if all(p.isalpha() for p in parts if p):
                return '/'.join(process_word(p, True) for p in parts)
            return word

        # Lowercase words (except if first word)
        word_lower = word.lower()
        if not is_first and word_lower in lowercase_words:
            return word_lower

        # Standard title case
        return word.capitalize()

    # Split by spaces but preserve original spacing
    words = text.split(' ')
    result_words = []

    for i, word in enumerate(words):
        # Handle trailing punctuation
        suffix = ''
        if word.endswith(','):
            suffix = ','
            word = word[:-1]
        elif word.endswith('.'):
            suffix = '.'
            word = word[:-1]

        processed = process_word(word, i == 0)
        result_words.append(processed + suffix)

    return ' '.join(result_words)
