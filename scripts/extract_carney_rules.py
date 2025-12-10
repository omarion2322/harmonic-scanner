"""
Extract harmonic pattern specifications and trading rules from Scott Carney's PDF
"""

import pdfplumber
import re
import json

def extract_pdf_text(pdf_path):
    """Extract all text from PDF"""
    print(f"Extracting text from {pdf_path}...")
    text_by_page = []

    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"Total pages: {total_pages}")

        for i, page in enumerate(pdf.pages, 1):
            if i % 10 == 0:
                print(f"Processing page {i}/{total_pages}...")
            text = page.extract_text()
            if text:
                text_by_page.append({
                    'page': i,
                    'text': text
                })

    print(f"Extracted text from {len(text_by_page)} pages")
    return text_by_page

def search_pattern_info(text_by_page, pattern_name):
    """Search for specific pattern information"""
    results = []
    pattern_lower = pattern_name.lower()

    for page_data in text_by_page:
        page_num = page_data['page']
        text = page_data['text']

        # Check if pattern name appears on this page
        if pattern_lower in text.lower():
            # Look for ratio mentions nearby
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if pattern_lower in line.lower():
                    # Get context (3 lines before and after)
                    start = max(0, i - 3)
                    end = min(len(lines), i + 4)
                    context = '\n'.join(lines[start:end])

                    results.append({
                        'page': page_num,
                        'context': context
                    })

    return results

def find_fibonacci_ratios(text_by_page):
    """Find all Fibonacci ratio mentions"""
    ratios = []
    ratio_pattern = r'(0\.\d{3}|1\.\d{3}|2\.\d{3}|3\.\d{3})'

    for page_data in text_by_page:
        text = page_data['text']
        matches = re.finditer(ratio_pattern, text)

        for match in matches:
            ratio_value = match.group(1)
            # Get surrounding context
            start = max(0, match.start() - 100)
            end = min(len(text), match.end() + 100)
            context = text[start:end]

            ratios.append({
                'page': page_data['page'],
                'ratio': ratio_value,
                'context': context.strip()
            })

    return ratios

def search_trading_rules(text_by_page):
    """Search for trading rules and guidelines"""
    keywords = [
        'entry', 'exit', 'stop loss', 'profit target',
        'risk', 'reward', 'position', 'PRZ',
        'potential reversal zone', 'confirmation'
    ]

    results = []

    for keyword in keywords:
        for page_data in text_by_page:
            text = page_data['text']
            if keyword.lower() in text.lower():
                # Find sentences containing the keyword
                sentences = re.split(r'[.!?]', text)
                for sentence in sentences:
                    if keyword.lower() in sentence.lower():
                        results.append({
                            'page': page_data['page'],
                            'keyword': keyword,
                            'sentence': sentence.strip()
                        })

    return results

def main():
    pdf_path = "//training/scottvol1.pdf"

    # Extract all text
    text_by_page = extract_pdf_text(pdf_path)

    # Save full text for reference
    print("\nSaving full text extraction...")
    with open('extracted_full_text.txt', 'w', encoding='utf-8') as f:
        for page_data in text_by_page:
            f.write(f"\n{'='*80}\n")
            f.write(f"PAGE {page_data['page']}\n")
            f.write(f"{'='*80}\n")
            f.write(page_data['text'])
            f.write("\n")

    print("Saved to: extracted_full_text.txt")

    # Search for specific patterns
    print("\n" + "="*80)
    print("SEARCHING FOR PATTERN SPECIFICATIONS")
    print("="*80)

    patterns = ['Gartley', 'Bat', 'Butterfly', 'Crab', 'Shark', 'Cypher', 'AB=CD', '5-0']

    pattern_info = {}
    for pattern in patterns:
        print(f"\nSearching for {pattern} pattern...")
        results = search_pattern_info(text_by_page, pattern)
        if results:
            print(f"  Found {len(results)} mentions")
            pattern_info[pattern] = results

            # Save to file
            with open(f'pattern_{pattern.lower()}_info.txt', 'w', encoding='utf-8') as f:
                for r in results:
                    f.write(f"Page {r['page']}:\n")
                    f.write(r['context'])
                    f.write("\n" + "-"*80 + "\n")

    # Find Fibonacci ratios
    print("\n" + "="*80)
    print("SEARCHING FOR FIBONACCI RATIOS")
    print("="*80)

    ratios = find_fibonacci_ratios(text_by_page)
    print(f"Found {len(ratios)} ratio mentions")

    # Save unique ratios
    unique_ratios = {}
    for r in ratios:
        ratio_val = r['ratio']
        if ratio_val not in unique_ratios:
            unique_ratios[ratio_val] = []
        unique_ratios[ratio_val].append(r)

    with open('fibonacci_ratios.txt', 'w', encoding='utf-8') as f:
        f.write("FIBONACCI RATIOS FOUND IN BOOK\n")
        f.write("="*80 + "\n\n")
        for ratio in sorted(unique_ratios.keys()):
            f.write(f"\nRatio: {ratio}\n")
            f.write(f"Occurrences: {len(unique_ratios[ratio])}\n")
            # Show first 3 contexts
            for i, r in enumerate(unique_ratios[ratio][:3], 1):
                f.write(f"\n  Context {i} (Page {r['page']}):\n")
                f.write(f"  {r['context']}\n")
            f.write("-"*80 + "\n")

    # Search for trading rules
    print("\n" + "="*80)
    print("SEARCHING FOR TRADING RULES")
    print("="*80)

    rules = search_trading_rules(text_by_page)
    print(f"Found {len(rules)} rule mentions")

    with open('trading_rules.txt', 'w', encoding='utf-8') as f:
        f.write("TRADING RULES AND GUIDELINES\n")
        f.write("="*80 + "\n\n")

        # Group by keyword
        by_keyword = {}
        for rule in rules:
            kw = rule['keyword']
            if kw not in by_keyword:
                by_keyword[kw] = []
            by_keyword[kw].append(rule)

        for keyword in sorted(by_keyword.keys()):
            f.write(f"\n{keyword.upper()}\n")
            f.write("-"*80 + "\n")
            for rule in by_keyword[keyword][:10]:  # Limit to 10 per keyword
                f.write(f"Page {rule['page']}: {rule['sentence']}\n")
            f.write("\n")

    # Create summary
    print("\n" + "="*80)
    print("CREATING SUMMARY")
    print("="*80)

    summary = {
        'total_pages': len(text_by_page),
        'patterns_found': list(pattern_info.keys()),
        'unique_ratios': list(unique_ratios.keys()),
        'trading_rule_keywords': list(by_keyword.keys())
    }

    with open('extraction_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    print("\n" + "="*80)
    print("EXTRACTION COMPLETE!")
    print("="*80)
    print("\nGenerated files:")
    print("  - extracted_full_text.txt (complete book text)")
    print("  - pattern_*.txt (pattern-specific information)")
    print("  - fibonacci_ratios.txt (all Fibonacci ratios found)")
    print("  - trading_rules.txt (trading guidelines)")
    print("  - extraction_summary.json (summary statistics)")
    print("\nNext: Review these files to identify specific ratios and rules to implement.")

if __name__ == "__main__":
    main()
