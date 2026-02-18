import pandas as pd
from datetime import datetime, timedelta
import os

# Get the directory where this script is located
script_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(script_dir, 'logs.csv')

# Load the data
df = pd.read_csv(csv_path)

# Convert 'Time logged' to datetime
df['Time logged'] = pd.to_datetime(df['Time logged'], format='%d/%m/%Y %H:%M:%S')

# ADL Domain Mappings with Expected Frequencies
ADL_DOMAINS = {
    'Washing / Bathing': {
        'items': ['Getting Washed'],
        'expected_per_day': 1,
        'max_gap_amber': 24,  # hours
        'max_gap_red': 48
    },
    'Oral Care': {
        'items': ['Oral Hygiene'],
        'expected_per_day': 2,
        'max_gap_amber': 16,
        'max_gap_red': 24
    },
    'Dressing / Clothing': {
        'items': ['Getting Dressed'],
        'expected_per_day': 1,
        'max_gap_amber': 24,
        'max_gap_red': 48
    },
    'Toileting': {
        'items': ['Toileting'],
        'expected_per_day': 4,
        'max_gap_amber': 12,
        'max_gap_red': 24
    },
    'Grooming': {
        'items': ['Shaving', 'Hair Care'],
        'expected_per_day': 0.5,  # Every 2 days
        'max_gap_amber': 48,
        'max_gap_red': 96
    }
}

# Consistent Risk Thresholds (Applied Uniformly)
REFUSAL_THRESHOLDS = {
    'amber': 2,  # 2 refusals = monitoring required
    'red': 4     # 4+ refusals = immediate review
}

DOCUMENTATION_THRESHOLDS = {
    'amber': 0.6,  # <60% of expected entries = monitoring
    'red': 0.4     # <40% of expected entries = immediate review
}


def categorize_assistance(description):
    """Extract assistance level from description text."""
    if pd.isna(description):
        return 'Not Specified'
    desc_lower = description.lower()
    
    if 'on his own' in desc_lower or 'on her own' in desc_lower or 'independently' in desc_lower or 'dressed herself' in desc_lower:
        return 'Independent'
    elif 'full support' in desc_lower or 'full assistance' in desc_lower:
        return 'Full Assistance'
    elif 'with assistance' in desc_lower or 'some assistance' in desc_lower or 'prompting' in desc_lower or 'prompted' in desc_lower:
        return 'Some Assistance'
    else:
        return 'Not Specified'


def detect_refusal(description, title):
    """Detect if entry indicates a refusal."""
    if pd.isna(description):
        description = ''
    if pd.isna(title):
        title = ''
    
    combined = (description + ' ' + title).lower()
    refusal_keywords = ['refused', 'declined', 'didn\'t want', 'did not want', 'skipped']
    
    return any(keyword in combined for keyword in refusal_keywords)


def calculate_time_gaps(times):
    """Calculate gaps between consecutive entries (in hours)."""
    if len(times) < 2:
        return []
    
    sorted_times = sorted(times)
    gaps = []
    for i in range(1, len(sorted_times)):
        gap = (sorted_times[i] - sorted_times[i-1]).total_seconds() / 3600
        gaps.append(gap)
    
    return gaps


def detect_dependency_change(assistance_levels):
    """Detect if there's a pattern of increasing dependency."""
    if len(assistance_levels) < 3:
        return False
    
    # Define dependency scores
    dependency_score = {
        'Independent': 0,
        'Some Assistance': 1,
        'Full Assistance': 2,
        'Not Specified': None
    }
    
    scores = [dependency_score.get(level) for level in assistance_levels if dependency_score.get(level) is not None]
    
    if len(scores) < 3:
        return False
    
    # Check if recent entries show higher dependency than earlier ones
    recent_avg = sum(scores[-3:]) / 3
    earlier_avg = sum(scores[:3]) / 3
    
    return recent_avg > earlier_avg


def assess_care_risk(refusal_count, max_gap, dependency_changed, gap_red_threshold, gap_amber_threshold):
    """
    Assess care delivery risk based on factual indicators.
    
    Returns: tuple of (risk_level, findings, score)
    """
    findings = []
    score = 0
    
    # Refusal analysis (consistent thresholds)
    if refusal_count > 0:
        findings.append(f"{refusal_count} refusal(s) recorded")
        if refusal_count >= REFUSAL_THRESHOLDS['red']:
            score += 3
        elif refusal_count >= REFUSAL_THRESHOLDS['amber']:
            score += 2
        else:
            score += 1
    
    # Gap analysis (domain-specific thresholds)
    if max_gap:
        if max_gap > gap_red_threshold:
            findings.append(f"Maximum gap: {max_gap:.1f} hours (exceeds {gap_red_threshold}h threshold)")
            score += 3
        elif max_gap > gap_amber_threshold:
            findings.append(f"Gap of {max_gap:.1f} hours observed (exceeds {gap_amber_threshold}h threshold)")
            score += 2
    
    # Dependency change
    if dependency_changed:
        findings.append("Trend toward increased assistance level observed")
        score += 2
    
    # Risk level determination
    if score == 0:
        return 'GREEN', ['No care delivery concerns'], 0
    elif score >= 5:
        return 'RED', findings, score
    elif score >= 2:
        return 'AMBER', findings, score
    else:
        return 'GREEN', findings, score


def assess_documentation_risk(actual_count, expected_total):
    """
    Assess documentation compliance.
    
    Returns: tuple of (risk_level, findings, score)
    """
    if expected_total == 0:
        return 'N/A', ['No entries expected'], 0
    
    compliance_rate = actual_count / expected_total
    findings = []
    
    if compliance_rate < DOCUMENTATION_THRESHOLDS['red']:
        findings.append(f"Only {actual_count} entries vs {expected_total:.0f} expected ({compliance_rate:.0%} compliance)")
        return 'RED', findings, 3
    elif compliance_rate < DOCUMENTATION_THRESHOLDS['amber']:
        findings.append(f"{actual_count} entries vs {expected_total:.0f} expected ({compliance_rate:.0%} compliance)")
        return 'AMBER', findings, 2
    elif compliance_rate < 0.9:
        findings.append(f"{actual_count} entries vs {expected_total:.0f} expected ({compliance_rate:.0%} compliance)")
        return 'GREEN', findings, 1
    else:
        return 'GREEN', ['Documentation complete'], 0


def analyze_adl_domain(domain_name, domain_config, days=7):
    """
    Analyze a specific ADL domain for all residents.
    
    Returns: dict of resident analyses
    """
    end_date = df['Time logged'].max()
    start_date = end_date - timedelta(days=days)
    
    item_types = domain_config['items']
    expected_per_day = domain_config['expected_per_day']
    gap_amber = domain_config['max_gap_amber']
    gap_red = domain_config['max_gap_red']
    
    # Filter for this domain's activities
    domain_df = df[
        (df['Category'] == 'Personal Care') & 
        (df['Item'].isin(item_types)) &
        (df['Time logged'] >= start_date)
    ].copy()
    
    if domain_df.empty:
        return None
    
    # Extract metadata
    domain_df['Assistance Level'] = domain_df['Description'].apply(categorize_assistance)
    domain_df['Refusal'] = domain_df.apply(lambda x: detect_refusal(x['Description'], x['Title']), axis=1)
    
    results = {}
    
    for resident in sorted(domain_df['Resident'].unique()):
        resident_data = domain_df[domain_df['Resident'] == resident].sort_values('Time logged')
        
        # Calculate metrics
        total_entries = len(resident_data)
        refusal_count = resident_data['Refusal'].sum()
        
        times = resident_data['Time logged'].tolist()
        gaps = calculate_time_gaps(times)
        max_gap = max(gaps) if gaps else None
        
        assistance_levels = resident_data['Assistance Level'].tolist()
        dependency_changed = detect_dependency_change(assistance_levels)
        
        # Expected entries for this domain
        expected_total = expected_per_day * days
        
        # Dual risk assessment
        care_risk, care_findings, care_score = assess_care_risk(
            refusal_count, max_gap, dependency_changed, gap_red, gap_amber
        )
        
        doc_risk, doc_findings, doc_score = assess_documentation_risk(
            total_entries, expected_total
        )
        
        # Overall risk is the highest of the two
        if care_risk == 'RED' or doc_risk == 'RED':
            overall_risk = 'RED'
        elif care_risk == 'AMBER' or doc_risk == 'AMBER':
            overall_risk = 'AMBER'
        else:
            overall_risk = 'GREEN'
        
        results[resident] = {
            'total_entries': total_entries,
            'expected_entries': expected_total,
            'refusal_count': refusal_count,
            'max_gap_hours': max_gap,
            'dependency_changed': dependency_changed,
            'assistance_breakdown': resident_data['Assistance Level'].value_counts().to_dict(),
            'overall_risk': overall_risk,
            'care_risk': care_risk,
            'care_findings': care_findings,
            'care_score': care_score,
            'doc_risk': doc_risk,
            'doc_findings': doc_findings,
            'doc_score': doc_score
        }
    
    return results


def generate_adl_report(days=7):
    """
    Generate CQC-aligned ADL domain report with dual risk scoring.
    """
    end_date = df['Time logged'].max()
    start_date = end_date - timedelta(days=days)
    
    print(f"\n{'='*80}")
    print(f"CQC-ALIGNED ADL DOMAIN ANALYSIS")
    print(f"{'='*80}")
    print(f"\nAnalysis Period: {start_date.strftime('%d/%m/%Y')} to {end_date.strftime('%d/%m/%Y')}")
    print(f"Duration: {days} days")
    print(f"\nRisk Thresholds Applied:")
    print(f"  Refusals: {REFUSAL_THRESHOLDS['amber']}+ = AMBER, {REFUSAL_THRESHOLDS['red']}+ = RED")
    print(f"  Documentation: <{DOCUMENTATION_THRESHOLDS['amber']*100:.0f}% = AMBER, <{DOCUMENTATION_THRESHOLDS['red']*100:.0f}% = RED")
    print(f"\n{'='*80}\n")
    
    # Analyze each ADL domain
    for domain_name, domain_config in ADL_DOMAINS.items():
        print(f"\n{'-'*80}")
        print(f"ADL DOMAIN: {domain_name.upper()}")
        print(f"Expected: {domain_config['expected_per_day']} per day | Max Gap: {domain_config['max_gap_amber']}h (AMBER), {domain_config['max_gap_red']}h (RED)")
        print(f"{'-'*80}\n")
        
        results = analyze_adl_domain(domain_name, domain_config, days)
        
        if not results:
            print(f"No data available for this domain in the analysis period.\n")
            continue
        
        # Report by resident
        for resident, metrics in results.items():
            overall_risk = metrics['overall_risk']
            risk_symbol = '🟢' if overall_risk == 'GREEN' else ('🟡' if overall_risk == 'AMBER' else '🔴')
            
            print(f"{resident}")
            print(f"  Overall Risk: {risk_symbol} {overall_risk}")
            print(f"  Entries: {metrics['total_entries']} / {metrics['expected_entries']:.0f} expected")
            
            # Care Risk Section
            care_symbol = '🟢' if metrics['care_risk'] == 'GREEN' else ('🟡' if metrics['care_risk'] == 'AMBER' else '🔴')
            print(f"\n  CARE DELIVERY RISK: {care_symbol} {metrics['care_risk']} (Score: {metrics['care_score']})")
            
            if metrics['refusal_count'] > 0:
                print(f"    • Refusals: {metrics['refusal_count']}")
            
            if metrics['max_gap_hours']:
                print(f"    • Maximum Gap: {metrics['max_gap_hours']:.1f} hours")
            
            if metrics['dependency_changed']:
                print(f"    • Dependency Trend: Increasing")
            
            for finding in metrics['care_findings']:
                if finding not in ['No care delivery concerns']:
                    print(f"    • {finding}")
            
            # Documentation Risk Section
            doc_symbol = '🟢' if metrics['doc_risk'] == 'GREEN' else ('🟡' if metrics['doc_risk'] == 'AMBER' else '🔴')
            print(f"\n  DOCUMENTATION COMPLIANCE: {doc_symbol} {metrics['doc_risk']} (Score: {metrics['doc_score']})")
            
            for finding in metrics['doc_findings']:
                print(f"    • {finding}")
            
            # Assistance breakdown
            assistance = metrics['assistance_breakdown']
            if assistance:
                print(f"\n  Assistance Levels:")
                for level, count in assistance.items():
                    print(f"    - {level}: {count}")
            
            print()
        
    print(f"{'='*80}")
    print("END OF REPORT")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    # Run the ADL domain analysis
    generate_adl_report(days=7)
