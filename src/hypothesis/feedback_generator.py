"""미달 차원 → sharpener 재호출 피드백 생성.

"통과한 차원은 건드리지 마라" 메타 지시로 단조 수렴 유도. lang별 액션 템플릿.
"""
from __future__ import annotations

from src.design_schemas import HypothesisOutput
from src.hypothesis.scorecard_schemas import ScorecardResult

DIM_LABEL = {
    "D1": "측정가능성", "D2": "반증가능성", "D3": "인과 메커니즘",
    "D4": "측정정렬·리스크", "D5": "대안탐색", "D6": "명료성",
}

_ACTIONS_KO = {
    "D1": "1차 지표 '{metric}'가 모호/동어반복이다. '전환율', 'D7 잔존율'처럼 관측 가능한 단일 지표로 교체하라.",
    "D2": "반증 조건이 없다. '지표 X가 Y 미만이면 가설 기각' 같은 실패 조건을 sharpened_hypothesis에 1문장 추가하라. ({note})",
    "D3": "인과 경로에 비약: {note}. 개입→행동→지표 사이 끊긴 중간 단계를 명시하라.",
    "D4": "측정정렬·리스크 약함: {note}. 1차 지표 개선 시 악화될 가드레일 지표와 처치·지표 둘 다에 영향주는 교란을 명시하라.",
    "D5": "대안 검토 근거가 빈약하다: {note}. rejected_alternatives에 '왜 다른 후보보다 이 가설이 나은지' 실질 사유를 1개+ 추가하라.",
    "D6": "문장이 모호하다: {note}. sharpened_hypothesis를 단일 개입+단일 지표+방향이 명확한 한 문장으로 재작성하라.",
}
_ACTIONS_EN = {
    "D1": "Primary metric '{metric}' is vague/tautological. Replace with a single observable metric (e.g. conversion rate, D7 retention).",
    "D2": "No falsification condition. Add one sentence stating a failing condition (e.g. 'reject if metric X < Y'). ({note})",
    "D3": "Causal gap: {note}. Make the missing intermediate step in intervention→behavior→metric explicit.",
    "D4": "Weak alignment/risk: {note}. State a guardrail metric that could worsen and a confounder affecting both assignment and the metric.",
    "D5": "Thin alternative justification: {note}. Add a substantive reason in rejected_alternatives for why this beats other candidates.",
    "D6": "Hypothesis is vague: {note}. Rewrite sharpened_hypothesis as one sentence with a single intervention, single metric, explicit direction.",
}


def build_feedback(sc: ScorecardResult, h: HypothesisOutput, lang: str = "ko") -> dict:
    actions = _ACTIONS_EN if lang == "en" else _ACTIONS_KO
    items = []
    for d in sc.failed_set:
        note = next((s.note for k, s in sc.scores.items() if k == d), "")
        items.append({
            "dimension": f"{d} {DIM_LABEL.get(d, '')}",
            "current_status": note or "통과조건 미달",
            "action_required": actions[d].format(metric=h.suggested_primary_metric or "", note=note),
        })
    directive = ("Fix only the listed deficiencies; do NOT modify dimensions that already passed."
                 if lang == "en" else
                 "아래 결손만 교정하고 이미 통과한 차원은 절대 수정하지 마라.")
    constraints = ("Keep the well-formed jtbd_reframe and already-passing dimensions intact."
                   if lang == "en" else
                   "잘 작성된 jtbd_reframe과 통과한 차원은 그대로 유지하라.")
    return {"refinement_directive": directive, "failed_dimensions": items, "constraints": constraints}
