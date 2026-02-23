"""
Care Analytics Scoring Engine
Implements dual scoring system: Care Risk Score (CRS) + Documentation Compliance Score (DCS)

Design Principles:
- Fixed thresholds (no drift)
- Transparent calculations (audit-ready)
- Domain-specific expectations
- Separation of care quality vs documentation compliance
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
from enum import Enum


class RiskLevel(Enum):
    """Fixed risk level classifications"""
    GREEN = 'GREEN'
    AMBER = 'AMBER'
    RED = 'RED'
    NOT_APPLICABLE = 'N/A'


class AssistanceLevel(Enum):
    """Standard assistance level categories"""
    INDEPENDENT = 'Independent'
    SOME_ASSISTANCE = 'Some Assistance'
    FULL_ASSISTANCE = 'Full Assistance'
    REFUSED = 'Refused'
    NOT_SPECIFIED = 'Not Specified'


# Fixed Thresholds (Constants)
# Refusal thresholds are defined as 7-day baseline counts and converted to per-day rates
# for period-length-normalized scoring.
REFUSAL_THRESHOLD_AMBER = 2  # 7-day baseline: 2 refusals = monitoring required
REFUSAL_THRESHOLD_RED = 4    # 7-day baseline: 4 refusals = immediate review
REFUSAL_BASELINE_DAYS = 7
REFUSAL_RATE_THRESHOLD_AMBER = REFUSAL_THRESHOLD_AMBER / REFUSAL_BASELINE_DAYS
REFUSAL_RATE_THRESHOLD_RED = REFUSAL_THRESHOLD_RED / REFUSAL_BASELINE_DAYS

DOCUMENTATION_THRESHOLD_AMBER = 0.60  # <60% compliance = monitoring
DOCUMENTATION_THRESHOLD_RED = 0.40    # <40% compliance = immediate review


@dataclass
class DomainConfig:
    """ADL domain scoring configuration"""
    domain_name: str
    expected_per_day: float  # Expected frequency (events/day)
    gap_threshold_amber: int  # Max gap in hours before AMBER alert
    gap_threshold_red: int    # Max gap in hours before RED alert
    

# Standard ADL Domain Configurations
ADL_DOMAINS = {
    'Washing/Bathing': DomainConfig('Washing/Bathing', 1.0, 24, 48),
    'Oral Care': DomainConfig('Oral Care', 2.0, 16, 24),
    'Dressing/Clothing': DomainConfig('Dressing/Clothing', 1.0, 24, 48),
    'Toileting': DomainConfig('Toileting', 4.0, 12, 24),
    'Grooming': DomainConfig('Grooming', 0.5, 48, 96),
}


@dataclass
class ADLEvent:
    """Single ADL care event"""
    event_timestamp: datetime
    logged_timestamp: datetime
    assistance_level: AssistanceLevel
    is_refusal: bool
    event_title: Optional[str] = None
    event_description: Optional[str] = None
    staff_name: Optional[str] = None


@dataclass
class ScoreComponent:
    """Individual component of a risk score"""
    component_name: str
    points: int
    description: str
    raw_value: Optional[float] = None


@dataclass
class CareRiskScore:
    """Care Risk Score result"""
    risk_level: RiskLevel
    total_points: int
    components: List[ScoreComponent]
    
    @property
    def explanation(self) -> str:
        """Human-readable explanation of score"""
        lines = []
        for comp in self.components:
            if comp.points > 0:
                lines.append(f"  • {comp.description} → {comp.points} points")
        lines.append(f"  Total: {self.total_points} points = {self.risk_level.value}")
        return "\n".join(lines)


@dataclass
class DocumentationComplianceScore:
    """Documentation Compliance Score result"""
    risk_level: RiskLevel
    compliance_percentage: float
    actual_entries: int
    expected_entries: float
    
    @property
    def explanation(self) -> str:
        """Human-readable explanation of score"""
        return (
            f"{self.actual_entries} entries recorded / "
            f"{self.expected_entries:.1f} expected = "
            f"{self.compliance_percentage:.0f}% compliance → {self.risk_level.value}"
        )


@dataclass
class ResidentDomainAnalysis:
    """Complete analysis for a resident in a specific ADL domain"""
    resident_id: str
    domain_name: str
    period_days: int
    
    care_risk_score: CareRiskScore
    documentation_score: DocumentationComplianceScore
    
    # Supporting metrics
    total_events: int
    refusal_count: int
    max_gap_hours: Optional[float]
    assistance_distribution: Dict[AssistanceLevel, int]
    
    @property
    def overall_risk(self) -> RiskLevel:
        """Worst of care risk or documentation risk"""
        if self.care_risk_score.risk_level == RiskLevel.RED or \
           self.documentation_score.risk_level == RiskLevel.RED:
            return RiskLevel.RED
        elif self.care_risk_score.risk_level == RiskLevel.AMBER or \
             self.documentation_score.risk_level == RiskLevel.AMBER:
            return RiskLevel.AMBER
        else:
            return RiskLevel.GREEN


class ScoringEngine:
    """
    Core scoring engine for care risk assessment
    
    All calculations are deterministic and based on fixed thresholds.
    No machine learning, no dynamic adjustment - just explicit rules.
    """
    
    @staticmethod
    def calculate_refusal_score(refusal_count: int, period_days: int = REFUSAL_BASELINE_DAYS) -> ScoreComponent:
        """
        Calculate refusal component of Care Risk Score

        Thresholds are rate-based to normalize across lookback windows.

        Baseline (7-day equivalent):
          AMBER at 2 refusals / 7 days  (~0.286 refusals/day)
          RED at   4 refusals / 7 days  (~0.571 refusals/day)
        """
        if period_days <= 0:
            raise ValueError("period_days must be a positive integer")

        refusal_rate = refusal_count / period_days

        if refusal_rate >= REFUSAL_RATE_THRESHOLD_RED:
            return ScoreComponent(
                component_name='refusal_score',
                points=3,
                description=(
                    f'{refusal_count} refusals in {period_days}d '
                    f'({refusal_rate:.2f}/day ≥ {REFUSAL_RATE_THRESHOLD_RED:.2f}/day = RED)'
                ),
                raw_value=float(refusal_rate)
            )
        elif refusal_rate >= REFUSAL_RATE_THRESHOLD_AMBER:
            return ScoreComponent(
                component_name='refusal_score',
                points=2,
                description=(
                    f'{refusal_count} refusals in {period_days}d '
                    f'({refusal_rate:.2f}/day ≥ {REFUSAL_RATE_THRESHOLD_AMBER:.2f}/day = AMBER)'
                ),
                raw_value=float(refusal_rate)
            )
        elif refusal_count > 0:
            return ScoreComponent(
                component_name='refusal_score',
                points=0,
                description=(
                    f'{refusal_count} refusal(s) in {period_days}d '
                    f'({refusal_rate:.2f}/day below threshold)'
                ),
                raw_value=float(refusal_rate)
            )
        else:
            return ScoreComponent(
                component_name='refusal_score',
                points=0,
                description='No refusals',
                raw_value=0.0
            )
    
    @staticmethod
    def calculate_gap_score(
        max_gap_hours: Optional[float],
        domain_config: DomainConfig
    ) -> ScoreComponent:
        """
        Calculate gap component of Care Risk Score
        
        Uses domain-specific thresholds:
          <= amber_threshold: 0 points (GREEN)
          > amber, <= red:    2 points (AMBER)
          > red_threshold:    3 points (RED)
        """
        if max_gap_hours is None:
            return ScoreComponent(
                component_name='gap_score',
                points=0,
                description='Insufficient data for gap analysis',
                raw_value=None
            )
        
        amber_threshold = domain_config.gap_threshold_amber
        red_threshold = domain_config.gap_threshold_red
        
        if max_gap_hours > red_threshold:
            return ScoreComponent(
                component_name='gap_score',
                points=3,
                description=f'Max gap {max_gap_hours:.1f}h (>{red_threshold}h = RED)',
                raw_value=max_gap_hours
            )
        elif max_gap_hours > amber_threshold:
            return ScoreComponent(
                component_name='gap_score',
                points=2,
                description=f'Max gap {max_gap_hours:.1f}h (>{amber_threshold}h = AMBER)',
                raw_value=max_gap_hours
            )
        else:
            return ScoreComponent(
                component_name='gap_score',
                points=0,
                description=f'Max gap {max_gap_hours:.1f}h (within threshold)',
                raw_value=max_gap_hours
            )
    
    @staticmethod
    def calculate_dependency_score(events: List[ADLEvent]) -> ScoreComponent:
        """
        Calculate dependency trend component of Care Risk Score
        
        Logic:
        - Compare average assistance level of recent 3 events vs first 3 events
        - Requires minimum 6 events to detect meaningful trend
        - Increasing dependency = 2 points (may indicate health deterioration)
        """
        if len(events) < 6:
            return ScoreComponent(
                component_name='dependency_score',
                points=0,
                description='Insufficient events for trend analysis',
                raw_value=None
            )
        
        # Assistance level scoring
        assistance_scores = {
            AssistanceLevel.INDEPENDENT: 0,
            AssistanceLevel.SOME_ASSISTANCE: 1,
            AssistanceLevel.FULL_ASSISTANCE: 2,
            AssistanceLevel.REFUSED: None,  # Exclude from average
            AssistanceLevel.NOT_SPECIFIED: None
        }
        
        # Sort by timestamp
        sorted_events = sorted(events, key=lambda e: e.event_timestamp)
        
        # Get numeric scores (excluding None)
        numeric_scores = [
            assistance_scores.get(e.assistance_level)
            for e in sorted_events
            if assistance_scores.get(e.assistance_level) is not None
        ]
        
        if len(numeric_scores) < 6:
            return ScoreComponent(
                component_name='dependency_score',
                points=0,
                description='Insufficient valid assistance levels for trend',
                raw_value=None
            )
        
        # Compare first 3 vs last 3
        baseline_avg = sum(numeric_scores[:3]) / 3
        recent_avg = sum(numeric_scores[-3:]) / 3
        
        # Threshold: increase of >0.5 indicates meaningful shift
        if recent_avg > baseline_avg + 0.5:
            return ScoreComponent(
                component_name='dependency_score',
                points=2,
                description=f'Increasing dependency trend (baseline: {baseline_avg:.1f} → recent: {recent_avg:.1f})',
                raw_value=recent_avg - baseline_avg
            )
        else:
            return ScoreComponent(
                component_name='dependency_score',
                points=0,
                description='No significant dependency change',
                raw_value=recent_avg - baseline_avg
            )
    
    @staticmethod
    def calculate_care_risk_score(
        events: List[ADLEvent],
        domain_config: DomainConfig,
        period_days: int = REFUSAL_BASELINE_DAYS
    ) -> CareRiskScore:
        """
        Calculate overall Care Risk Score
        
        CRS = Refusal Score + Gap Score + Dependency Score
        
        Risk levels:
          0-1 points:  GREEN  (no concern)
          2-4 points:  AMBER  (monitoring required)
          5+ points:   RED    (immediate review)
        """
        # Count refusals
        refusal_count = sum(1 for e in events if e.is_refusal)
        
        # Calculate gaps between consecutive events
        sorted_events = sorted(events, key=lambda e: e.event_timestamp)
        gaps = []
        for i in range(1, len(sorted_events)):
            gap_hours = (sorted_events[i].event_timestamp - sorted_events[i-1].event_timestamp).total_seconds() / 3600
            gaps.append(gap_hours)
        max_gap_hours = max(gaps) if gaps else None
        
        # Calculate components
        refusal_score = ScoringEngine.calculate_refusal_score(refusal_count, period_days)
        gap_score = ScoringEngine.calculate_gap_score(max_gap_hours, domain_config)
        dependency_score = ScoringEngine.calculate_dependency_score(events)
        
        # Sum components
        total_points = refusal_score.points + gap_score.points + dependency_score.points
        
        # Determine risk level
        if total_points >= 5:
            risk_level = RiskLevel.RED
        elif total_points >= 2:
            risk_level = RiskLevel.AMBER
        else:
            risk_level = RiskLevel.GREEN
        
        return CareRiskScore(
            risk_level=risk_level,
            total_points=total_points,
            components=[refusal_score, gap_score, dependency_score]
        )
    
    @staticmethod
    def calculate_documentation_score(
        actual_entries: int,
        expected_per_day: float,
        period_days: int
    ) -> DocumentationComplianceScore:
        """
        Calculate Documentation Compliance Score
        
        DCS = (Actual Entries / Expected Entries) × 100
        
        Risk levels:
          90-100%:  GREEN  (compliant)
          60-89%:   AMBER  (gaps in recording)
          <60%:     RED    (non-compliant)
        """
        expected_entries = expected_per_day * period_days
        
        if expected_entries == 0:
            return DocumentationComplianceScore(
                risk_level=RiskLevel.NOT_APPLICABLE,
                compliance_percentage=0.0,
                actual_entries=actual_entries,
                expected_entries=0.0
            )
        
        compliance_percentage = (actual_entries / expected_entries) * 100
        
        if compliance_percentage >= 90:
            risk_level = RiskLevel.GREEN
        elif compliance_percentage >= DOCUMENTATION_THRESHOLD_AMBER * 100:
            risk_level = RiskLevel.AMBER
        else:
            risk_level = RiskLevel.RED
        
        return DocumentationComplianceScore(
            risk_level=risk_level,
            compliance_percentage=compliance_percentage,
            actual_entries=actual_entries,
            expected_entries=expected_entries
        )
    
    @staticmethod
    def analyze_resident_domain(
        resident_id: str,
        domain_name: str,
        events: List[ADLEvent],
        period_days: int
    ) -> ResidentDomainAnalysis:
        """
        Complete analysis of a resident in a specific ADL domain
        
        Returns both care risk and documentation compliance assessments.
        """
        domain_config = ADL_DOMAINS.get(domain_name)
        if not domain_config:
            raise ValueError(f"Unknown domain: {domain_name}")
        
        # Calculate scores
        care_risk = ScoringEngine.calculate_care_risk_score(events, domain_config, period_days)
        doc_score = ScoringEngine.calculate_documentation_score(
            actual_entries=len(events),
            expected_per_day=domain_config.expected_per_day,
            period_days=period_days
        )
        
        # Calculate supporting metrics
        refusal_count = sum(1 for e in events if e.is_refusal)
        
        # Max gap
        sorted_events = sorted(events, key=lambda e: e.event_timestamp)
        gaps = []
        for i in range(1, len(sorted_events)):
            gap_hours = (sorted_events[i].event_timestamp - sorted_events[i-1].event_timestamp).total_seconds() / 3600
            gaps.append(gap_hours)
        max_gap_hours = max(gaps) if gaps else None
        
        # Assistance distribution
        assistance_distribution = {}
        for event in events:
            level = event.assistance_level
            assistance_distribution[level] = assistance_distribution.get(level, 0) + 1
        
        return ResidentDomainAnalysis(
            resident_id=resident_id,
            domain_name=domain_name,
            period_days=period_days,
            care_risk_score=care_risk,
            documentation_score=doc_score,
            total_events=len(events),
            refusal_count=refusal_count,
            max_gap_hours=max_gap_hours,
            assistance_distribution=assistance_distribution
        )


def calculate_time_gaps(timestamps: List[datetime]) -> List[float]:
    """
    Calculate gaps between consecutive timestamps
    
    Args:
        timestamps: List of event timestamps (will be sorted)
        
    Returns:
        List of gaps in hours
    """
    if len(timestamps) < 2:
        return []
    
    sorted_times = sorted(timestamps)
    gaps = []
    for i in range(1, len(sorted_times)):
        gap_hours = (sorted_times[i] - sorted_times[i-1]).total_seconds() / 3600
        gaps.append(gap_hours)
    
    return gaps


def parse_assistance_level(description: str, title: str = '') -> AssistanceLevel:
    """
    Extract assistance level from text description
    
    This is a heuristic function - ideally logs should have structured fields.
    """
    if not description:
        description = ''
    if not title:
        title = ''
    
    combined = (description + ' ' + title).lower()

    away_keywords = [' away', 'away ', 'away.', 'away,', 'on leave', 'out with family', 'at hospital']
    if any(keyword in combined for keyword in away_keywords):
        return AssistanceLevel.NOT_SPECIFIED
    
    # Check for refusal keywords first
    refusal_keywords = ['refused', 'declined', "didn't want", 'did not want', 'skipped']
    if any(keyword in combined for keyword in refusal_keywords):
        return AssistanceLevel.REFUSED
    
    # Check for independence
    if any(phrase in combined for phrase in ['on his own', 'on her own', 'independently', 'dressed herself', 'dressed himself']):
        return AssistanceLevel.INDEPENDENT
    
    # Check for full assistance
    if any(phrase in combined for phrase in ['full support', 'full assistance', 'fully assisted']):
        return AssistanceLevel.FULL_ASSISTANCE
    
    # Check for partial assistance
    if any(phrase in combined for phrase in ['with assistance', 'some assistance', 'prompting', 'prompted', 'helped']):
        return AssistanceLevel.SOME_ASSISTANCE
    
    return AssistanceLevel.NOT_SPECIFIED


def is_refusal(description: str, title: str = '') -> bool:
    """Check if event indicates a refusal"""
    combined = (str(description) + ' ' + str(title)).lower()
    away_keywords = [' away', 'away ', 'away.', 'away,', 'on leave', 'out with family', 'at hospital']
    if any(keyword in combined for keyword in away_keywords):
        return False

    refusal_keywords = ['refused', 'declined', "didn't want", 'did not want', 'skipped']
    return any(keyword in combined for keyword in refusal_keywords)


# Example usage validation
if __name__ == '__main__':
    # Test case: Resident with some refusals and a large gap
    test_events = [
        ADLEvent(
            event_timestamp=datetime(2026, 2, 10, 8, 0),
            logged_timestamp=datetime(2026, 2, 10, 8, 5),
            assistance_level=AssistanceLevel.SOME_ASSISTANCE,
            is_refusal=False,
            event_title='Morning oral care'
        ),
        ADLEvent(
            event_timestamp=datetime(2026, 2, 10, 20, 0),
            logged_timestamp=datetime(2026, 2, 10, 20, 5),
            assistance_level=AssistanceLevel.REFUSED,
            is_refusal=True,
            event_title='Evening oral care - refused'
        ),
        ADLEvent(
            event_timestamp=datetime(2026, 2, 11, 8, 0),
            logged_timestamp=datetime(2026, 2, 11, 8, 5),
            assistance_level=AssistanceLevel.SOME_ASSISTANCE,
            is_refusal=False
        ),
        ADLEvent(
            event_timestamp=datetime(2026, 2, 11, 20, 0),
            logged_timestamp=datetime(2026, 2, 11, 20, 5),
            assistance_level=AssistanceLevel.REFUSED,
            is_refusal=True
        ),
        ADLEvent(
            event_timestamp=datetime(2026, 2, 12, 20, 0),
            logged_timestamp=datetime(2026, 2, 12, 20, 5),
            assistance_level=AssistanceLevel.SOME_ASSISTANCE,
            is_refusal=False
        ),
    ]
    
    analysis = ScoringEngine.analyze_resident_domain(
        resident_id='R001',
        domain_name='Oral Care',
        events=test_events,
        period_days=7
    )
    
    print("Test Analysis Results")
    print("=" * 60)
    print(f"Resident: {analysis.resident_id}")
    print(f"Domain: {analysis.domain_name}")
    print(f"Period: {analysis.period_days} days")
    print()
    print(f"Overall Risk: {analysis.overall_risk.value}")
    print()
    print("Care Risk Score:")
    print(analysis.care_risk_score.explanation)
    print()
    print("Documentation Compliance:")
    print(analysis.documentation_score.explanation)
    print()
    print(f"Refusals: {analysis.refusal_count}")
    print(f"Max Gap: {analysis.max_gap_hours:.1f} hours")
    print()
    print("Assistance Distribution:")
    for level, count in analysis.assistance_distribution.items():
        print(f"  {level.value}: {count}")
